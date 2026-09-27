"""`GET /api/v1/papers/{id}?q=` (task-087; spec 04 §Endpoints): the paper page's highlights. The spans are the
ones `/search` gives the same paper as a hit for the same query and index (checked hit by hit over every
Trust-Evals protocol string on the 5k fixture); a paper the query doesn't match is `matched: false` with empty
highlights; without `q` both are null. `q` is admitted exactly as `/search` admits it: every refusal in the one
envelope with its diagnostics, the verified-clause cap and charge, the candidate ceiling, and no query text in
the access line."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings import search
from openproceedings.api import RateLimit
from openproceedings.query.parser import MAX_QUERY_LENGTH, parse

from tests.contract.conftest import SECRET, Store, make_app
from tests.contract.test_abuse_limits import error
from tests.contract.test_abuse_limits_r2 import SLOT_FREE, clause, many_verified
from tests.contract.test_abuse_limits_r3 import TWO, candidates, never
from tests.contract.test_parse_papers_meta import Logs
from tests.golden.test_trust_evals import STRINGS

SEARCH = "/api/v1/search"
NATIVE = [
    "trust",
    "trust AND calibrat*",
    '"language model" OR benchmark*',
    "agents NEAR/3 reliance",
    '"trust calibrat*"',  # position-verified
    "title:(ai AND trustworthy) track:blogpost modeling",
]
NOT_HITS = 5  # papers outside the matched set checked per query


def paper(client: TestClient, pid: str, **params: Any) -> dict[str, Any]:
    r = client.get(f"/api/v1/papers/{pid}", params=params)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def hits(client: TestClient, q: str, mode: str) -> tuple[list[dict[str, Any]], int]:
    r = client.get(SEARCH, params={"q": q, "mode": mode, "limit": 200})
    assert r.status_code == 200, r.text
    return r.json()["hits"], r.json()["total"]


def engine_ids(client: TestClient, q: str, mode: str) -> tuple[frozenset[str], list[str]]:
    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    ast = parse(q, mode).effective_ast  # type: ignore[arg-type]
    return engine.match_ids(ast), sorted(engine.ids)


def same_as_search(client: TestClient, q: str, mode: str) -> int:
    """Every hit of `/search`'s first page has the same highlights on its paper page; a few papers outside the
    matched set are `matched: false` with nothing lit. Returns how many hits were compared."""
    page, total = hits(client, q, mode)
    for hit in page:
        body = paper(client, hit["id"], q=q, mode=mode)
        assert body["matched"] is True, (q, hit["id"])
        assert body["highlights"] == hit["highlights"], (q, hit["id"])
        assert body["paper"]["title"] == hit["title"] and body["paper"]["abstract"] == hit["abstract"]
    matched, every = engine_ids(client, q, mode)
    assert len(matched) == total
    for pid in [i for i in every if i not in matched][:NOT_HITS]:
        body = paper(client, pid, q=q, mode=mode)
        assert (body["matched"], body["highlights"]) == (False, {"title": [], "abstract": []}), (q, pid)
    return len(page)


@pytest.mark.parametrize("name", list(STRINGS))
def test_highlights_equal_search_for_every_trust_evals_string(client: TestClient, name: str) -> None:
    same_as_search(client, STRINGS[name], "scholar")


def test_the_trust_evals_comparison_is_not_vacuous(client: TestClient) -> None:
    compared = sum(len(hits(client, q, "scholar")[0]) for q in STRINGS.values())
    assert compared >= 50  # the fixture has hits for the protocol strings, so the equality above bites


@pytest.mark.parametrize("q", NATIVE)
def test_highlights_equal_search_for_native_queries(client: TestClient, q: str) -> None:
    assert same_as_search(client, q, "native") > 0


def test_without_q_matched_and_highlights_are_null(client: TestClient) -> None:
    hit = hits(client, "trust", "native")[0][0]
    body = paper(client, hit["id"])
    assert set(body) == {
        "index_version",
        "tokenizer_version",
        "query_version",
        "paper",
        "matched",
        "highlights",
    }
    assert (body["matched"], body["highlights"]) == (None, None)
    assert paper(client, hit["id"], mode="native")["highlights"] is None  # the declared default: accepted


def test_golden_an_astral_plane_title_in_code_points(client: TestClient) -> None:
    """fx:0525's title, `langonedo modeling 4o 4o 𝔸I a trustworthy`: spans after `𝔸` are code points (one
    less than UTF-16 indices), as `/search`'s golden pins them."""
    q = "title:(ai AND trustworthy) track:blogpost modeling"
    (hit,) = hits(client, q, "native")[0]
    body = paper(client, hit["id"], q=q)
    assert body["paper"]["title"] == "langonedo modeling 4o 4o 𝔸I a trustworthy"
    assert body["highlights"]["title"] == [[10, 18], [25, 27], [30, 41]]
    assert [body["paper"]["title"][s:e] for s, e in body["highlights"]["title"]] == [
        "modeling",
        "𝔸I",
        "trustworthy",
    ]


