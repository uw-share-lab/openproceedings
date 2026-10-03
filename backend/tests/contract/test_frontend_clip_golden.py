"""The frontend's `clip` quotes a value exactly as the backend's `diagnostics.clip` does (TASK-144, TASK-160).

`frontend/src/lib/clip.ts` is the twin of `diagnostics.clip` (error-diagnostics skill): the same escapes, the
same whitespace set, the same width in code points. `frontend/src/lib/clip-golden.json` holds what the backend
gives for each case below (the input as code points), and `clip.test.ts` requires the frontend to give the
same, so the two cannot drift.

This test fails when the file is stale. Regenerate it with
`(cd backend && uv run python -m tests.contract.test_frontend_clip_golden --write)` and commit it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from openproceedings.diagnostics import clip

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "frontend" / "src" / "lib" / "clip-golden.json"
GENERATED = (
    "by (cd backend && uv run python -m tests.contract.test_frontend_clip_golden --write); do not edit"
)

# (input, width): None is the default width (40)
CASES: list[tuple[str, int | None]] = [
    ("a`b", None),
    ("a\nb\t\tc", None),
    ("\x00\x1b", None),
    ("x\u202ey", None),
    ("a\u2028b", None),
    ("\ufeff", None),
    ("a\x1cb", None),
    ("a\x85b", None),
    ("\ud800", None),
    ("\U000e0001", None),
    ("k" * 50, None),
    ("a" * 38 + "`", None),
    ("\U0001f600" * 41, None),
    ("\\alpha", None),
    (" lead  trail ", None),
    ("a\u00a0b\u3000c\u200bd", None),  # NBSP and ideographic space collapse; a zero-width space is escaped
    ("\x7f\x9f\u061c\u2066\u2069", None),  # DEL, a C1 control, bidi marks and isolates
    ("main`\n\x00\x1b\u202e", None),  # the hostile value the call-site tests use
    ("ab`", 5),
    ("ab`", 6),
    ("abc", 3),
    ("abcd", 3),
    ("\U0001f600\U0001f600\U0001f600", 2),
    ("", None),
]


def build() -> dict[str, Any]:
    return {
        "_generated": GENERATED,
        "cases": [
            {
                # code points, not a string: a lone surrogate is not valid JSON text for every reader (Vite's)
                "input": [ord(c) for c in text],
                "width": width,
                "output": clip(text) if width is None else clip(text, width),
            }
            for text, width in CASES
        ],
    }


def render(data: dict[str, Any]) -> str:
    # ASCII escapes, so a lone surrogate, a control or a bidi character survives the file and any editor intact
    return json.dumps(data, ensure_ascii=True, indent=1) + "\n"


def test_the_frontend_clip_golden_is_current() -> None:
    assert GOLDEN.read_text(encoding="utf-8") == render(build()), (
        f"{GOLDEN.relative_to(ROOT)} is stale: run "
        "`(cd backend && uv run python -m tests.contract.test_frontend_clip_golden --write)` and commit it"
    )


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        sys.exit("usage: test_frontend_clip_golden.py --write")
    GOLDEN.write_text(render(build()), encoding="utf-8")
    print(f"wrote {GOLDEN.relative_to(ROOT)}")
