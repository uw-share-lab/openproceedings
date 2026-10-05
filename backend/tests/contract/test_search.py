"""`GET /api/v1/search` (task-035; spec 04 §SearchResponse): the shape, `op search`'s answer for the same
index, `total` independent of paging, `excluded` always present and pinned, disjunctive facets
(decision-001) against ReferenceEngine, expansions, code-point highlights (the golden astral-plane title),
and every refusal in the one envelope."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient
from openproceedings import cli
from openproceedings.api.models import MAX_LIMIT, Sort
from openproceedings.engine.exclusions import excluded
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import SORTS, TantivyEngine
from openproceedings.query import QUERY_VERSION
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import parse

from tests.contract.conftest import Store
from tests.fixtures.corpus.synthetic_5k import records
from tests.golden.test_tantivy_200 import as_paper

SEARCH = "/api/v1/search"
QUERIES = [
    "trust",
    "trust AND calibrat*",
    '"language model" OR benchmark*',
    "trust track:workshop",  # the user's own track set: only status is a default
    "trust track:workshop status:rejected",  # no defaults: nothing excluded
    "(trust AND track:workshop) OR calibration",  # nested: the default still applies (WARN_NESTED_FILTER)
    "trust NOT venue:ICLR year:2020..2023",
    "agents NEAR/3 reliance",
]
HIT_KEYS = {
    "id", "title", "abstract", "authors", "venue", "year", "track", "status", "presentation", "score",
    "highlights", "urls", "abstract_source", "abstract_withheld", "twins",
}  # fmt: skip


@pytest.fixture(scope="module")
def reference() -> ReferenceEngine:
    """The oracle over the same 5k corpus, with the index's ids."""

    class Rec:
        def __init__(self, r: Any) -> None:
            p = as_paper(r)
            self.id, self.title, self.abstract = p.id, p.title, p.abstract
            self.venue, self.year, self.track, self.status = p.venue, p.year, p.track, p.status

    return ReferenceEngine([Rec(r) for r in records()])


def engine_of(client: TestClient) -> TantivyEngine:
    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    assert engine is not None
    return engine  # type: ignore[no-any-return]


def ok(client: TestClient, q: str, **params: Any) -> dict[str, Any]:
    r = client.get(SEARCH, params={"q": q, **params})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def pages(
    client: TestClient, q: str, sort: str = "relevance", limit: int = MAX_LIMIT
) -> Iterator[dict[str, Any]]:
    offset = 0
    while True:
        body = ok(client, q, sort=sort, offset=offset, limit=limit)
        yield body
        offset += limit
        if offset >= body["total"]:
            return


# --- AC1: the shape -------------------------------------------------------------------------------------
def test_the_response_has_every_field_of_spec_04(client: TestClient, store: Store) -> None:
    body = ok(client, "trust AND calibrat*")
    assert set(body) == {
        "query", "index_version", "tokenizer_version", "query_version", "total", "excluded", "facets", "hits",
        "identified_total", "unclassified_total", "groups",
    }  # fmt: skip
    assert (body["index_version"], body["tokenizer_version"], body["query_version"]) == (
        store.big,
        TOKENIZER_VERSION,
        QUERY_VERSION,
    )
    result = parse("trust AND calibrat*")
    assert body["query"] == {
        "input": "trust AND calibrat*",
        "canonical": result.canonical,
        "canonical_hash": result.canonical_hash,
        "identification_query": result.identification_query,
        "warnings": [],
        "translations": [],
        "expansions": {"calibrat*": list(engine_of(client).expand(result.ast.children[1]))},  # type: ignore[union-attr]
    }
    assert set(body["facets"]) == {"venue", "year", "track", "status"}
    assert body["hits"] and all(set(h) == HIT_KEYS for h in body["hits"])
    assert all(set(h["highlights"]) == {"title", "abstract"} for h in body["hits"])
    assert all(set(h["urls"]) == {"forum", "pdf", "proceedings", "doi"} for h in body["hits"])


def test_warnings_and_translations_come_back_with_spans(client: TestClient) -> None:
    body = ok(client, "trust or calibration")
    assert [(w["code"], w["span"]) for w in body["query"]["warnings"]] == [
        ("WARN_LOWERCASE_OPERATOR", [6, 8])
    ]
    scholar = ok(client, "trust source:ICLR", mode="scholar")["query"]
    assert scholar == {
        **scholar,
        "translations": parse("trust source:ICLR", "scholar").model_dump(mode="json")["translations"],
    }
    alias = [t for t in scholar["translations"] if t["code"] == "COMPAT_SOURCE_ALIAS"]
    assert [t["span"] for t in alias] == [[13, 17]]


