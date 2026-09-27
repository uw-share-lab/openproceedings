"""Each filter field's top-level clause for facet clicks (TASK-078; spec 02 §Filter clauses; decision-011).

The goldens are shared with the frontend reducer's test (`frontend/src/lib/filter-clause-golden.json`): here
`query.clauses.filter_clauses` must report exactly the listed clauses, and every expected click result must
parse with the clicked field's clause admitting the new values, so the reducer's splice and the server agree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from openproceedings.query.ast import FILTER_FIELDS, YearRange
from openproceedings.query.clauses import (
    CLAUSE_REASONS,
    EVERY_YEAR,
    VOCABULARY,
    ParsedClause,
    ParsedYearClause,
    filter_clauses,
)
from openproceedings.query.parser import MAX_QUERY_LENGTH, Mode, parse
from pydantic import ValidationError

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


def test_a_typed_clause_at_depth_64_is_still_editable() -> None:
    """A splice inside the query adds no nesting (`track:(…)` is not a group level); only the wrap does."""
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


def test_models_refuse_inconsistent_reports() -> None:
    ok: dict[str, Any] = {
        "field": "venue",
        "negated": False,
        "span": (0, 1),
        "toggleable": True,
        "reason": None,
    }
    ParsedClause(**ok, values=["ICLR"])
    for bad in (
        {**ok, "span": None},  # values without a span
        {**ok, "reason": "nested"},  # toggleable with a reason
        {**ok, "toggleable": False},  # not toggleable without one
        {**ok, "negated": True},  # a negated clause is never toggleable
    ):
        with pytest.raises(ValidationError):
            ParsedClause(**bad, values=["ICLR"])
    with pytest.raises(ValidationError):
        ParsedYearClause(**ok, ranges=None)
    ParsedYearClause(**ok, ranges=[YearRange(lo=2020, hi=2021)])
