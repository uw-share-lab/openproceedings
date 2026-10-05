"""`GET /api/v1/search`'s `groups` (TASK-176; spec 04 §SearchResponse): each concept group's count alone,
against ReferenceEngine over the same 5k corpus; why a query has none; the limit an operator sets; nothing
else in the response changed by it; and an access line that carries two integers, never a span."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.api.config import ApiConfig
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.groups import split
from openproceedings.query.parser import parse
from openproceedings.search import run

from tests.contract.conftest import SECRET, Store, make_app
from tests.contract.test_access_log import Logs, access
from tests.contract.test_frontend_builder_golden import READ_GOLDEN
from tests.contract.test_search import SEARCH, engine_of, ok, pages, reference

__all__ = ["reference"]  # the oracle fixture, shared with test_search.py

GROUPED = [
    ("(trust OR reliance) AND calibrat* AND model*", "native"),
    ('"language model" benchmark* NOT survey year:2019..2024', "native"),
    ("trust model track:workshop status:rejected", "native"),
    ("(agents NEAR/3 reliance) AND (trust OR calibrat*)", "native"),
    ("(trust|reliance) model$ source:ICLR", "scholar"),
]


def expected(reference: ReferenceEngine, q: str, mode: str) -> list[dict[str, Any]]:
    """Each group's span and the oracle's two counts: the query with every other group removed, and the
    query with that group removed."""
    ast = parse(q, mode).effective_ast  # type: ignore[arg-type]
    assert ast is not None
    found = split(ast)
    return [
        {
            "span": list(g.span),
            "total": len(reference.match_ids(found.alone(g))),
            "total_without": len(reference.match_ids(found.without(g))),
        }
        for g in found.groups
    ]


@pytest.mark.parametrize(("q", "mode"), GROUPED)
def test_each_groups_count_is_the_oracles(
    client: TestClient, reference: ReferenceEngine, q: str, mode: str
) -> None:
    body = ok(client, q, mode=mode)
    counts = expected(reference, q, mode)
    assert body["groups"] == {
        "counts": counts,
        "groups_total": len(counts),
        "limit": ApiConfig.model_fields["max_counted_groups"].default,
        "not_counted": None,
    }
    assert len(counts) >= 2
    assert all(min(c["total"], c["total_without"]) >= body["total"] for c in counts)


def test_a_groups_span_is_its_code_point_range_in_q(client: TestClient) -> None:
    plain = ok(client, "trust AND model*")["groups"]["counts"]
    assert [c["span"] for c in plain] == [[0, 5], [10, 16]]
    # five astral letters (NFKC: `trust`): one code point each, two UTF-16 units, before the second group
    astral = ok(client, "\U0001d42d\U0001d42b\U0001d42e\U0001d42c\U0001d42d AND model*")["groups"]["counts"]
    assert astral == plain  # the same spans in code points, the same counts
    grouped = ok(client, "(trust OR reliance) AND model*")["groups"]["counts"]
    assert [c["span"] for c in grouped] == [[0, 19], [24, 30]]  # a group's parentheses are in its span


def test_the_counts_are_the_same_on_every_page_and_sort(client: TestClient) -> None:
    q = "(trust OR reliance) AND model*"
    first = ok(client, q)["groups"]
    assert first["not_counted"] is None
    assert all(body["groups"] == first for body in pages(client, q, sort="title", limit=7))
    assert ok(client, q, limit=0)["groups"] == first


@pytest.mark.parametrize(
    ("q", "n"),
    [
        ("trust", 1),
        ("trust OR calibration", 1),
        ("trust NOT survey year:2020..2024", 1),
        ("NOT survey trust", 1),
    ],
)
def test_a_query_that_is_not_an_and_of_groups_has_no_counts(client: TestClient, q: str, n: int) -> None:
    assert ok(client, q)["groups"] == {
        "counts": [],
        "groups_total": n,
        "limit": 10,
        "not_counted": "fewer_than_two_groups",
    }


def test_a_query_over_the_limit_gets_its_whole_result_without_counts(store: Store) -> None:
    q = "trust model calibration"
    with TestClient(make_app(store.indexes.parent, max_counted_groups=2)) as limited:
        over = ok(limited, q)
        at = ok(limited, "trust model")
    with TestClient(make_app(store.indexes.parent)) as default:
        counted = ok(default, q)
    assert over["groups"] == {"counts": [], "groups_total": 3, "limit": 2, "not_counted": "too_many_groups"}
    assert at["groups"]["not_counted"] is None and len(at["groups"]["counts"]) == 2
    assert len(counted["groups"]["counts"]) == 3
    # the search itself is whole either way: every other key is the counted answer's
    assert {k: v for k, v in over.items() if k != "groups"} == {
        k: v for k, v in counted.items() if k != "groups"
    }


def test_a_query_whose_counting_reads_too_many_terms_gets_its_whole_result_without_counts(
    store: Store,
) -> None:
    """`max_counted_terms`: `trust model* NOT bias*` reads 2 × (1 + |model*|) + 2 × 2 × |bias*| terms."""
    q = "trust model* NOT bias*"
    with TestClient(make_app(store.indexes.parent)) as default:
        counted = ok(default, q)
        expansions = counted["query"]["expansions"]
        read = 2 * (1 + len(expansions["model*"])) + 2 * 2 * len(expansions["bias*"])
    with TestClient(make_app(store.indexes.parent, max_counted_terms=read)) as at:
        assert ok(at, q)["groups"] == counted["groups"]
    with TestClient(make_app(store.indexes.parent, max_counted_terms=read - 1)) as under:
        over = ok(under, q)
    assert counted["groups"]["not_counted"] is None and len(counted["groups"]["counts"]) == 2
    assert over["groups"] == {"counts": [], "groups_total": 2, "limit": 10, "not_counted": "too_costly"}
    # the other bound: a kept position-verified clause's ids, read by every tree counted
    near = "trust model NOT (model NEAR/10 model*)"
    with TestClient(make_app(store.indexes.parent, max_counted_ids=1)) as few:
        costly = ok(few, near)
    with TestClient(make_app(store.indexes.parent)) as default:
        cheap = ok(default, near)
    assert costly["groups"] == {"counts": [], "groups_total": 2, "limit": 10, "not_counted": "too_costly"}
    assert cheap["groups"]["not_counted"] is None and len(cheap["groups"]["counts"]) == 2
    assert {k: v for k, v in over.items() if k != "groups"} == {
        k: v for k, v in counted.items() if k != "groups"
    }


@pytest.mark.parametrize(("q", "mode"), GROUPED)
def test_the_counts_change_nothing_else_in_the_response(client: TestClient, q: str, mode: str) -> None:
    """`total`, the page and its scores, `excluded` and the facets are the search's without groups (`run`, as
    `op search` and a record's save call it: guarantees 4 and 5)."""
    body = ok(client, q, mode=mode)
    engine = engine_of(client)
    plain = run(engine, parse(q, mode), facets=True)  # type: ignore[arg-type]
    assert plain.groups is None and plain.facets is not None
    assert body["total"] == plain.total
    assert [(h["id"], h["score"]) for h in body["hits"]] == [(h.id, h.score) for h in plain.hits]
    assert body["excluded"] == plain.excluded.to_json()
    assert body["facets"] == plain.facets


