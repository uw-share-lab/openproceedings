"""Properties over generated trees (task-017): canonical form round-trips and never changes meaning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from hypothesis import given
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.ast import And, Node, Not, Or, structure
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.parser import parse

from tests.strategies import asts, negative_asts


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
