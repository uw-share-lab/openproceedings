"""`_tokenize_each_char` as it stood before TASK-088 (`query/normalize.py` at 05eff53, TASK-067's linear runs of
marks included), frozen as the oracle for the faster loop: `tests/unit/engine/test_highlight_speed.py` checks
that both give identical tokens (text, span and `op`) and the identical `Tail`. Only the loop is copied; the
helpers it calls (`_latex_mask`, `_fold`, `_cluster_spans`, …) are normalize's own, which TASK-088 did not
change. Never edit it to follow the tokenizer: it is the "before" of a differential test.
"""

from __future__ import annotations

import unicodedata

from openproceedings.query.normalize import (
    JOIN,
    KEEP,
    SEP,
    SUB,
    Tail,
    Token,
    _cluster_spans,
    _fold,
    _is_word_char,
    _latex_mask,
    _Op,
)


def _tokenize_each_char(text: str, tail: list[Tail] | None = None) -> list[Token]:
    """`tokenize`'s definition for any text, one raw character at a time (steps 1-5 above). Given a `tail`
    list, it appends the text's `Tail` to it."""
    subs: dict[int, tuple[str, bool, int, bool]] = {}
    latex = _latex_mask(text, subs=subs)
    out: list[Token] = []
    buf: list[str] = []
    start = end = 0
    base: str | None = None
    lead: int | None = None  # where markup before a word began (`\\"{O}del`): the word's span starts there
    # The separator pieces since the last word or operator TOKEN (the Tail). A word clears it only when it
    # is emitted: a marks-only word (`-` + a lone vowel sign) is dropped, so the `-` stays what the text ends
    # with (M3a gate round 2: clearing it on the mark let `vision-ަ*` pass as `vision*`).
    rest: list[str] = []
    rest_start = len(text)

    def close() -> None:
        nonlocal buf, rest
        if buf:
            word = unicodedata.normalize("NFC", "".join(buf))
            # A run of marks with no letter (a lone vowel sign) is not a word.
            if not all(unicodedata.category(ch).startswith("M") for ch in word):
                out.append(Token(word, start, end))
                rest = []
            buf = []

    n = len(text)
    # The run of combining marks last found (TASK-067): it ends at `run_end`, and `run_slash` is one past its
    # last slash (the run's start if it has none). A mark inside a run reuses them, so a run is scanned once,
    # not once per mark (quadratic: a `q` or an abstract of a few thousand marks cost seconds).
    run_end = run_slash = 0
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
            rest = []
            lead = None
            # an operator's name is its own token's: skip it, so no word after it starts inside it (`\\leq5`)
            i = cmd_end if operator else i + 1
            continue
        if latex[i] == SEP:
            close()
            base = lead = None
            if not rest:
                rest_start = i
            rest.append(c)
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
        if c < "\x80" and (stop == n or not unicodedata.combining(text[stop])):
            # an ASCII character with no mark after it (most characters of most texts; task-073): `_fold`
            # would give it back lower-cased, and it is a word character exactly when it is alphanumeric
            if c.isalnum():
                if not buf:
                    start = i if first is None else first
                base = c.lower()
                buf.append(base)
                end = stop
            else:
                close()
                base = None
                if not rest:
                    rest_start = i
                rest.append(c)
            i = stop
            continue
        if i + 1 > run_end:  # past the last run found: find where the marks after i end, and the last slash
            run_end = run_slash = i + 1
            while run_end < n and latex[run_end] == KEEP and unicodedata.combining(text[run_end]):
                if text[run_end] == "\u0338":
                    run_slash = run_end + 1
                run_end += 1
        j = run_end  # whether a position continues a run doesn't depend on where the run began
        cluster = run_slash > i + 1  # a slash among text[i + 1 : j]
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
                rest = []
            elif _is_word_char(piece):
                if not buf:
                    start = piece_start if first is None else first
                buf.append(piece)
                end = piece_end
            else:
                close()
                if not rest:
                    rest_start = i
                rest.append(piece)
            # markup before this character belongs to its first piece only: a word that starts after an
            # operator or a separator piece (`\\"∭` + slash + U+0345 → int ×3, then ι) starts at its own piece (task-075)
            first = None
        i = stop
    close()
    if tail is not None:
        tail.append(Tail(rest_start, "".join(rest)) if rest else Tail(len(text), ""))
    return out
