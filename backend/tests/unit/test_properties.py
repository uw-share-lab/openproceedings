"""Properties over generated trees (task-017): canonical form round-trips and never changes meaning."""

from __future__ import annotations

import re
import unicodedata

from hypothesis import assume, example, given, settings
from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode, clip
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.ast import And, Filter, Node, Not, Or, structure
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.lexer import Kind, lex
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


# near-cap queries (1,500 to 2,000 code points), each parsed twice: no per-example deadline
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


@given(queries(), st.sampled_from(["native", "scholar"]))
@example("x (a b OR c) OR y z", "native")  # nested levels: each reading clears its own level only
@example("a b   OR   c", "native")  # the reading is shorter than the span it replaces
@example(" ".join(f"(a{i} b{i} OR c{i})" for i in range(22)), "native")  # past the cap: "… and 2 more"
def test_loading_a_mixed_reading_keeps_the_query_and_clears_that_level(q: str, mode: str) -> None:
    """TASK-099: WARN_MIXED_AND_OR's `reading`, spliced over its span ("Load with parentheses"), gives a query
    with the same canonical form and one mixed level fewer (the other levels are quoted as typed). In a query
    that parses, only the "… and N more" summary past MAX_PER_CODE has no reading."""
    result = parse(q, mode)  # type: ignore[arg-type]
    mixed = [w for w in result.warnings if w.code is DiagnosticCode.WARN_MIXED_AND_OR]
    assume(not result.errors and mixed)
    capped = len(mixed) > MAX_PER_CODE
    assert [w.reading is None for w in mixed].count(True) == int(capped), q
    for w in mixed:
        if w.reading is None:
            continue  # the summary
        assert w.span is not None
        loaded = q[: w.span[0]] + w.reading + q[w.span[1] :]
        after = parse(loaded, mode)  # type: ignore[arg-type]
        assert after.errors == [], (q, loaded, after.errors)
        assert after.canonical == result.canonical, (q, loaded)
        left = len(_mixed(loaded, mode))
        assert left <= len(mixed) if capped else left == len(mixed) - 1, (q, loaded)


# Pieces that don't parse where a query term could be (TASK-140): an empty group or phrase, a lone `-`, a bare
# `NOT`, an empty field, an unclosed group, a stray `OR`
BROKEN = st.sampled_from(["()", '""', "-", "NOT", "title:", "(", "OR"])


@st.composite
def queries_with_a_broken_piece(draw: st.DrawFn) -> str:
    words = draw(queries()).split(" ")
    at = draw(st.integers(0, len(words)))
    return " ".join([*words[:at], draw(BROKEN), *words[at:]])


def _ors_spelled_out(text: str) -> str:
    """`text` with every OR operator written `OR` (`|` is one too) and whitespace removed."""
    out, at = [], 0
    for lx in lex(text).lexemes:
        if lx.kind is Kind.OR:
            out += [text[at : lx.start], "OR"]
            at = lx.end
    out.append(text[at:])
    return "".join(c for c in "".join(out) if not c.isspace())


def _faithful(reading: str, text: str) -> bool:
    """Whether `reading` is `text` with only parentheses added (the reading writes its own level's ORs as ` OR `,
    whatever was typed, e.g. `|`, and quotes nested levels as typed): nothing at the span dropped."""
    it = iter(_ors_spelled_out(text))
    want = next(it, None)
    for c in _ors_spelled_out(reading):
        if c == want:
            want = next(it, None)
        elif c not in "()":
            return False
    return want is None


@given(st.one_of(queries(), queries_with_a_broken_piece()), st.sampled_from(["native", "scholar"]))
@example("a b OR () OR c", "native")
@example("a b () OR c", "native")  # the AND group's node stops before `()`
@example("a b OR c ()", "native")
@example("a b OR c)", "native")  # an error outside the level: the reading stays
@example("a | b c", "native")  # `|` is read as OR and written ` OR ` in the reading
def test_the_mixed_message_quotes_only_the_reading_it_carries(q: str, mode: str) -> None:
    """TASK-140: WARN_MIXED_AND_OR's message quotes exactly its `reading` (clipped to 120) when there is one,
    and otherwise the level as typed (clipped the same way; nothing on the summary); a reading is never lossy (only parentheses added to the text at its
    span), even in a query with errors elsewhere."""
    result = parse(q, mode)  # type: ignore[arg-type]
    for w in result.warnings:
        if w.code is not DiagnosticCode.WARN_MIXED_AND_OR:
            continue
        quoted = re.findall(r"`([^`]*)`", w.message)
        if w.reading is None:  # the level as typed (it has errors), or nothing on the "… and N more" summary
            want = [] if w.message.startswith("…") else [clip(q[slice(*w.span)], 120)] if w.span else None
            assert quoted == want, (q, w.message)
            continue
        assert quoted == [clip(w.reading, 120)], (q, w.message)
        assert w.span is not None and _faithful(w.reading, q[slice(*w.span)]), (q, w.span, w.reading)


# TASK-141: characters that would break a quoted span in a message (a backtick ends it; a newline, tab or the
# like splits it across lines; a control or format character is invisible or rewrites a terminal)
HOSTILE = st.sampled_from(
    ["`", "\n", "\t", "\r", "\x00", "\x1b", "\x07", "\x7f", "\x85", " ", " ", " ", "​", "‮", "﻿", "\ud800"]
)


@st.composite
def queries_with_hostile_characters(draw: st.DrawFn) -> str:
    q = draw(st.one_of(queries(), queries_with_a_broken_piece()))
    for _ in range(draw(st.integers(1, 4))):
        at = draw(st.integers(0, len(q)))
        q = q[:at] + draw(HOSTILE) + q[at:]
    return q


@given(queries_with_hostile_characters(), st.sampled_from(["native", "scholar"]))
@example("a b OR `c`", "native")
@example('"trust\x00 in\nmodels', "native")
@example("trust NEAR/x`y b", "native")
@example("venue:IC\x07LR", "scholar")
def test_every_message_quotes_query_text_on_one_visible_line(q: str, mode: str) -> None:
    """Every diagnostic that quotes the query does so through `clip`: its backticks pair up, and it holds no
    whitespace but a space and no control, format or surrogate character, whatever the query contains."""
    result = parse(q, mode)  # type: ignore[arg-type]
    for d in result.errors + result.warnings + result.translations:
        assert d.message.count("`") % 2 == 0, (q, d.message)
        for c in d.message:
            assert c == " " or not c.isspace(), (q, d.message)
            assert unicodedata.category(c) not in ("Cc", "Cf", "Cs"), (q, d.message)
