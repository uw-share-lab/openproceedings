"""The frontend reducer's wrap goldens agree with the server parser (TASK-039 review, Should 1).

`frontend/src/lib/search-state.ts` writes an applied default out as `(q) AND field:(…)`. Each case in
`frontend/src/lib/wrap-golden.json` is either an exact expected string (the reducer's test pins it; here
the parser must accept both `q` and that string, and the string must mean `(identification_query) AND
<clause>`, canonical form for canonical form) or a `refused` q (the reducer throws; here the parser
accepts `q` but rejects its wrapped form, which is why the reducer must refuse it). Every case runs in
native and Scholar mode (M3a review gate).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query.clauses import filter_clauses
from openproceedings.query.parser import Mode, parse

GOLDEN = Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "wrap-golden.json"
CASES: list[dict[str, Any]] = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]


def _id(case: dict[str, Any]) -> str:
    return repr(case["q"])


MODES = ("native", "scholar")


def _clause(case: dict[str, Any]) -> str:
    return f"{case['field']}:({' OR '.join([*case['values'], case['add']])})"


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", [c for c in CASES if "expected" in c], ids=_id)
def test_expected_wrap_parses_and_keeps_the_meaning(case: dict[str, Any], mode: Mode) -> None:
    """The wrapped string means exactly the query's own part AND the widened clause: its canonical form is
    that of `(identification_query) AND <clause>`, so wrapping neither drops nor reinterprets anything."""
    original = parse(case["q"], mode)
    assert original.errors == [] and original.identification_query
    wrapped = parse(case["expected"], mode)
    assert wrapped.errors == [], [e.code for e in wrapped.errors]
    meant = parse(f"({original.identification_query}) AND {_clause(case)}")  # canonical text is native
    assert meant.errors == [] and wrapped.canonical == meant.canonical


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", [c for c in CASES if "refused" in c], ids=_id)
def test_refused_q_would_break_when_wrapped(case: dict[str, Any], mode: Mode) -> None:
    assert parse(case["q"], mode).errors == []
    naive = f"({case['q']}) AND {_clause(case)}"
    assert DiagnosticCode.PARSE_UNBALANCED_PAREN in [e.code for e in parse(naive, mode).errors]


def test_golden_has_both_kinds() -> None:
    assert any("expected" in c for c in CASES) and any("refused" in c for c in CASES)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=_id)
def test_parse_reports_the_clause_the_golden_wraps(case: dict[str, Any], mode: Mode) -> None:
    """TASK-078: `/parse` hands the reducer exactly the clause each golden starts from: the applied default at
    the zero-width span `(len(q), len(q))` with the golden's values, toggleable; a refused `q` (its wrap would
    not parse) is reported not toggleable, so the UI disables the control before the reducer sees it."""
    filters = filter_clauses(case["q"], parse(case["q"], mode))
    assert filters is not None
    clause = getattr(filters, case["field"])
    assert clause.span == (len(case["q"]), len(case["q"])) and sorted(clause.values) == sorted(case["values"])
    if "expected" in case:
        assert clause.toggleable, clause.reason
    else:
        assert (clause.toggleable, clause.reason) == (False, "unparsable_edit")
