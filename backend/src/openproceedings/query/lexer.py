"""The query lexer (spec 02 §Grammar; decision-001): `q` → lexemes with half-open code-point spans.

Lexical rules, in the order they are tried at the start of each lexeme:

- Whitespace (any Unicode space) separates. `(`, `)` and `|` are single-character lexemes (`|` is `OR`).
- A double quote (`"`, `“`, `”`, `„`, `‟`) opens a phrase that runs to the next unescaped double quote;
  its parts are split on whitespace, and operators inside it are ordinary words. With no closing quote
  the phrase runs to the end of `q` and PARSE_UNTERMINATED_PHRASE is raised.
- `-` is `NOT` when it starts the query or follows whitespace, `(`, `|` or a field's `:`, and a primary
  follows it directly. Any other word that starts with `-` (`a - b`, `"x"-based`, `--x`) is
  PARSE_AMBIGUOUS_MINUS: it would otherwise silently mean either NOT or a literal hyphen.
- A letter, then letters/digits/underscores, then `:` is a field (case-insensitive). An unknown name is
  FIELD_UNKNOWN but is still emitted as a field so the parser can go on. `title: trust` (a space after
  the colon) is accepted; `title :trust` is PARSE_STRAY_COLON.
- Anything else runs to the next whitespace, parenthesis, `|` or double quote, except that LaTeX math
  (`$f(x)$`, found exactly as the tokenizer finds it) keeps its parentheses and bars. A backslash keeps
  the character after it in the word (`G\\"odel`). The words `AND`, `OR`, `NOT` (uppercase only) are
  operators; `NEAR/n` (n ≤ 100) is proximity, and a bare `NEAR` between terms is PARSE_BAD_NEAR;
  `2020..2026` is a range; everything else is a WORD.
- A WORD (or phrase part) ending in `*` or in a `$` outside math is a wildcard. Its stem must keep at
  least 3 letters or digits after normalisation, counting the words before it in a phrase (decision-001;
  `"generative AI$"` is fine, as `generative-AI$` is), and the wildcard must directly follow a
  letter or digit (`vision-*` is PARSE_WILDCARD_DETACHED). A `*` or `$` anywhere else outside math is
  PARSE_WILDCARD_NOT_SUFFIX, except a `$` before a digit (currency, `US$5`).

Characters whose NFKC form is one of these syntax characters (full-width `（`, `－`, `＂`, `＊`, …) act as
that character, since the tokenizer applies NFKC too. Super/subscript parentheses (math notation) and the
full-width backslash (ordinary text, spec 02) are deliberately excluded; a test re-derives this table
from the Unicode database.

Warnings, raised where an operator would have made sense: a lowercase `and`/`or`/`not`/`near/n` between
two terms (WARN_LOWERCASE_OPERATOR); a word that starts with a dash or single quote that only looks like
an operator (`−bias`, `‘trust`: WARN_LOOKALIKE_OPERATOR); a word whose trailing `+`/`#` is dropped by the
tokenizer (`C++` → `c`: WARN_SYMBOLS_DROPPED). Bad input is a diagnostic, never an exception.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from openproceedings.diagnostics import Diagnostic, DiagnosticCode
from openproceedings.query.normalize import math_regions, tokenize

FIELDS = ("title", "abstract", "venue", "year", "track", "status", "source")
MIN_STEM = 3  # letters or digits a wildcard stem keeps after normalisation (spec 02, decision-001)
MAX_NEAR = 100
QUOTES = frozenset('"“”„‟＂«»「」『』')
LPARENS = frozenset("(（﹙︵")
RPARENS = frozenset(")）﹚︶")
PIPES = frozenset("|｜")
COLONS = frozenset(":：﹕︓")
MINUSES = frozenset("-－﹣")
STARS = frozenset("*＊﹡")
DOLLARS = frozenset("$＄﹩")  # only the ASCII `$` can delimit LaTeX math (spec 02 §Token semantics)
# Every dash (Unicode category Pd) that is not an ASCII-equivalent MINUSES entry, plus the minus sign
# U+2212: not operators, but easily meant as `-`. A test re-derives this set from the Unicode database.
_LOOKALIKE_MINUS = frozenset(
    "\u058a\u05be\u1400\u1806\u2010\u2011\u2012\u2013\u2014\u2015\u2e17\u2e1a\u2e3a\u2e3b\u2e40\u2e5d"
    "\u301c\u3030\u30a0\ufe31\ufe32\ufe58\U00010ead\u2212"
)
_SINGLE_QUOTES = ("‘", "`")
_BREAKS = LPARENS | RPARENS | PIPES
_FIELD = re.compile(r"([^\W\d_]\w*)[:：﹕︓]")
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
    stem: str | None = None  # WORD: `text` without its wildcard
    wildcard: str | None = None  # WORD: "*" or "$"
    field: str | None = None  # FIELD: the lowercased name, known or not
    near: int | None = None  # NEAR: the distance n
    range: tuple[int, int] | None = None  # RANGE: (start, end) as written
    parts: tuple[Lexeme, ...] = ()  # PHRASE: its WORDs, in order
    closed: bool = True  # PHRASE: False when the closing quote is missing


@dataclass(frozen=True, slots=True)
class LexResult:
    lexemes: tuple[Lexeme, ...]
    warnings: tuple[Diagnostic, ...]
    errors: tuple[Diagnostic, ...]


def _diag(code: DiagnosticCode, message: str, start: int, end: int) -> Diagnostic:
    return Diagnostic(code=code, message=message, span=(start, end))


def _step(q: str, j: int) -> int:
    """The index after the character at `j`; a backslash also takes the (non-space) character after it."""
    return j + 2 if q[j] == "\\" and j + 1 < len(q) and not q[j + 1].isspace() else j + 1


class _Lexer:
    def __init__(self, q: str) -> None:
        self.q = q
        self.out: list[Lexeme] = []
        self.errors: list[Diagnostic] = []
        self.warnings: list[Diagnostic] = []

    def error(self, code: DiagnosticCode, message: str, start: int, end: int) -> None:
        self.errors.append(_diag(code, message, start, end))

    def warn(self, code: DiagnosticCode, message: str, start: int, end: int) -> None:
        self.warnings.append(_diag(code, message, start, end))

    def run(self) -> None:
        q, n, i = self.q, len(self.q), 0
        while i < n:
            c = q[i]
            if c.isspace():
                i += 1
            elif c in _BREAKS:
                kind = Kind.LPAREN if c in LPARENS else Kind.RPAREN if c in RPARENS else Kind.OR
                self.out.append(Lexeme(kind, i, i + 1, c))
                i += 1
            elif c in QUOTES:
                i = self.phrase(i)
            elif c in MINUSES and self.negates(i):
                self.out.append(Lexeme(Kind.NOT, i, i + 1, c))
                i += 1
            elif m := _FIELD.match(q, i):
                self.field(i, m)
                i = m.end()
            else:
                i = self.word_or_operator(i)
        self.after_pass()

    def negates(self, i: int) -> bool:
        """Whether the `-` at `i` is NOT: at a primary's start, directly followed by what it excludes."""
        q = self.q
        prev = q[i - 1] if i else " "
        nxt = q[i + 1] if i + 1 < len(q) else " "
        starts = prev.isspace() or prev in LPARENS or prev in PIPES or prev in COLONS
        return starts and not nxt.isspace() and nxt not in RPARENS and nxt not in PIPES and nxt not in MINUSES

    def field(self, i: int, m: re.Match[str]) -> None:
        name = m.group(1).lower()
        if name not in FIELDS:
            valid = ", ".join(f"`{f}:`" for f in FIELDS)
            hint = " (Scholar's `intitle:` is `title:` here)" if name in ("intitle", "allintitle") else ""
            self.error(
                DiagnosticCode.FIELD_UNKNOWN,
                f"`{m.group()}` is not a field{hint} — use one of {valid}, or quote the text to search for it.",
                i,
                m.end(),
            )
        self.out.append(Lexeme(Kind.FIELD, i, m.end(), m.group(), field=name))

    def phrase(self, i: int) -> int:
        q, n = self.q, len(self.q)
        j = i + 1
        while j < n and q[j] not in QUOTES:
            j = _step(q, j)
        j = min(j, n)
        closed = j < n
        if not closed:
            self.error(
                DiagnosticCode.PARSE_UNTERMINATED_PHRASE,
                f'The phrase starting `{q[i : i + 20]}` has no closing quote — add a closing `"`.',
                i,
                n,
            )
        end = j + 1 if closed else n
        parts: list[Lexeme] = []
        k = i + 1
        while k < j:
            if q[k].isspace():
                k += 1
                continue
            m = self.math_run(k, j)
            if m < 0:
                m = k
                while m < j and not q[m].isspace():
                    m += 1
            before = sum(len(t.text) for p in parts for t in tokenize(p.text))  # letters of earlier words
            parts.append(self.word(k, m, in_phrase=True, before=before))
            k = m
        self.out.append(Lexeme(Kind.PHRASE, i, end, q[i:end], parts=tuple(parts), closed=closed))
        return end

    def math_run(self, i: int, limit: int) -> int:
        """If LaTeX math opens at `i` and closes before `limit` at the end of a word (`$\\alpha + \\beta$`),
        the index after it; else -1. So math with spaces stays one word, while `behavio$r colo$r` (the `$`
        not at a word's start) never pairs across words."""
        if self.q[i] != "$":
            return -1
        ends = [b for a, b in math_regions(self.q[i:limit]) if a == 0]
        if not ends:
            return -1
        end = i + ends[0]
        at_boundary = end == limit or self.q[end].isspace() or self.q[end] in _BREAKS | QUOTES
        return end if at_boundary else -1

    def word_end(self, i: int) -> int:
        """End of the word at `i`: a whole LaTeX math run, or the next break (except inside LaTeX math within
        the same chunk)."""
        q, n = self.q, len(self.q)
        limit = next((k for k in range(i, n) if q[k] in QUOTES), n)
        if (end := self.math_run(i, limit)) > 0:
            return end
        chunk_end = i
        while chunk_end < n and not q[chunk_end].isspace() and q[chunk_end] not in QUOTES:
            chunk_end = _step(q, chunk_end)
        chunk_end = min(chunk_end, n)
        math_ends = {i + a: i + b for a, b in math_regions(q[i:chunk_end])}
        j = i
        while j < chunk_end:
            if j in math_ends:
                j = math_ends[j]
            elif q[j] in _BREAKS:
                break
            else:
                j = _step(q, j)
        return min(j, chunk_end)

    def word_or_operator(self, i: int) -> int:
        j = self.word_end(i)
        raw = self.q[i:j]
        key = unicodedata.normalize("NFKC", raw)  # `ＯＲ` is `OR`, as the tokenizer would read it
        if key in _OPERATORS:
            self.out.append(Lexeme(_OPERATORS[key], i, j, raw))
        elif (near := _NEAR.fullmatch(key)) and int(near.group(1)) <= MAX_NEAR:
            self.out.append(Lexeme(Kind.NEAR, i, j, raw, near=int(near.group(1))))
        elif key.startswith("NEAR/"):
            self.error(
                DiagnosticCode.PARSE_BAD_NEAR,
                f"`{raw}` needs a whole-number distance up to {MAX_NEAR} — write e.g. `NEAR/3` (at most 3 words "
                "apart).",
                i,
                j,
            )
        elif rng := _RANGE.fullmatch(key):
            self.out.append(Lexeme(Kind.RANGE, i, j, raw, range=(int(rng.group(1)), int(rng.group(2)))))
        else:
            self.out.append(self.word(i, j, in_phrase=False))
        return j

    def word(self, start: int, end: int, *, in_phrase: bool, before: int = 0) -> Lexeme:
        """A WORD over `q[start:end]`, with its wildcard split off and checked. `before` is the number of
        letters and digits of the phrase words before it, which count toward a wildcard's stem."""
        raw = self.q[start:end]
        regions = math_regions(raw)
        wild: list[int] = []  # offsets in `raw` of `*`/`$` that act as wildcards (outside math, not currency)
        k = 0
        while k < len(raw):
            c = raw[k]
            if c == "\\":
                k += 2
                continue
            in_math = any(a <= k < b for a, b in regions)
            currency = c in DOLLARS and k + 1 < len(raw) and raw[k + 1].isdigit()
            if (c in STARS or c in DOLLARS) and not in_math and not currency:
                wild.append(k)
            k += 1
        wildcard = None
        if wild and wild[-1] == len(raw) - 1:
            wildcard = "*" if raw[-1] in STARS else "$"
            wild.pop()
        stem = raw[:-1] if wildcard else raw
        if wild:
            s = wild[0]
            self.error(
                DiagnosticCode.PARSE_WILDCARD_NOT_SUFFIX,
                f"`{raw}` has a `{raw[s]}` that is neither a wildcard at the end of a word (e.g. `bench*`, "
                "`model$`) nor closed LaTeX math (`$x$`) — search the whole word, or close the math.",
                start + s,
                start + s + 1,
            )
        elif wildcard:
            self.check_stem(raw, stem, wildcard, start, end, before)
        if not in_phrase:
            self.check_word(raw, stem, start, end)
        return Lexeme(Kind.WORD, start, end, raw, stem=stem, wildcard=wildcard)

    def check_stem(self, raw: str, stem: str, wildcard: str, start: int, end: int, before: int) -> None:
        toks = tokenize(stem)
        if not toks or before + len("".join(t.text for t in toks)) < MIN_STEM:
            self.error(
                DiagnosticCode.WILDCARD_STEM_TOO_SHORT,
                f"The wildcard `{raw}` keeps fewer than {MIN_STEM} letters or digits before `{wildcard}`, so it "
                "would match too many words — use a longer stem (e.g. `bench*`, not `be*`).",
                start,
                end,
            )
        elif toks[-1].end < len(stem):
            self.error(
                DiagnosticCode.PARSE_WILDCARD_DETACHED,
                f"The `{wildcard}` in `{raw}` follows `{stem[toks[-1].end :]}`, not a letter or digit, so it would "
                f"match any word starting `{toks[-1].text}` — put it straight after the stem, e.g. "
                f"`{stem[: toks[-1].end]}{wildcard}`.",
                start,
                end,
            )

    def check_word(self, raw: str, stem: str, start: int, end: int) -> None:
        """Checks for a top-level WORD (not a phrase part, where these characters are plainly literal)."""
        if raw[0] in MINUSES:
            self.error(
                DiagnosticCode.PARSE_AMBIGUOUS_MINUS,
                f"`{raw}`: to exclude a word, put one `-` straight before it after a space (`trust -bias`); to "
                "search a hyphenated term, quote it.",
                start,
                end,
            )
        elif raw[0] in COLONS:
            self.error(
                DiagnosticCode.PARSE_STRAY_COLON,
                f"`{raw}` starts with a colon — a field name must touch its colon, e.g. `title:trust`.",
                start,
                end,
            )
        elif raw[0] in _LOOKALIKE_MINUS:
            self.warn(
                DiagnosticCode.WARN_LOOKALIKE_OPERATOR,
                f"`{raw}` starts with `{raw[0]}`, which is not an operator, so the word is searched — to exclude "
                f"it, type an ASCII hyphen: `-{raw[1:]}`.",
                start,
                end,
            )
        elif raw.startswith(_SINGLE_QUOTES):
            self.warn(
                DiagnosticCode.WARN_LOOKALIKE_OPERATOR,
                f'`{raw}` starts with a single quote, which does not make a phrase — use double quotes: `"…"`.',
                start,
                end,
            )
        if stem.endswith(("+", "#")) and (toks := tokenize(stem)):
            searched = " ".join(t.text for t in toks)
            self.warn(
                DiagnosticCode.WARN_SYMBOLS_DROPPED,
                f"`{raw}` is searched as `{searched}`: symbols such as `+` and `#` are not indexed, so it matches "
                f"every `{searched}`.",
                start,
                end,
            )

    def after_pass(self) -> None:
        """Diagnostics that depend on the neighbouring lexemes: words that look like operators."""
        for x in self.out:
            if x.kind is Kind.WORD and unicodedata.normalize("NFKC", x.text) == "NEAR":
                self.error(
                    DiagnosticCode.PARSE_BAD_NEAR,
                    "`NEAR` needs a distance — write e.g. `NEAR/3` (Web of Science's bare `NEAR` means `NEAR/15`); "
                    'to search the word, write `near` or `"NEAR"`.',
                    x.start,
                    x.end,
                )
        for before, x, after in zip(self.out, self.out[1:], self.out[2:], strict=False):
            if x.kind is not Kind.WORD or before.kind not in _ENDS_A_TERM or after.kind not in _STARTS_A_TERM:
                continue
            upper = unicodedata.normalize("NFKC", x.text).upper()
            if upper == "NEAR":
                continue
            if upper in _OPERATORS:
                self.warn(
                    DiagnosticCode.WARN_LOWERCASE_OPERATOR,
                    f"`{x.text}` is searched as a word — write `{upper}` to combine terms (operators are uppercase "
                    "only).",
                    x.start,
                    x.end,
                )
            elif _NEAR.fullmatch(upper):
                self.warn(
                    DiagnosticCode.WARN_LOWERCASE_OPERATOR,
                    f"`{x.text}` is searched as words — write `{upper}` for a proximity search (operators are "
                    "uppercase only).",
                    x.start,
                    x.end,
                )


def _by_position(d: Diagnostic) -> tuple[int, int]:
    return d.span or (0, 0)


def lex(q: str) -> LexResult:
    """Split `q` into lexemes. Never raises: problems come back as `errors` and `warnings`, in order."""
    lexer = _Lexer(q)
    lexer.run()
    return LexResult(
        tuple(lexer.out),
        tuple(sorted(lexer.warnings, key=_by_position)),
        tuple(sorted(lexer.errors, key=_by_position)),
    )
