"""Takedowns at serve time (TASK-136, decision-022; spec 04, spec 08 §Deploy): every index version the API loads
withholds each listed abstract from hits, highlights, `/papers/{id}` (its provenance too) and every export
format, marked withheld (never shown as missing); what matches is unchanged (decision-022: a pinned version
still matches on the withheld text, so a search record replays `reproduced`); the list is re-read on every
reload, and a list that doesn't parse changes nothing.

Two indexes of the same records: `old`, built before the takedown (it holds the abstract), and `new`, built
with the list (its snapshot withheld the abstract). A search record saved on `old` pins it."""

from __future__ import annotations

import csv
import io
import json
import shutil
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings import cli, takedown_check, takedowns
from openproceedings import export as exporter
from openproceedings.api import export as route
from openproceedings.api import papers as papers_route
from openproceedings.api import search as search_route
from openproceedings.api import server as api_server
from openproceedings.api.state import IndexState, Served
from openproceedings.engine.index import build_index
from openproceedings.ingest import snapshot as snapshot_module
from openproceedings.ingest.dedup import DedupResult, Merge
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.snapshot import render, withhold
from openproceedings.query.normalize import normalize
from openproceedings.vocab import STATUSES, TRACKS
from refaudit.bibtex import parse_string
from scholarmend.parse import parse_ris

from tests.contract.conftest import attributed, make_app, point_current
from tests.contract.test_pinned import Logs
from tests.contract.test_records import replayed, save
from tests.fixtures.corpus.synthetic_5k import records
from tests.unit.engine.test_exclusions import BUILT

EXPORT = "/api/v1/export"
DATE = "2026-09-30"
EVERY = f"track:({' OR '.join(TRACKS)}) status:({' OR '.join(STATUSES)})"
FORMATS = ("ris", "csv", "bibtex", "jsonl")


def _pick(papers: list[PaperRecord]) -> tuple[PaperRecord, str]:
    """A paper with an attributed abstract and a word its abstract has and no title in the corpus has: a
    query for that word matches it through the abstract alone."""
    in_titles = {t for p in papers for t in normalize(p.title)}
    for p in papers:
        if p.abstract is None or not p.claims("abstract"):
            continue
        only = sorted(set(normalize(p.abstract)) - in_titles)
        if only and only[0].isalpha():
            return p, only[0]
    raise AssertionError("the fixture has no paper to take down")


def _build(
    papers: list[PaperRecord], data: Path, name: str, listed: frozenset[str], merges: tuple[Merge, ...] = ()
) -> str:
    snap = data / "snapshots" / name
    snap.mkdir(parents=True)
    done = withhold(DedupResult(tuple(sorted(papers, key=lambda p: p.id)), merges, ()), listed)
    for file, blob in render(done.result, [], BUILT, withheld=done.withheld).items():
        (snap / file).write_bytes(blob)
    return build_index(snap, data / "indexes", BUILT).index_version


type Store = tuple[Path, str, str, PaperRecord, str]  # data dir, old, new, the paper, its abstract-only word


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Store:
    data = tmp_path_factory.mktemp("takedowns") / "data"
    papers = [attributed(r) for r in list(records())[:900]]
    paper, word = _pick(papers)
    old = _build(papers, data, "old", frozenset())
    new = _build(papers, data, "new", frozenset({paper.id}))
    (data / "indexes" / "current").symlink_to(old)
    return data, old, new, paper, word


@pytest.fixture(autouse=True)
def fixed_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exporter, "utc_date", lambda: DATE)
    monkeypatch.setattr(route, "utc_date", lambda: DATE)


@pytest.fixture
def data_dir(store: Store, tmp_path: Path) -> Path:
    """A copy of the store with an empty list: `new`'s snapshot withheld an abstract, so a missing list fails
    every load (TASK-067); the tests of a missing list delete it."""
    shutil.copytree(store[0], tmp_path / "data", symlinks=True)
    listing(tmp_path / "data")
    return tmp_path / "data"


def unlisted(data_dir: Path) -> None:
    (data_dir / "takedowns" / "withheld.txt").unlink()


def listing(data_dir: Path, *ids: str, text: str | None = None) -> None:
    (data_dir / "takedowns").mkdir(exist_ok=True)
    (data_dir / "takedowns" / "withheld.txt").write_text(
        text if text is not None else "".join(f"{i}  # logged\n" for i in ids), encoding="utf-8"
    )


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    with TestClient(make_app(data_dir)) as c:
        yield c


def reload(client: TestClient) -> bool:
    state: IndexState = client.app.state.index  # type: ignore[attr-defined]
    return state.load()


def search(client: TestClient, q: str) -> dict[str, Any]:
    r = client.get("/api/v1/search", params={"q": q, "limit": 200})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def the_hit(body: dict[str, Any], rid: str) -> dict[str, Any]:
    [hit] = [h for h in body["hits"] if h["id"] == rid]
    return hit


def exported(client: TestClient, fmt: str, **params: str) -> str:
    r = client.get(EXPORT, params={"format": fmt, **params})
    assert r.status_code == 200, r.text
    return r.text


