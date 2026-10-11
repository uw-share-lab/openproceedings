"""Index schema 4 (decision-049): `abstract_kind` is a raw fast field; facets and combos are per engine. Over the
small every-kind corpus (`tests/fixtures/corpus/abstract_kinds.py`), the schema-4 engine agrees with the oracle on
`abstract_kind:` queries, its facets and its combos; a schema-3 build refuses a record whose abstract is OpenAlex's,
which is what keeps the schema-3 display fallback (`none`/`official` from the stored abstract) exact."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from openproceedings.engine import tantivy_engine
from openproceedings.engine.exclusions import excluded
from openproceedings.engine.index import SCHEMA_VERSION, SERVED_SCHEMAS, IndexBuildError
from openproceedings.engine.protocol import EngineInputError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import COMBO, TantivyEngine, _Parts
from openproceedings.query.ast import And, Node, Not
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.groups import split
from openproceedings.query.parser import parse

from tests.fixtures.corpus import abstract_kinds
from tests.fixtures.corpus.synthetic_5k import vocab_of
from tests.strategies import SPAN, engine_asts, filters
from tests.unit.engine.facets_before import facets_before
from tests.unit.engine.test_exclusions import tantivy_of

CORPUS = abstract_kinds.records()
KIND = {r.id: r.abstract_kind for r in CORPUS}


@pytest.fixture(scope="module")
def engine(tmp_path_factory: pytest.TempPathFactory) -> TantivyEngine:
    return tantivy_of(CORPUS, tmp_path_factory.mktemp("s4"), "4")


@pytest.fixture(scope="module")
def oracle() -> ReferenceEngine:
    return ReferenceEngine(CORPUS)


def test_schema_4_is_current_and_3_still_served() -> None:
    assert SCHEMA_VERSION == "4" and list(SERVED_SCHEMAS) == ["3", "4"]
    assert SERVED_SCHEMAS["3"].facets == ("venue", "track", "status")
    assert SERVED_SCHEMAS["4"].facets == ("venue", "track", "status", "abstract_kind")
    assert COMBO == ("venue", "year", "track", "status", "abstract_kind")


def test_every_kind_is_in_the_fixture() -> None:
    assert {r.abstract_kind for r in CORPUS} == {"official", "openalex", "none"}


def test_the_engines_combo_is_its_own(engine: TantivyEngine, tmp_path: Path) -> None:
    assert engine.combo == engine.filter_fields == COMBO
    old = tantivy_of([r for r in CORPUS if r.abstract_kind != "openalex"], tmp_path, "3")
    assert old.combo == old.filter_fields == ("venue", "year", "track", "status")


@pytest.mark.parametrize(
    "q",
    [
        "abstract_kind:openalex",
        "trust abstract_kind:(official OR none)",
        "NOT abstract_kind:official agents",
        "venue:AAAI abstract_kind:openalex",
        "(trust OR audit) NOT abstract_kind:none venue:FAccT",
        "abstract_kind:openalex OR fairness",  # nested: not set aside
    ],
)
def test_abstract_kind_facets_equal_the_oracle_and_per_set_collections(
    engine: TantivyEngine, oracle: ReferenceEngine, q: str
) -> None:
    ast = parse(q).effective_ast
    assert ast is not None
    assert engine.match_ids(ast) == oracle.match_ids(ast)
    facets = engine.facets(ast)
    assert facets == oracle.facets(ast)
    assert set(facets) == set(COMBO)
    # the disjunctive count, one collection per kept set: each field over the query without its own top-level
    # filters (a facet click on abstract_kind keeps the other kinds' counts)
    assert facets == facets_before(engine, ast, engine.filter_fields)


@settings(max_examples=200, deadline=None)
@given(engine_asts(vocab_of(CORPUS)))
def test_generated_trees_agree_with_the_oracle_on_schema_4(
    engine: TantivyEngine, oracle: ReferenceEngine, ast: Node
) -> None:
    try:
        expected = oracle.match_ids(ast)
    except EngineInputError as e:  # a wildcard over the cap: the engine refuses it alike
        with pytest.raises(EngineInputError) as refused:
            engine.match_ids(ast)
        assert refused.value.code == e.code
        return
    assert engine.match_ids(ast) == expected
    assert engine.facets(ast) == oracle.facets(ast)
    assert engine.count(ast) == len(expected)
    parsed = parse(render(ast))
    if parsed.effective_ast is not None:  # a tree the parser accepts: its exclusion counts agree too
        total = len(expected)
        assert excluded(engine, parsed, total) == excluded(oracle, parsed, total)


@st.composite
def grouped_kind_asts(draw: st.DrawFn) -> Node:
    """As `test_group_counts.grouped_asts`, over this corpus: an AND of 1 to 4 trees and top-level filters (or NOT
    of one), every filter field drawn, so `abstract_kind:openalex` matches papers here (the 5k corpus has none)."""
    parts: list[Node] = draw(st.lists(engine_asts(vocab_of(CORPUS)), min_size=1, max_size=4))
    parts += [
        Not(span=SPAN, child=f) if draw(st.booleans()) else f for f in draw(st.lists(filters(), max_size=3))
    ]
    return parts[0] if len(parts) == 1 else And(span=SPAN, children=tuple(draw(st.permutations(parts))))


class _Bitwise(_Parts):
    """`_Parts` held on the bitwise path (each conjunct collected as a bitmap), whatever `counts` decides."""

    bitwise = property(lambda self: True, lambda self, value: None)  # type: ignore[assignment]


def _a_thread(job: Callable[[Callable[[], bool]], None]) -> None:
    """A `spread` that starts the second worker on a thread of its own at once."""
    threading.Thread(target=job, args=(lambda: False,), daemon=True).start()


def _outcome(f: Callable[[], Any]) -> Any:
    try:
        return f()
    except EngineInputError as e:
        return ("refused", e.code)


# each example counts up to nine trees four ways and evaluates them with the oracle: no per-example deadline
@settings(max_examples=100, deadline=None)
@given(tree=grouped_kind_asts())
def test_group_counts_over_every_kind_are_the_oracles(
    engine: TantivyEngine, oracle: ReferenceEngine, tree: Node
) -> None:
    """Gate C round 2 (exactness): `counts`, with the memo cleared and kept, with and without the second worker,
    and on the bitwise path, equals ReferenceEngine's count of each tree, with OpenAlex documents among them."""
    ast = canonicalize(tree)
    found = split(ast)
    trees = (
        [ast, *map(found.alone, found.groups), *map(found.without, found.groups)]
        if len(found.groups) >= 2
        else [ast]
    )
    expected = _outcome(lambda: [len(oracle.match_ids(t)) for t in trees])
    for bitwise in (False, True):
        with pytest.MonkeyPatch.context() as m:
            if bitwise:
                m.setattr(tantivy_engine, "_Parts", _Bitwise)
            for spread in (None, _a_thread):
                engine.faceted.clear()
                for _memo in ("cleared", "kept"):
                    got = _outcome(lambda spread=spread: engine.counts(trees, spread=spread))
                    assert got == expected, (render(ast), bitwise, spread is not None, _memo)


