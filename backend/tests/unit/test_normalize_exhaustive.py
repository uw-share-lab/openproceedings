"""Exhaustive tokenizer check over every Unicode code point (task-010 review): the char-by-char tokenizer
must equal the whole-string definition in `test_normalize.reference`, and re-indexing must be idempotent,
for each code point in 8 contexts; and (tokenizer 3) every Unicode form of each code point in those contexts and in
LaTeX ones tokenizes alike. ~1.1M code points, so it runs only when OP_EXHAUSTIVE=1 (nightly)."""

import os
import unicodedata

import pytest
from openproceedings.query.normalize import normalize

from .test_normalize import LATEX_SYNTAX, reference

pytestmark = pytest.mark.skipif(
    os.environ.get("OP_EXHAUSTIVE") != "1", reason="exhaustive: set OP_EXHAUSTIVE=1"
)

CONTEXTS = ("{c}", "a{c}", "{c}a", "a{c}a", "{c}{c}", "ᄀ{c}", "{c}́", "α{c}ͅ")


def test_every_code_point_in_every_context() -> None:
    divergent, not_idempotent = [], []
    for cp in range(0x110000):
        if 0xD800 <= cp <= 0xDFFF:
            continue
        c = chr(cp)
        if c in LATEX_SYNTAX:  # LaTeX syntax: covered by the golden table, not modelled by reference()
            continue
        for ctx in CONTEXTS:
            text = ctx.format(c=c)
            tokens = normalize(text)
            if tokens != reference(text):
                divergent.append(text)
            if normalize(" ".join(tokens)) != tokens:
                not_idempotent.append(text)
    assert not divergent, [t.encode("unicode_escape") for t in divergent[:20]]
    assert not not_idempotent, [t.encode("unicode_escape") for t in not_idempotent[:20]]


# LaTeX contexts where a backslash or math reads the character after it (TASK-168: `\\` + an accented letter)
LATEX_CONTEXTS = ("\\{c}", "a\\{c}a", "\\H{{{c}}}a", '\\"{c}', "${c}$", "$\\{c}$", "$x^{c}$", "{c}\\{c}")


def test_every_unicode_form_of_every_code_point_tokenizes_alike() -> None:
    divergent = []
    for cp in range(0x110000):
        if 0xD800 <= cp <= 0xDFFF:
            continue
        c = chr(cp)
        for ctx in CONTEXTS + LATEX_CONTEXTS:
            text = ctx.format(c=c)
            # a text that is all four of its forms has nothing to compare (most: the check stays minutes long)
            forms = {unicodedata.normalize(f, text) for f in ("NFC", "NFD", "NFKC", "NFKD")} - {text}
            if forms and any(normalize(form) != normalize(text) for form in forms):
                divergent.append(text)
    assert not divergent, [t.encode("unicode_escape") for t in divergent[:20]]
