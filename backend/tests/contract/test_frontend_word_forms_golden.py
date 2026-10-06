"""The frontend's "Add `$`" edit writes exactly the query the server read back (TASK-175; spec 02 §Word forms).

`POST /parse` reports where a `$` can go (`word_forms`: code-point `at`, `insert`), and
`frontend/src/lib/word-forms.ts` splices them into the draft. `frontend/src/lib/word-forms-golden.json` holds,
for each query below, the server's report (and the notice it hangs from; the terms it skips and why, TASK-192), the query with
every edit made, and the query with each one made alone, all written by `query.wordforms.apply`; `word-forms.test.ts` requires the frontend's splice to give the
same strings (astral characters included: the offsets are code points, the editor's are UTF-16), and
`test_parse_word_forms.py` that `/parse` serves the same report.

This test fails when the file is stale. Regenerate it with
`(cd backend && uv run python -m tests.contract.test_frontend_word_forms_golden --write)` and commit it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query.parser import MAX_QUERY_LENGTH, Mode, parse
from openproceedings.query.wordforms import apply, report

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "frontend" / "src" / "lib" / "word-forms-golden.json"
GENERATED = (
    "by (cd backend && uv run python -m tests.contract.test_frontend_word_forms_golden --write); do not edit"
)
LINES = (ROOT / "backend" / "tests" / "fixtures" / "queries" / "trust-evals.txt").read_text().split("\n")
TRUST_EVALS = {LINES[i][3:]: LINES[i + 1] for i in range(len(LINES) - 1) if LINES[i].startswith("## ")}

# two code points under the cap: `trust`, written in hundreds of places, has no room for its `$` in all of them,
# the two left go to `model` and `agent`, and `judge` (no room) and `AI` (too short) are named as skipped (TASK-192)
_TAIL = " OR model OR agent OR judge OR AI"
_HEAD = " OR ".join(["trust"] * ((MAX_QUERY_LENGTH - 2 - len(_TAIL)) // 9))
NEAR_CAP = _HEAD + " " * (MAX_QUERY_LENGTH - 2 - len(_TAIL) - len(_HEAD)) + _TAIL

# (name, query, mode): only the inputs are chosen here
CASES: list[tuple[str, str, Mode]] = [
    ("words", "LLM benchmark", "scholar"),
    ("phrase: last word only", '("large language model" OR LLM) trust', "scholar"),
    ("Scholar | item read as a phrase", "(large language model | LLM)", "scholar"),
    (
        "wildcards and filter values are left alone",
        "model$ bench* trust year:2020..2024 source:PMLR",
        "scholar",
    ),
    ("short stems and symbols are left alone", 'AI C++ US$5 "generative AI"', "scholar"),
    ("two words in one unspaced run", "(model|LLM) trust", "scholar"),
    ("each place a term is written", "trust OR (trust AND model)", "scholar"),
    ("field prefix, NOT and NEAR", 'title:trust -bias model NEAR/3 "language model"', "scholar"),
    ("astral letters before the terms", "𝒜𝒜𝒜 (model|LLM) \U0001f600\U0001f600trust", "scholar"),
    ("lowercase operator words are left alone", "trust | LLM and model not", "scholar"),
    ("no named term can take a $", "AI C++ or", "scholar"),
    ("nothing the notice names", "bench* model$", "scholar"),
    ("native syntax has no notice", "LLM benchmark", "native"),
    ("a query with errors", "(LLM benchmark", "scholar"),
    ("the review's primary string", TRUST_EVALS["main-7-most-updated"], "scholar"),
    ("near the length cap", NEAR_CAP, "scholar"),
]


def build() -> dict[str, Any]:
    cases = []
    for name, q, mode in CASES:
        result = parse(q, mode)
        found = report(q, result)
        forms = None if found is None else found.forms
        notice = [t.message for t in result.translations if t.code is DiagnosticCode.COMPAT_NO_STEMMING]
        cases.append(
            {
                "name": name,
                "q": q,
                "mode": mode,
                "notice": notice[0] if notice else None,  # the `COMPAT_NO_STEMMING` message, for UI tests
                "word_forms": None if forms is None else [f.model_dump() for f in forms],
                "word_forms_skipped": None if found is None else [t.model_dump() for t in found.skipped],
                "all": None if forms is None else apply(q, forms),
                "each": None if forms is None else [apply(q, [f]) for f in forms],
            }
        )
    return {"_generated": GENERATED, "cases": cases}


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def test_the_frontend_word_forms_golden_is_current() -> None:
    assert GOLDEN.read_text(encoding="utf-8") == render(build()), (
        f"{GOLDEN.relative_to(ROOT)} is stale: run "
        "`(cd backend && uv run python -m tests.contract.test_frontend_word_forms_golden --write)` and commit it"
    )


def test_the_golden_covers_each_kind_of_answer() -> None:
    cases = build()["cases"]
    assert any(c["word_forms"] is None for c in cases)  # errors
    assert any(c["word_forms"] == [] and c["mode"] == "native" for c in cases)
    assert any(f["insert"] == "$ " for c in cases for f in c["word_forms"] or [])
    assert any(c["word_forms"] == [] and c["notice"] for c in cases)  # a notice with nothing to offer
    reasons = {t["reason"] for c in cases for t in c["word_forms_skipped"] or []}
    assert reasons == {
        "too_short",
        "symbol",
        "dollar_nearby",
        "operator_word",
        "too_long",
    }  # not `unconfirmed`
    assert any(
        c["word_forms"] and any(t["reason"] == "too_long" for t in c["word_forms_skipped"]) for c in cases
    )
    assert any(
        len(c["q"].encode("utf-16-le")) // 2 != len(c["q"]) for c in cases
    )  # astral: UTF-16 ≠ code points


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        sys.exit("usage: test_frontend_word_forms_golden.py --write")
    GOLDEN.write_text(render(build()), encoding="utf-8")
    print(f"wrote {GOLDEN.relative_to(ROOT)}")
