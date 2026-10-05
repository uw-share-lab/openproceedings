"""Where a `$` can be added to the terms the Scholar-mode no-stemming notice names (TASK-175; spec 02 §Word
forms; spec 05 §Components 1).

Google Scholar stems words and openproceedings never does (guarantee 1), so a Scholar string run unchanged
identifies fewer records, and `COMPAT_NO_STEMMING` names the terms matched exactly. The UI offers to write the
notice's own suggestion, `$`, into the query text: an edit of `q` the reader triggers and sees (guarantees 3
and 6), never a change to how a query is matched. The UI must not re-parse the query to find the terms, so the
server reports each place a `$` can go: `at`, a code-point offset in `q`, and `insert`, the text to put there.

A term is offered when the notice names it (`parser.exact_leaves`: a word or phrase with no wildcard, in a
NEAR or under a NOT too) and `$` would be a valid wildcard on it as written:
- a phrase takes the `$` on its **last word** only (`"large language model"` → `"large language model$"`, as
  the review's own strings write it); its inner words are left alone, and a phrase that already holds a
  wildcard is not named by the notice;
- the stem keeps at least `MIN_STEM` letters or digits, counting a phrase's earlier words (`AI` is left
  alone, `"generative AI"` is offered), and the `$` would directly follow a letter or digit (`C++` is left
  alone): the lexer's own conditions (`_Lexer.check_stem`);
- the unspaced run the word sits in (up to whitespace or a quote: where the lexer looks for LaTeX math) holds
  no `$` or backslash already, since a second `$` in a run would close math (`US$5`, `(model$|LLM)`);
- filter and `source:` values are never offered: they are not terms, and take no wildcards.

Two offered words in one unspaced run (`(model|LLM)`) would read as math once both had a `$`
(`(model$|LLM$)`), so every one but the last gets `insert` `"$ "`, the `$` and a space: `(model$ |LLM$)`.
Whitespace there changes nothing else, and with it any subset of the edits is sound, not only all of them.

The answer is then checked by making every edit at once and parsing the result with the parser itself, in the
query's mode: it must parse, and its tree must be the original with exactly those leaves made `$` wildcards.
If it is not (for example the edited query would be over the length cap), nothing is offered, so an offered
edit is always one the server has read back. `test_wordforms.py` checks every single edit as well.

Not part of `parse` (as `clauses.filter_clauses` is not): the edited string is work `/search` and replay do
not need. `POST /parse` serves it as `word_forms`.
"""

from __future__ import annotations

import bisect

from pydantic import BaseModel, ConfigDict, Field

from openproceedings.query.ast import And, Leaf, Near, Node, Not, Or, Phrase, Term, Wildcard, structure
from openproceedings.query.compat import group_phrases
from openproceedings.query.lexer import (
    DOLLARS,
    LATEX_LOOKALIKES,
    MIN_STEM,
    QUOTES,
    Kind,
    Lexeme,
    letters,
    lex,
)
from openproceedings.query.normalize import tokenize_with_tail
from openproceedings.query.parser import ParseResult, exact_leaves, exact_name, parse

# a run holding one of these may already have LaTeX math or an escape in it: a `$` added there is not offered
_BACKSLASHES = frozenset({"\\"} | {c for c, to in LATEX_LOOKALIKES.items() if to == "\\"})
_LATEX = DOLLARS | frozenset(LATEX_LOOKALIKES) | _BACKSLASHES


class WordForm(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)
    term: str = Field(
        description="The term as the `COMPAT_NO_STEMMING` notice names it: its normalised tokens, a phrase's "
        "joined by spaces. One term written in several places has one entry per place."
    )
    at: int = Field(
        ge=0,
        description="The code-point offset in `q` to insert at: the end of the word, or of a phrase's last word.",
    )
    insert: str = Field(
        pattern=r"^\$ ?$",
        description="The text to insert at `at`, as it is: `$`, or `$` and a space where another offered word "
        "follows in the same unspaced run (`(model|LLM)`), so that the two `$` are not read as LaTeX math.",
    )


def _takes_dollar(word: Lexeme, before: int, tokenizer: str) -> bool:
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


def _runs(q: str) -> list[int]:
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


