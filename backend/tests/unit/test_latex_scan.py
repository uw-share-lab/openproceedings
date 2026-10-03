"""The LaTeX scan is linear (task-070): `_Closers` answers `_find` and `_find_closing_dollar` for every start
from one right-to-left pass, so an unclosed opener costs a lookup, not a scan to the end of the text. The
tables must agree with the scans exactly, or a token changes (the exhaustive suite checks tokens too)."""

from __future__ import annotations

import time
from collections.abc import Callable
from statistics import median

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
        t = time.thread_time()  # CPU time: being preempted on a busy machine doesn't count
        f(arg)
        best = min(best, time.thread_time() - t)
    return best


def cpu_batch(f: Callable[[str], object], arg: str) -> float:
    """Amortize the CPU clock over eight calls without excluding allocation or GC cost."""
    t = time.thread_time()
    for _ in range(8):
        f(arg)
    return (time.thread_time() - t) / 8


@pytest.mark.parametrize("unit", ["$1", "\\(", "\\["])  # `$$` never was quadratic: it closes at the next `$$`
def test_unclosed_openers_are_linear(unit: str) -> None:
    # Quadratic before task-070: quadrupling the input costs ~4x when linear and ~16x when
    # quadratic. Keep the <8 boundary, but pair nearby CPU measurements: independent minima
    # can compare a fast small-input phase with a slower large-input phase (nightly 37053299707).
    small_arg, large_arg = (unit * (n // len(unit)) for n in (2_000, 8_000))
    tokenize(small_arg)
    tokenize(large_arg)
    pairs = []
    for round_number in range(9):
        # Alternate order to reduce size-correlated CPU frequency and allocation drift.
        if round_number % 2:
            large = cpu_batch(tokenize, large_arg)
            small = cpu_batch(tokenize, small_arg)
        else:
            small = cpu_batch(tokenize, small_arg)
            large = cpu_batch(tokenize, large_arg)
        pairs.append((small, large))
    ratio = median(large / small for small, large in pairs)
    assert ratio < 8, (unit, ratio, pairs)
    # at the query cap: ~10 ms now, 0.3-0.8 s quadratic; 1 s leaves slow CI runners room (the ratio is the check)
    assert fastest(parse, unit * (2_000 // len(unit))) < 1.0, unit
