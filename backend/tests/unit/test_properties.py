"""Properties over generated trees (task-017): canonical form round-trips and never changes meaning."""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.ast import And, Filter, Node, Not, Or, structure
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.parser import parse

from tests.corpus import fixture_records
from tests.strategies import asts, filters, negative_asts

ENGINE = ReferenceEngine(fixture_records())


@given(asts())
def test_canonical_string_parses_back_to_the_canonical_tree(tree: Node) -> None:
    canonical = canonicalize(tree)
    result = parse(render(canonical))
    assert result.errors == [], (render(canonical), result.errors)
    # printing never causes a warning; WARN_NESTED_FILTER is about the tree's meaning, so it may remain
    printed = [w for w in result.warnings if w.code is not DiagnosticCode.WARN_NESTED_FILTER]
    assert printed == [], (render(canonical), printed)
    assert result.ast is not None
    assert structure(canonicalize(result.ast)) == structure(canonical)


@given(asts())
def test_canonical_form_preserves_the_match_set(tree: Node) -> None:
    canonical = canonicalize(tree)
    reparsed = parse(render(canonical)).ast
    assert reparsed is not None
    assert ENGINE.match_ids(tree) == ENGINE.match_ids(canonical) == ENGINE.match_ids(reparsed)


def _positive(n: Node) -> bool:
    """Spec 02: a query must restrict the corpus. NOT x is negative, NOT NOT x is x, AND needs one positive
    child, OR needs every branch positive."""
    if isinstance(n, Not):
        return isinstance(n.child, Not) and _positive(n.child.child)
    if isinstance(n, And):
        return any(_positive(c) for c in n.children)
    if isinstance(n, Or):
        return all(_positive(c) for c in n.children)
    return True


@given(negative_asts())
def test_all_negative_trees_are_rejected(tree: Node) -> None:
    canonical = canonicalize(tree)
    result = parse(render(canonical))
    codes = [e.code for e in result.errors]
    if _positive(canonical):  # only when NOT NOT x collapsed; otherwise every such tree is negative
        assert codes == [], (render(canonical), codes)
    else:
        assert codes == [DiagnosticCode.PARSE_ALL_NEGATIVE], (render(canonical), codes)


@given(asts())
def test_scholar_mode_reads_a_canonical_string_the_same_way(tree: Node) -> None:
    text = render(canonicalize(tree))
    assert parse(text, "scholar").canonical == parse(text).canonical


@given(asts(), st.sampled_from(["venue", "year", "track", "status"]))
def test_a_facet_of_a_field_the_query_never_filters_counts_its_matches(tree: Node, field: str) -> None:
    """Independent of how the oracle picks conjuncts: with no filter on F anywhere in the tree, F's facet
    partitions exactly the query's matches."""
    assume(field not in str(structure(tree)))
    assert sum(ENGINE.facets(tree, (field,))[field].values()) == len(ENGINE.match_ids(tree))


@given(filters())
def test_facets_of_a_lone_filter_count_every_record_for_its_own_field(f: Node) -> None:
    field = f.field  # type: ignore[union-attr]
    assert sum(ENGINE.facets(f, (field,))[field].values()) == len(ENGINE.universe)


def _flatten(n: Node) -> list[Node]:
    """Top-level conjuncts with nested ANDs flattened (spec 02 judges top-level on the canonical tree)."""
    if not isinstance(n, And):
        return [n]
    out: list[Node] = []
    for c in n.children:
        out.extend(_flatten(c))
    return out


def test_generated_trees_mostly_match_something() -> None:
    """Guard against vacuous properties: an empty match set checks nothing, so keep coverage up."""
    hits, total = 0, 0

    @settings(max_examples=400, database=None, derandomize=True)
    @given(asts())
    def count(tree: Node) -> None:
        nonlocal hits, total
        total += 1
        hits += bool(ENGINE.match_ids(tree))

    count()
    assert hits / total >= 0.4, f"only {hits}/{total} generated trees match a record"


def _own_field(n: Node) -> str | None:
    inner = n.child if isinstance(n, Not) else n
    return inner.field if isinstance(inner, Filter) else None
