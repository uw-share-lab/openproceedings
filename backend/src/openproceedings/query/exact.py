"""The terms a query matches exactly, and which of them can take a `$` as written (TASK-175, TASK-181; spec
02 §Word forms).

Scholar mode's `COMPAT_NO_STEMMING` notice names the exact terms (`exact_leaves`, `exact_name`) and ends with an
example of one made a wildcard; `wordforms.py` reports where the UI may write a `$`. Both ask the same
question, "is `$` a valid wildcard on this term as written?", and `dollar_places` is its one answer: the
notice's example is always a term the UI would offer, never one the parser would refuse (`ai$`).

This module sits below `parser.py` (which builds the notice) and `wordforms.py` (which parses the edited
query to read it back), so neither imports the other's work and `parse` never recurses. The rules are stated
in `wordforms.py`'s docstring and spec 02 §Word forms.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from collections.abc import Sequence
from typing import NamedTuple

from openproceedings.query.ast import And, Near, Node, Not, Or, Phrase, Term, Wildcard
from openproceedings.query.lexer import (
    DOLLARS,
    LATEX_LOOKALIKES,
    MIN_STEM,
    OPERATOR_WORDS,
    QUOTES,
    Kind,
    Lexeme,
    letters,
)
from openproceedings.query.normalize import tokenize_with_tail

# a run holding one of these may already have LaTeX math or an escape in it: a `$` added there is not offered
_BACKSLASHES = frozenset({"\\"} | {c for c, to in LATEX_LOOKALIKES.items() if to == "\\"})
_LOWER_NEAR = re.compile(r"near/[0-9]+")
_LATEX = DOLLARS | frozenset(LATEX_LOOKALIKES) | _BACKSLASHES


def exact_leaves(n: Node) -> list[Term | Phrase]:
    """Words and phrases matched exactly (no wildcard), in order: what Scholar would have stemmed. The
    no-stemming notice names them; `dollar_places` says which can take a `$`."""
    if isinstance(n, Term):
        return [n]
    if isinstance(n, Phrase) and not any(isinstance(i, Wildcard) for i in n.items):
        return [n]
    if isinstance(n, Near):
        return exact_leaves(n.left) + exact_leaves(n.right)
    if isinstance(n, Not):
        return exact_leaves(n.child)
    if isinstance(n, And | Or):
        return [t for c in n.children for t in exact_leaves(c)]
    return []


def exact_name(leaf: Term | Phrase) -> str:
    """An exact leaf as the no-stemming notice names it: its normalised tokens."""
    if isinstance(leaf, Term):
        return leaf.token
    return " ".join(i.token for i in leaf.items if isinstance(i, Term))


def takes_dollar(word: Lexeme, before: int, tokenizer: str) -> bool:
    """Whether `word` + `$` is a valid wildcard: the lexer's stem conditions (`_Lexer.check_stem`). `before`
    is the letters and digits of the phrase words before it."""
    if word.kind is not Kind.WORD or word.wildcard is not None:
        return False
    toks, tail = tokenize_with_tail(word.text, tokenizer)
    return (
        bool(toks)
        and before + sum(len(t.text) for t in toks) >= MIN_STEM
        and not toks[-1].op
        and not tail.pieces
    )


def reads_as_operator(word: Lexeme) -> bool:
    """Whether the lexer and Scholar mode's phrase grouping know `word` by its text: a lowercase (or
    full-width) `and`, `or`, `not` or `near/n`. With a `$` it would be another word to both."""
    key = unicodedata.normalize("NFKC", word.text).casefold()
    return key in OPERATOR_WORDS or word.text.casefold() in OPERATOR_WORDS or bool(_LOWER_NEAR.fullmatch(key))


def runs(q: str) -> list[int]:
    """For each offset `i` in `0..len(q)`, where the unspaced run ending at `i` starts, or -1 when that run
    holds LaTeX syntax (or `i` follows a break, so there is no word to end there). A backslash keeps the
    character after it in the run, as it does in the lexer's word (`G\\"odel`)."""
    out = [-1] * (len(q) + 1)
    start, latex, escaped = 0, False, False
    marks: list[int] = []  # the offsets of the current run, rewritten to -1 if LaTeX syntax turns up in it
    for i, c in enumerate(q):
        if not escaped and (c.isspace() or c in QUOTES):
            start, latex, marks = i + 1, False, []
            continue
        escaped = not escaped and c in _BACKSLASHES
        if c in _LATEX and not latex:
            latex = True
            for m in marks:
                out[m] = -1
        if not latex:
            out[i + 1] = start
            marks.append(i + 1)
    return out


class Place(NamedTuple):
    """One exact term that can take a `$` as written."""

    term: str  # as the notice names it (`exact_name`)
    at: int  # the code-point offset in `q` the `$` goes at: the end of the word, or of a phrase's last word
    run: int  # where the unspaced run `at` ends starts: two places in one run can't both take a bare `$`
    leaf_end: int  # the end of the leaf's span, which identifies the leaf


def dollar_places(q: str, ast: Node, lexemes: Sequence[Lexeme], tokenizer: str) -> list[Place]:
    """Each exact term of `ast` that can take a `$` as written, in order of `at`. `lexemes` are `q`'s as the
    parser read them (in Scholar mode after `compat.group_phrases`), lexed with `tokenizer`."""
    # An exact leaf's span holds its one word or phrase lexeme, and may be wider: a field prefix, the
    # parentheses of a group of one (`(model)`). Leaves never overlap, so a lexeme has at most one.
    leaves = sorted(exact_leaves(ast), key=lambda leaf: leaf.span)
    starts = [leaf.span[0] for leaf in leaves]
    run_of = runs(q)
    found: dict[int, Place | None] = {}  # by the leaf's end
    for x in lexemes:
        if x.kind not in (Kind.WORD, Kind.PHRASE):
            continue
        i = bisect.bisect_right(starts, x.start) - 1
        if i < 0 or x.end > leaves[i].span[1]:
            continue
        leaf = leaves[i]
        end = leaf.span[1]
        if end in found:  # a second lexeme in one leaf: not a shape this knows, so not offered
            found[end] = None
            continue
        found[end] = None
        if x.kind is Kind.PHRASE:
            if not x.parts:
                continue
            word, before = x.parts[-1], sum(letters(p.stem or "", tokenizer) for p in x.parts[:-1])
        elif reads_as_operator(x):
            continue
        else:
            word, before = x, 0
        if run_of[word.end] >= 0 and takes_dollar(word, before, tokenizer):
            found[end] = Place(term=exact_name(leaf), at=word.end, run=run_of[word.end], leaf_end=end)
    return sorted((place for place in found.values() if place is not None), key=lambda place: place.at)
