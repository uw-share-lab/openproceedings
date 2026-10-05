"""`POST /api/v1/compare` (TASK-177; spec 04 §Comparing with a RIS file): a reviewer's own RIS file against a
query's result. What it answers (kept, dropped with why, not in the index, added, not compared; each record of
the file counted once), that it is `/search`'s result and never changes it (guarantee 5), that it is the one
comparison core's answer, and everything a hostile or careless upload can try: the wrong media type, a form, a
compressed body, bytes that aren't UTF-8, a body, a record count, a line or a title over its cap, formula cells,
a slot already taken, a comparison past its time, an index swapped mid-request. And that nothing of the file is
logged or written anywhere.

The corpus is 800 records of the synthetic 5k fixture as a crawl would hold them (`conftest.attributed`: most
with an independent source, every 7th RIS-only) plus the one record that shares a title, venue and year with
another (an ambiguous match)."""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
import tempfile
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, get_args

import anyio
import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from openproceedings import cli
from openproceedings import export as exporter
from openproceedings.api import ApiConfig, RateLimit
from openproceedings.api import compare as route
from openproceedings.api import server as api_server
from openproceedings.api.middleware import BodyLimit, drain
from openproceedings.api.middleware import RateLimit as RateLimitMiddleware
from openproceedings.api.models import CompareReason, MatchedBy, NotComparedReason
from openproceedings.api.state import IndexState, MatchTable
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.eval import scholar_compare
from openproceedings.eval.scholar_compare import ONLY_OP, ONLY_SCHOLAR, MatchIndex, Scope, read_ris
from openproceedings.export import csv_cell
from openproceedings.ingest import dedup
from openproceedings.ingest.caps import MAX_TITLE
from openproceedings.ingest.record import PaperRecord
from openproceedings.query.normalize import TOKENIZER_VERSION, normalize
from openproceedings.query.parser import parse
from scholarmend.parse import parse_ris

from tests.contract.conftest import SECRET, Store, attributed, build, make_app, point_current
from tests.contract.test_abuse_limits import error
from tests.fixtures.corpus.synthetic_5k import records

COMPARE = "/api/v1/compare"
RIS = {"Content-Type": "application/x-research-info-systems"}
Q = "benchmark"
DATE = "2026-10-05"
TWIN = 3561  # the 5k record that shares its title, venue and year with record 516
Logs = Callable[[], list[dict[str, Any]]]


# --- the corpus and a file built from it ----------------------------------------------------------------------
PAPERS: list[PaperRecord] = sorted(
    (attributed(r) for r in [*list(records())[:800], list(records())[TWIN]]), key=lambda p: p.id
)
BY_ID = {p.id: p for p in PAPERS}
ORACLE = ReferenceEngine(PAPERS)
INDEX = MatchIndex.build(PAPERS)


def ids_of(q: str, *, defaults: bool = True) -> frozenset[str]:
    parsed = parse(q, "native", TOKENIZER_VERSION)
    tree = parsed.effective_ast if defaults else parsed.identification_ast
    assert tree is not None
    return ORACLE.match_ids(tree)


def tokens(p: PaperRecord) -> set[str]:
    return set(normalize(p.title, TOKENIZER_VERSION)) | set(normalize(p.abstract or "", TOKENIZER_VERSION))


def plain(p: PaperRecord) -> bool:
    """A record a title alone identifies in its venue and year, on one line."""
    key = dedup.title_key(p.title)
    return bool(key) and len(INDEX.titles[(p.venue, p.year, key)]) == 1 and "\n" not in p.title


def one_line(text: str) -> str:
    return " ".join(text.split())


def entry(
    title: str,
    venue: str | None = "NeurIPS",
    year: int | None = 2024,
    url: str | None = None,
    tag: str = "TI",
) -> str:
    lines = ["TY  - JOUR", f"{tag}  - {title}"]
    lines += [f"JF  - {venue}"] if venue is not None else []
    lines += [f"PY  - {year}///"] if year is not None else []
    lines += [f"UR  - {url}"] if url else []
    return "\n".join([*lines, "ER  - ", "", ""])


def by_title(p: PaperRecord) -> str:
    return entry(one_line(p.title), p.venue, p.year)


def by_forum(p: PaperRecord, title: str = "a title the index does not hold") -> str:
    return entry(title, p.venue, p.year, f"https://openreview.net/forum?id={p.native}")


RESULT = ids_of(Q)
IDENTIFIED = ids_of(Q, defaults=False)
KEPT = sorted(i for i in RESULT if plain(BY_ID[i]))[:4]
FILTERED = sorted(i for i in IDENTIFIED - RESULT if plain(BY_ID[i]))[:2]
STEMMED = sorted(
    i
    for i, p in BY_ID.items()
    if i not in IDENTIFIED
    and "benchmarks" in tokens(p)
    and i in ids_of("benchmarks")
    and plain(p)
    and p.abstract is not None
)[:2]
UNMATCHED = sorted(
    i
    for i, p in BY_ID.items()
    if i in ids_of("agent")
    and not tokens(p) & {"benchmark", "benchmarks", "benchmarking", "benchmarked"}
    and plain(p)
    and p.abstract is not None
)[:2]


def the_file() -> str:
    """Every bucket once or more: four kept (one by forum id under a wrong title, one written twice), two
    dropped by a default filter, two dropped that match only as `benchmarks`, two dropped with no match, one
    paper the index doesn't hold, one from another venue."""
    k = [BY_ID[i] for i in KEPT]
    return "".join(
        [
            by_forum(k[0]),
            by_title(k[1]),
            by_title(k[2]),
            by_title(k[1]),  # a repeat
            by_title(k[3]),
            *(by_title(BY_ID[i]) for i in FILTERED),
            *(by_title(BY_ID[i]) for i in STEMMED),
            *(by_title(BY_ID[i]) for i in UNMATCHED),
            entry("a paper nobody indexed about benchmark", "NeurIPS", 2024),
            entry("benchmark at another venue", "AISTATS", 2024),
        ]
    )


@pytest.fixture(autouse=True)
def fixed_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exporter, "utc_date", lambda: DATE)
    monkeypatch.setattr(route, "utc_date", lambda: DATE)


@pytest.fixture(scope="module")
def corpus_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("compare-data")
    corpus = [*list(records())[:800], list(records())[TWIN]]
    version = build(corpus, root / "snapshots", "compared", root / "indexes", paper=attributed)
    (root / "indexes" / "current").symlink_to(version)
    return root


# no pause between one test's comparisons (the cooldown has its own tests, in test_compare_review.py)
NO_COOLDOWN = RateLimit(capacity=10_000, compare_cooldown_factor=0)


def app_of(data: Path, **overrides: Any) -> TestClient:
    return TestClient(make_app(data, **{"compare_enabled": True, "rate_limit": NO_COOLDOWN, **overrides}))


@pytest.fixture(scope="module")
def shared(corpus_dir: Path) -> Iterator[TestClient]:
    """One app for the tests that only ask (no config of their own, nothing held)."""
    with app_of(corpus_dir) as c:
        yield c


def post(client: TestClient, body: str | bytes, q: str = Q, **params: str) -> Any:
    data = body.encode("utf-8") if isinstance(body, str) else body
    return client.post(COMPARE, params={"q": q, **params}, content=data, headers=RIS)


def compared(client: TestClient, body: str | bytes, q: str = Q, **params: str) -> dict[str, Any]:
    r = post(client, body, q, **params)
    assert r.status_code == 200, r.text
    return dict(r.json())


def exported_ids(client: TestClient, q: str = Q) -> list[str]:
    r = client.get("/api/v1/export", params={"q": q, "format": "jsonl"})
    assert r.status_code == 200, r.text
    return [json.loads(line)["id"] for line in r.text.splitlines()]


