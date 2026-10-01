"""Each filter field's top-level clause for facet clicks (TASK-078; spec 02 §Filter clauses; decision-011).

The goldens are shared with the frontend reducer's test (`frontend/src/lib/filter-clause-golden.json`): here
`query.clauses.filter_clauses` must report exactly the listed clauses, and every expected click result must
parse with the clicked field's clause admitting the new values, so the reducer's splice and the server agree.
"""

from __future__ import annotations

import json
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from hypothesis import assume, event, example, given, seed, settings
from hypothesis import strategies as st
from openproceedings.query import clauses
from openproceedings.query.ast import (
    FILTER_FIELDS,
    MAX_YEAR,
    MIN_YEAR,
    And,
    Filter,
    Node,
    Not,
    YearRange,
    structure,
)
from openproceedings.query.clauses import (
    CLAUSE_REASONS,
    EVERY_YEAR,
    VOCABULARY,
    ParsedClause,
    ParsedYearClause,
    filter_clauses,
)
from openproceedings.query.parser import MAX_QUERY_LENGTH, Mode, ParseResult, parse
from pydantic import ValidationError

from tests.strategies import YearEditCase, clause_queries, near_cap_queries, queries, year_edit_cases

ROOT = Path(__file__).resolve().parents[3]
GOLDEN: list[dict[str, Any]] = json.loads(
    (ROOT / "frontend" / "src" / "lib" / "filter-clause-golden.json").read_text(encoding="utf-8")
)["cases"]
QUERIES = (ROOT / "backend" / "tests" / "fixtures" / "queries" / "trust-evals.txt").read_text().split("\n")
TRUST_EVALS = [QUERIES[i + 1] for i in range(len(QUERIES) - 1) if QUERIES[i].startswith("## ")]


def text(case: dict[str, Any], key: str) -> str:
    """`case[key]`, or its `<key>_parts` runs ([text, times]) concatenated."""
    if key in case:
        return str(case[key])
    return "".join(part * times for part, times in case[f"{key}_parts"])


def report(q: str, mode: Mode = "native") -> dict[str, Any]:
    filters = filter_clauses(q, parse(q, mode))
    assert filters is not None
    return filters.model_dump(mode="json")


def admits_after(clause: dict[str, Any], click: dict[str, Any]) -> list[str]:
    """The values the clicked clause admits after the click, sorted as the canonical form keeps them."""
    values = list(clause["values"])
    value = click["value"]
    return sorted([v for v in values if v != value] if value in values else [*values, value])


@pytest.mark.parametrize("case", GOLDEN, ids=[c["name"] for c in GOLDEN])
def test_golden_report(case: dict[str, Any]) -> None:
    got = report(text(case, "q"), case["mode"])
    assert {f: got[f] for f in case["filters"]} == case["filters"]


@pytest.mark.parametrize("case", [c for c in GOLDEN if "refused" not in c], ids=lambda c: c["name"])
def test_golden_click_result_parses_with_the_new_values(case: dict[str, Any]) -> None:
    """The reducer's output (pinned in the golden) is a query whose clicked clause admits exactly the new
    values: the splice replaced the whole clause, and nothing else of that field is left at the top level."""
    field = case["click"]["field"]
    after = report(text(case, "expected"), case["mode"])[field]
    assert after["toggleable"], after
    assert after["values"] == admits_after(case["filters"][field], case["click"])


def test_golden_covers_every_reason() -> None:
    reasons = {c["reason"] for case in GOLDEN for c in case["filters"].values()}
    assert reasons == {None, *CLAUSE_REASONS}


def test_a_query_with_errors_has_no_filters() -> None:
    assert filter_clauses("(trust", parse("(trust")) is None
    assert filter_clauses("x" * (MAX_QUERY_LENGTH + 1), parse("x" * (MAX_QUERY_LENGTH + 1))) is None


def test_every_field_is_reported_in_order() -> None:
    assert list(report("trust")) == list(FILTER_FIELDS)
    assert all(report("trust")[f]["field"] == f for f in FILTER_FIELDS)


