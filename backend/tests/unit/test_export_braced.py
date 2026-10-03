"""`export._braced` after its output-identical guards (M3a review gate round 2): a value with no brace skips
the balance count, `&%#` are escaped by one pass that reads each backslash run whole (only when one occurs),
and `@` is rewritten only when one occurs. Held byte for byte to a frozen copy of the function as it was."""

from __future__ import annotations

import re

from hypothesis import example, given, settings
from hypothesis import strategies as st
from openproceedings import export
from openproceedings.export import _debraced, _one_line

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