def test_the_every_kind_count_property_sees_openalex_on_every_path(
    engine: TantivyEngine, oracle: ReferenceEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The property above is not vacuous: one fixed AND of two groups under `abstract_kind:openalex` counts a
    non-zero set on each path."""
    ast = parse("(trust OR audit) paper abstract_kind:openalex").effective_ast
    assert ast is not None
    found = split(ast)
    trees = [ast, *map(found.alone, found.groups), *map(found.without, found.groups)]
    expected = [len(oracle.match_ids(t)) for t in trees]
    assert expected[0] > 0
    for bitwise in (False, True):
        with monkeypatch.context() as m:
            if bitwise:
                m.setattr(tantivy_engine, "_Parts", _Bitwise)
            for spread in (None, _a_thread):
                engine.faceted.clear()
                assert engine.counts(trees, spread=spread) == expected


def test_bitwise_combos_equal_aggregated_combos_on_schema_4(engine: TantivyEngine) -> None:
    ast = parse("trust OR calibration").effective_ast  # every kind among its matches
    assert ast is not None
    parts = _Parts(engine, None)
    parts.bitwise = True
    engine.faceted.clear()
    bitwise = engine.combos([ast], parts=parts)
    engine.faceted.clear()
    assert bitwise == engine._aggregate([ast], None, engine.combo, None)
    assert {c[-1] for c, _n in bitwise} == {"official", "openalex", "none"}
    assert sum(n for _c, n in bitwise) == len(engine.match_ids(ast))


def test_a_schema_4_base_memo_stays_within_the_tripled_budget(engine: TantivyEngine) -> None:
    assert TantivyEngine.MAX_FACET_COMBOS == 300_000
    engine.faceted.clear()
    ast = parse("trust").effective_ast
    assert ast is not None
    engine.facets(ast)
    assert sum(engine.charges["faceted"]) <= TantivyEngine.MAX_FACET_COMBOS


def test_display_records_carry_the_kind_on_both_schemas(tmp_path: Path, engine: TantivyEngine) -> None:
    hits = engine.display(sorted(engine.ids))
    assert len(hits) == len(CORPUS)
    assert all(h["abstract_kind"] == KIND[i] for i, h in hits.items())
    total, documents = engine.documents(parse("abstract_kind:openalex").effective_ast)  # type: ignore[arg-type]
    assert total == 15 and all(d["abstract_kind"] == "openalex" for d in documents)
    plain = [r for r in CORPUS if r.abstract_kind != "openalex"]
    old = tantivy_of(plain, tmp_path, "3")
    shown = old.display(sorted(old.ids))
    assert len(shown) == len(plain)
    assert all(h["abstract_kind"] == KIND[i] for i, h in shown.items())  # derived from the stored abstract
    assert {h["abstract_kind"] for h in shown.values()} == {"official", "none"}


def test_a_schema_3_build_refuses_an_openalex_record(tmp_path: Path) -> None:
    with pytest.raises(IndexBuildError, match="needs index schema 4"):
        tantivy_of(CORPUS, tmp_path, "3")
    assert not [p for p in (tmp_path / "indexes").iterdir() if not p.name.startswith(".")]  # nothing placed
