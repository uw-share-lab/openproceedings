"""Properties over generated trees (task-017): canonical form round-trips and never changes meaning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.ast import And, Filter, Node, Not, Or, structure
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.parser import parse

from tests.strategies import asts, filters, negative_asts


@dataclass(frozen=True)
class Rec:
    id: str
    title: str
    abstract: str | None
    venue: str
    year: int
    track: str
    status: str


CORPUS = Path(__file__).parents[1] / "fixtures" / "corpus" / "reference-200.jsonl"
ENGINE = ReferenceEngine([Rec(**json.loads(line)) for line in CORPUS.read_text().splitlines()])


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
def test_facet_counts_add_up(tree: Node, field: str) -> None:
    """Each facet counts every record matched once F's own top-level conjuncts are dropped, exactly once."""
    counts = ENGINE.facets(tree, (field,))[field]
    conjuncts = _flatten(tree)
    own = [c for c in conjuncts if _own_field(c) == field]
    kept = [c for c in conjuncts if c not in own]
    expected = (
        ENGINE.match_ids(And(span=(0, 0), children=tuple(kept)))
        if len(kept) > 1
        else (ENGINE.match_ids(kept[0]) if kept else ENGINE.universe)
    )
    assert sum(counts.values()) == len(expected)
    if not own:
        assert sum(counts.values()) == len(ENGINE.match_ids(tree))


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