def withheld_in_export(fmt: str, text: str, rid: str) -> bool:
    """Whether `rid`'s record in an export body carries no abstract and says a takedown withheld it (read
    back with the reference parsers)."""
    if fmt == "ris":
        [rec] = [r for r in parse_ris(text, "x.ris") if r.first("ID") == rid]
        notes = rec.fields["N1"]
        return (
            not rec.fields.get("AB")
            and notes[-1].startswith("openproceedings ")  # the provenance line stays the last N1
            and notes[-2] == exporter.TAKEDOWN  # the takedown sentence just before it
            and sum(n.startswith("Abstract ") for n in notes) == 1  # no source line beside it
        )
    if fmt == "bibtex":
        [e] = [e for e in parse_string(text) if e.fields["openproceedings_id"] == rid]
        return "abstract" not in e.fields and e.fields.get("abstract_withheld") == exporter.TAKEDOWN
    if fmt == "csv":
        [row] = [r for r in csv.DictReader(io.StringIO(text.removeprefix("﻿"))) if r["id"] == rid]
        return (row["abstract"], row["abstract_withheld"], row["abstract_withheld_reason"]) == (
            "", "true", "takedown",
        )  # fmt: skip
    [obj] = [o for o in map(json.loads, text.splitlines()) if o["id"] == rid]
    return (
        obj["abstract"] is None and obj["abstract_withheld"] and obj["abstract_withheld_reason"] == "takedown"
    )


# --- the served index still holds the abstract (listed after it was built) -------------------------------------


def test_a_listed_hit_matches_as_before_and_shows_nothing_of_its_abstract(
    client: TestClient, data_dir: Path, store: Store
) -> None:
    _, _, _, paper, word = store
    q = f"abstract:{word} {EVERY}"
    before = search(client, q)
    hit = the_hit(before, paper.id)
    assert (
        hit["abstract"] == paper.abstract and hit["highlights"]["abstract"] and not hit["abstract_withheld"]
    )
    listing(data_dir, paper.id)
    assert reload(client)
    after = search(client, q)
    hit = the_hit(after, paper.id)  # still a hit: decision-022 (the index matches the text it holds)
    assert hit["abstract"] is None and hit["abstract_withheld"] is True
    assert hit["highlights"]["abstract"] == [] and hit["abstract_source"] is None
    assert hit["title"] == paper.title
    # membership, order and counts are the index's: nothing but the display changed
    assert (after["total"], after["facets"], after["excluded"]) == (
        before["total"],
        before["facets"],
        before["excluded"],
    )
    assert [h["id"] for h in after["hits"]] == [h["id"] for h in before["hits"]]
    assert paper.abstract is not None and paper.abstract not in json.dumps(after)
    broad = search(client, f"agents {EVERY}")["hits"]  # every other hit is as it was
    assert broad and all(h["abstract_withheld"] is (h["id"] == paper.id) for h in broad)


def test_the_paper_page_withholds_the_abstract_and_its_claims(
    client: TestClient, data_dir: Path, store: Store
) -> None:
    _, _, _, paper, word = store
    listing(data_dir, paper.id)
    assert reload(client)
    body = client.get(f"/api/v1/papers/{paper.id}", params={"q": f"abstract:{word} {EVERY}"}).json()
    assert body["abstract_withheld"] is True and body["matched"] is True  # the index's answer, as /search's
    assert body["highlights"]["abstract"] == []
    shown = {k: v for k, v in body["paper"].items() if k != "venue_name"}  # derived, never stored
    record = PaperRecord.model_validate_json(json.dumps(shown))  # content_hash consistent with what is shown
    assert record.abstract is None and record.claims("abstract") == ()
    assert record.provenance and record.title == paper.title
    assert paper.abstract is not None and paper.abstract not in json.dumps(body)
    plain = client.get(f"/api/v1/papers/{paper.id}").json()
    assert plain["abstract_withheld"] is True and plain["paper"]["abstract"] is None


@pytest.mark.parametrize("fmt", FORMATS)
def test_every_export_withholds_the_listed_abstract(
    client: TestClient, data_dir: Path, store: Store, fmt: str
) -> None:
    _, old, _, paper, word = store
    q = f"abstract:{word} {EVERY}"
    assert paper.abstract is not None and paper.abstract in exported(client, fmt, q=q)
    listing(data_dir, paper.id)
    assert reload(client)
    body = exported(client, fmt, q=q)
    assert paper.abstract not in body and withheld_in_export(fmt, body, paper.id)
    assert exported(client, fmt, q=q, index_version=old) == body  # the served index, named


def test_the_export_counts_the_records_it_withholds_in_a_header(
    client: TestClient, data_dir: Path, store: Store
) -> None:
    """`X-Abstracts-Withheld` (decision-022): how many records of the body a takedown withholds, before the
    body; the served index, a named one and a search record's own index alike; 0 when none."""
    _, old, _, paper, word = store
    q = f"abstract:{word} {EVERY}"
    record_id = save(client, q)
    assert client.get(EXPORT, params={"format": "ris", "q": q}).headers["X-Abstracts-Withheld"] == "0"
    listing(data_dir, paper.id)
    assert reload(client)
    for params in ({"q": q}, {"q": q, "index_version": old}, {"record_id": record_id}):
        r = client.get(EXPORT, params={"format": "csv", **params})
        assert (r.headers["X-Abstracts-Withheld"], r.headers["X-Abstract-Source"]) == ("1", "attributed")
    other = client.get(EXPORT, params={"format": "csv", "q": f"agents NOT abstract:{word} {EVERY}"})
    assert other.headers["X-Abstracts-Withheld"] == "0"  # the listed paper isn't in that set