def test_year_is_ranges() -> None:
    year = report("trust year:(2020..2022 OR 2024 OR 2023)")["year"]
    assert year["ranges"] == [{"lo": 2020, "hi": 2024}]  # merged, as the canonical form keeps them
    assert year["toggleable"] and year["span"] == [6, 39]
    assert report("trust")["year"]["ranges"] == [EVERY_YEAR.model_dump()]


def test_a_nested_filter_beside_a_top_level_one_leaves_the_top_level_one_editable() -> None:
    """Spec 05: only a field whose *only* clause is nested has no editable clause; a nested one stays applied."""
    got = report("track:main (track:workshop OR x)")["track"]
    assert (got["span"], got["values"], got["toggleable"]) == ([0, 10], ["main"], True)


def test_default_clause_nested_elsewhere_is_nested() -> None:
    assert report("x (status:rejected OR y)")["status"]["reason"] == "nested"
    assert report("x NOT (status:rejected y)")["status"]["reason"] == "nested"


def test_not_not_clause_is_positive_and_spliced_whole() -> None:
    got = report("NOT NOT track:main x")["track"]
    assert (got["negated"], got["span"], got["toggleable"]) == (False, [0, 18], True)


def test_clause_top_level_only_once_canonicalised_is_nested() -> None:
    """`NOT NOT (a track:x)` flattens to a top-level `track:x`, but as written it is inside a NOT group."""
    assert report("NOT NOT (a track:main) b")["track"]["reason"] == "nested"


def test_written_copy_inside_a_group_that_flattens_is_multiple() -> None:
    got = report("track:main NOT NOT (track:main a)")["track"]
    assert (got["span"], got["values"], got["reason"]) == (None, None, "multiple_clauses")


def test_negated_or_group() -> None:
    got = report("x -(track:workshop OR track:competition)")["track"]
    assert (got["negated"], got["span"], got["values"], got["reason"]) == (
        True,
        [2, 40],
        ["competition", "workshop"],
        "negated",
    )


def test_a_year_clause_followed_by_a_group_is_editable() -> None:
    """The widest year edit (`MAX_YEAR_RANGES` ranges) is grouped like every clause; a year clause followed directly
    by a group (which only a range or a group can be, `year:2020(x)` not parsing) stays editable."""
    got = report("year:(2020 OR 2022)(x)")["year"]
    assert (got["span"], got["toggleable"]) == ([0, 19], True)


def test_a_year_clause_followed_by_a_word_is_editable_because_the_edit_is_grouped() -> None:
    """`year:1000..9999status:accepted` doesn't parse (FIELD_UNKNOWN_VALUE), `year:(1000..9999)status:accepted`
    does: the widest year edit must be written grouped, or this clause reads as not editable (review gate r2)."""
    got = report("year:(2019)status:accepted")["year"]
    assert (got["span"], got["toggleable"], got["reason"]) == ([0, 11], True, None)


def test_a_typed_clause_at_depth_64_is_still_editable() -> None:
    """A splice inside the query adds no nesting (`track:(…)` is not a group level); only the wrap does. So
    `too_deep` is reachable only for a field with no clause: a typed clause's golden edge is `too_long`."""
    q = "(" * 64 + "a track:main" + ")" * 64
    got = report(q)
    assert got["track"]["toggleable"] and got["venue"]["reason"] == "too_deep"


@pytest.mark.parametrize("q", TRUST_EVALS)
def test_trust_evals_strings_splice_as_reported(q: str) -> None:
    """For every review string: each toggleable clause's span holds that clause, and replacing it with one
    new value (the reducer's splice) or wrapping q (a zero-width span) parses to a clause admitting it."""
    result = parse(q, "scholar")
    filters = filter_clauses(q, result)
    assert filters is not None
    for field in ("venue", "track", "status"):
        clause = getattr(filters, field)
        assert isinstance(clause, ParsedClause) and clause.toggleable and clause.span is not None
        start, end = clause.span
        value = VOCABULARY[field][-1]
        edited = f"({q}) AND {field}:{value}" if start == end else f"{q[:start]}{field}:{value}{q[end:]}"
        after = filter_clauses(edited, parse(edited, "scholar"))
        assert after is not None and getattr(after, field).values == [value]