def rows_of(text: str) -> list[dict[str, str]]:
    assert text.startswith("﻿")
    return list(csv.DictReader(io.StringIO(text.removeprefix("﻿"))))


# --- what it answers ---------------------------------------------------------------------------------------------
def test_the_test_corpus_has_every_case() -> None:
    assert len(KEPT) == 4 and len(FILTERED) == 2 and len(STEMMED) == 2 and len(UNMATCHED) == 2
    assert INDEX.independent and set(BY_ID) - INDEX.independent  # crawled and RIS-only records both


def test_every_record_of_the_file_is_in_exactly_one_list(shared: TestClient) -> None:
    body = compared(shared, the_file())
    assert [r["id"] for r in body["kept"]] == [KEPT[0], KEPT[1], KEPT[2], KEPT[3]]  # file order
    assert {r["id"] for r in body["dropped"]} == {*FILTERED, *STEMMED, *UNMATCHED}
    assert [r["title"] for r in body["not_in_index"]] == ["a paper nobody indexed about benchmark"]
    assert [r["title"] for r in body["not_compared"]] == ["benchmark at another venue"]
    assert body["records_total"] == 13 and body["duplicates_total"] == 1 and body["not_compared_total"] == 1
    assert body["papers_total"] == 11
    for name in ("kept", "dropped", "not_in_index", "added", "not_compared"):
        assert body[f"{name}_total"] == len(body[name])
    assert (
        body["records_total"] == body["not_compared_total"] + body["duplicates_total"] + body["papers_total"]
    )
    assert body["papers_total"] == body["kept_total"] + body["dropped_total"] + body["not_in_index_total"]
    # the repeat is counted on its paper, and the file's positions are 1-based
    assert [(r["ris_record"], r["copies"]) for r in body["kept"]] == [(1, 1), (2, 2), (3, 1), (5, 1)]
    assert body["not_compared"][0] == {
        "ris_record": 13,
        "title": "benchmark at another venue",
        "venue": "AISTATS",
        "year": 2024,
        "reason": "venue_unrecognised",
    }


def test_kept_and_added_are_exactly_the_search_result(shared: TestClient) -> None:
    """Guarantee 5 and AC#4: the comparison's result is `/search`'s and `/export`'s for the same query, whatever
    the file; `total` is theirs, and kept ∪ added is the whole set."""
    body = compared(shared, the_file())
    search = shared.get("/api/v1/search", params={"q": Q, "limit": 0}).json()
    result = exported_ids(shared)
    assert body["total"] == search["total"] == len(result) == len(RESULT)
    assert set(result) == RESULT
    kept, added = [r["id"] for r in body["kept"]], [r["id"] for r in body["added"]]
    assert sorted([*kept, *added]) == result and not set(kept) & set(added)
    assert added == sorted(added)  # id order, as an export's
    assert body["query"] == {
        "input": Q,
        "mode": "native",
        "canonical": search["query"]["canonical"],
        "canonical_hash": search["query"]["canonical_hash"],
    }
    assert (body["index_version"], body["tokenizer_version"], body["query_version"]) == (
        search["index_version"],
        search["tokenizer_version"],
        search["query_version"],
    )


def test_a_comparison_never_changes_the_search(shared: TestClient) -> None:
    def search() -> Any:
        return shared.get("/api/v1/search", params={"q": Q, "limit": 200}).json()

    before = search()
    first = compared(shared, the_file())
    other = compared(shared, by_title(BY_ID[KEPT[0]]))
    assert search() == before
    assert first["total"] == other["total"] == before["total"]  # the file never moves the result
    assert other["kept_total"] == 1 and other["added_total"] == before["total"] - 1


def test_the_same_query_index_and_file_give_the_same_bytes(shared: TestClient) -> None:
    assert post(shared, the_file()).content == post(shared, the_file()).content


def test_how_each_record_was_matched(shared: TestClient) -> None:
    twin = BY_ID[sorted(i for i in BY_ID if i.endswith("Fx0516"))[0]]
    file = "".join(
        [
            by_forum(BY_ID[KEPT[0]]),
            by_title(BY_ID[KEPT[1]]),
            entry(one_line(twin.title), twin.venue, twin.year),  # two index records have this title there
            entry("a paper nobody indexed", "ICLR", 2023),
            entry(one_line(BY_ID[KEPT[2]].title), BY_ID[KEPT[2]].venue, None),  # no year: never by title
            entry(one_line(BY_ID[KEPT[3]].title), BY_ID[KEPT[3]].venue, BY_ID[KEPT[3]].year + 1),
        ]
    )
    body = compared(shared, file)
    assert [(r["ris_record"], r["matched_by"]) for r in body["kept"]] == [
        (1, "forum_id"),
        (2, "title_venue_year"),
    ]
    assert [(r["ris_record"], r["matched_by"], r["reason"], r["id"]) for r in body["not_in_index"]] == [
        (3, "ambiguous", "unsettled", None),
        (4, "not_found", "coverage_gap", None),
        (5, "no_year", "unsettled", None),
        (6, "not_found", "coverage_gap", None),  # the same title in another year is never a match
    ]
    assert all(not r["settled"] for r in body["not_in_index"])
    assert body["kept"][0]["title"] == "a title the index does not hold"  # the file's own, as written


def test_why_each_paper_was_dropped(shared: TestClient) -> None:
    body = compared(shared, the_file())
    why = {r["id"]: r for r in body["dropped"]}
    for i in FILTERED:
        assert why[i]["reason"] == "filtered" and why[i]["fails_filters"] is True
        p = BY_ID[i]
        assert f"track={p.track}" in why[i]["detail"] or f"status={p.status}" in why[i]["detail"]
    for i in STEMMED:
        assert why[i]["reason"] == "stemming" and "benchmarks" in why[i]["detail"]
    for i in UNMATCHED:
        assert why[i]["reason"] == "full_text" and "no title or abstract match" in why[i]["detail"]
    assert all(r["reason"] is None and r["detail"] == "" for r in body["kept"])
    assert {r["reason"] for r in body["added"]} == {"scholar_missed"}
    # the counts by reason are the server's, in the protocol's order: a client never counts rows
    assert body["reason_totals"] == {
        "kept": {},
        "dropped": {"filtered": 2, "stemming": 2, "full_text": 2},
        "not_in_index": {"coverage_gap": 1},
        "added": {"scholar_missed": body["added_total"]},
    }
    assert list(body["reason_totals"]["dropped"]) == ["filtered", "stemming", "full_text"]


def test_each_row_says_whether_its_record_rests_on_a_crawl(shared: TestClient) -> None:
    """`independent` is the core's flag: false for a record only an imported RIS set holds."""
    some = sorted(INDEX.independent)[:3] + sorted(set(BY_ID) - INDEX.independent)[:3]
    body = compared(shared, "".join(by_forum(BY_ID[i]) for i in some))
    rows = [*body["kept"], *body["dropped"]]
    assert {r["id"]: r["independent"] for r in rows} == {i: i in INDEX.independent for i in some}
    assert body["kept_ris_only_total"] == sum(r["independent"] is False for r in body["kept"])
    assert body["dropped_ris_only_total"] == sum(r["independent"] is False for r in body["dropped"])
    assert body["kept_ris_only_total"] + body["dropped_ris_only_total"] == 3
    assert all(r["independent"] is None for r in body["not_in_index"])
    assert {r["independent"] for r in body["added"]} == {True, False}