def test_a_paper_the_default_filters_remove_is_not_matched(client: TestClient) -> None:
    """Matching is the effective query's, defaults included, as `/search`'s `total` counts it: a workshop
    paper whose text matches `trust` is not matched by `trust` (the default `track:main` removes it)."""
    (hit, *_), _total = hits(client, "trust track:workshop", "native")
    body = paper(client, hit["id"], q="trust")
    assert (body["matched"], body["highlights"]) == (False, {"title": [], "abstract": []})
    assert paper(client, hit["id"], q="trust track:workshop")["highlights"] == hit["highlights"]


def test_a_filter_only_query_matches_and_lights_nothing(client: TestClient) -> None:
    (hit, *_), _total = hits(client, "venue:ICLR", "native")
    body = paper(client, hit["id"], q="venue:ICLR")
    assert (body["matched"], body["highlights"]) == (True, {"title": [], "abstract": []})


# --- refusals: /search's, in the one envelope -------------------------------------------------------------
def some_paper(client: TestClient) -> str:
    return str(hits(client, "trust", "native")[0][0]["id"])


def test_a_query_that_does_not_parse_is_a_422_with_code_point_spans(client: TestClient) -> None:
    pid = some_paper(client)
    e = error(client.get(f"/api/v1/papers/{pid}", params={"q": "𝔸I (trust"}), 422, "PARSE_UNBALANCED_PAREN")
    assert [(d["code"], d["span"]) for d in e["diagnostics"]] == [("PARSE_UNBALANCED_PAREN", [3, 4])]
    e = error(
        client.get(f"/api/v1/papers/{pid}", params={"q": "trust track:nope"}), 422, "FIELD_UNKNOWN_VALUE"
    )
    assert e["diagnostics"][0]["span"] == [12, 16]


def test_an_over_long_query_is_parse_too_long(client: TestClient) -> None:
    pid = some_paper(client)
    e = error(
        client.get(f"/api/v1/papers/{pid}", params={"q": "a" * (MAX_QUERY_LENGTH + 1)}), 422, "PARSE_TOO_LONG"
    )
    assert e["diagnostics"][0]["code"] == "PARSE_TOO_LONG"


@pytest.mark.parametrize(
    "params",
    [{"mode": "scholar"}, {"mode": "wos", "q": "trust"}, {"q": "trust", "sort": "title"}],
    ids=["mode-without-q", "bad-mode", "unknown-parameter"],
)
def test_bad_parameters_are_422_api_bad_param(client: TestClient, params: dict[str, Any]) -> None:
    error(client.get(f"/api/v1/papers/{some_paper(client)}", params=params), 422, "API_BAD_PARAM")


def test_q_given_twice_is_422_api_bad_param(client: TestClient) -> None:
    r = client.get(f"/api/v1/papers/{some_paper(client)}?q=trust&q=agents")
    error(r, 422, "API_BAD_PARAM")


def test_an_unknown_paper_with_q_is_still_404(client: TestClient) -> None:
    error(client.get("/api/v1/papers/op:iclr:2024:nope", params={"q": "trust"}), 404, "API_PAPER_NOT_FOUND")