def test_two_written_copies_are_two_clauses_even_when_both_are_every_value() -> None:
    """A splice over the first would leave the second harmless here, but the rule is the written count."""
    every = "track:(" + " OR ".join(VOCABULARY["track"]) + ")"
    got = report(f"x {every} {every}")["track"]
    assert (got["span"], got["reason"]) == (None, "multiple_clauses")


class _CountingParse:
    """`parse`, counting the calls `filter_clauses` makes (the edited strings it checks)."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, q: str, mode: Mode = "native") -> ParseResult:
        self.calls += 1
        return parse(q, mode)


def _parses(q: str, monkeypatch: pytest.MonkeyPatch, mode: Mode = "native") -> tuple[int, dict[str, Any]]:
    result = parse(q, mode)
    counting = _CountingParse()
    with monkeypatch.context() as m:
        m.setattr(clauses, "parse", counting)
        filters = filter_clauses(q, result)
    assert filters is not None
    return counting.calls, filters.model_dump(mode="json")


@pytest.mark.parametrize(
    ("q", "most"),
    [
        ("trust", 1),  # every field written out by one wrap
        ("trust venue:ICLR", 2),  # + the typed clause's splice
        ("trust venue:ICLR year:2024 track:main status:accepted", 4),  # one splice each, no wrap
        ("a" * 1853, 5),  # the wrap is too long, so each field is checked alone (golden: venue still fits)
        ("(" * 64 + "a" + ")" * 64, 1),  # too deep for one is too deep for all
        ("a" * 1880 + " venue:ICLR year:2020 track:main", 4),  # one field left: its wrap is checked once
    ],
)
def test_filter_clauses_cost_is_bounded(q: str, most: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """`/parse`'s extra work (security review): one parse for the wraps in the common case, and at most one
    per field on top when that edit can't be made. Counted, not timed."""
    calls, _ = _parses(q, monkeypatch)
    assert calls == most


# near-cap queries (up to 2,000 code points) parsed once per filter field and wrap: no per-example deadline
@given(q=st.one_of(queries(), near_cap_queries(1_800, 2_000)), mode=st.sampled_from(["native", "scholar"]))
@settings(max_examples=60, deadline=None)
def test_the_one_wrap_parse_answers_exactly_as_per_field_parses(q: str, mode: Mode) -> None:
    """Old vs new: every field with no clause gets the reason its own wrap alone gives, and the cost is at
    most one parse per typed clause plus one, or plus five when the combined wrap can't be written."""
    result = parse(q, mode)
    assume(result.ast is not None)
    with pytest.MonkeyPatch.context() as m:
        calls, got = _parses(q, m, mode)
    wrapped = [f for f in FILTER_FIELDS if got[f]["span"] == [len(q), len(q)] and not got[f]["negated"]]
    for field in wrapped:
        assert got[field]["reason"] == clauses._check_wrap(q, mode, (field,)), field
    typed = len(FILTER_FIELDS) - len(wrapped)
    assert calls <= typed + (1 if all(got[f]["toggleable"] for f in wrapped) else 1 + len(wrapped))


@pytest.mark.parametrize("depth", [62, 63, 64])
def test_the_one_wrap_parse_answers_exactly_as_per_field_parses_at_the_depth_limit(depth: int) -> None:
    q = "(" * depth + "a" + ")" * depth
    for mode in ("native", "scholar"):
        got = report(q, mode)
        for field in FILTER_FIELDS:
            assert got[field]["reason"] == clauses._check_wrap(q, mode, (field,))


def _splice(q: str, span: tuple[int, int], field: str, values: list[str]) -> str:
    """The reducer's edit (`search-state.ts::spliceClause`, `formatClause`): the grouped clause over the span,
    or `(q) AND clause` at the zero-width end span. Spans are code points, as Python indexes str."""
    text = f"{field}:({' OR '.join(values)})"
    start, end = span
    return f"({q}) AND {text}" if start == end == len(q) else q[:start] + text + q[end:]