def test_op_export_withholds_as_the_api_does(
    data_dir: Path, store: Store, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, _, _, paper, word = store
    listing(data_dir, paper.id)
    out = tmp_path / "x.jsonl"
    assert cli.main(["--data-dir", str(data_dir), "export", f"abstract:{word} {EVERY}", "--format", "jsonl",
                     "--out", str(out)]) == 0  # fmt: skip
    with TestClient(make_app(data_dir)) as c:
        assert out.read_text(encoding="utf-8") == exported(c, "jsonl", q=f"abstract:{word} {EVERY}")
    assert withheld_in_export("jsonl", out.read_text(encoding="utf-8"), paper.id)
    assert (
        "op export: 1 record(s) have their abstract withheld at a rights holder's request"
        in capsys.readouterr().err
    )


# --- a new index built with the list, the old one pinned by a search record ------------------------------------


def test_a_record_on_the_old_index_replays_reproduced_and_exports_withheld(
    data_dir: Path, store: Store
) -> None:
    """Guarantee 4 (decision-022): the record's ids are its pinned index's, whatever the list says; the record's
    export (the ids it cites) withholds the abstract that index still holds."""
    _, old, new, paper, word = store
    q = f"abstract:{word} {EVERY}"
    with TestClient(make_app(data_dir)) as c:
        record_id = save(c, q)
        before = replayed(c, record_id, ids=True)
    assert before["replay"]["status"] == "reproduced" and paper.id in before["record"]["ids"]
    listing(data_dir, paper.id)
    point_current(data_dir, new)
    with TestClient(make_app(data_dir)) as c:
        after = replayed(c, record_id, ids=True)
        assert after["replay"]["status"] == "reproduced"
        assert after["record"]["ids"] == before["record"]["ids"]
        assert after["replay"]["index_version"] == old
        for fmt in FORMATS:
            body = exported(c, fmt, record_id=record_id)
            assert paper.abstract is not None and paper.abstract not in body
            assert withheld_in_export(fmt, body, paper.id)
            pinned = exported(c, fmt, q=q, index_version=old)  # the old index named explicitly
            assert paper.abstract not in pinned and withheld_in_export(fmt, pinned, paper.id)
        # on the new index the abstract is gone from the index itself: the word no longer finds the paper
        assert paper.id not in {h["id"] for h in search(c, q)["hits"]}


def test_a_snapshot_withheld_abstract_is_marked_withheld_even_off_the_list(
    data_dir: Path, store: Store
) -> None:
    """The new index's snapshot withheld the abstract: it is marked withheld, not missing, though the list no
    longer names it (a takedown lifted later needs a rebuild without the id to bring it back)."""
    _, _, new, paper, _ = store
    with TestClient(make_app(data_dir)) as c:
        old_missing = c.get("/api/v1/coverage").json()["totals"]["abstract_missing"]
    listing(data_dir)  # an empty list: every takedown lifted (a missing one would refuse the load, below)
    point_current(data_dir, new)
    with TestClient(make_app(data_dir)) as c:
        hit = the_hit(search(c, f'title:"{paper.title}" {EVERY}'), paper.id)
        assert hit["abstract"] is None and hit["abstract_withheld"] is True
        assert c.get(f"/api/v1/papers/{paper.id}").json()["abstract_withheld"] is True
        totals = c.get("/api/v1/coverage").json()["totals"]
        assert (totals["abstract_withheld"], totals["abstract_missing"]) == (1, old_missing)


def test_coverage_counts_what_is_withheld_when_served(
    client: TestClient, data_dir: Path, store: Store
) -> None:
    _, _, _, paper, _ = store
    before = client.get("/api/v1/coverage").json()
    assert before["totals"]["abstract_withheld"] == 0
    listing(data_dir, paper.id)
    assert reload(client)
    after = client.get("/api/v1/coverage").json()
    assert after["totals"]["abstract_withheld"] == 1
    assert after["totals"]["abstract_missing"] == before["totals"]["abstract_missing"]  # it had an abstract
    [vy] = [v for v in after["venue_years"] if (v["venue"], v["year"]) == (paper.venue, paper.year)]
    [track] = [t for t in vy["tracks"] if t["track"] == paper.track]
    assert vy["abstract_withheld"] == track["abstract_withheld"] == 1


# --- the list's lifecycle ---------------------------------------------------------------------------------------


def test_coverage_counts_a_listed_record_without_an_abstract_once(
    client: TestClient, data_dir: Path, store: Store
) -> None:
    """Listed after the build, a record the sources gave no abstract moves from missing to withheld: never
    counted twice, at every level."""
    before = client.get("/api/v1/coverage").json()
    bare = next(
        attributed(r) for r in list(records())[:900] if attributed(r).abstract is None
    )  # the same 900 records the indexes hold
    listing(data_dir, bare.id)
    assert reload(client)
    after = client.get("/api/v1/coverage").json()

    def at(c: dict[str, Any]) -> tuple[tuple[int, int], ...]:
        [vy] = [v for v in c["venue_years"] if (v["venue"], v["year"]) == (bare.venue, bare.year)]
        [track] = [t for t in vy["tracks"] if t["track"] == bare.track]
        return tuple((x["abstract_missing"], x["abstract_withheld"]) for x in (c["totals"], vy, track))

    assert at(after) == tuple((m - 1, w + 1) for m, w in at(before))


def test_a_missing_list_after_one_was_applied_fails_the_reload(
    client: TestClient, data_dir: Path, store: Store
) -> None:
    """A renamed or unmounted takedowns/ never lifts every takedown silently: the reload fails and the list
    in force stays."""
    _, _, _, paper, _ = store
    listing(data_dir, paper.id)
    assert reload(client)
    (data_dir / "takedowns" / "withheld.txt").unlink()
    assert reload(client) is False
    assert client.get(f"/api/v1/papers/{paper.id}").json()["abstract_withheld"] is True


def test_a_failed_promotion_still_applies_a_new_list(logs: Logs, data_dir: Path, store: Store) -> None:
    """The list parsed, the index `current` names doesn't load: the served index keeps serving, with the new
    list (the operator's latest instruction), and its coverage counts it; both lines are logged."""
    _, old, _, paper, _ = store
    with TestClient(make_app(data_dir)) as client:
        listing(data_dir, paper.id)
        current = data_dir / "indexes" / "current"
        current.unlink()
        current.symlink_to("does-not-exist")
        assert reload(client) is False
        assert client.get(f"/api/v1/papers/{paper.id}").json()["abstract_withheld"] is True
        assert client.get("/api/v1/coverage").json()["totals"]["abstract_withheld"] == 1
    events = [x for x in logs() if x["event"] in ("index_load_failed", "takedowns_reloaded")]
    assert [x["event"] for x in events] == ["index_load_failed", "takedowns_reloaded"]
    assert {k: events[1][k] for k in ("index_version", "abstracts_withheld", "takedowns_not_in_index")} == {
        "index_version": old, "abstracts_withheld": 1, "takedowns_not_in_index": 0,
    }  # fmt: skip


def test_the_load_and_reload_lines_count_the_list(logs: Logs, data_dir: Path, store: Store) -> None:
    """Counts, never ids: how many the list names, and how many of those the index doesn't hold."""
    paper = store[3]
    listing(data_dir, paper.id, "op:iclr:2024:NotInThisIndex")
    with TestClient(make_app(data_dir)) as client:
        listing(data_dir, paper.id)
        assert reload(client)
        r = client.get(EXPORT, params={"format": "jsonl", "q": f'title:"{paper.title}" {EVERY}'})
        assert r.headers["X-Abstracts-Withheld"] == "1"
    lines = logs()
    [loaded] = [x for x in lines if x["event"] == "index_loaded"]
    assert (loaded["abstracts_withheld"], loaded["takedowns_not_in_index"], loaded["takedowns_list"]) == (
        2, 1, "present",
    )  # fmt: skip
    [reloaded] = [x for x in lines if x["event"] == "takedowns_reloaded"]
    assert (reloaded["abstracts_withheld"], reloaded["takedowns_not_in_index"]) == (1, 0)
    [access] = [x for x in lines if x["event"] == "request" and x.get("route") == EXPORT]
    assert access["abstracts_withheld"] == 1
    assert paper.id not in json.dumps(lines) and "NotInThisIndex" not in json.dumps(lines)


def test_a_start_without_the_list_refuses_an_index_whose_snapshot_withheld(
    logs: Logs, data_dir: Path, store: Store
) -> None:
    """The snapshot proves this deployment has takedowns, so a missing list (an unmounted takedowns/) is a
    failed load, never a silent lifting at startup."""
    point_current(data_dir, store[2])
    unlisted(data_dir)
    with TestClient(make_app(data_dir)) as c:
        assert c.get("/api/v1/coverage").status_code == 503
    [failed] = [x for x in logs() if x["event"] == "index_load_failed"]
    assert failed["reason"] == "takedowns_missing"


def test_the_list_is_reread_on_reload_and_a_bad_list_changes_nothing(
    client: TestClient, data_dir: Path, store: Store
) -> None:
    _, _, _, paper, _ = store
    shown = lambda: client.get(f"/api/v1/papers/{paper.id}").json()["abstract_withheld"]  # noqa: E731
    assert shown() is False
    listing(data_dir, paper.id)
    assert shown() is False  # not before a reload (SIGHUP)
    assert reload(client) and shown() is True
    listing(data_dir, text=f"{paper.id}\nnot-an-id\n")
    assert reload(client) is False and shown() is True  # the old list kept; logged index_load_failed
    listing(data_dir)  # emptied: the takedown lifted
    assert reload(client) and shown() is False


def test_a_bad_list_at_startup_serves_nothing(data_dir: Path) -> None:
    listing(data_dir, text="op:iclr:2024:x y\n")
    with TestClient(make_app(data_dir)) as c:
        r = c.get("/api/v1/coverage")
        assert r.status_code == 503 and r.json()["error"]["code"] == "API_INDEX_NOT_LOADED"


# --- op takedown check (AC8) ------------------------------------------------------------------------------------


def fetcher(client: TestClient) -> takedown_check.Fetch:
    def fetch(path: str, params: Mapping[str, str]) -> tuple[int, str]:
        r = client.get(path, params=dict(params))
        return r.status_code, r.text

    return fetch


def test_the_check_passes_when_every_loaded_version_withholds(data_dir: Path, store: Store) -> None:
    _, old, new, paper, _ = store
    listing(data_dir, paper.id)
    point_current(data_dir, new)
    with TestClient(make_app(data_dir)) as c:
        c.get(EXPORT, params={"format": "jsonl", "q": "agents", "index_version": old})  # loads the pinned one
        report = takedown_check.check(fetcher(c), frozenset({paper.id}))
    assert report.problems == ()
    assert set(report.index_versions) == {old, new} and report.exports == 2 * (
        len(FORMATS) + 1
    )  # + its title


def test_the_check_fails_when_the_served_index_serves_a_listed_abstract(
    data_dir: Path, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mutant: serve-time withholding switched off. The old index (served) still holds the abstract."""
    _, old, _, paper, _ = store
    listing(data_dir, paper.id)
    monkeypatch.setattr(Served, "withheld_in", lambda self, records: frozenset())
    with TestClient(make_app(data_dir)) as c:
        report = takedown_check.check(fetcher(c), frozenset({paper.id}))
    problems = "\n".join(report.problems)
    assert f"{paper.id}: /papers on index {old} serves its abstract" in problems
    assert "doesn't mark the abstract withheld" in problems
    assert f"its /search hit on index {old} serves the abstract" in problems
    for fmt in FORMATS:
        assert f"the {fmt} export of index {old} serves its abstract" in problems
    assert paper.abstract is not None and paper.abstract not in problems


def test_the_check_fails_when_only_a_pinned_versions_export_serves_it(
    data_dir: Path, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The new index (served) withheld it in its snapshot; the mutant drops the list, so the old one, loaded
    only as a pin, would hand it out in exports."""
    _, old, new, paper, _ = store
    listing(data_dir, paper.id)
    point_current(data_dir, new)
    real = Served.withheld_in
    monkeypatch.setattr(
        Served,
        "withheld_in",
        lambda self, records: (
            real(self, records) if records is self.records else real(self, records) - self.listed
        ),
    )
    with TestClient(make_app(data_dir)) as c:
        report = takedown_check.check(fetcher(c), frozenset({paper.id}))
    assert sorted(report.problems) == sorted(
        f"{paper.id}: the {fmt} export of index {old} serves its abstract" for fmt in FORMATS
    )


def _check_with(data_dir: Path, store: Store) -> list[str]:
    _, _, _, paper, _ = store
    listing(data_dir, paper.id)
    with TestClient(make_app(data_dir)) as c:
        return sorted(takedown_check.check(fetcher(c), frozenset({paper.id})).problems)


def test_the_check_catches_an_abstract_claim_left_on_the_paper_page(
    data_dir: Path, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, old, _, paper, _ = store
    monkeypatch.setattr(papers_route, "withhold_record", lambda r: r.model_copy(update={"abstract": None}))
    assert _check_with(data_dir, store) == [
        f"{paper.id}: /papers on index {old} serves its abstract or an abstract claim"
    ]


@pytest.mark.parametrize(
    ("leak", "problem"),
    [
        ("abstract_source", "serves the abstract, its spans or its source"),
        ("abstract_withheld", "doesn't mark the abstract withheld"),
    ],
)
def test_the_check_catches_a_hit_that_keeps_its_source_or_loses_its_marker(
    data_dir: Path, store: Store, monkeypatch: pytest.MonkeyPatch, leak: str, problem: str
) -> None:
    _, old, _, paper, _ = store
    real = search_route._hit

    def leaky(found: Any, source: Any, *, withheld: bool, twins: tuple[str, ...]) -> Any:
        hit = real(found, source, withheld=withheld, twins=twins)
        update = {"abstract_source": source} if leak == "abstract_source" else {"abstract_withheld": False}
        return hit.model_copy(update=update) if withheld else hit

    monkeypatch.setattr(search_route, "_hit", leaky)
    assert _check_with(data_dir, store) == [f"{paper.id}: its /search hit on index {old} {problem}"]


def test_the_check_catches_an_export_that_doesnt_say_why(
    data_dir: Path, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The RIS and BibTeX markers are the sentence; CSV and JSONL say it with `abstract_withheld_reason`."""
    _, old, new, paper, _ = store
    monkeypatch.setitem(exporter.SENTENCES, "takedown", "Abstract withheld.")
    assert _check_with(data_dir, store) == sorted(
        f"{paper.id}: the {fmt} export of index {v} doesn't say a takedown withheld it"
        for v in (old, new)
        for fmt in ("bibtex", "ris")
    )


def test_the_check_names_a_listed_id_no_index_holds(client: TestClient) -> None:
    report = takedown_check.check(fetcher(client), frozenset({"op:iclr:2024:NotInAnyIndex"}))
    assert report.problems == (
        "op:iclr:2024:NotInAnyIndex: no index this instance loads holds it; check the id on the list",
    )


def test_op_takedown_check_exits_1_on_a_problem_and_checks_the_log(
    data_dir: Path, store: Store, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, _, _, paper, _ = store
    listing(data_dir, paper.id)
    with TestClient(make_app(data_dir)) as c:
        monkeypatch.setattr(takedown_check, "http", lambda base: fetcher(c))
        argv = ["--data-dir", str(data_dir), "takedown", "check", "--api", "http://127.0.0.1:8000"]
        assert cli.main(argv) == 1  # the log is missing
        out = capsys.readouterr()
        assert out.out == "log.jsonl is missing: log each listed takedown\n"
        log = data_dir / "takedowns" / "log.jsonl"
        log.write_text(json.dumps({
            "record_id": paper.id, "received": "2026-09-30", "requester": "R <r@example.org>", "basis": "copyright",
            "decision": "withheld", "applied": "2026-09-30", "first_index_version": None,
        }) + "\n", encoding="utf-8")  # fmt: skip
        log.chmod(0o600)
        assert cli.main(argv) == 0
        assert "0 problem(s): 1 listed id(s) across 2 index version(s)" in capsys.readouterr().err
        log.chmod(0o644)
        assert cli.main(argv) == 1
        assert "readable by others" in capsys.readouterr().out
        assert cli.main([*argv[:-1], "file:///etc/passwd"]) == 1
        assert "--api must be an http(s) URL" in capsys.readouterr().err


# --- the same paper under another id on an older version (TASK-067) -------------------------------------------

type Aliased = tuple[Path, str, str, PaperRecord, PaperRecord, PaperRecord]  # data, prev, new, paper, old ids


@pytest.fixture(scope="module")
def aliased_store(tmp_path_factory: pytest.TempPathFactory) -> Aliased:
    """`prev` holds the paper as `rekeyed` (the same native id, a year off: the year later corrected) and as
    `dup`, a duplicate record; `new` holds it under its own id, and its merges.csv says `dup` merged into it.
    The list names only the id `new` has."""
    data = tmp_path_factory.mktemp("aliased") / "data"
    papers = [attributed(r) for r in list(records())[:300]]
    paper, _ = _pick(papers)
    _op, venue, year, native = paper.id.split(":", 3)
    rekeyed = paper.model_copy(update={"id": f"op:{venue}:{int(year) - 1}:{native}", "year": int(year) - 1})
    dup = paper.model_copy(update={"id": f"op:{venue}:{year}:Dup{native}"})
    others = [p for p in papers if p.id != paper.id]
    prev = _build([*others, rekeyed, dup], data, "prev", frozenset())
    merge = Merge(paper.id, dup.id, "title_venue_year", "k", venue, int(year), "openreview")
    new = _build(papers, data, "new", frozenset({paper.id}), (merge,))
    (data / "indexes" / "current").symlink_to(new)
    return data, prev, new, paper, rekeyed, dup


@pytest.fixture
def aliased(aliased_store: Aliased, tmp_path: Path) -> Aliased:
    shutil.copytree(aliased_store[0], tmp_path / "data", symlinks=True)
    listing(tmp_path / "data", aliased_store[3].id)
    return (tmp_path / "data", *aliased_store[1:])


def _title(paper: PaperRecord) -> str:
    return f'title:"{" ".join(normalize(paper.title)[:8])}" {EVERY}'


@pytest.mark.parametrize("fmt", FORMATS)
def test_an_older_version_withholds_the_paper_under_its_older_ids(aliased: Aliased, fmt: str) -> None:
    data, prev, _, paper, rekeyed, dup = aliased
    with TestClient(make_app(data)) as c:
        text = exported(c, fmt, q=_title(paper), index_version=prev)
    assert withheld_in_export(fmt, text, rekeyed.id) and withheld_in_export(fmt, text, dup.id)
    assert paper.abstract is not None and paper.abstract.split()[0] not in (text if fmt == "jsonl" else "")


def test_op_export_withholds_the_older_ids_too(aliased: Aliased, capsys: pytest.CaptureFixture[str]) -> None:
    data, prev, _, paper, rekeyed, dup = aliased
    argv = ["--data-dir", str(data), "export", _title(paper), "--index", prev, "--format", "jsonl"]
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    assert withheld_in_export("jsonl", out, rekeyed.id) and withheld_in_export("jsonl", out, dup.id)


def test_the_check_catches_an_older_id_left_served(aliased: Aliased, monkeypatch: pytest.MonkeyPatch) -> None:
    """The mutant: withholding by the listed id only (as before TASK-067)."""
    data, prev, _, paper, rekeyed, dup = aliased
    with TestClient(make_app(data)) as c:
        c.get(EXPORT, params={"format": "jsonl", "q": "agents", "index_version": prev})
        assert takedown_check.check(fetcher(c), frozenset({paper.id})).problems == ()
    monkeypatch.setattr(
        takedowns, "same_paper", lambda listed, merges, ids, twins=(): listed & frozenset(ids)
    )
    with TestClient(make_app(data)) as c:
        problems = takedown_check.check(fetcher(c), frozenset({paper.id})).problems
    assert sorted(problems) == sorted(
        f"{rid}: the jsonl export of index {prev} serves the abstract of {paper.id}'s paper under this id; "
        "list it too"
        for rid in (rekeyed.id, dup.id)
    )


# --- a missing list fails closed (TASK-067) ----------------------------------------------------------------------


def test_a_rolled_back_index_without_the_list_serves_nothing(logs: Logs, data_dir: Path) -> None:
    """`current` names `old`, from before the takedown, but `new`'s snapshot on disk withheld an abstract: the
    deployment has takedowns, so a missing list fails the start (it would serve the listed abstract)."""
    unlisted(data_dir)
    with TestClient(make_app(data_dir)) as c:
        assert c.get("/api/v1/coverage").status_code == 503
    [failed] = [x for x in logs() if x["event"] == "index_load_failed"]
    assert failed["reason"] == "takedowns_missing"


def test_a_required_list_that_is_missing_serves_nothing(logs: Logs, data_dir: Path) -> None:
    """No snapshot withheld anything yet, and no list: with the list required (`op serve` off loopback), the
    start fails rather than serving every abstract a list SIGHUP'd in before the rebuild would withhold; an
    empty list serves."""
    shutil.rmtree(data_dir / "snapshots" / "new")
    unlisted(data_dir)
    with TestClient(make_app(data_dir)) as c:
        assert c.get("/api/v1/coverage").status_code == 200  # not required: a local instance
    with TestClient(make_app(data_dir, takedown_list_required=True)) as c:
        assert c.get("/api/v1/coverage").status_code == 503
    [failed] = [x for x in logs() if x["event"] == "index_load_failed"]
    assert failed["reason"] == "takedowns_missing"
    listing(data_dir)
    with TestClient(make_app(data_dir, takedown_list_required=True)) as c:
        assert c.get("/api/v1/coverage").status_code == 200


@pytest.mark.parametrize(
    ("host", "required"), [("127.0.0.1", False), ("0.0.0.0", True), ("example.org", True)]
)
def test_op_serve_requires_the_list_off_loopback(
    host: str, required: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    served: list[Any] = []
    monkeypatch.setattr(api_server, "serve", lambda config, *a: served.append(config))
    assert cli.main(["--data-dir", str(tmp_path), "serve", "--host", host]) == 0
    assert served[0].takedown_list_required is required


def test_op_takedown_check_refuses_a_missing_list(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """TASK-067: a missing list is never "nothing to check" (an OP_DATA_DIR pointing elsewhere, a renamed file)."""
    monkeypatch.setattr(takedown_check, "http", lambda base: fetcher(client))
    unlisted(data_dir)
    argv = ["--data-dir", str(data_dir), "takedown", "check", "--api", "http://127.0.0.1:8000"]
    assert cli.main(argv) == 1
    assert "withheld.txt is missing" in capsys.readouterr().err


def test_no_response_may_be_stored_by_a_cache(client: TestClient, store: Store) -> None:
    """TASK-067: a proxy or CDN in front of the API could keep serving an abstract after the SIGHUP that
    withholds it; every answer, errors included, says `no-store`."""
    _, _, _, paper, word = store
    for path, params in [
        (f"/api/v1/papers/{paper.id}", {}),
        ("/api/v1/search", {"q": f"abstract:{word}"}),
        (EXPORT, {"format": "ris", "q": f"abstract:{word}"}),
        ("/api/v1/coverage", {}),
        ("/api/v1/papers/op:iclr:2024:NotHere1", {}),
        ("/api/v1/nowhere", {}),
    ]:
        assert client.get(path, params=params).headers["cache-control"] == "no-store", path


def test_coverage_counts_a_listed_paper_held_under_other_ids(logs: Logs, aliased: Aliased) -> None:
    """`prev` holds the listed paper twice, under its pre-rekey id and as a duplicate: both are withheld, so
    both are counted withheld, and the load line counts them followed (TASK-067 review)."""
    data, prev, *_ = aliased
    point_current(data, prev)
    with TestClient(make_app(data)) as c:
        totals = c.get("/api/v1/coverage").json()["totals"]
    assert totals["abstract_withheld"] == 2
    [loaded] = [x for x in logs() if x["event"] == "index_loaded"]
    assert (loaded["takedowns_followed"], loaded["takedowns_not_in_index"]) == (2, 1)


def test_a_damaged_merges_file_never_stops_the_list(logs: Logs, aliased: Aliased) -> None:
    """One old snapshot whose merges.csv doesn't match its manifest: the load still applies the list (the
    listed id, and its native-id rekey) without any merges, and says so once, naming the snapshot."""
    data, prev, _, paper, rekeyed, dup = aliased
    merges = data / "snapshots" / "new" / "merges.csv"
    merges.chmod(0o644)
    merges.write_text(merges.read_text(encoding="utf-8") + "x,y,z\n", encoding="utf-8")
    with TestClient(make_app(data)) as c:
        assert c.get(f"/api/v1/papers/{paper.id}").json()["abstract_withheld"] is True
        text = exported(c, "jsonl", q=_title(paper), index_version=prev)
    assert withheld_in_export("jsonl", text, rekeyed.id)  # the native id still links
    assert not withheld_in_export("jsonl", text, dup.id)  # the merge is what was lost
    [line] = [x for x in logs() if x["event"] == "takedown_merges_unavailable"]
    assert (line["snapshot"], line["reason"], line["level"]) == ("new", "merges_mismatch", "ERROR")


def test_a_pinned_export_waiting_past_the_bound_is_busy(logs: Logs, data_dir: Path, store: Store) -> None:
    """TASK-067 review: the bounded wait covers the pinned snapshot's verification (`pinned_records`) as well
    as the engine's open, over HTTP: 503 API_BUSY with Retry-After, never a queue."""
    _, old, new, _, word = store
    point_current(data_dir, new)
    with TestClient(make_app(data_dir, pinned_open_wait_seconds=0.05, busy_retry_seconds=3)) as c:
        state: IndexState = c.app.state.index  # type: ignore[attr-defined]
        assert state.pinned(old).reason == "ok"  # the engine is cached: only the records must wait
        assert state._open_slot.acquire(timeout=5)
        try:
            r = c.get(EXPORT, params={"format": "jsonl", "q": f"abstract:{word}", "index_version": old})
        finally:
            state._open_slot.release()
        assert r.status_code == 503 and r.json()["error"]["code"] == "API_BUSY"
        assert r.headers["retry-after"] == "3" and r.headers["cache-control"] == "no-store"
        [line] = [x for x in logs() if x["event"] == "request" and x.get("code") == "API_BUSY"]
        assert line["busy"] == "pinned_open"  # told apart from a full verification slot
        r = c.get(EXPORT, params={"format": "jsonl", "q": f"abstract:{word}", "index_version": old})
        assert r.status_code == 200  # not remembered


def test_op_serve_behind_a_trusted_proxy_requires_the_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """On loopback but with a trusted proxy, clients reach it through that proxy: a public instance."""
    served: list[Any] = []
    monkeypatch.setattr(api_server, "serve", lambda config, *a: served.append(config))
    assert cli.main(["--data-dir", str(tmp_path), "serve", "--trusted-proxy", "127.0.0.1"]) == 0
    assert served[0].takedown_list_required is True


def test_op_export_refuses_a_missing_list_once_a_snapshot_withheld(
    data_dir: Path, store: Store, capsys: pytest.CaptureFixture[str]
) -> None:
    """`new`'s snapshot withheld an abstract; with the list gone, exporting `old` (from before the takedown)
    would hand the listed abstract out, so op export refuses as the API does (TASK-067 review)."""
    _, old, _, _, word = store
    unlisted(data_dir)
    argv = ["--data-dir", str(data_dir), "export", f"abstract:{word}", "--index", old, "--format", "jsonl"]
    assert cli.main(argv) == 1
    assert "withheld.txt is missing" in capsys.readouterr().err


def test_a_damaged_snapshot_drops_only_its_own_merges(logs: Logs, aliased: Aliased) -> None:
    """Another snapshot's merges.csv is damaged: `new`'s merge is still followed (TASK-067 review round 2)."""
    data, prev, _, paper, _, dup = aliased
    other = data / "snapshots" / "aaa-other"  # sorts before `new`: a skip, never a stop (round 3)
    shutil.copytree(data / "snapshots" / "new", other)
    (other / "merges.csv").chmod(0o644)
    (other / "merges.csv").write_text("survivor_id,merged_id\nx,y\n", encoding="utf-8")
    with TestClient(make_app(data)) as c:
        text = exported(c, "jsonl", q=_title(paper), index_version=prev)
    assert withheld_in_export("jsonl", text, dup.id)
    [line] = [x for x in logs() if x["event"] == "takedown_merges_unavailable"]
    assert (line["snapshot"], line["error"]) == ("aaa-other", "SnapshotError")


def test_op_export_applies_the_list_without_a_damaged_snapshots_merges(
    aliased: Aliased, capsys: pytest.CaptureFixture[str]
) -> None:
    data, prev, _, paper, rekeyed, dup = aliased
    merges = data / "snapshots" / "new" / "merges.csv"
    merges.chmod(0o644)
    merges.write_text(merges.read_text(encoding="utf-8") + "x,y,z\n", encoding="utf-8")
    argv = ["--data-dir", str(data), "export", _title(paper), "--index", prev, "--format", "jsonl"]
    assert cli.main(argv) == 0
    out = capsys.readouterr()
    assert withheld_in_export("jsonl", out.out, rekeyed.id) and not withheld_in_export(
        "jsonl", out.out, dup.id
    )
    assert "the takedown list applies without new's merges" in out.err


def test_op_takedown_check_reports_a_damaged_merges_file_and_a_suspect_merge(
    aliased: Aliased, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Through the CLI (TASK-067 review round 2): a damaged merges.csv is a problem of its own, and a merge to a
    paper the served index holds under another title is a suspect merge."""
    data, _, _, paper, _, _ = aliased
    log = data / "takedowns" / "log.jsonl"
    log.write_text(json.dumps({
        "record_id": paper.id, "received": "2026-09-30", "requester": "R", "basis": "b",
        "decision": "withheld", "applied": None, "first_index_version": None,
    }) + "\n", encoding="utf-8")  # fmt: skip
    log.chmod(0o600)
    argv = ["--data-dir", str(data), "takedown", "check", "--api", "http://127.0.0.1:8000"]
    with TestClient(make_app(data)) as c:
        monkeypatch.setattr(takedown_check, "http", lambda base: fetcher(c))
        assert cli.main(argv) == 0, capsys.readouterr().out  # the fixture's own merge: the same title
        stranger = next(
            p.id for p in [attributed(r) for r in list(records())[:300]] if p.title != paper.title
        )
        monkeypatch.setattr(
            snapshot_module, "merges_on_disk", lambda snapshots, on_damaged=None: ((paper.id, stranger),)
        )
        capsys.readouterr()
        assert cli.main(argv) == 1
        assert f"{stranger}: withheld as {paper.id}'s paper" in capsys.readouterr().out
        monkeypatch.undo()
        monkeypatch.setattr(takedown_check, "http", lambda base: fetcher(c))
        merges = data / "snapshots" / "new" / "merges.csv"
        merges.chmod(0o644)
        merges.write_text(merges.read_text(encoding="utf-8") + "x,y,z\n", encoding="utf-8")
        assert cli.main(argv) == 1
        assert "the API applies the list without new's merges" in capsys.readouterr().out


def test_the_reload_lines_count_the_ids_followed(logs: Logs, aliased: Aliased) -> None:
    """`takedowns_reloaded` counts followed ids on both paths: the same index with a new list, and a failed
    promotion that still applies the new list (TASK-067 review round 3)."""
    data, prev, _, paper, _, _ = aliased
    point_current(data, prev)
    listing(data)
    with TestClient(make_app(data)) as client:
        listing(data, paper.id)
        assert reload(client)  # the same index, another list
        listing(data, "op:iclr:2024:NotInThisIndex")  # the paper lifted: nothing followed any more
        current = data / "indexes" / "current"
        current.unlink()
        current.symlink_to("does-not-exist")
        assert reload(client) is False  # the promotion fails; the new list still applies
    lines = [x for x in logs() if x["event"] == "takedowns_reloaded"]
    assert [x["takedowns_followed"] for x in lines] == [2, 0]  # the new bundle's count, not the old one's
