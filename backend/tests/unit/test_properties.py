"""Properties over generated trees (task-017): canonical form round-trips and never changes meaning."""

from __future__ import annotations

from hypothesis import assume, example, given, settings
from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.ast import And, Filter, Node, Not, Or, structure
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.parser import MAX_PER_CODE, MAX_QUERY_LENGTH, parse

from tests.corpus import fixture_records
from tests.strategies import asts, filters, near_cap_queries, negative_asts, queries

ENGINE = ReferenceEngine(fixture_records())


@given(asts())
def test_canonical_string_parses_back_to_the_canonical_tree(tree: Node) -> None:
    canonical = canonicalize(tree)
    result = parse(render(canonical))
    assert result.errors == [], (render(canonical), result.errors)
    # printing never causes a warning; WARN_NESTED_FILTER is about the tree's meaning, so it may remain
    semantic = (
        DiagnosticCode.WARN_NESTED_FILTER,
        DiagnosticCode.WARN_CJK_RUN,
    )  # about the tree, not printing
    printed = [w for w in result.warnings if w.code not in semantic]
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


@settings(deadline=None)
@given(near_cap_queries(), st.sampled_from(["native", "scholar"]))
@example(" ".join(f"w{i:04d}" for i in range(284)), "native")  # 1,703 cp; canonical 2,909: refused
@example("(" + "x" * 1_963 + " AND track:main AND status:accepted)", "native")  # canonical at the cap
def test_an_accepted_query_near_the_cap_replays_from_its_canonical_string(q: str, mode: str) -> None:
    """decision-008: a query is accepted only if its canonical string is too, so a saved search record can
    always be replayed and pasted back (records.py re-parses the canonical string, natively)."""
    result = parse(q, mode)  # type: ignore[arg-type]
    if result.errors:
        return
    assert result.canonical is not None and len(result.canonical) <= MAX_QUERY_LENGTH
    again = parse(result.canonical)
    assert again.errors == [], (q, again.errors)
    assert again.canonical == result.canonical and again.canonical_hash == result.canonical_hash


def _mixed(q: str, mode: str) -> list[tuple[int, int] | None]:
    return [w.span for w in parse(q, mode).warnings if w.code is DiagnosticCode.WARN_MIXED_AND_OR]  # type: ignore[arg-type]


@settings(deadline=None)
@given(queries(), st.sampled_from(["native", "scholar"]))
@example("x (a b OR c) OR y z", "native")  # nested levels: each reading clears its own level only
@example("a b   OR   c", "native")  # the reading is shorter than the span it replaces
def test_loading_a_mixed_reading_keeps_the_query_and_clears_that_level(q: str, mode: str) -> None:
    """TASK-099: WARN_MIXED_AND_OR's `reading`, spliced over its span ("Load with parentheses"), gives a query
    with the same canonical form and one mixed level fewer (the other levels are quoted as typed)."""
    result = parse(q, mode)  # type: ignore[arg-type]
    mixed = [w for w in result.warnings if w.code is DiagnosticCode.WARN_MIXED_AND_OR]
    assume(not result.errors and mixed and len(mixed) < MAX_PER_CODE)
    for w in mixed:
        assert w.span is not None and w.reading is not None
        loaded = q[: w.span[0]] + w.reading + q[w.span[1] :]
        after = parse(loaded, mode)  # type: ignore[arg-type]
        assert after.errors == [], (q, loaded, after.errors)
        assert after.canonical == result.canonical, (q, loaded)
        assert len(_mixed(loaded, mode)) == len(mixed) - 1, (q, loaded)
