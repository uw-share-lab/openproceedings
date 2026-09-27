"""task-086: facets and exclusion counts from one collection's (venue, year, track, status) combos equal the
implementation they replace (one collection per kept set, frozen in `facets_before.py`) and ReferenceEngine,
on the synthetic 5k corpus (every combination of the four fields occurs in it). Generated trees get extra
top-level filter conjuncts (`Filter` or `NOT` of one, any field, possibly several on one field), since
those are what the new path sets aside and evaluates per combo."""

from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from openproceedings.engine.exclusions import excluded
from openproceedings.engine.protocol import FACET_FIELDS, EngineInputError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import COMBO, TantivyEngine
from openproceedings.query.ast import And, Node, Not
from openproceedings.query.canonical import render
from openproceedings.query.parser import parse

from tests.fixtures.corpus.synthetic_5k import records, vocab
from tests.strategies import SPAN, engine_asts, filters
from tests.unit.engine.facets_before import facets_before
from tests.unit.engine.test_exclusions import tantivy_of

RECORDS = list(records())
type Engines = tuple[ReferenceEngine, TantivyEngine]


@pytest.fixture(scope="module")
def engines(tmp_path_factory: pytest.TempPathFactory) -> Engines:
    return ReferenceEngine(RECORDS), tantivy_of(RECORDS, tmp_path_factory.mktemp("facets"))


class Before:
    """The Tantivy engine with the frozen facets: what exclusion accounting computed before task-086."""

    def __init__(self, engine: TantivyEngine) -> None:
        self.engine = engine

    def __getattr__(self, name: str) -> Any:
        return getattr(self.engine, name)

    def facets(self, ast: Node, fields: tuple[str, ...] = FACET_FIELDS) -> dict[str, dict[str, int]]:
        return facets_before(self.engine, ast, fields)


@st.composite
def filtered_asts(draw: st.DrawFn) -> Node:
    tree = draw(engine_asts(vocab()))
    extra = [
        Not(span=SPAN, child=f) if draw(st.booleans()) else f for f in draw(st.lists(filters(), max_size=4))
    ]
    if not extra:
        return tree
    parts = [*(tree.children if isinstance(tree, And) and draw(st.booleans()) else (tree,)), *extra]
    return And(span=SPAN, children=tuple(draw(st.permutations(parts))))


def outcome(f: Any, *args: Any) -> Any:
    try:
        return f(*args)
    except EngineInputError as e:
        return ("refused", e.code)


@settings(
    max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)
@given(ast=filtered_asts())
def test_facets_equal_the_per_kept_set_collections_and_the_oracle(engines: Engines, ast: Node) -> None:
    reference, tantivy = engines
    tantivy.faceted.clear()  # a fresh base as often as a memoised one: both paths are checked
    got = outcome(tantivy.facets, ast)
    q = render(ast)
    assert got == outcome(facets_before, tantivy, ast), q
    assert got == outcome(reference.facets, ast), q
    if isinstance(got, dict):
        assert got == tantivy.facets(ast), q  # from the memo, the same
        for f in FACET_FIELDS:  # one field alone is the same field of the whole
            assert tantivy.facets(ast, (f,)) == {f: got[f]}, q


@settings(
    max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)
@given(ast=filtered_asts())
def test_exclusion_counts_equal_the_per_kept_set_collections_and_the_oracle(
    engines: Engines, ast: Node
) -> None:
    reference, tantivy = engines
    parsed = parse(render(ast))
    if parsed.effective_ast is None:
        return  # a tree the parser refuses (bare, all-negative) has no exclusion accounting
    total = outcome(tantivy.match_ids, parsed.effective_ast)
    if not isinstance(total, frozenset):
        return  # refused (a wildcard over the cap): facets refuse alike, checked above
    tantivy.faceted.clear()
    got = json.dumps(excluded(tantivy, parsed, len(total)).to_json())  # order-sensitive: spec 04 pins it
    assert got == json.dumps(excluded(Before(tantivy), parsed, len(total)).to_json()), render(ast)  # type: ignore[arg-type]
    assert got == json.dumps(excluded(reference, parsed, len(total)).to_json()), render(ast)


def test_the_combo_fields_are_the_facet_fields() -> None:
    assert sorted(COMBO) == sorted(FACET_FIELDS)


def test_combos_cover_every_document_of_the_base(engines: Engines) -> None:
    """Every matching document is in exactly one combo: no document lacks a value the nested aggregation
    would drop it for (the counts would then undercount silently)."""
    _reference, tantivy = engines
    assert sum(n for _combo, n in tantivy.combos([])) == len(RECORDS)
    ast = parse("model OR trust").ast
    assert ast is not None
    assert sum(n for _combo, n in tantivy.combos([ast])) == len(tantivy.match_ids(ast))