def test_the_access_line_counts_the_groups_and_holds_no_span(client: TestClient, logs: Logs) -> None:
    assert client.get(SEARCH, params={"q": f"trust AND ({SECRET} OR model*)"}).status_code == 200
    assert client.get(SEARCH, params={"q": "trust"}).status_code == 200
    counted, single = access(logs)
    assert (counted["groups"], counted["groups_counted"]) == (2, 2)
    assert (single["groups"], single["groups_counted"]) == (1, 0)
    assert SECRET not in logs.raw.getvalue()  # type: ignore[attr-defined]
    for line in (counted, single):
        assert not {"span", "spans", "q", "counts"} & set(line)


# --- the builder finds its groups' counts by their spans (frontend/src/builder/group-counts.ts) ------------------
def test_every_server_group_is_one_builder_groups_on_the_read_golden() -> None:
    """The builder gives a group the count whose span holds one of the group's terms. On every query of its
    read golden that fits the builder, that rule gives each server group to exactly one builder group, in
    order; a builder group left without one repeats an earlier group (the canonical query holds it once)."""
    fitting = groups = repeats = 0
    for case in json.loads(READ_GOLDEN.read_text(encoding="utf-8"))["cases"]:
        read = case["read"]
        if not read or "groups" not in read:  # the query has errors, or doesn't fit the builder
            continue
        q = case["q"]
        ast = parse(q, case["mode"]).effective_ast
        assert ast is not None
        server = [g.span for g in split(ast).groups]
        holders = []
        for leaves in read["groups"]:
            inside = [s for s in server if any(s[0] <= a and b <= s[1] for a, b in leaves)]
            assert len(inside) <= 1, q
            holders.append(inside[0] if inside else None)
        assert [h for h in holders if h is not None] == server, q
        texts = [sorted(q[a:b].casefold() for a, b in leaves) for leaves in read["groups"]]
        for i, held in enumerate(holders):
            if held is None:
                assert texts[i] in texts[:i], q
                repeats += 1
        fitting, groups = fitting + 1, groups + len(holders)
    assert fitting > 250 and groups > 600 and repeats >= 1  # the golden still holds each case


def test_a_count_that_fails_is_reported_and_the_search_is_whole(
    client: TestClient, logs: Logs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The counts are an extra: when they fail the response is a 200 with everything else as it would be,
    `not_counted: count_failed`, and one ERROR line with no query text."""
    q = f"trust AND ({SECRET} OR model*)"
    whole = ok(client, q)

    def broken(*_a: Any, **_kw: Any) -> list[int]:
        raise RuntimeError(SECRET)

    monkeypatch.setattr(engine_of(client), "counts", broken)
    body = ok(client, q)
    assert body["groups"] == {"counts": [], "groups_total": 2, "limit": 10, "not_counted": "count_failed"}
    assert {k: v for k, v in body.items() if k != "groups"} == {
        k: v for k, v in whole.items() if k != "groups"
    }
    (failed,) = [line for line in logs() if line["event"] == "group_count_failed"]
    assert (failed["level"], failed["groups"], failed["error"]) == ("ERROR", 2, "RuntimeError")
    assert SECRET not in logs.raw.getvalue()  # type: ignore[attr-defined]
    assert [(line["groups"], line["groups_counted"]) for line in access(logs)] == [(2, 2), (2, 0)]
