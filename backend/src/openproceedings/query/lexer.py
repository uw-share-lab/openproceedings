"""The query lexer (spec 02 §Grammar; decision-001): `q` → lexemes with half-open code-point spans.

Lexical rules, in the order they are tried at the start of each lexeme:

- Whitespace (any Unicode space) separates. `(`, `)` and `|` are single-character lexemes (`|` is `OR`).
- A quote (`"`, `“` or `”`) opens a phrase that runs to the next unescaped quote; its parts are split on
  whitespace, and operators inside it are ordinary words. With no closing quote, the phrase runs to the
  end of `q` and PARSE_UNTERMINATED_PHRASE is raised.
- `-` directly before a primary (not before a space, `)` or `|`) is `NOT`. Elsewhere it is part of a word.
- Letters followed by `:` are a field (case-insensitive). An unknown name is FIELD_UNKNOWN, but it is
  still emitted as a field so the parser can go on.
- Anything else runs to the next whitespace, parenthesis, `|` or quote. A backslash keeps the character
  after it in the word, so LaTeX such as `G\\"odel` survives. The word `AND`, `OR` or `NOT` (uppercase
  only) is an operator; `NEAR/n` is proximity; `2020..2026` is a range; everything else is a WORD.
- A WORD (or a phrase part) ending in an unescaped `*`, or in a `$` that is not closing a `$…$` math pair,
  is a wildcard. Its stem must keep at least 3 letters or digits after normalisation (decision-001), and a
  `*` anywhere else outside math is PARSE_WILDCARD_NOT_SUFFIX.

A lowercase `and`/`or`/`not`/`near/n` between two terms is searched as a word and raises
WARN_LOWERCASE_OPERATOR. Bad input is a diagnostic, never an exception.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from openproceedings.diagnostics import Diagnostic, DiagnosticCode
from openproceedings.query.normalize import normalize

FIELDS = ("title", "abstract", "venue", "year", "track", "status", "source")
MIN_STEM = 3  # letters or digits a wildcard stem keeps after normalisation (spec 02, decision-001)
QUOTES = frozenset('"“”')
_DELIMITERS = frozenset("()|") | QUOTES
_FIELD = re.compile(r"[A-Za-z]+:")
_NEAR = re.compile(r"NEAR/([0-9]+)")
_RANGE = re.compile(r"([0-9]+)\.\.([0-9]+)")


class Kind(StrEnum):
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    NEAR = "NEAR"
    FIELD = "FIELD"
    WORD = "WORD"
    PHRASE = "PHRASE"
    RANGE = "RANGE"


_OPERATORS = {"AND": Kind.AND, "OR": Kind.OR, "NOT": Kind.NOT}
_ENDS_A_TERM = frozenset({Kind.WORD, Kind.PHRASE, Kind.RPAREN, Kind.RANGE})
_STARTS_A_TERM = frozenset({Kind.WORD, Kind.PHRASE, Kind.LPAREN, Kind.FIELD, Kind.NOT, Kind.RANGE})


@dataclass(frozen=True, slots=True)
class Lexeme:
    """One lexeme. `text` is always `q[start:end]`; the other fields are set only for their kinds."""

    kind: Kind
    start: int
    end: int
    text: str
    stem: str = ""  # WORD: `text` without its wildcard
    wildcard: str | None = None  # WORD: "*" or "$"
    field: str | None = None  # FIELD: the lowercased name, known or not
    near: int | None = None  # NEAR: the distance n
    range: tuple[int, int] | None = None  # RANGE: (start, end) as written
    parts: tuple[Lexeme, ...] = ()  # PHRASE: its WORDs, in order


@dataclass(frozen=True, slots=True)
class LexResult:
    lexemes: list[Lexeme] = field(default_factory=list)
    warnings: list[Diagnostic] = field(default_factory=list)
    errors: list[Diagnostic] = field(default_factory=list)


def _err(code: DiagnosticCode, message: str, start: int, end: int) -> Diagnostic:
    return Diagnostic(code=code, message=message, span=(start, end))


def _word(q: str, start: int, end: int, errors: list[Diagnostic]) -> Lexeme:
    """A WORD over `q[start:end]`, with its wildcard split off and checked."""
    raw = q[start:end]
    dollars: list[int] = []  # offsets in `raw` of unescaped `$`
    stars: list[int] = []  # offsets in `raw` of unescaped `*`
    k = 0
    while k < len(raw):
        if raw[k] == "\\":
            k += 2
            continue
        if raw[k] == "$":
            dollars.append(k)
        elif raw[k] == "*":
            stars.append(k)
        k += 1
    wildcard = None
    if stars and stars[-1] == len(raw) - 1:
        wildcard = "*"
        stars.pop()
    elif dollars and dollars[-1] == len(raw) - 1 and len(dollars) % 2 == 1:
        wildcard = "$"  # an odd count: the last `$` closes no math pair
        dollars.pop()
    stem = raw[:-1] if wildcard else raw
    math = list(zip(dollars[::2], dollars[1::2], strict=False))
    stray = [s for s in stars if not any(a < s < b for a, b in math)]
    if stray:
        s = stray[0]
        errors.append(
            _err(
                DiagnosticCode.PARSE_WILDCARD_NOT_SUFFIX,
                f"`*` can only end a word, but `{raw}` has one inside it — use `{raw[:s]}*` or search the whole word.",
                start + s,
                start + s + 1,
            )
        )
    elif wildcard and len("".join(normalize(stem))) < MIN_STEM:
        errors.append(
            _err(
                DiagnosticCode.WILDCARD_STEM_TOO_SHORT,
                f"The wildcard `{raw}` keeps fewer than {MIN_STEM} letters or digits before `{wildcard}`, so it would "
                "match too many words — use a longer stem (e.g. `bench*`, not `be*`).",
                start,
                end,
            )
        )
    return Lexeme(Kind.WORD, start, end, raw, stem=stem, wildcard=wildcard)


def _phrase(q: str, i: int, errors: list[Diagnostic]) -> Lexeme:
    """The phrase whose opening quote is at `i`."""
    n = len(q)
    j = i + 1
    while j < n and q[j] not in QUOTES:
        j += 2 if q[j] == "\\" else 1
    j = min(j, n)
    if j >= n:
        errors.append(
            _err(
                DiagnosticCode.PARSE_UNTERMINATED_PHRASE,
                f'The phrase starting `{q[i : i + 20]}` has no closing quote — add a closing `"`.',
                i,
                n,
            )
        )
        end = n
    else:
        end = j + 1
    parts = []
    k = i + 1
    while k < j:
        if q[k].isspace():
            k += 1
            continue
        m = k
        while m < j and not q[m].isspace():
            m += 1
        parts.append(_word(q, k, m, errors))
        k = m
    return Lexeme(Kind.PHRASE, i, end, q[i:end], parts=tuple(parts))


def _word_end(q: str, i: int) -> int:
    j = i
    while j < len(q) and not q[j].isspace() and q[j] not in _DELIMITERS:
        j += 2 if q[j] == "\\" and j + 1 < len(q) and not q[j + 1].isspace() else 1
    return j


def _lowercase_warnings(lexemes: list[Lexeme]) -> list[Diagnostic]:
    warnings = []
    for before, x, after in zip(lexemes, lexemes[1:], lexemes[2:], strict=False):
        if x.kind is not Kind.WORD or before.kind not in _ENDS_A_TERM or after.kind not in _STARTS_A_TERM:
            continue
        upper = x.text.upper()
        if x.text == upper:
            continue
        if upper in _OPERATORS:
            message = f"`{x.text}` is searched as a word — write `{upper}` to combine terms (operators are uppercase only)."
        elif _NEAR.fullmatch(upper):
            message = f"`{x.text}` is searched as words — write `{upper}` for a proximity search (operators are uppercase only)."
        else:
            continue
        warnings.append(_err(DiagnosticCode.WARN_LOWERCASE_OPERATOR, message, x.start, x.end))
    return warnings


def lex(q: str) -> LexResult:
    """Split `q` into lexemes. Never raises: problems come back as `errors` and `warnings`."""
    out: list[Lexeme] = []
    errors: list[Diagnostic] = []
    n = len(q)
    i = 0
    after_dash = False  # a `-` just became NOT; a second one is part of the word
    while i < n:
        c = q[i]
        if c.isspace():
            i += 1
            after_dash = False
            continue
        dash, after_dash = after_dash, False
        if c in "()|":
            kind = {"(": Kind.LPAREN, ")": Kind.RPAREN, "|": Kind.OR}[c]
            out.append(Lexeme(kind, i, i + 1, c))
            i += 1
            continue
        if c in QUOTES:
            out.append(_phrase(q, i, errors))
            i = out[-1].end
            continue
        if c == "-" and not dash and i + 1 < n and not q[i + 1].isspace() and q[i + 1] not in ")|":
            out.append(Lexeme(Kind.NOT, i, i + 1, c))
            i += 1
            after_dash = True
            continue
        m = _FIELD.match(q, i)
        if m:
            name = m.group()[:-1].lower()
            if name not in FIELDS:
                valid = ", ".join(f"`{f}:`" for f in FIELDS)
                errors.append(
                    _err(
                        DiagnosticCode.FIELD_UNKNOWN,
                        f"`{m.group()}` is not a field — use one of {valid}, or quote the text to search for it.",
                        i,
                        m.end(),
                    )
                )
            out.append(Lexeme(Kind.FIELD, i, m.end(), m.group(), field=name))
            i = m.end()
            continue
        j = _word_end(q, i)
        raw = q[i:j]
        if raw in _OPERATORS:
            out.append(Lexeme(_OPERATORS[raw], i, j, raw))
        elif near := _NEAR.fullmatch(raw):
            out.append(Lexeme(Kind.NEAR, i, j, raw, near=int(near.group(1))))
        elif raw.startswith("NEAR/"):
            errors.append(
                _err(
                    DiagnosticCode.PARSE_BAD_NEAR,
                    f"`{raw}` needs a whole-number distance — write e.g. `NEAR/3` (at most 3 words apart).",
                    i,
                    j,
                )
            )
        elif rng := _RANGE.fullmatch(raw):
            out.append(Lexeme(Kind.RANGE, i, j, raw, range=(int(rng.group(1)), int(rng.group(2)))))
        else:
            out.append(_word(q, i, j, errors))
        i = j
    return LexResult(out, _lowercase_warnings(out), errors)
