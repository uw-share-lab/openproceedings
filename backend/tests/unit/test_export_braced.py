"""`export._braced` after its output-identical guards (M3a review gate round 2): a value with no brace skips
the balance count, `&%#` are escaped by one pass that reads each backslash run whole (only when one occurs),
and `@` is rewritten only when one occurs. Held byte for byte to a frozen copy of the function as it was.

And after TASK-274: its three backslash-run patterns start a match only where a run starts (`(?<!\\)`), so a
long run costs one pass instead of one attempt per backslash. Held to the patterns as they were, exhaustively
over every short string of the characters they read, and in CPU growth over a long run."""

from __future__ import annotations

import re
from collections.abc import Callable
from itertools import product

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from openproceedings import export
from openproceedings.export import _debraced, _one_line

from tests.timing import growth

# --- frozen: export.py's `_balances` and `_braced` before the guards (30756ce) ------------------------------
_BRACE = re.compile(r"(\\*)[{}]")
_EVEN_BACKSLASHES = r"(?<!\\)((?:\\\\)*)"
_AT = re.compile(r"(\\*)@")


def _old_balances(text: str, *, escaped_count: bool) -> bool:
    depth = 0
    for m in _BRACE.finditer(text):
        if len(m.group(1)) >= 2:
            return False
        if not escaped_count and len(m.group(1)) % 2 == 1:
            continue
        depth += 1 if text[m.end() - 1] == "{" else -1
        if depth < 0:
            return False
    return depth == 0


def _old_braced(text: str) -> str:
    text = _one_line(text)
    if not (_old_balances(text, escaped_count=True) and _old_balances(text, escaped_count=False)):
        text = _debraced(text)
    text = re.sub(_EVEN_BACKSLASHES + r"([&%#])", r"\1\\\2", text)
    text = _AT.sub(lambda m: m.group(1)[: len(m.group(1)) // 2 * 2] + "{@}", text)
    if text.endswith("\\"):
        text += " "
    return "{" + text + "}"


# ------------------------------------------------------------------------------------------------------------

# the characters `_braced` treats specially, dense enough that runs of backslashes before them are common
TRICKY = st.text(alphabet=st.sampled_from(list("\\\\\\{}&%#@$_ aé\n\t\x01")), max_size=40)


@settings(max_examples=3_000)
@given(st.one_of(TRICKY, st.text(max_size=60)))
@example("")
@example("\\&")
@example("\\\\&")
@example("\\\\\\%")
@example("a & b \\# c \\\\\\\\# d")
@example("{BERT} & {GPT}")
@example("\\{x} @article{y, \\@ \\\\@")
@example("ends in a backslash \\")
def test_braced_is_the_frozen_function_byte_for_byte(text: str) -> None:
    assert export._braced(text) == _old_braced(text)


@settings(max_examples=2_000)
@given(TRICKY, st.booleans())
def test_balances_is_the_frozen_function(text: str, escaped_count: bool) -> None:
    assert export._balances(text, escaped_count=escaped_count) == _old_balances(
        text, escaped_count=escaped_count
    )


# --- frozen: export.py's three backslash-run patterns before TASK-274 (f81c71cc) -----------------------------
# A match could start at any backslash: on a run that no brace, `&%#` or `@` ends, `\\*` took the rest of the
# run and gave it back one backslash at a time at every start, so a run of n cost ~n²/2 steps (TASK-274: 7.3 s
# for one 20,000-character abstract).
_PRE274 = {
    "_BRACE": re.compile(r"(\\*)[{}]"),
    "_SPECIAL": re.compile(r"(\\*)([&%#])"),
    "_AT": re.compile(r"(\\*)@"),
}

# every character the three patterns and `_braced` read (a backslash, what ends a run, one ordinary character)
ALPHABET = "\\{}&%#@x"
EXHAUSTIVE = (
    6  # every string up to 6 characters: 299,593 strings, runs of up to 5 backslashes before a character
)


def _every_short_string() -> list[str]:
    return ["".join(p) for n in range(EXHAUSTIVE + 1) for p in product(ALPHABET, repeat=n)]


def _matches(pattern: re.Pattern[str], text: str) -> list[tuple[tuple[int, int], tuple[str | None, ...]]]:
    return [(m.span(), m.groups()) for m in pattern.finditer(text)]


@pytest.fixture(scope="module")
def short_strings() -> list[str]:
    return _every_short_string()


def test_each_pattern_finds_the_same_matches_as_before_on_every_short_string(
    short_strings: list[str],
) -> None:
    """The same spans and groups, so every `sub`, `finditer` and replacement built on them is unchanged."""
    for name, old in _PRE274.items():
        new = getattr(export, name)
        assert new.pattern.startswith("(?<!\\\\)"), name  # anchored at a run's start (AC #1)
        for text in short_strings:
            assert _matches(new, text) == _matches(old, text), (name, text)


def _pre274(f: Callable[[], str]) -> str:
    """`f()` with export's three patterns put back as they were before TASK-274."""
    saved = {name: getattr(export, name) for name in _PRE274}
    try:
        for name, old in _PRE274.items():
            setattr(export, name, old)
        return f()
    finally:
        for name, new in saved.items():
            setattr(export, name, new)


def test_braced_balances_and_debraced_are_byte_identical_on_every_short_string(
    short_strings: list[str],
) -> None:
    def outputs() -> list[tuple[str, str, bool, bool]]:
        return [
            (
                export._braced(t),
                export._debraced(t),
                export._balances(t, escaped_count=True),
                export._balances(t, escaped_count=False),
            )
            for t in short_strings
        ]

    before = _pre274(outputs)
    after = outputs()
    assert len(before) == len(after) == len(short_strings)
    for text, old, new in zip(short_strings, before, after, strict=True):
        assert new == old, text


@given(
    st.one_of(TRICKY, st.text(alphabet=st.sampled_from(list(ALPHABET)), max_size=80), st.text(max_size=60))
)
@example("{" + "\\" * 40 + "x&@")
def test_braced_is_byte_identical_to_the_pre274_patterns(text: str) -> None:
    """Longer strings than the exhaustive check reaches, the patterns' callers included (`_braced` and its
    `_balances`, `_debraced`, `_escape_special`)."""
    assert export._braced(text) == _pre274(lambda: export._braced(text))


@pytest.mark.parametrize(
    "shape",
    [
        pytest.param(lambda n: "{" + "\\" * n + "x", id="brace"),  # `_balances` and `_debraced`: `_BRACE`
        pytest.param(lambda n: "\\" * n + "x&", id="special"),  # `_SPECIAL`
        pytest.param(lambda n: "\\" * n + "x@", id="at"),  # `_AT`
        pytest.param(lambda n: "{" + "\\" * n + "x&@", id="all"),  # TASK-274's abstract: every pass
    ],
)
def test_braced_is_linear_in_a_backslash_run(shape: Callable[[int], str]) -> None:
    """testing-standards §CPU growth checks: quadrupling the run costs ~4x when linear, ~16x when quadratic.
    Before TASK-274 every backslash of a run that no brace, `&%#` or `@` ends started a match attempt that read
    the rest of the run (n = 1,000 to 4,000: ratios 15.8-16.0, `all` 0.27 s a call at 4,000)."""
    small_arg, large_arg = shape(1_000), shape(4_000)
    # tests/timing.py's paired, median measure, eight calls a sample, the garbage collector paused
    ratio, pairs = growth(
        lambda: export._braced(small_arg), lambda: export._braced(large_arg), floor=1e-9, calls=8
    )
    assert ratio < 8, (ratio, pairs)
