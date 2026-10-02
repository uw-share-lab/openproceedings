"""task-086: facets and exclusion counts from one collection's (venue, year, track, status) combos equal the
implementation they replace (one collection per kept set, frozen in `facets_before.py`) and ReferenceEngine,
on the synthetic 5k corpus (every combination of the four fields occurs in it). Generated trees get extra
top-level filter conjuncts (`Filter` or `NOT` of one, any field, possibly several on one field), since
those are what the new path sets aside and evaluates per combo."""

from __future__ import annotations

import json
from functools import partial
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from openproceedings.engine.exclusions import ORDER, excluded
from openproceedings.engine.protocol import FACET_FIELDS, EngineInputError, EngineInternalError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import COMBO, TantivyEngine
from openproceedings.query.ast import And, Node, Not
from openproceedings.query.canonical import render
from openproceedings.query.parser import parse

from tests.bench.test_bench import trust_evals
from tests.fixtures.corpus.synthetic_5k import records, vocab
from tests.golden.test_trust_evals import STRINGS
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


# each example runs facets three ways over the 5k corpus, the oracle among them: no per-example deadline
@settings(max_examples=150, deadline=None)
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
        # aggregated over the default fields only (TASK-166), their counts are the same; the other fields'
        # filters are then in the collected query, not evaluated per combo
        narrow = tantivy.facets(ast, ORDER, over=ORDER)
        assert narrow == {f: got[f] for f in ORDER}, q
        for f in FACET_FIELDS:  # any one field aggregated alone, too
            assert tantivy.facets(ast, (f,), over=(f,)) == {f: got[f]}, q


# exclusion accounting three ways over the 5k corpus: no per-example deadline
@settings(max_examples=100, deadline=None)
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
    # what a search without facets runs (TASK-166), from a cold memo and then a warm one
    tantivy.faceted.clear()
    for _ in range(2):
        narrow = excluded(tantivy, parsed, len(total), facets=partial(tantivy.facets, over=ORDER))
        assert json.dumps(narrow.to_json()) == got, render(ast)


@pytest.mark.parametrize("name", STRINGS)
def test_exclusion_counts_of_each_trust_evals_string_are_the_same_from_the_default_fields_alone(
    engines: Engines, name: str
) -> None:
    """TASK-166 AC #2: the default fields' aggregation gives every Trust-Evals string the exclusion counts
    the facet combos give it, and the oracle's."""
    reference, tantivy = engines
    parsed = trust_evals(name)
    assert parsed.effective_ast is not None
    total = len(tantivy.match_ids(parsed.effective_ast))
    tantivy.faceted.clear()
    narrow = excluded(tantivy, parsed, total, facets=partial(tantivy.facets, over=ORDER))
    assert narrow == excluded(tantivy, parsed, total)
    assert narrow == excluded(reference, parsed, total)


def test_a_counted_field_must_be_aggregated(engines: Engines) -> None:
    _reference, tantivy = engines
    ast = parse("model").effective_ast
    assert ast is not None
    with pytest.raises(EngineInternalError):
        tantivy.facets(ast, ("venue",), over=ORDER)


def test_the_combo_fields_are_the_facet_fields() -> None:
    assert sorted(COMBO) == sorted(FACET_FIELDS)


def test_combos_cover_every_document_of_the_base(engines: Engines) -> None:
    """Every matching document is in exactly one combo: no document lacks a value the nested aggregation
    would drop it for (the counts would then undercount silently)."""
    _reference, tantivy = engines
    assert sum(n for _combo, n in tantivy.combos([])) == len(RECORDS)
    ast = parse("model OR trust").ast
    assert ast is not None
    for over in (COMBO, ORDER, ("year",)):
        assert sum(n for _combo, n in tantivy.combos([], over=over)) == len(RECORDS)
        combos = tantivy.combos([ast], over=over)
        assert sum(n for _combo, n in combos) == len(tantivy.match_ids(ast))
        assert all(len(combo) == len(over) for combo, _n in combos)
