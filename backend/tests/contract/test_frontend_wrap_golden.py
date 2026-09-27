"""The frontend reducer's wrap goldens agree with the server parser (TASK-039 review, Should 1).

`frontend/src/lib/search-state.ts` writes an applied default out as `(q) AND field:(…)`. Each case in
`frontend/src/lib/wrap-golden.json` is either an exact expected string (the reducer's test pins it; here
the parser must accept both `q` and that string) or a `refused` q (the reducer throws; here the parser
accepts `q` but rejects its wrapped form, which is why the reducer must refuse it).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query.parser import parse

GOLDEN = Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "wrap-golden.json"
CASES: list[dict[str, Any]] = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]


def _id(case: dict[str, Any]) -> str:
    return repr(case["q"])


@pytest.mark.parametrize("case", [c for c in CASES if "expected" in c], ids=_id)
def test_expected_wrap_parses(case: dict[str, Any]) -> None:
    assert parse(case["q"]).errors == []
    wrapped = parse(case["expected"])
    assert wrapped.errors == [], [e.code for e in wrapped.errors]


@pytest.mark.parametrize("case", [c for c in CASES if "refused" in c], ids=_id)
def test_refused_q_would_break_when_wrapped(case: dict[str, Any]) -> None:
    assert parse(case["q"]).errors == []
    values = [*case["values"], case["add"]]
    naive = f"({case['q']}) AND {case['field']}:({' OR '.join(values)})"
    assert DiagnosticCode.PARSE_UNBALANCED_PAREN in [e.code for e in parse(naive).errors]


def test_golden_has_both_kinds() -> None:
    assert any("expected" in c for c in CASES) and any("refused" in c for c in CASES)
