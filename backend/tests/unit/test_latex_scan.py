"""The LaTeX scan is linear (task-070): `_Closers` answers `_find` and `_find_closing_dollar` for every start
from one right-to-left pass, so an unclosed opener costs a lookup, not a scan to the end of the text. The
tables must agree with the scans exactly, or a token changes (the exhaustive suite checks tokens too)."""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest
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


def fastest(f: Callable[[str], object], arg: str) -> float:
    best = float("inf")
    for _ in range(9):  # best of 9: headroom when the machine is busy
        t = time.perf_counter()
        f(arg)
        best = min(best, time.perf_counter() - t)
    return best


@pytest.mark.parametrize("unit", ["$1", "\\(", "\\["])  # `$$` never was quadratic: it closes at the next `$$`
def test_unclosed_openers_are_linear(unit: str) -> None:
    # quadratic before task-070. Quadrupling the text costs ~4x when linear, ~16x when quadratic; the
    # ratio doesn't depend on the machine, and the old scan fails it in about 4 s per opener
    small, large = (fastest(tokenize, unit * (n // len(unit))) for n in (2_000, 8_000))
    assert large / small < 8, (unit, small, large)
    assert fastest(parse, unit * (2_000 // len(unit))) < 0.25, unit  # at the query cap