def _field_of(n: Node) -> str | None:
    inner = n.child if isinstance(n, Not) else n
    return inner.field if isinstance(inner, Filter) else None


def _top(ast: Node | None) -> list[Node]:
    assert ast is not None
    return list(ast.children) if isinstance(ast, And) else [ast]


def _rest(ast: Node | None, field: str) -> Counter[str]:
    """The effective canonical conjuncts other than `field`'s clauses, structurally (spans ignored)."""
    return Counter(json.dumps(structure(c), sort_keys=True) for c in _top(ast) if _field_of(c) != field)


@given(q=clause_queries(), mode=st.sampled_from(["native", "scholar"]))
def test_every_single_value_click_on_a_toggleable_clause_parses_and_edits_only_that_clause(
    q: str, mode: Mode
) -> None:
    """Guarantee 3 for facet clicks (query-semantics review): every toggle and include a toggleable clause
    offers (each vocabulary value added or removed, never the last one) gives a query that parses, within the
    cap, whose top-level clause of the field admits exactly the new values, and whose every other effective
    conjunct is unchanged. The widest-edit check is sound for every edit because every edit is grouped."""
    before = parse(q, mode)
    assume(before.ast is not None)
    filters = filter_clauses(q, before)
    assert filters is not None
    for field in ("venue", "track", "status"):
        clause = getattr(filters, field)
        if not clause.toggleable:
            continue
        for value in VOCABULARY[field]:
            values = (
                [v for v in clause.values if v != value]
                if value in clause.values
                else [*clause.values, value]
            )
            if not values:
                continue  # LAST_VALUE: the reducer refuses
            edited = _splice(q, clause.span, field, values)
            assert len(edited) <= MAX_QUERY_LENGTH, edited
            after = parse(edited, mode)
            assert after.errors == [], (edited, [e.code for e in after.errors])
            assert _rest(after.effective_ast, field) == _rest(before.effective_ast, field), edited
            own = [c for c in _top(after.effective_ast) if _field_of(c) == field]
            assert len(own) == 1 and isinstance(own[0], Filter), edited
            assert sorted(map(str, own[0].values)) == sorted(values), edited


def test_the_grouped_form_has_the_bare_forms_canonical_string_and_hash() -> None:
    """A click writes `track:(main)` where a bare `track:main` would do: the search record doesn't change."""
    for bare, grouped in [("trust track:main", "trust track:(main)"), ("x year:2020", "x year:(2020)")]:
        a, b = parse(bare), parse(grouped)
        assert (a.canonical, a.canonical_hash) == (b.canonical, b.canonical_hash)


def test_models_refuse_inconsistent_reports() -> None:
    ok: dict[str, Any] = {
        "field": "venue",
        "negated": False,
        "span": (0, 1),
        "toggleable": True,
        "reason": None,
        "blocking_spans": [],
    }
    ParsedClause(**ok, values=["ICLR"])
    for bad in (
        {**ok, "span": None},  # values without a span
        {**ok, "blocking_spans": [(0, 1)]},  # blocking spans on a toggleable clause
        {**ok, "reason": "nested"},  # toggleable with a reason
        {**ok, "toggleable": False},  # not toggleable without one
        {**ok, "negated": True},  # a negated clause is never toggleable
    ):
        with pytest.raises(ValidationError):
            ParsedClause(**bad, values=["ICLR"])
    with pytest.raises(ValidationError):
        ParsedYearClause(**ok, ranges=None)
    ParsedYearClause(**ok, ranges=[YearRange(lo=2020, hi=2021)])
    negated = {**ok, "toggleable": False, "negated": True, "reason": "negated"}
    with pytest.raises(ValidationError):  # only multiple_clauses, nested and mixed_fields name clauses
        ParsedClause(**{**negated, "blocking_spans": [(0, 1)]}, values=["ICLR"])
    nested = {**ok, "span": None, "toggleable": False, "reason": "nested", "blocking_spans": [(0, 1)]}
    ParsedClause(**nested, values=None)