def test_an_over_cap_wildcard_is_its_own_located_422(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    import openproceedings.engine.tantivy_engine as te

    with TestClient(make_app(store.indexes.parent)) as c:
        pid = some_paper(c)
        monkeypatch.setattr(te, "MAX_EXPANSIONS", 1)  # calibrat* has 2
        e = error(c.get(f"/api/v1/papers/{pid}", params={"q": "𝔸I trust calibrat*"}), 422,
                  "WILDCARD_TOO_MANY_EXPANSIONS")  # fmt: skip
    assert [d["span"] for d in e["diagnostics"]] == [[9, 18]]


def test_the_verified_clause_cap_is_search_s(store: Store) -> None:
    q = many_verified(3)
    with TestClient(make_app(store.indexes.parent, max_verified_clauses=2)) as c:
        pid = some_paper(c)
        e = error(c.get(f"/api/v1/papers/{pid}", params={"q": q}), 422, "API_TOO_MANY_VERIFIED_CLAUSES")
        assert [q[d["span"][0] : d["span"][1]] for d in e["diagnostics"]] == [clause(i) for i in range(3)]
        assert c.get(f"/api/v1/papers/{pid}", params={"q": many_verified(2)}).status_code == 200


def test_each_verified_clause_costs_what_it_costs_on_search(store: Store) -> None:
    limit = RateLimit(
        capacity=25, refill_per_second=0.001, export_weight=10, verified_weight=10, verify_token_ms=SLOT_FREE
    )
    pid = "op:iclr:2024:nope"  # charged before the 404, as the parse comes first
    with TestClient(make_app(store.indexes.parent, rate_limit=limit, max_verified_clauses=2)) as c:
        error(
            c.get(f"/api/v1/papers/{pid}", params={"q": many_verified(2)}), 404, "API_PAPER_NOT_FOUND"
        )  # 21
        error(c.get(f"/api/v1/papers/{pid}", params={"q": '"trust calibrat*"'}), 429, "API_RATE_LIMITED")


def test_the_candidate_ceiling_is_search_s(store: Store) -> None:
    q = " OR ".join(TWO)
    with TestClient(make_app(store.indexes.parent)) as probe:
        need = candidates(probe.app.state.index.engine, q)  # type: ignore[attr-defined]
        pid = some_paper(probe)
    with TestClient(make_app(store.indexes.parent, max_verification_candidates=need - 1)) as c:
        c.app.state.index.engine.read = never  # type: ignore[attr-defined]
        e = error(c.get(f"/api/v1/papers/{pid}", params={"q": q}), 422, "API_QUERY_TOO_COSTLY")
    assert [q[d["span"][0] : d["span"][1]] for d in e["diagnostics"]] == list(TWO)


def test_highlighting_a_paper_verifies_nothing(client: TestClient) -> None:
    """No collection and no position check: the paper's own text is evaluated, so no slot is taken (no
    API_BUSY, no deadline) however cold the verified clause is."""
    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    pid = some_paper(client)
    engine.read = never
    engine.page = never
    body = paper(client, pid, q='"trust calibrat*" OR trust')
    assert body["matched"] is True


def test_the_access_line_holds_no_query_text(client: TestClient, logs: Logs) -> None:
    pid = some_paper(client)
    paper(client, pid, q=f"trust OR {SECRET}")
    client.get(f"/api/v1/papers/{pid}", params={"q": f"({SECRET}"})
    lines = [x for x in logs() if x["event"] == "request" and x["route"] == "/api/v1/papers/{id}"]
    assert [x["status"] for x in lines] == [200, 422]
    assert lines[0]["canonical_hash"] == parse(f"trust OR {SECRET}").canonical_hash
    assert lines[1]["error_codes"] == ["PARSE_UNBALANCED_PAREN"]
    assert SECRET not in logs.raw.getvalue()  # type: ignore[attr-defined]


def test_the_snapshot_record_is_unchanged_by_q(client: TestClient) -> None:
    pid = some_paper(client)
    assert paper(client, pid, q="trust")["paper"] == paper(client, pid)["paper"]


# --- round-1 review: matched is the engine's membership on every paper ---------------------------------------
FULL_CORPUS = [
    ("trust", "native"),  # the default filters
    ("trust track:workshop status:(accepted OR rejected)", "native"),  # both defaults overridden
    ("calibrat* (track:workshop OR benchmark*)", "native"),  # a nested filter: the default still applies
    ("trust NOT calibrat*", "native"),  # NOT
    ('"trust calibrat*" OR agents NEAR/3 reliance', "native"),  # position-verified
    ("trust source:ICLR", "scholar"),
]


@pytest.mark.parametrize(("q", "mode"), FULL_CORPUS, ids=[q for q, _m in FULL_CORPUS])
def test_matched_is_membership_for_every_paper_in_the_corpus(client: TestClient, q: str, mode: str) -> None:
    """`search.highlight` says a paper matches exactly when the engine's `match_ids` holds it, for all 5k
    fixture papers (not a sample of non-hits): the highlighter's evaluation and the engine's agree on
    defaults, overrides, a nested filter, NOT and verified clauses."""
    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    parsed = parse(q, mode)
    assert parsed.effective_ast is not None
    matched = engine.match_ids(parsed.effective_ast)
    shown = engine.display(sorted(engine.ids))
    assert 0 < len(matched) < len(shown)
    lit = {pid for pid, record in shown.items() if search.highlight(engine, parsed, record) is not None}
    assert lit == matched


def test_the_paper_page_reads_the_display_record_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The existence check's display record is the one highlighted (spec 04: no second index read)."""
    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    pid = some_paper(client)
    reads: list[list[str]] = []
    real = type(engine).display

    def display(self: Any, ids: list[str]) -> dict[str, dict[str, Any]]:
        reads.append(list(ids))
        return real(self, ids)  # type: ignore[no-any-return]

    monkeypatch.setattr(type(engine), "display", display)
    assert paper(client, pid, q="trust")["matched"] is True
    assert reads == [[pid]]