# --- the API adds transport, not behaviour -----------------------------------------------------------------
@pytest.mark.parametrize("q", QUERIES)
def test_the_match_set_and_ranking_equal_op_search(
    client: TestClient, store: Store, q: str, capsys: pytest.CaptureFixture[str]
) -> None:
    data = str(store.indexes.parent)
    assert cli.main(["--data-dir", data, "search", q, "--ids"]) == 0
    expected = capsys.readouterr().out.split()
    ids = [h["id"] for body in pages(client, q) for h in body["hits"]]
    assert sorted(ids) == expected and len(ids) == len(set(ids))


def cli_report(out: str) -> dict[str, Any]:
    """`op search`'s PRISMA header and ranked lines, read back: identified, the default-filter buckets,
    screened, and each hit's (id, score)."""
    lines = out.splitlines()
    one = {
        k: next(line for line in lines if line.startswith(k))
        for k in ("identified ", "removed by ", "screened ")
    }
    removed = re.fullmatch(
        r"removed by default filters (\d+): ineligible \d+ \(track: (.*); status: (.*)\), "
        r"unclassified (\d+) \(track unknown (\d+), status unknown (\d+)\)",
        one["removed by "],
    )
    assert removed is not None, one["removed by "]

    def buckets(text: str, unknown: str) -> dict[str, int]:
        named = {} if text == "none" else {v: int(n) for v, n in (b.rsplit(" ", 1) for b in text.split(", "))}
        return {**named, "unknown": int(unknown)}

    return {
        "identified": int(one["identified "].split()[1]),
        "excluded": {
            "total": int(removed.group(1)),
            "track": buckets(removed.group(2), removed.group(5)),
            "status": buckets(removed.group(3), removed.group(6)),
        },
        "unclassified": int(removed.group(4)),
        "total": int(one["screened "].split()[2]),
        "hits": [
            (line.split()[2], float(line.split()[1]))
            for line in lines
            if line[:5].strip().rstrip(".").isdigit()
        ],
    }