BLOCKING_CASES = [  # (q, field, reason, the clauses behind it, as text)
    ("track:workshop llm AND (venue:NeurIPS track:workshop)", "track", "multiple_clauses",
     ["track:workshop", "track:workshop"]),
    ("track:main NOT NOT (track:main a)", "track", "multiple_clauses", ["track:main", "NOT NOT (track:main a)"]),
    ("llm (a OR track:workshop)", "track", "nested", ["(a OR track:workshop)"]),
    ("NOT NOT (a track:workshop) b", "track", "nested", ["NOT NOT (a track:workshop)"]),
    ("x (track:workshop OR venue:ICLR)", "venue", "mixed_fields", ["(track:workshop OR venue:ICLR)"]),
    ("x (track:workshop OR venue:ICLR)", "track", "mixed_fields", ["(track:workshop OR venue:ICLR)"]),
    ("𝔘ber trust year:2020 (year:2021 y)", "year", "multiple_clauses", ["year:2020", "year:2021"]),
]  # fmt: skip


@pytest.mark.parametrize(("q", "field", "reason", "texts"), BLOCKING_CASES)
def test_blocking_spans_are_the_clauses_behind_the_reason(
    q: str, field: str, reason: str, texts: list[str]
) -> None:
    """TASK-091: code-point spans into `q` (an astral character before them counts one) of each written
    top-level conjunct holding a filter of the field, in order."""
    filters = filter_clauses(q, parse(q))
    assert filters is not None
    clause = getattr(filters, field)
    assert (clause.reason, clause.span, clause.toggleable) == (reason, None, False)
    assert [q[a:b] for a, b in clause.blocking_spans] == texts
    assert clause.blocking_spans == sorted(clause.blocking_spans)


@pytest.mark.parametrize("q", ["trust venue:ICLR", "trust", "NOT track:main x", "a" * 1950 + " track:main"])
def test_no_blocking_spans_for_any_other_clause(q: str) -> None:
    filters = filter_clauses(q, parse(q))
    assert filters is not None
    for field in ("venue", "year", "track", "status"):
        clause = getattr(filters, field)
        assert clause.reason not in ("multiple_clauses", "nested", "mixed_fields")
        assert clause.blocking_spans == []


# --- year actions (TASK-092) ---------------------------------------------------------------------------------
# `year-clause-golden.json` is shared with the reducer's test: here the server reports exactly each case's `year`,
# every expected string parses with its year clause admitting exactly `ranges_after`, and nothing else changes.

YEAR_GOLDEN: dict[str, Any] = json.loads(
    (ROOT / "frontend" / "src" / "lib" / "year-clause-golden.json").read_text(encoding="utf-8")
)
YEAR_CASES: list[dict[str, Any]] = YEAR_GOLDEN["cases"]


def test_year_golden_shares_the_servers_bounds() -> None:
    """The reducer's MAX_YEAR_RANGES and year bounds are checked against the same file (search-state.test.ts)."""
    assert YEAR_GOLDEN["max_year_ranges"] == clauses.MAX_YEAR_RANGES
    assert (YEAR_GOLDEN["min_year"], YEAR_GOLDEN["max_year"]) == (MIN_YEAR, MAX_YEAR)


def test_the_widest_year_edit_is_max_year_ranges_disjoint_full_width_ranges() -> None:
    """Every year clause a year action writes is at most this long, raw and canonical: at most
    MAX_YEAR_RANGES ranges, each at most `dddd..dddd`, kept apart by the canonical form."""
    widest = clauses.WIDEST_YEAR
    assert len(widest) == clauses.MAX_YEAR_RANGES
    assert all(len(f"{r.lo}..{r.hi}") == 10 for r in widest)
    assert all(a.hi + 1 < b.lo for a, b in pairwise(widest))
    clause = "year:(" + " OR ".join(f"{r.lo}..{r.hi}" for r in widest) + ")"
    assert clauses._widest_clause("year") == clause
    assert clause in (parse(f"x {clause}").canonical or "")