def test_it_is_the_cores_answer(shared: TestClient) -> None:
    """AC#2: one implementation. The route's lists are `compare_query`'s rows for the same inputs."""
    side = scholar_compare.scope_and_match(read_ris(the_file(), "file"), INDEX, Scope())
    core = scholar_compare.compare_query(
        "file",
        Q,
        side=side,
        index=INDEX,
        engine=ORACLE,
        fetch=lambda ids: {i: BY_ID[i] for i in ids},
        scope=Scope(),
        mode="native",
    )
    body = compared(shared, the_file())
    for name in ("kept", "dropped", "not_in_index", "added"):
        assert [(r["id"], r["reason"], r["detail"]) for r in body[name]] == [
            (r.op_id or None, r.auto_class or None, r.auto_evidence if r.auto_class else "")
            for r in getattr(core, name)
        ]


def test_the_enums_are_the_cores(shared: TestClient) -> None:
    assert set(get_args(CompareReason)) == {*ONLY_SCHOLAR, *ONLY_OP}
    assert set(get_args(MatchedBy)) >= {"forum_id", "proceedings_id", "title_venue_year"}
    assert set(get_args(NotComparedReason)) == {"venue_unrecognised", "venue", "year"}
    paths = shared.get("/api/v1/openapi.json").json()["paths"]
    assert paths["/api/v1/compare"]["post"]["operationId"] == "compare_records"


def test_scholar_mode_runs_the_string_as_search_does(shared: TestClient) -> None:
    q = "benchmark$ source:ICLR"
    body = compared(shared, by_title(BY_ID[KEPT[0]]), q, mode="scholar")
    search = shared.get("/api/v1/search", params={"q": q, "mode": "scholar", "limit": 0}).json()
    assert body["total"] == search["total"] and body["query"]["mode"] == "scholar"
    assert body["query"]["canonical_hash"] == search["query"]["canonical_hash"]


# --- the added list as RIS -----------------------------------------------------------------------------------------
def test_the_added_papers_come_as_the_exports_own_ris(shared: TestClient) -> None:
    body = compared(shared, the_file())
    got = parse_ris(body["added_ris"], "added.ris")
    assert [rec.fields["ID"][0] for rec in got] == [row["id"] for row in body["added"]]
    whole = {
        rec.fields["ID"][0]: rec.raw
        for rec in parse_ris(shared.get("/api/v1/export", params={"q": Q, "format": "ris"}).text, "all.ris")
    }
    assert all(rec.raw == whole[rec.fields["ID"][0]] for rec in got)  # byte for byte what /export writes
    assert "a title the index does not hold" not in body["added_ris"]  # nothing of the file is in it
    everything = compared(shared, "".join(by_forum(BY_ID[i]) for i in sorted(RESULT)))
    assert everything["added_total"] == 0 and everything["added_ris"] == ""


def test_the_response_holds_no_abstract_but_the_added_papers_own(shared: TestClient) -> None:
    """Nothing beyond what `/search` serves for the same hit: the lists carry no abstract at all, and the RIS
    of the added papers carries each one's, as the export does."""
    body = compared(shared, the_file())
    lists = json.dumps(
        {k: body[k] for k in ("kept", "dropped", "not_in_index", "added", "not_compared", "csv")}
    )
    for i in [*KEPT, *FILTERED, *STEMMED, *UNMATCHED]:
        abstract = BY_ID[i].abstract
        assert abstract is None or one_line(abstract)[:60] not in lists
    assert {key for row in body["added"] for key in row if "abstract" in key} == {"abstract_withheld"}
    hits = {h["id"]: h for h in shared.get("/api/v1/search", params={"q": Q, "limit": 200}).json()["hits"]}
    for rec in parse_ris(body["added_ris"], "added.ris"):
        abstract = hits[rec.fields["ID"][0]]["abstract"]
        assert rec.fields.get("AB", [None])[0] == (one_line(abstract) if abstract else None)


# --- the capability is the operator's ---------------------------------------------------------------------------
def test_it_is_off_unless_configured(corpus_dir: Path, logs: Logs) -> None:
    with TestClient(make_app(corpus_dir)) as c:
        e = error(post(c, the_file()), 403, "API_COMPARE_DISABLED")
        assert "not turned on" in e["message"]
        assert c.get("/api/v1/meta").json()["limits"]["compare"] is None
        # and no body larger than any other route's is ever read on that path
        error(post(c, b"x" * 70_000), 413, "API_BODY_TOO_LARGE")
        state: IndexState = c.app.state.index  # type: ignore[attr-defined]
        assert state.served is not None and state.served.matches is None  # no table is built
    assert not [x for x in logs() if x["event"].startswith("match_index")]


def test_meta_states_the_caps(corpus_dir: Path) -> None:
    with app_of(corpus_dir, compare_max_records=7, compare_max_body_bytes=4096) as c:
        assert c.get("/api/v1/meta").json()["limits"]["compare"] == {
            "max_body_bytes": 4096,
            "max_records": 7,
            "max_line_length": 32_768,
            "max_title_length": MAX_TITLE,
            "max_results": 5_000,
            "max_seconds": 60.0,
            "max_response_bytes": 16 * 1024 * 1024,
        }


@pytest.mark.parametrize(
    ("flags", "on"),
    [
        ([], True),
        (["--host", "localhost"], True),
        (["--host", "0.0.0.0"], False),
        (["--host", "example.org"], False),
        (["--trusted-proxy", "10.0.0.1"], False),  # a proxy in front means clients reach it
        (["--host", "0.0.0.0", "--compare"], True),  # the operator's choice
        (["--no-compare"], False),
    ],
)
def test_op_serve_offers_it_on_a_local_instance_only_by_default(
    flags: list[str], on: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    served: list[ApiConfig] = []
    monkeypatch.setattr(api_server, "serve", lambda config, *a: served.append(config))
    assert cli.main(["--data-dir", str(tmp_path), "serve", *flags]) == 0
    assert served[0].compare_enabled is on


# --- what is accepted as a body ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "multipart/form-data; boundary=x"},
        {"Content-Type": "application/x-www-form-urlencoded"},
        {"Content-Type": "application/json"},
        {"Content-Type": "text/plain"},
        {"Content-Type": "application/x-research-info-systems; charset=latin-1"},
        {"Content-Type": "application/x-research-info-systems", "Content-Encoding": "gzip"},
        {"Content-Type": "application/x-research-info-systems", "Content-Encoding": "deflate"},
    ],
)
def test_only_a_plain_ris_body_is_read(shared: TestClient, headers: dict[str, str]) -> None:
    r = shared.post(COMPARE, params={"q": Q}, content=the_file().encode(), headers=headers)
    error(r, 415, "API_UNSUPPORTED_MEDIA_TYPE")
    assert r.headers["connection"] == "close"


def test_a_body_without_a_content_type_is_refused(shared: TestClient) -> None:
    request = shared.build_request("POST", COMPARE, params={"q": Q}, content=the_file().encode())
    assert "content-type" not in request.headers
    error(shared.send(request), 415, "API_UNSUPPORTED_MEDIA_TYPE")


