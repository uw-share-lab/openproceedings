"""`tokenize` as it stood before task-073 (`query/normalize.py` at dcdd129), frozen as the oracle for the faster
one: `tests/unit/engine/test_highlight_speed.py` checks that both give identical tokens (text, span and
`op`). Only the loop is copied; the helpers it calls (`_latex_mask`, `_fold`, `_cluster_spans`, …) are
normalize's own, which task-073 did not change. Never edit it to follow the tokenizer: it is the "before"
of a differential test. (The one edit since: `Token.reach` was retired after decision-008, as nothing read it,
so its bookkeeping was removed here too; texts, spans and `op` are computed exactly as before.)
"""

from __future__ import annotations

import unicodedata

from openproceedings.query.normalize import (
    JOIN,
    KEEP,
    SEP,
    SUB,
    Token,
    _cluster_spans,
    _fold,
    _is_word_char,
    _latex_mask,
    _Op,
)


def tokenize(text: str) -> list[Token]:
    """Tokens of `text` with their raw code-point spans."""
    subs: dict[int, tuple[str, bool, int, bool]] = {}
    latex = _latex_mask(text, subs=subs)
    out: list[Token] = []
    buf: list[str] = []
    start = end = 0
    base: str | None = None
    lead: int | None = None  # where markup before a word began (`\\"{O}del`): the word's span starts there

    def close() -> None:
        nonlocal buf
        if buf:
            word = unicodedata.normalize("NFC", "".join(buf))
            # A run of marks with no letter (a lone vowel sign) is not a word.
            if not all(unicodedata.category(ch).startswith("M") for ch in word):
                out.append(Token(word, start, end))
            buf = []

    n = len(text)
    i = 0
    while i < n:
        c, stop = text[i], i + 1
        if latex[i] == SUB:  # a math command with a Unicode spelling; its span starts at its name
            spelling, operator, cmd_end, split = subs[i]
            if operator or split:
                close()
            if operator:  # a token of its own
                out.append(Token(spelling, i + 1, cmd_end, op=True))
                base = None
            else:  # a Greek letter: part of the word, like the letter itself
                folded, base = _fold(spelling, base)
                if not buf:
                    start = i + 1 if lead is None else lead
                buf.extend(p for p in folded if isinstance(p, str))
                end = cmd_end
            lead = None
            # an operator's name is its own token's: skip it, so no word after it starts inside it (`\\leq5`)
            i = cmd_end if operator else i + 1
            continue
        if latex[i] == SEP:
            close()
            base = lead = None
            i += 1
            continue
        if latex[i] == JOIN:  # markup inside a word: keep the word open and cover the markup in its span
            if buf:
                end = i + 1
            elif lead is None:  # markup before any letter: a word starting next starts here
                lead = i
            i += 1
            continue
        first, lead = lead, None
        j = i + 1
        while j < n and latex[j] == KEEP and unicodedata.combining(text[j]):
            j += 1
        cluster = "\u0338" in text[i + 1 : j]
        if cluster:
            # a slash among the marks after a character: NFKC the whole cluster, as the whole-string rule
            # would (`∈` + slash is `∉`, full-width `＝` + slash is `≠`, whatever the marks' order)
            c, stop = text[i:j], j
        folded, folded_base = _fold(c, base)
        spans = _cluster_spans(text, i, j, folded, base) if cluster else [(i, stop)] * len(folded)
        base = folded_base
        if not folded:  # combining mark or invisible format char: extends an open word, never starts one
            if buf:
                end = stop
            i = stop
            continue
        for piece, (piece_start, piece_end) in zip(folded, spans, strict=True):
            if isinstance(piece, _Op):
                close()
                out.append(Token(piece.name, piece_start, piece_end, op=True))
            elif _is_word_char(piece):
                if not buf:
                    start = piece_start if first is None else first
                buf.append(piece)
                end = piece_end
            else:
                close()
            # markup before this character belongs to its first piece only: a word that starts after an
            # operator or a separator piece (`\\"∭` + slash + U+0345 → int ×3, then ι) starts at its own piece (task-075)
            first = None
        i = stop
    close()
    return out