@pytest.mark.parametrize("case", YEAR_CASES, ids=[c["name"] for c in YEAR_CASES])
def test_year_golden_report(case: dict[str, Any]) -> None:
    assert report(text(case, "q"), case["mode"])["year"] == case["year"]


@pytest.mark.parametrize("case", [c for c in YEAR_CASES if "refused" not in c], ids=lambda c: c["name"])
def test_year_golden_edit_parses_and_changes_only_the_year_clause(case: dict[str, Any]) -> None:
    q, edited, mode = text(case, "q"), text(case, "expected"), case["mode"]
    before, after = parse(q, mode), parse(edited, mode)
    assert after.errors == [], [e.message for e in after.errors]
    assert len(edited) <= MAX_QUERY_LENGTH
    was, got = report(q, mode), report(edited, mode)
    assert got["year"]["toggleable"], got["year"]
    assert got["year"]["ranges"] == case["ranges_after"]
    assert _rest(after.effective_ast, "year") == _rest(before.effective_ast, "year")
    for field in ("venue", "track", "status"):  # the other clauses are reported alike (their spans may move)
        assert {k: v for k, v in got[field].items() if k != "span"} == {
            k: v for k, v in was[field].items() if k != "span"
        }


def test_year_golden_covers_every_action_and_reason() -> None:
    assert {c["action"]["type"] for c in YEAR_CASES} == {"yearSet", "yearClear", "yearAdd", "yearRemove"}
    assert {c["year"]["reason"] for c in YEAR_CASES} == {None, *CLAUSE_REASONS}


def _year_clause(ranges: list[YearRange]) -> str:
    """The reducer's year clause (`search-state.ts::formatYearClause`): grouped, sorted, merged."""
    return "year:(" + " OR ".join(str(r.lo) if r.lo == r.hi else f"{r.lo}..{r.hi}" for r in ranges) + ")"


def _merged(ranges: list[YearRange]) -> list[YearRange]:
    """Sorted, overlapping or adjacent ranges joined (`search-state.ts::mergeRanges`)."""
    out: list[YearRange] = []
    for r in sorted(ranges, key=lambda r: (r.lo, r.hi)):
        if out and r.lo <= out[-1].hi + 1:
            out[-1] = YearRange(lo=out[-1].lo, hi=max(out[-1].hi, r.hi))
        else:
            out.append(r)
    return out


_YEARS = st.integers(MIN_YEAR, MAX_YEAR)
# up to six drawn ranges, merged, then the first MAX_YEAR_RANGES of them: the most a year action writes
_RANGES = st.lists(
    st.tuples(_YEARS, _YEARS).map(lambda t: YearRange(lo=min(t), hi=max(t))), min_size=1, max_size=6
).map(lambda rs: _merged(rs)[: clauses.MAX_YEAR_RANGES])
# The seed at which drawing any clause or near-cap query and assume()ing the preconditions failed the
# filter_too_much health check every time (TASK-145); year_edit_cases builds the preconditions instead.
_FILTER_TOO_MUCH_SEED = 197275319351247031457750150800712837025


def _check_year_edit(case: YearEditCase, ranges: list[YearRange]) -> None:
    q, mode = case.q, case.mode
    before = parse(q, mode)
    filters = filter_clauses(q, before)
    assert filters is not None, (q, [e.code for e in before.errors])
    year = filters.year
    event(f"mode: {mode}")
    event(f"source: {case.source}")
    # a near miss: filter_clauses must refuse it, for the reason it was built with
    if case.reason is not None:
        event(f"near miss: {case.reason}")
        assert not year.toggleable and year.reason == case.reason, (q, year.reason)
        return
    assert year.toggleable and year.span is not None, (q, year.reason)  # year_edit_cases builds it so
    start, end = year.span
    clause = _year_clause(ranges)
    edited = f"({q}) AND {clause}" if start == end == len(q) else q[:start] + clause + q[end:]
    event("year clause: absent (wrapped)" if start == end == len(q) else "year clause: present (spliced)")
    if " OR year:" in q[start:end]:
        event("year clause: an OR of year filters")
    if q.count("year:") > q[start:end].count("year:"):
        event("year filter nested beside the clause")
    assert len(edited) <= MAX_QUERY_LENGTH, edited
    after = parse(edited, mode)
    assert after.errors == [], (edited, [e.code for e in after.errors])
    longest = max(len(edited), len(after.canonical or ""))  # the cap holds for both (decision-008)
    event("edit within 200 code points of the cap" if longest > MAX_QUERY_LENGTH - 200 else "edit shorter")
    assert _rest(after.effective_ast, "year") == _rest(before.effective_ast, "year"), edited
    own = [c for c in _top(after.effective_ast) if _field_of(c) == "year"]
    assert len(own) == 1 and isinstance(own[0], Filter) and list(own[0].values) == ranges, edited