def test_a_multipart_upload_is_never_parsed(shared: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """No form parser runs (Starlette's would spool a large part to disk)."""
    import starlette.formparsers as forms

    def never(*a: Any, **k: Any) -> None:
        raise AssertionError("a form parser ran")

    monkeypatch.setattr(forms.MultiPartParser, "__init__", never)
    monkeypatch.setattr(forms.FormParser, "__init__", never)
    r = shared.post(COMPARE, params={"q": Q}, files={"file": ("mine.ris", the_file().encode())})
    error(r, 415, "API_UNSUPPORTED_MEDIA_TYPE")


def test_a_compressed_body_is_never_decompressed(shared: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    bomb = gzip.compress(b"TY  - JOUR\n" * 2_000_000)  # 22 MB of records in ~20 KB
    assert len(bomb) < 100_000
    r = shared.post(COMPARE, params={"q": Q}, content=bomb, headers={**RIS, "Content-Encoding": "gzip"})
    error(r, 415, "API_UNSUPPORTED_MEDIA_TYPE")
    # and sent as if it were RIS, it is bytes that aren't UTF-8 text: refused, never inflated
    error(shared.post(COMPARE, params={"q": Q}, content=bomb, headers=RIS), 422, "API_RIS_INVALID")


def test_a_bom_crlf_and_a_charset_are_accepted(shared: TestClient) -> None:
    want = compared(shared, the_file())
    crlf = the_file().replace("\n", "\r\n")
    for body in (b"\xef\xbb\xbf" + the_file().encode(), crlf.encode(), b"\xef\xbb\xbf" + crlf.encode()):
        got = shared.post(
            COMPARE,
            params={"q": Q},
            content=body,
            headers={"Content-Type": "Application/X-Research-Info-Systems; charset=UTF-8"},
        )
        assert got.status_code == 200 and got.json() == want


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"   \n\n",
        b"TI  - a title before any record\n" + by_title(PAPERS[0]).encode(),
        b"Title,Year\nbenchmark,2024\n",  # a CSV
        "TY  - JOUR\nTI  - café\nER  - \n".encode("latin-1"),
        b"\xff\xfeT\x00Y\x00",  # UTF-16
        b"TY  - JOUR\nTI  - \xed\xa0\x80\nER  - \n",  # an encoded surrogate
        b"TY  - JOUR\rTI  - old mac line endings\rER  - \r",
    ],
)
def test_a_body_that_is_not_utf8_ris_is_refused(shared: TestClient, body: bytes) -> None:
    e = error(shared.post(COMPARE, params={"q": Q}, content=body, headers=RIS), 422, "API_RIS_INVALID")
    assert "title" not in e["message"] and "caf" not in e["message"]  # never the file's content
    assert "diagnostics" not in e


# --- the caps -----------------------------------------------------------------------------------------------------
def test_a_body_over_the_cap_is_refused_by_its_declared_length_unread() -> None:
    sent: list[dict[str, Any]] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        raise AssertionError("the app ran")

    async def receive() -> dict[str, Any]:
        raise AssertionError("the body was read")

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": COMPARE, "headers": [(b"content-length", b"5000")]}
    anyio.run(BodyLimit(app, 64, {COMPARE: 4096}), scope, receive, send)
    assert sent[0]["status"] == 413 and b"API_BODY_TOO_LARGE" in sent[1]["body"]
    assert (b"connection", b"close") in sent[0]["headers"]


