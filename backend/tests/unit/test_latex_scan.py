"""The LaTeX scan is linear (task-070): `_Closers` answers `_find` and `_find_closing_dollar` for every start
from one right-to-left pass, so an unclosed opener costs a lookup, not a scan to the end of the text. The
tables must agree with the scans exactly, or a token changes (the exhaustive suite checks tokens too)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.query.normalize import _Closers, _find, _find_closing_dollar, tokenize
from openproceedings.query.parser import parse

from tests.timing import cpu, growth

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


@pytest.mark.parametrize("unit", ["$1", "\\(", "\\["])  # `$$` never was quadratic: it closes at the next `$$`
def test_unclosed_openers_are_linear(unit: str) -> None:
    # Quadratic before task-070: quadrupling the input costs ~4x when linear and ~16x when quadratic. Pair nearby
    # CPU measurements (independent minima compared a fast small-input phase with a slower large-input phase,
    # nightly 37053299707): tests/timing.py's `growth`, eight calls a sample, nine paired rounds, median ratio
    small_arg, large_arg = (unit * (n // len(unit)) for n in (2_000, 8_000))
    ratio, pairs = growth(lambda: tokenize(small_arg), lambda: tokenize(large_arg), floor=1e-6, calls=8)
    assert ratio < 8, (unit, ratio, pairs)
    # at the query cap: ~10 ms now, 0.3-0.8 s quadratic; 1 s leaves slow CI runners room (the ratio is the check)
    assert min(cpu(lambda: parse(unit * (2_000 // len(unit)))) for _ in range(9)) < 1.0, unit
