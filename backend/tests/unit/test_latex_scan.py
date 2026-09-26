"""The LaTeX scan is linear (task-070): `_Closers` answers `_find` and `_find_closing_dollar` for every start
from one right-to-left pass, so an unclosed opener costs a lookup, not a scan to the end of the text. The
tables must agree with the scans exactly, or a token changes (the exhaustive suite checks tokens too)."""

from __future__ import annotations

import time

from hypothesis import given
from hypothesis import strategies as st
from openproceedings.query.normalize import _Closers, _find, _find_closing_dollar, tokenize
from openproceedings.query.parser import parse

TEXTS = st.text(alphabet="$\\()[] 1a\t", max_size=40)


@given(TEXTS)
def test_the_tables_answer_exactly_what_the_scans_do(text: str) -> None:
    closers = _Closers(text)
    for start in range(len(text) + 3):
        for closer in ("\\)", "\\]", "$$"):
            assert closers.find(start, closer) == _find(text, start, closer), (text, start, closer)
    for i, c in enumerate(text):
        if c == "$":
            assert closers.dollar(i) == _find_closing_dollar(text, i), (text, i)


def fastest(f: object, arg: str) -> float:
    best = float("inf")
    for _ in range(3):
        t = time.perf_counter()
        f(arg)  # type: ignore[operator]
        best = min(best, time.perf_counter() - t)
    return best


def test_unclosed_openers_are_linear() -> None:
    # quadratic before task-070: 0.56-0.78 s for `$1` at the 2,000-character query cap, ~200 s at 40,000
    for unit in ("$1", "\\(", "\\[", "$$1"):
        assert fastest(parse, unit * (2_000 // len(unit))) < 0.25, unit
        assert fastest(tokenize, unit * (40_000 // len(unit))) < 2.0, unit