_WIDEST = list(clauses.WIDEST_YEAR)


# One near miss per reason, pinned (year_edit_cases builds each only now and then); the cap's boundary (1,862
# code points still fit, 1,863 don't); a year filter nested beside the top-level clause; an OR of year filters as
# the clause
@example(case=YearEditCase("trust -year:2021", "native", "pinned", "negated"), ranges=_WIDEST)
@example(
    case=YearEditCase("trust year:2021 year:2020..2022", "scholar", "pinned", "multiple_clauses"),
    ranges=_WIDEST,
)
@example(case=YearEditCase("trust (year:2021 OR x)", "native", "pinned", "nested"), ranges=_WIDEST)
@example(
    case=YearEditCase("trust (year:2021 OR track:main)", "scholar", "pinned", "mixed_fields"), ranges=_WIDEST
)
@example(case=YearEditCase("a" * 1_863, "native", "pinned", "too_long"), ranges=_WIDEST)
@example(case=YearEditCase("year:2021 " + "a" * 1_900, "scholar", "pinned", "too_long"), ranges=_WIDEST)
@example(case=YearEditCase("(" * 64 + "a" + ")" * 64, "native", "pinned", "too_deep"), ranges=_WIDEST)
@example(case=YearEditCase("trust NOT NOT (year:2021 x)", "scholar", "pinned", "nested"), ranges=_WIDEST)
@example(case=YearEditCase("a" * 1_863, "scholar", "pinned", "too_long"), ranges=_WIDEST)
@example(case=YearEditCase("a" * 1_862, "native", "pinned"), ranges=_WIDEST)
@example(
    case=YearEditCase("year:2021 (year:2023 OR x) NOT (year:2017 a)", "native", "pinned"), ranges=_WIDEST
)
@example(case=YearEditCase("x (year:2021 OR year:2020..2022)", "scholar", "pinned"), ranges=_WIDEST)
# queries padded toward the length and depth caps, parsed with each year edit: no per-example deadline
@example(case=YearEditCase("a" * 1_862, "scholar", "pinned"), ranges=_WIDEST)
@given(case=year_edit_cases(), ranges=_RANGES)
@settings(deadline=None)
def test_every_year_edit_on_a_toggleable_clause_parses_and_edits_only_that_clause(
    case: YearEditCase, ranges: list[YearRange]
) -> None:
    """Guarantee 3 for the year control: any year clause a year action writes (at most MAX_YEAR_RANGES merged
    ranges) over a toggleable year clause gives a query that parses, within the cap, whose top-level year clause
    admits exactly those ranges, and whose every other effective conjunct is unchanged. And the near misses
    `year_edit_cases` builds (one step past a rule) are refused, with the reason they were built with."""
    _check_year_edit(case, ranges)


# 200 at every profile: the health check runs on the first draws, and the property's own run above is the one
# that scales with the profile; no per-example deadline, as above
@seed(_FILTER_TOO_MUCH_SEED)
@given(case=year_edit_cases(), ranges=_RANGES)
@settings(deadline=None, max_examples=200)
def test_the_year_edit_property_passes_at_the_seed_that_failed_its_health_check(
    case: YearEditCase, ranges: list[YearRange]
) -> None:
    """TASK-145 regression: the same property at the seed where it used to filter out too many draws."""
    _check_year_edit(case, ranges)