@pytest.mark.parametrize("sort", get_args(Sort))
@pytest.mark.parametrize("q", QUERIES)
def test_the_counts_and_the_ranked_page_equal_op_search(
    client: TestClient, store: Store, q: str, sort: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Spec 04 as built: the ids, order, `total` and `excluded` equal `op search`'s, for every sort."""
    assert (
        cli.main(["--data-dir", str(store.indexes.parent), "search", q, "--sort", sort, "--limit", "20"]) == 0
    )
    report = cli_report(capsys.readouterr().out)
    body = ok(client, q, sort=sort, limit=20)
    assert body["total"] == report["total"]
    assert body["excluded"] == report["excluded"]
    assert list(body["excluded"]["track"]) == list(report["excluded"]["track"])  # the same bucket order
    assert report["identified"] == body["total"] + body["excluded"]["total"]
    # TASK-090: the API sends the CLI's two derived counts, so no client adds numbers
    assert body["identified_total"] == report["identified"]
    assert body["unclassified_total"] == report["unclassified"]
    assert [h["id"] for h in body["hits"]] == [i for i, _s in report["hits"]]
    assert [round(h["score"], 4) for h in body["hits"]] == [s for _i, s in report["hits"]]


@pytest.mark.parametrize("sort", get_args(Sort))
def test_total_is_independent_of_sort_offset_and_limit(client: TestClient, sort: str) -> None:
    q = "trust OR model"
    expected = engine_of(client).match_ids(parse(q).effective_ast)  # type: ignore[arg-type]
    totals = {
        ok(client, q, sort=sort, offset=o, limit=n)["total"]
        for o, n in ((0, 0), (0, 7), (13, 200), (10**6, 5))
    }
    assert totals == {len(expected)}
    seen = [h["id"] for body in pages(client, q, sort=sort, limit=37) for h in body["hits"]]
    assert len(seen) == len(set(seen)) and set(seen) == expected  # pages are stable and cover the set
    assert ok(client, q, sort=sort, offset=10**6)["hits"] == []


def test_the_sorts_are_the_engines() -> None:
    assert get_args(Sort) == SORTS


# --- excluded -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("q", QUERIES)
def test_excluded_matches_the_oracle_in_the_pinned_shape(
    client: TestClient, reference: ReferenceEngine, q: str
) -> None:
    body = ok(client, q, limit=0)
    result = parse(q)
    oracle = excluded(reference, result, len(reference.match_ids(result.effective_ast)))  # type: ignore[arg-type]
    got = body["excluded"]
    assert got == oracle.to_json()
    for field in ("track", "status"):
        buckets = list(got[field].items())
        assert buckets[-1][0] == "unknown"  # always present, always last
        named = buckets[:-1]
        assert named == sorted(named, key=lambda kv: (-kv[1], kv[0]))  # by count, then name
    assert got["total"] == sum(got["track"].values()) + sum(got["status"].values())


def test_excluded_is_present_even_when_nothing_was_removed(client: TestClient) -> None:
    body = ok(client, "trust track:workshop status:rejected")
    assert body["excluded"] == {"total": 0, "track": {"unknown": 0}, "status": {"unknown": 0}}


# --- AC4: disjunctive facets (decision-001) ---------------------------------------------------------------
@pytest.mark.parametrize("q", QUERIES)
def test_facets_equal_the_oracles(client: TestClient, reference: ReferenceEngine, q: str) -> None:
    assert ok(client, q, limit=0)["facets"] == reference.facets(parse(q).effective_ast)  # type: ignore[arg-type]


def test_a_facet_drops_only_its_own_top_level_conjuncts(
    client: TestClient, reference: ReferenceEngine
) -> None:
    """`track:workshop` at the top level is dropped from the track facet; nested under OR it stays applied
    (only the top-level default is dropped). Counted by brute force over the oracle's match sets."""

    def by_track(q: str) -> dict[str, int]:
        ids = reference.match_ids(parse(q).effective_ast)  # type: ignore[arg-type]
        counts: dict[str, int] = {}
        for d in reference.docs:
            if d.id in ids:
                counts[d.track] = counts.get(d.track, 0) + 1
        return dict(sorted(counts.items()))

    every_track = "track:(" + " OR ".join(sorted({r.track for r in records()})) + ")"
    top = ok(client, "trust track:workshop", limit=0)["facets"]["track"]
    assert top == by_track(f"trust {every_track}")  # the workshop clause dropped: every track counted
    assert top["main"] > 0  # so the UI can offer "main" beside workshop
    nested = ok(client, "(trust AND track:workshop) OR calibration", limit=0)["facets"]["track"]
    assert nested == by_track(f"((trust AND track:workshop) OR calibration) {every_track}")
    dropped = by_track(f"(trust OR calibration) {every_track}")
    assert nested != dropped  # had the nested filter been dropped too, these would be equal
    status = ok(client, "trust track:workshop", limit=0)["facets"]["status"]
    workshop_only = by_track(
        "trust track:workshop status:(" + " OR ".join(sorted({r.status for r in records()})) + ")"
    )
    assert sum(status.values()) == workshop_only["workshop"]  # the status facet keeps the track clause


# --- expansions and highlights ------------------------------------------------------------------------------
def test_every_expansion_is_listed_in_full(client: TestClient) -> None:
    q = "benchmark* OR calibrat* OR agent*"
    body = ok(client, q, limit=1)
    engine = engine_of(client)
    expected = {f"{s}{o}": list(t) for (s, o), t in engine.expansions(parse(q).effective_ast).items()}  # type: ignore[arg-type]
    assert body["query"]["expansions"] == expected
    assert set(expected) == {"benchmark*", "calibrat*", "agent*"} and all(expected.values())


def test_highlights_are_code_point_spans_over_the_stored_text(client: TestClient) -> None:
    body = ok(client, "trust OR calibration", limit=MAX_LIMIT)
    lit = 0
    for hit in body["hits"]:
        for field in ("title", "abstract"):
            text = hit[field] or ""
            for start, end in hit["highlights"][field]:
                assert 0 <= start < end <= len(text)
                assert unicodedata.normalize("NFKC", text[start:end]).casefold() in {"trust", "calibration"}
                lit += 1
    assert lit >= len(body["hits"])  # every hit lights at least one span


def test_golden_a_title_with_astral_plane_characters(client: TestClient) -> None:
    """fx:0525's title is `langonedo modeling 4o 4o 𝔸I a trustworthy`: `𝔸` is one code point (two UTF-16
    units), so every span after it is one less than a UTF-16 index would be. Pinned literally."""
    (hit,) = ok(client, "title:(ai AND trustworthy) track:blogpost modeling")["hits"]
    assert hit["title"] == "langonedo modeling 4o 4o 𝔸I a trustworthy"
    assert hit["highlights"]["title"] == [[10, 18], [25, 27], [30, 41]]
    assert [hit["title"][s:e] for s, e in hit["highlights"]["title"]] == ["modeling", "𝔸I", "trustworthy"]
    utf16 = hit["title"].encode("utf-16-le")
    assert utf16[31 * 2 : 42 * 2].decode("utf-16-le") == "trustworthy"  # what the frontend converts to


# --- refusals, in the one envelope --------------------------------------------------------------------------
def error(r: Any, status: int, code: str) -> dict[str, Any]:
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return body["error"]  # type: ignore[no-any-return]


def test_a_query_that_does_not_parse_is_a_422_with_code_point_spans(client: TestClient) -> None:
    e = error(client.get(SEARCH, params={"q": "𝔸I (trust"}), 422, "PARSE_UNBALANCED_PAREN")
    assert [(d["code"], d["span"]) for d in e["diagnostics"]] == [("PARSE_UNBALANCED_PAREN", [3, 4])]
    e = error(client.get(SEARCH, params={"q": "trust track:nope"}), 422, "FIELD_UNKNOWN_VALUE")
    assert e["diagnostics"][0]["span"] == [12, 16]  # the value


@pytest.mark.parametrize(
    "params",
    [
        {"limit": MAX_LIMIT + 1},  # never clamped
        {"limit": -1},
        {"offset": -1},
        {"sort": "semantic"},
        {"mode": "wos"},
    ],
)
def test_bad_parameters_are_422_api_bad_param(client: TestClient, params: dict[str, Any]) -> None:
    error(client.get(SEARCH, params={"q": "trust", **params}), 422, "API_BAD_PARAM")


def test_limit_200_is_served_in_full(client: TestClient) -> None:
    body = ok(client, "trust OR model OR agents", limit=MAX_LIMIT)
    assert body["total"] > MAX_LIMIT and len(body["hits"]) == MAX_LIMIT


def test_an_over_cap_wildcard_is_refused_with_its_own_code(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    import openproceedings.engine.tantivy_engine as te

    from tests.contract.conftest import make_app

    monkeypatch.setattr(te, "MAX_EXPANSIONS", 1)  # calibrat* has 2, trust has none
    with TestClient(make_app(store.indexes.parent)) as c:
        e = error(
            c.get(SEARCH, params={"q": "𝔸I trust calibrat* OR (x AND calibrat*)"}),
            422,
            "WILDCARD_TOO_MANY_EXPANSIONS",
        )
    # every over-cap wildcard, located by code point in q (spec 04 row 1: the diagnostics carry the spans)
    assert [(d["code"], d["span"]) for d in e["diagnostics"]] == [
        ("WILDCARD_TOO_MANY_EXPANSIONS", [9, 18]),
        ("WILDCARD_TOO_MANY_EXPANSIONS", [29, 38]),
    ]


def test_a_hit_shows_its_status(client: TestClient) -> None:
    """Coordinator decision (task-035 review): a hit carries `status`, so an included rejected paper says so."""
    rejected = ok(client, "trust status:rejected", limit=MAX_LIMIT)["hits"]
    assert rejected and {h["status"] for h in rejected} == {"rejected"}
    assert {h["status"] for h in ok(client, "trust", limit=MAX_LIMIT)["hits"]} == {"accepted"}


@pytest.mark.parametrize(
    ("q", "title", "spans"),
    [
        # `ﬁ` (one code point) is `fi` (two) after NFKC: spans after it stay over the raw title
        ("ﬁne-tuning trust", "ﬁne-tuning 𝐓rust agents", [[0, 10], [11, 16]]),
        # LaTeX before a match: `α` lights the command name `alpha` (no backslash), `trust` is over the raw text
        ("α trust", "$\\alpha$-divergence trust", [[2, 7], [20, 25]]),
    ],
)
def test_golden_highlights_after_length_changing_text_are_over_the_raw_title(
    store: Store, tmp_path: Any, q: str, title: str, spans: list[list[int]]
) -> None:
    """An API-level golden: NFKC and LaTeX change lengths, highlights never move (spec 04 §Span units)."""
    from tests.contract.conftest import build, make_app, point_current
    from tests.corpus import Rec

    version = build([Rec(id="fx:0001", title=title, abstract=None)], tmp_path / "data" / "snapshots", "one",
                    tmp_path / "data" / "indexes")  # fmt: skip
    point_current(tmp_path / "data", version)
    with TestClient(make_app(tmp_path / "data")) as c:
        (hit,) = ok(c, f"title:({q.replace(' ', ' AND ')})")["hits"]
    assert hit["title"] == title
    assert hit["highlights"]["title"] == spans


def test_op_search_logs_an_over_cap_wildcard_as_engine_input_error(
    store: Store, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Locating the refused wildcard (for the API's diagnostics) keeps the logged type stable (spec 08)."""
    import json

    import openproceedings.engine.tantivy_engine as te

    monkeypatch.setattr(te, "MAX_EXPANSIONS", 1)
    argv = ["--data-dir", str(store.indexes.parent), "--log-level", "DEBUG", "search", "calibrat*"]
    assert cli.main(argv) == 1
    err = capsys.readouterr().err
    refused = [
        json.loads(line) for line in err.splitlines() if line.startswith("{") and "cli_refused" in line
    ]
    assert [(r["error"], r["code"]) for r in refused] == [
        ("EngineInputError", "WILDCARD_TOO_MANY_EXPANSIONS")
    ]