def test_the_streamed_path_is_not_read_before_the_route_asks() -> None:
    """Within its declared cap the body stays unread: the app gets a counting `receive`, not buffered bytes."""
    reads = 0

    async def app(scope: Any, receive: Any, send: Any) -> None:
        assert reads == 0  # nothing was read on the way in
        assert (await receive())["body"] == b"abc"

    async def receive() -> dict[str, Any]:
        nonlocal reads
        reads += 1
        return {"type": "http.request", "body": b"abc", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        raise AssertionError("nothing is refused")

    scope = {"type": "http", "method": "POST", "path": COMPARE, "headers": [(b"content-length", b"3")]}
    anyio.run(BodyLimit(app, 2, {COMPARE: 4096}), scope, receive, send)
    assert reads == 1


def test_a_body_over_the_cap_is_413_by_length_and_by_count(corpus_dir: Path, logs: Logs) -> None:
    big = the_file() * 4
    with app_of(corpus_dir, compare_max_body_bytes=len(big.encode()) - 1) as c:
        e = error(post(c, big), 413, "API_BODY_TOO_LARGE")
        assert "file" in e["message"]

        def chunks() -> Iterator[bytes]:  # no Content-Length: counted as it arrives
            data = big.encode()
            for at in range(0, len(data), 512):
                yield data[at : at + 512]

        r = c.post(COMPARE, params={"q": Q}, content=chunks(), headers=RIS)
        error(r, 413, "API_BODY_TOO_LARGE")
        assert r.headers["connection"] == "close"
        assert post(c, the_file()).status_code == 200  # a file within the cap, and the slot was given back
    assert [x["status"] for x in logs() if x["event"] == "request"] == [413, 413, 200]


def test_more_records_than_the_cap_is_refused_not_cut(corpus_dir: Path) -> None:
    with app_of(corpus_dir, compare_max_records=12) as c:
        e = error(post(c, the_file()), 413, "API_RIS_TOO_LARGE")  # 13 records
        assert "13 records" in e["message"] and "at most 12" in e["message"]
    with app_of(corpus_dir, compare_max_records=13) as c:
        assert compared(c, the_file())["records_total"] == 13


def test_a_line_over_the_cap_is_refused_before_parsing(
    corpus_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def never(*a: Any) -> None:
        raise AssertionError("the file was parsed")

    monkeypatch.setattr(route, "read_ris", never)
    with app_of(corpus_dir, compare_max_line_chars=200) as c:
        long = "TY  - JOUR\nAB  - " + "x" * 200 + "\nER  - \n"
        e = error(post(c, the_file() + long), 413, "API_RIS_TOO_LARGE")
        line = the_file().count("\n") + 2
        assert (
            f"Line {line} " in e["message"] and "200 characters" in e["message"] and "xxx" not in e["message"]
        )


@pytest.mark.parametrize("tag", ["TI", "T1", "JF", "JO", "T2", "J2", "JA", "BT"])
def test_a_title_or_venue_over_the_corpus_cap_is_refused(shared: TestClient, tag: str) -> None:
    long = f"TY  - JOUR\n{tag}  - " + "y" * (MAX_TITLE + 1) + "\nER  - \n"
    e = error(post(shared, long), 413, "API_RIS_TOO_LARGE")
    assert "Line 2" in e["message"] and "yyy" not in e["message"]
    at_cap = f"TY  - JOUR\n{tag}  - " + "y" * MAX_TITLE + "\nPY  - 2024\nER  - \n"
    assert post(shared, at_cap).status_code == 200


def test_a_file_of_many_one_tag_lines_is_refused_before_parsing(
    corpus_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Millions of tags in one record would be millions of field strings: the line count is capped first."""

    def never(*a: Any) -> None:
        raise AssertionError("the file was parsed")

    monkeypatch.setattr(route, "read_ris", never)
    with app_of(corpus_dir, compare_max_records=2) as c:
        tags = "TY  - JOUR\n" + "AU  - a\n" * (2 * route.MAX_LINES_PER_RECORD + 1) + "ER  - \n"
        e = error(post(c, tags), 413, "API_RIS_TOO_LARGE")
        assert "lines" in e["message"]


def test_a_result_larger_than_the_cap_is_refused(corpus_dir: Path) -> None:
    with app_of(corpus_dir, compare_max_results=5) as c:
        e = error(post(c, the_file()), 422, "API_COMPARE_TOO_COSTLY")
        assert "at most 5" in e["message"] and "diagnostics" not in e
    with app_of(corpus_dir, compare_max_results=len(RESULT) - 4) as c:
        assert compared(c, the_file())["added_total"] == len(RESULT) - 4  # at the cap: served


def test_a_phrase_with_too_many_spellings_is_refused(
    shared: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scholar_compare, "MAX_PHRASE_FORMS", 1)
    e = error(post(shared, the_file(), '"language model"'), 422, "API_COMPARE_TOO_COSTLY")
    assert "spellings" in e["message"]


def test_a_query_is_refused_as_search_refuses_it(shared: TestClient) -> None:
    for q in ("(benchmark", "be*", "x" * 2_001):
        mine = post(shared, the_file(), q)
        theirs = shared.get("/api/v1/search", params={"q": q})
        assert mine.status_code == theirs.status_code == 422 and mine.json() == theirs.json()


def test_parameters_are_exact(shared: TestClient) -> None:
    body = the_file().encode()
    error(
        shared.post(COMPARE, params={"q": Q, "limit": "5"}, content=body, headers=RIS), 422, "API_BAD_PARAM"
    )
    error(
        shared.post(COMPARE, params={"q": Q, "format": "csv"}, content=body, headers=RIS),
        422,
        "API_BAD_PARAM",
    )
    error(shared.post(COMPARE, content=body, headers=RIS), 422, "API_BAD_PARAM")  # no q
    error(shared.post(COMPARE + "/", params={"q": Q}, content=body, headers=RIS), 404, "API_NOT_FOUND")
    r = shared.get(COMPARE, params={"q": Q})
    error(r, 405, "API_METHOD_NOT_ALLOWED")
    assert r.headers["allow"] == "POST"


# --- exported cells ------------------------------------------------------------------------------------------------
FORMULAS = [
    '=HYPERLINK("http://evil.example","x")',
    "+1+cmd|' /C calc'!A0",
    "-2+3",
    "@SUM(1)",
    " =1+1",
    "＝1+1",
    '"quoted", with a comma',
]


def test_no_exported_cell_starts_a_formula(shared: TestClient) -> None:
    file = "".join(entry(t, v, 2024) for t in FORMULAS for v in ("NeurIPS", "=AISTATS()"))
    body = compared(shared, file)
    seen = []
    for name in ("not_in_index", "not_compared"):
        rows = rows_of(body["csv"][name])
        assert [r["title"] for r in rows] == [csv_cell(r["title"]) for r in body[name]]
        for row in rows:
            for cell in row.values():
                assert not cell.lstrip().startswith(("=", "+", "@", "＝")), cell
                assert not (cell.startswith("-") and name)  # no cell starts with a minus either
            seen.append(row["title"])
    # ` =1+1` and the full-width `＝1+1` are one title key, so one paper of the six not in the index
    assert len(seen) == 6 + len(FORMULAS) and all(t.startswith("'") for t in seen[:5])
    assert all(r["venue"] == "'=AISTATS()" for r in rows_of(body["csv"]["not_compared"]))


@settings(max_examples=40, deadline=None)  # each example is a whole request: long by design
@given(
    st.lists(
        st.text(
            st.characters(blacklist_categories=["Cs"], blacklist_characters="\n\r"), min_size=1, max_size=40
        ).filter(lambda t: t.strip() != ""),
        min_size=1,
        max_size=5,
    )
)
def test_any_title_comes_back_as_one_guarded_cell(shared: TestClient, titles: list[str]) -> None:
    """Whatever a title holds (quotes, commas, formula starts, control characters), the CSV has one row per
    record and the title cell is `export.csv_cell` of the title the response gives."""
    r = post(shared, "".join(entry(t, "AISTATS", 2024) for t in titles))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["not_compared_total"] == len(titles)
    rows = rows_of(body["csv"]["not_compared"])
    assert [row["title"] for row in rows] == [csv_cell(n["title"]) for n in body["not_compared"]]
    assert [row["ris_record"] for row in rows] == [str(n) for n in range(1, len(titles) + 1)]


def test_the_csv_lists_are_the_rows(shared: TestClient) -> None:
    body = compared(shared, the_file())
    for name in ("kept", "dropped", "not_in_index", "added"):
        rows = rows_of(body["csv"][name])
        assert tuple(rows[0]) == route.CSV_COLUMNS if rows else True
        assert [(r["list"], r["id"], r["reason"], r["matched_by"]) for r in rows] == [
            (name, r["id"] or "", r["reason"] or "", r["matched_by"] or "") for r in body[name]
        ]
        assert {r["index_version"] for r in rows} <= {body["index_version"]}
        assert {r["canonical_hash"] for r in rows} <= {body["query"]["canonical_hash"]}
    sources = {r["id"]: r["record_source"] for r in rows_of(body["csv"]["added"])}
    assert set(sources.values()) == {"crawled", "ris_only"}
    assert all((s == "crawled") == (i in INDEX.independent) for i, s in sources.items())


# --- nothing of the file is kept -----------------------------------------------------------------------------------
def tree(root: Path) -> dict[str, tuple[int, int]]:
    return {
        str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.name.startswith(".tantivy")
    }


def test_the_file_is_never_logged(corpus_dir: Path, logs: Logs) -> None:
    file = the_file() + entry(f"{SECRET} title", f"{SECRET} venue", 2024) + by_forum(BY_ID[KEPT[2]], SECRET)
    with app_of(corpus_dir) as c:
        body = compared(c, file, f"benchmark OR {SECRET}")
        post(c, file.encode() + b"\xff")  # a refused file
    raw = logs.raw.getvalue()  # type: ignore[attr-defined]
    assert SECRET not in raw and "nobody indexed" not in raw and "AISTATS" not in raw
    lines = [x for x in logs() if x["event"] == "request" and x["route"] == COMPARE]
    assert [x["status"] for x in lines] == [200, 422]
    first = lines[0]
    # 15 records: the file's 11 papers and its 2 others, one more outside the venues, one more repeat
    assert (first["ris_records"], first["ris_papers"], first["ris_bytes"]) == (15, 11, len(file.encode()))
    assert (first["kept"], first["dropped"], first["not_in_index"], first["added"], first["total"]) == (
        body["kept_total"],
        body["dropped_total"],
        body["not_in_index_total"],
        body["added_total"],
        body["total"],
    )
    assert first["canonical_hash"] == body["query"]["canonical_hash"] and first["compare_ms"] > 0
    assert lines[1]["code"] == "API_RIS_INVALID" and "kept" not in lines[1]
    allowed = {"request_id", "method", "route", "status", "ms", "index_version", "canonical_hash", "total",
               "token_count", "n_errors", "error_codes", "warning_codes", "verified_clauses", "ris_bytes",
               "ris_records", "ris_papers", "kept", "dropped", "not_in_index", "added", "compare_ms",
               "compare_cost_ms", "compare_tokens", "abstract_source", "abstracts_withheld", "code",
               "ts", "level", "logger", "event"}  # fmt: skip
    assert all(set(x) <= allowed for x in lines), [set(x) - allowed for x in lines]


def test_the_file_is_never_written_anywhere(corpus_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Not to the data directory (index, snapshot, record store), and not to a temporary file."""

    def never(*a: Any, **k: Any) -> None:
        raise AssertionError("a temporary file was opened")

    with app_of(corpus_dir) as c:
        before = tree(corpus_dir)
        for name in ("TemporaryFile", "NamedTemporaryFile", "SpooledTemporaryFile", "mkstemp", "mkdtemp"):
            monkeypatch.setattr(tempfile, name, never)
        compared(c, the_file())
        monkeypatch.undo()
        assert tree(corpus_dir) == before
        assert not (corpus_dir / "records").exists()  # no search record either
        # and the index is what it was: the file's own papers are not in it
        assert c.get("/api/v1/search", params={"q": '"nobody indexed"'}).json()["total"] == 0


# --- cost: the rate limit, the slot, the time ---------------------------------------------------------------------
def test_a_comparison_costs_an_exports_weight_and_its_slot_time(corpus_dir: Path, logs: Logs) -> None:
    limit = RateLimit(
        capacity=25,
        refill_per_second=0.001,
        export_weight=10,
        compare_token_ms=1_000_000,
        compare_cooldown_factor=0,
    )
    with app_of(corpus_dir, rate_limit=limit) as c:
        assert post(c, the_file()).status_code == 200
        assert post(c, the_file()).status_code == 200
        r = post(c, the_file())  # 5 tokens left: a third can't be paid
        error(r, 429, "API_RATE_LIMITED")
        assert int(r.headers["retry-after"]) >= 1
        assert c.get("/api/v1/search", params={"q": Q}).status_code == 200  # a search still costs one
    line = next(x for x in logs() if x["event"] == "request" and x["route"] == COMPARE)
    assert line["compare_cost_ms"] > 0 and line["compare_tokens"] == round(line["compare_cost_ms"] / 1e6, 2)


def test_the_time_a_comparison_held_its_slot_is_debited(corpus_dir: Path) -> None:
    """One token per `compare_token_ms`: at a tiny rate one comparison leaves the client in debt."""
    limit = RateLimit(
        capacity=100,
        refill_per_second=0.001,
        export_weight=10,
        compare_token_ms=0.001,
        compare_cooldown_factor=0,
    )
    with app_of(corpus_dir, rate_limit=limit) as c:
        assert post(c, the_file()).status_code == 200
        error(c.get("/api/v1/search", params={"q": Q}), 429, "API_RATE_LIMITED")


def test_a_second_comparison_is_refused_while_the_slot_is_taken(
    corpus_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = threading.Event(), threading.Event()
    real = route._run

    def held(*a: Any) -> Any:
        entered.set()
        assert release.wait(30)
        return real(*a)

    monkeypatch.setattr(route, "_run", held)
    with app_of(corpus_dir) as c:
        first: list[Any] = []
        t = threading.Thread(target=lambda: first.append(post(c, the_file())))
        t.start()
        assert entered.wait(30)
        r = post(c, the_file())
        e = error(r, 503, "API_BUSY")
        assert r.headers["retry-after"] == "5" and "as many comparisons" in e["message"]
        assert c.get("/api/v1/search", params={"q": Q}).status_code == 200  # searches are not held up
        release.set()
        t.join(30)
        assert first[0].status_code == 200
        monkeypatch.setattr(route, "_run", real)
        assert post(c, the_file()).status_code == 200  # the slot came back


def test_a_comparison_past_its_time_is_stopped(corpus_dir: Path) -> None:
    with app_of(corpus_dir, compare_max_seconds=1e-9) as c:
        r = post(c, the_file())
        e = error(r, 503, "API_BUSY")
        assert r.headers["retry-after"] == "5" and "ran past" in e["message"]
        assert c.app.state.comparisons.slots.acquire(blocking=False)  # type: ignore[attr-defined]


def test_the_core_stops_at_a_tick_that_raises() -> None:
    """The time limit's hook: the oracle's evaluations are the comparison's cost, and each asks first."""
    side = scholar_compare.scope_and_match(read_ris(the_file(), "file"), INDEX, Scope())
    calls = 0

    class Stop(Exception):
        pass

    def tick() -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise Stop

    with pytest.raises(Stop):
        scholar_compare.compare_query(
            "file", Q, side=side, index=INDEX, engine=ORACLE, scope=Scope(), mode="native", tick=tick,
            fetch=lambda ids: {i: BY_ID[i] for i in ids},
        )  # fmt: skip
    assert calls == 3


def test_a_rate_limited_upload_is_drained_so_the_429_arrives() -> None:
    """A 429 sent while megabytes are still arriving would reach the client as a reset connection: the rest
    of the file is read and discarded first (for at most `DRAIN_SECONDS`), never kept."""
    sent: list[dict[str, Any]] = []
    left = [b"x" * 1000] * 5

    async def app(scope: Any, receive: Any, send: Any) -> None:
        raise AssertionError("the app ran")

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": left.pop(), "more_body": bool(left)}

    async def send(message: dict[str, Any]) -> None:
        assert not left, "answered before the file was drained"
        sent.append(message)

    limit = RateLimit(capacity=10, refill_per_second=0.001, export_weight=10)
    limiter = RateLimitMiddleware(app, limit, ())
    limiter.buckets.debit("203.0.113.9", 10)  # nothing left for this client
    scope = {"type": "http", "method": "POST", "path": COMPARE, "client": ("203.0.113.9", 1), "headers": []}
    anyio.run(limiter, scope, receive, send)
    assert sent[0]["status"] == 429 and not left


def test_a_drain_gives_up_after_its_time() -> None:
    async def forever() -> dict[str, Any]:
        await anyio.sleep(30)
        return {"type": "http.request", "body": b"", "more_body": True}

    async def run() -> float:
        started = anyio.current_time()
        await drain(forever, 0.05)
        return anyio.current_time() - started

    assert anyio.run(run) < 5


def test_a_file_that_arrives_too_slowly_is_408() -> None:
    class Slow:
        async def stream(self) -> Any:
            yield b"TY  - JOUR\n"
            await anyio.sleep(30)
            yield b"ER  - \n"

    async def read() -> None:
        await route._read(Slow(), 0.05)  # type: ignore[arg-type]

    with pytest.raises(route.ApiError) as caught:
        anyio.run(read)
    assert caught.value.code == "API_UPLOAD_TIMEOUT" and caught.value.status == 408
    assert caught.value.headers["Connection"] == "close"


# --- the match table and the served index --------------------------------------------------------------------------
def test_the_table_is_built_once_per_served_index(corpus_dir: Path, logs: Logs) -> None:
    with app_of(corpus_dir) as c:
        state: IndexState = c.app.state.index  # type: ignore[attr-defined]
        served = state.served
        assert served is not None and served.matches is not None and served.matches.index is not None
        table = served.matches.index
        compared(c, the_file())
        compared(c, the_file())
        assert state.load()  # SIGHUP with nothing changed
        assert state.served is served
        (data := corpus_dir / "takedowns").mkdir(exist_ok=True)
        try:
            (data / "withheld.txt").write_text(f"{KEPT[0]}  # logged\n", encoding="utf-8")
            assert state.load()  # the same index, another takedown list: a new bundle, the same table
            again = state.served
            assert again is not None and again is not served
            assert again.matches is served.matches and again.matches.index is table
            body = compared(c, the_file())
            row = body["kept"][0]
            assert row["id"] == KEPT[0] and row["abstract_withheld"] is True and row["detail"] == ""
        finally:
            (data / "withheld.txt").unlink()
            data.rmdir()
    built = [x for x in logs() if x["event"] == "match_index_built"]
    assert len(built) == 1 and built[0]["records"] == len(PAPERS) and built[0]["ms"] >= 0


def test_a_comparison_waits_for_the_table(corpus_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MatchTable, "build", lambda self, records, version: None)  # still being built
    with app_of(corpus_dir) as c:
        r = post(c, the_file())
        e = error(r, 503, "API_BUSY")
        assert r.headers["retry-after"] == "5" and "still being prepared" in e["message"]
        assert c.get("/api/v1/search", params={"q": Q}).status_code == 200


def test_a_table_that_cannot_be_built_is_logged_once(
    corpus_dir: Path, monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    def broken(records: Any) -> MatchIndex:
        raise RuntimeError(f"failed on {SECRET}")

    monkeypatch.setattr(MatchIndex, "build", broken)
    with app_of(corpus_dir) as c:
        error(post(c, the_file()), 500, "API_INTERNAL")
        assert c.get("/api/v1/search", params={"q": Q}).status_code == 200  # the index is served all the same
    (line,) = [x for x in logs() if x["event"] == "match_index_failed"]
    assert line["level"] == "ERROR" and line["error"] == "RuntimeError" and SECRET not in json.dumps(logs())


def test_a_swap_never_pairs_one_indexs_result_with_anothers_table(
    data_dir: Path, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A comparison in flight across a hot swap finishes on the index it started on, with that index's table:
    a record only the old index holds is still matched there, and the next request, on the new index, reports
    it as not in the index."""
    corpus = list(records())
    late = next(p for p in (attributed(r) for r in corpus[300:800]) if p.id in BY_ID and plain(p))
    early = attributed(corpus[0])
    file = by_forum(late) + by_forum(early)
    entered, release = threading.Event(), threading.Event()
    real = route._run

    def held(*a: Any) -> Any:
        entered.set()
        assert release.wait(30)
        return real(*a)

    with app_of(data_dir) as c:
        monkeypatch.setattr(route, "_run", held)
        first: list[Any] = []
        t = threading.Thread(target=lambda: first.append(post(c, file)))
        t.start()
        assert entered.wait(30)
        point_current(data_dir, store.small)
        state: IndexState = c.app.state.index  # type: ignore[attr-defined]
        assert state.load()
        release.set()
        t.join(30)
        monkeypatch.setattr(route, "_run", real)
        old, new = first[0].json(), compared(c, file)
    assert (old["index_version"], new["index_version"]) == (store.big, store.small)
    assert old["not_in_index_total"] == 0 and old["kept_total"] + old["dropped_total"] == 2
    assert [r["ris_record"] for r in new["not_in_index"]] == [1]  # the small index has only the first 300
    assert new["kept_total"] + new["dropped_total"] == 1


def test_a_table_must_be_its_bundles_snapshot(
    corpus_dir: Path, monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    """Defence in depth: a table whose ids are not the served records' is refused, never served."""
    other = MatchIndex.build(PAPERS[:10])
    monkeypatch.setattr(MatchIndex, "build", lambda records: other)
    with app_of(corpus_dir) as c:
        error(post(c, the_file()), 500, "API_INTERNAL")
    (line,) = [x for x in logs() if x["event"] == "match_index_failed"]
    assert line["reason"] == "match_index_mismatch"


# --- what a comparison may disclose (the 2026-10-05 audit of api/compare.py) -----------------------------------
def test_a_disabled_instance_answers_every_request_alike(corpus_dir: Path, tmp_path: Path) -> None:
    """Off, the path says one thing whatever is sent: nothing of the query, the body or the index is read."""
    with TestClient(make_app(corpus_dir)) as c:
        body = the_file().encode()
        answers = [
            c.post(COMPARE, params={"q": Q}, content=body, headers=RIS),
            c.post(COMPARE, content=body, headers=RIS),  # no q
            c.post(COMPARE, params={"q": "(unbalanced", "mode": "nonsense"}, content=body, headers=RIS),
            c.post(COMPARE, params={"q": Q}, content=body, headers={"Content-Type": "multipart/form-data"}),
            c.post(COMPARE, params={"q": Q}, content=b"\xff\xfe", headers=RIS),
            c.post(COMPARE, params={"q": Q}, content=body, headers={**RIS, "Origin": "https://evil.example"}),
        ]
        assert {r.status_code for r in answers} == {403}
        assert len({r.content for r in answers}) == 1
        e = error(answers[0], 403, "API_COMPARE_DISABLED")
        assert set(e) == {"code", "message"} and "access-control-allow-origin" not in answers[-1].headers
        # what any route refuses before its handler is refused here too, and says nothing of this feature
        error(c.post(COMPARE, params={"q": Q, "bogus": "1"}, content=body, headers=RIS), 422, "API_BAD_PARAM")
        error(c.post(COMPARE, params={"q": Q}, content=b"x" * 70_000, headers=RIS), 413, "API_BODY_TOO_LARGE")

        def chunked() -> Iterator[bytes]:  # the same size with no declared length: drained, then the 403
            for _ in range(70):
                yield b"x" * 1000

        assert c.post(COMPARE, params={"q": Q}, content=chunked(), headers=RIS).status_code == 403
        error(c.get(COMPARE, params={"q": Q}), 405, "API_METHOD_NOT_ALLOWED")
    with TestClient(make_app(corpus_dir, rate_limit=RateLimit(capacity=10, refill_per_second=0.001))) as c:
        assert c.post(COMPARE, params={"q": Q}, content=b"x", headers=RIS).status_code == 403
        error(c.post(COMPARE, params={"q": Q}, content=b"x", headers=RIS), 429, "API_RATE_LIMITED")
    (tmp_path / "indexes").mkdir()
    with TestClient(make_app(tmp_path)) as c:  # no index loaded: still the one answer, not the index's state
        assert c.post(COMPARE, params={"q": Q}, content=b"x", headers=RIS).content == answers[0].content


def test_a_withheld_abstract_is_never_returned_or_located(corpus_dir: Path) -> None:
    """Decision-022: a takedown withholds what is shown. A comparison says which list a withheld paper is in
    (whether the query matches it, as `/search` does: the accepted leak) and nothing more: no abstract, no
    evidence naming words or the field they are in, in the rows, the CSV or the RIS."""
    listed = [*sorted(i for i in RESULT - set(KEPT) if BY_ID[i].abstract)[:2], STEMMED[0], UNMATCHED[0]]
    (data := corpus_dir / "takedowns").mkdir(exist_ok=True)
    (data / "withheld.txt").write_text("".join(f"{i}  # logged\n" for i in listed), encoding="utf-8")
    try:
        with app_of(corpus_dir) as c:
            before = compared(c, the_file())  # the same file on the same index, the list applied
            raw = post(c, the_file()).text
            hits = c.get("/api/v1/search", params={"q": Q, "limit": 200}).json()["hits"]
    finally:
        (data / "withheld.txt").unlink()
        data.rmdir()
    rows = {r["id"]: r for name in ("kept", "dropped", "added") for r in before[name]}
    for i in listed:
        assert rows[i]["abstract_withheld"] is True and rows[i]["detail"] == ""
        abstract = BY_ID[i].abstract
        assert abstract is not None and one_line(abstract)[:40] not in raw and abstract[:40] not in raw
    # the list each is in is what /search already says of it: a hit or not
    assert {i for i in listed if any(i == r["id"] for r in before["added"])} == set(listed) & {
        h["id"] for h in hits
    }
    assert [rows[i]["reason"] for i in listed[2:]] == ["stemming", "full_text"]  # the class, not its evidence
    for name in ("dropped", "added"):
        assert all(r["detail"] == "" for r in rows_of(before["csv"][name]) if r["id"] in listed)
    withheld = [r for r in parse_ris(before["added_ris"], "added.ris") if r.fields["ID"][0] in listed]
    assert len(withheld) == 2
    assert all("AB" not in r.fields and exporter.TAKEDOWN in r.fields["N1"] for r in withheld)
    # every other row still explains itself
    assert all(r["detail"] for r in before["dropped"] if r["id"] not in listed)


def test_a_filtered_paper_is_one_search_serves_when_asked(shared: TestClient) -> None:
    """Decision-012: rejected, withdrawn and other-track records are indexed and public, excluded by default
    and served by a query that names them. A `filtered` row says no more than that query's hit does."""
    body = compared(shared, the_file())
    filtered = [r for r in body["dropped"] if r["reason"] == "filtered"]
    assert {r["id"] for r in filtered} == set(FILTERED)
    for row in filtered:
        p = BY_ID[row["id"]]
        q = f"{Q} status:{p.status} track:{p.track}"
        hit = next(h for h in shared.get("/api/v1/search", params={"q": q, "limit": 200}).json()["hits"]
                   if h["id"] == row["id"])  # fmt: skip
        said = dict(part.split("=") for part in row["detail"].split(", "))
        assert said and all(hit[field] == value for field, value in said.items())
        assert set(said) <= {"track", "status"}


def test_every_id_a_comparison_names_is_a_paper_the_index_serves(shared: TestClient) -> None:
    """The match table holds the served snapshot's records and no others: every id in a row, in its evidence,
    in a CSV or in the RIS answers on `/papers/{id}`."""
    twin = BY_ID[next(i for i in BY_ID if i.endswith("Fx0516"))]
    file = the_file() + entry(one_line(twin.title), twin.venue, twin.year)  # an ambiguous match names two ids
    file += entry(
        one_line(BY_ID[KEPT[3]].title), BY_ID[KEPT[3]].venue, BY_ID[KEPT[3]].year + 1
    )  # "elsewhere"
    raw = post(shared, file).text
    named = set(re.findall(r"op:[a-z]+:[0-9]{4}:[A-Za-z0-9_-]+", raw))
    assert len(named) > 30 and named <= set(BY_ID)
    assert all(shared.get(f"/api/v1/papers/{i}").status_code == 200 for i in sorted(named))


def test_one_requests_file_never_reaches_another(corpus_dir: Path) -> None:
    """Nothing parsed from a file outlives its request: the next client's answer holds none of it, and an
    answer is the same whatever was compared before it."""
    mine = entry(f"{SECRET} unpublished review protocol", "NeurIPS", 2024) + by_title(BY_ID[KEPT[0]])
    with app_of(corpus_dir) as c:
        fresh = post(c, the_file()).content
        assert SECRET in post(c, mine).text  # the sender gets their own titles back
        after = post(c, the_file())
        assert after.content == fresh and SECRET not in after.text
        assert SECRET not in c.get("/api/v1/search", params={"q": Q}).text
        state: IndexState = c.app.state.index  # type: ignore[attr-defined]
        assert state.served is not None and state.served.matches is not None
        table = state.served.matches.index
        assert table is not None and not any(SECRET in key for key in table.any_cell)
    # the app's own object for this route holds its slots and the networks' cooldown times, nothing else
    # (this checks that one object's attributes; the assertions above are what show no file is kept)
    assert set(vars(c.app.state.comparisons)) == {"slots", "cooldowns"}  # type: ignore[attr-defined]


def test_no_refusal_or_failure_says_what_the_file_held(
    corpus_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 4xx names a line number or a count, never content; a 500 names only the request id."""
    secret_file = entry(f"{SECRET} title", f"{SECRET} venue", 2024)
    with app_of(corpus_dir, compare_max_records=1, compare_max_line_chars=64) as c:
        refusals = [
            post(c, secret_file * 2),  # records
            post(c, secret_file + f"AB  - {SECRET}" + "x" * 80 + "\n"),  # a line
            post(c, f"{SECRET}\n" + secret_file),  # content before the first record
            post(c, secret_file.encode() + b"\xff"),  # not UTF-8
        ]
        assert [r.status_code for r in refusals] == [413, 413, 422, 422]
        # each message is the route's own: a constant for a 422 (never scholarmend's, which names the file and
        # its byte count), and for a 413 a sentence in which only numbers vary
        said = [r.json()["error"]["message"] for r in refusals]
        assert said[2] == route.NOT_RIS and said[3] == route.NOT_UTF8
        assert set(said[2:]) <= route.INVALID_MESSAGES
        assert re.fullmatch(
            r"The file holds [0-9,]+ records; this instance compares at most [0-9,]+ in one request\. "
            r"Split it into several files\.",
            said[0],
        )
        assert re.fullmatch(
            r"Line [0-9,]+ of the file is over [0-9,]+ characters, the longest line this instance reads\. "
            r"Leave the abstracts out: only titles, venues, years and links are compared\.",
            said[1],
        )
        for empty in (b"", b"  \n"):
            assert post(c, empty).json()["error"]["message"] == route.NO_RECORD
        assert post(c, b"TY  - JOUR\rER  - \r").json()["error"]["message"] == route.CR_ONLY

        def broken(*a: Any, **k: Any) -> None:
            raise RuntimeError(f"failed on {SECRET} at /srv/data/indexes")

        monkeypatch.setattr(scholar_compare, "scope_and_match", broken)
        monkeypatch.setattr(route, "scope_and_match", broken)
        failed = post(c, secret_file)
        refusals.append(failed)
        e = error(failed, 500, "API_INTERNAL")
        assert set(e) == {"code", "message"}
    for r in refusals:
        assert SECRET not in r.text and "/srv/" not in r.text and "Traceback" not in r.text
        assert "scholarmend" not in r.text and ".py" not in r.text


# --- CORS -----------------------------------------------------------------------------------------------------------
def test_cors_allows_the_upload_from_a_listed_origin_only(corpus_dir: Path) -> None:
    origin = "https://review.example"
    with app_of(corpus_dir, cors_origins=(origin,)) as c:
        ask = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
        ok = c.options(COMPARE, headers={"Origin": origin, **ask})
        assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == origin
        assert "access-control-allow-credentials" not in ok.headers
        assert c.options(COMPARE, headers={"Origin": "https://evil.example", **ask}).status_code == 400
        r = c.post(COMPARE, params={"q": Q}, content=the_file().encode(), headers={**RIS, "Origin": origin})
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origin
        r = c.post(
            COMPARE,
            params={"q": Q},
            content=the_file().encode(),
            headers={**RIS, "Origin": "https://evil.example"},
        )
        assert "access-control-allow-origin" not in r.headers  # answered, but no page elsewhere can read it
        assert r.headers["cache-control"] == "no-store"


# --- a property: the accounting holds for any file --------------------------------------------------------------
PLAIN = [p for p in PAPERS if plain(p)]


@settings(max_examples=25, deadline=None)  # each example is a whole comparison (the oracle over its records)
@given(
    st.lists(st.sampled_from(PLAIN), max_size=12),
    st.lists(st.sampled_from(["title", "forum"]), min_size=12, max_size=12),
    st.integers(0, 3),
    st.integers(0, 2),
    st.sampled_from([Q, "trust AND benchmark$", '"language model" OR llm$', "agent year:2020..2022"]),
)
def test_every_record_is_counted_once_and_the_result_is_the_searchs(
    shared: TestClient, picked: list[PaperRecord], how: list[str], unknown: int, elsewhere: int, q: str
) -> None:
    file = "".join(by_title(p) if h == "title" else by_forum(p) for p, h in zip(picked, how, strict=False))
    file += "".join(entry(f"a paper nobody indexed {n}", "ICML", 2021) for n in range(unknown))
    file += "".join(entry(f"elsewhere {n}", "AISTATS", 2021) for n in range(elsewhere))
    r = post(shared, file, q)
    if not picked and not unknown and not elsewhere:
        error(r, 422, "API_RIS_INVALID")  # no record
        return
    assert r.status_code == 200, r.text
    body = r.json()
    result = ids_of(q)
    held = {p.id for p in picked}
    assert body["total"] == len(result)
    assert {x["id"] for x in body["kept"]} == held & result
    assert {x["id"] for x in body["dropped"]} == held - result
    assert [x["id"] for x in body["added"]] == sorted(result - held)
    assert body["not_in_index_total"] == unknown and body["not_compared_total"] == elsewhere
    assert body["duplicates_total"] == len(picked) - len(held)
    assert body["records_total"] == len(picked) + unknown + elsewhere
    assert sum(x["copies"] for x in [*body["kept"], *body["dropped"]]) == len(picked)
    assert not [x for name in ("kept", "dropped", "added") for x in body[name] if x["reason"] == "our_bug"]
