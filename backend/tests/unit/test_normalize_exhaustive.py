"""Exhaustive tokenizer check over every Unicode code point (task-010 review): the char-by-char tokenizer
must equal the whole-string definition in `test_normalize.reference`, and re-indexing must be idempotent,
for each code point in 8 contexts. ~1.1M code points, so it runs only when OP_EXHAUSTIVE=1 (nightly)."""

import os

import pytest
from openproceedings.query.normalize import normalize

from .test_normalize import reference

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
        if c in "\\$":  # LaTeX syntax: covered by the golden table, not modelled by reference()
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