def _leaf_with_dollar(n: Leaf, ends: frozenset[int]) -> Leaf:
    if n.span[1] not in ends:
        return n
    if isinstance(n, Term):
        return Wildcard(span=n.span, stem=n.token, op="$", field=n.field)
    last = n.items[-1] if isinstance(n, Phrase) else None
    if not isinstance(n, Phrase) or not isinstance(last, Term):
        return n
    items = (*n.items[:-1], Wildcard(span=last.span, stem=last.token, op="$"))
    return Phrase(span=n.span, items=items, field=n.field)


def _with_dollar(n: Node, ends: frozenset[int]) -> Node:
    """`n` with each exact leaf that ends at one of `ends` made a `$` wildcard (a phrase's last word)."""
    if isinstance(n, Term | Phrase):
        return _leaf_with_dollar(n, ends)
    if isinstance(n, Near):
        left, right = _leaf_with_dollar(n.left, ends), _leaf_with_dollar(n.right, ends)
        return Near(span=n.span, left=left, right=right, distance=n.distance)
    if isinstance(n, Not):
        return Not(span=n.span, child=_with_dollar(n.child, ends))
    if isinstance(n, And | Or):
        return type(n)(span=n.span, children=tuple(_with_dollar(c, ends) for c in n.children))
    return n


def apply(q: str, forms: list[WordForm]) -> str:
    """`q` with every one of `forms` inserted: the edit the UI makes, in code points."""
    out, last = [], 0
    for f in sorted(forms, key=lambda f: f.at):
        out += [q[last : f.at], f.insert]
        last = f.at
    return "".join([*out, q[last:]])


def _candidates(q: str, ast: Node, result: ParseResult) -> list[tuple[WordForm, int]]:
    """Each edit the rules allow, in order, with the end of the leaf it rewrites: not yet read back."""
    # An exact leaf's span holds its one word or phrase lexeme, and may be wider: a field prefix, the
    # parentheses of a group of one (`(model)`). Leaves never overlap, so a lexeme has at most one.
    leaves = sorted(exact_leaves(ast), key=lambda leaf: leaf.span)
    starts = [leaf.span[0] for leaf in leaves]
    tokenizer = result.tokenizer_version
    lexemes, _, _ = group_phrases(q, lex(q, tokenizer).lexemes, tokenizer)
    runs = _runs(q)
    found: dict[int, tuple[str, int, int] | None] = {}  # the leaf's end → (term, at, the run's start)
    for x in lexemes:
        if x.kind not in (Kind.WORD, Kind.PHRASE):
            continue
        i = bisect.bisect_right(starts, x.start) - 1
        if i < 0 or x.end > leaves[i].span[1]:
            continue
        leaf = leaves[i]
        if leaf.span[1] in found:  # a second lexeme in one leaf: not a shape this knows, so not offered
            found[leaf.span[1]] = None
            continue
        found[leaf.span[1]] = None
        if x.kind is Kind.PHRASE:
            if not x.parts:
                continue
            word, before = x.parts[-1], sum(letters(p.stem or "", tokenizer) for p in x.parts[:-1])
        else:
            word, before = x, 0
        if runs[word.end] >= 0 and _takes_dollar(word, before, tokenizer):
            found[leaf.span[1]] = (exact_name(leaf), word.end, runs[word.end])
    offered = sorted((v[1], v[0], v[2], end) for end, v in found.items() if v is not None)
    return [
        (
            WordForm(
                term=term, at=at, insert="$ " if i + 1 < len(offered) and offered[i + 1][2] == run else "$"
            ),
            end,
        )
        for i, (at, term, run, end) in enumerate(offered)
    ]


def word_forms(q: str, result: ParseResult) -> list[WordForm] | None:
    """Each place a `$` can be added to a term the no-stemming notice names, in order. None exactly when
    `result` has errors; empty outside Scholar mode (no notice), and when the edits can't be made."""
    ast = result.ast
    if ast is None:
        return None
    if result.mode != "scholar":
        return []
    candidates = _candidates(q, ast, result)
    forms = [form for form, _ in candidates]
    if not forms:
        return []
    edited = parse(apply(q, forms), result.mode, result.tokenizer_version)
    expected = _with_dollar(ast, frozenset(end for _, end in candidates))
    if edited.ast is None or structure(edited.ast) != structure(expected):
        return []
    return forms
