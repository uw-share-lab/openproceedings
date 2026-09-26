"""Scholar / Publish-or-Perish input mode (spec 02 §Compatibility input modes; scholar-syntax-compat skill).

Compat mode is a front end to the native grammar: it rewrites, reports every rewrite in `translations`,
and produces a native AST and canonical string. It never changes what a native query means.

- `source:` values translate through SOURCE_ALIASES (matched exactly after the token contract, never as a
  substring) to `venue:`; PMLR also hosts other venues, so it raises WARN_SOURCE_PARTIAL too.
- A run of two or more juxtaposed unquoted words with `OR`/`|` directly on at least one side, bounded by
  `OR`/`|`, a parenthesis or the edge of the query, is read as one phrase (decision-002):
  `(large language model$ | LLM)` → `("large language model$" OR LLM)`.
- PoP's `$` is the Web of Science zero-or-one wildcard, as in native mode; Scholar mode says so.
"""

from __future__ import annotations

from openproceedings.diagnostics import Diagnostic, DiagnosticCode, clip
from openproceedings.query.lexer import MIN_STEM, Kind, Lexeme
from openproceedings.query.normalize import normalize

# normalised `source:` value → venue (every source value of the Trust-Evals corpus exports)
SOURCE_ALIASES = {
    "neurips": "NeurIPS",
    "neural information processing systems": "NeurIPS",
    "advances in neural information processing systems": "NeurIPS",
    "iclr": "ICLR",
    "international conference on learning representations": "ICLR",
    "icml": "ICML",
    "international conference on machine learning": "ICML",
    "pmlr": "ICML",
    "proceedings of machine learning research": "ICML",
}
PARTIAL_SOURCES = frozenset({"pmlr", "proceedings of machine learning research"})


def source_key(text: str) -> str:
    """A `source:` value as the alias table keys it: the token contract, tokens joined by one space."""
    return " ".join(normalize(text))


_OPERATOR_WORDS = frozenset({"and", "or", "not"})


def _joins(x: Lexeme) -> bool:
    """Whether a word can be part of a `|` item phrase: a plain word with something to search. A lowercase
    operator word (whose own warning says it is searched as a word) or a word with no letters or digits
    (`&`, an error of its own) ends the run instead of silently vanishing into a phrase."""
    return x.kind is Kind.WORD and x.text.casefold() not in _OPERATOR_WORDS and bool(normalize(x.stem or ""))


def _is_or(x: Lexeme | None) -> bool:
    return x is not None and x.kind is Kind.OR


def _bounds(x: Lexeme | None, edge: Kind) -> bool:
    return x is None or x.kind in (Kind.OR, edge)


def _cleared(run: tuple[Lexeme, ...]) -> set[tuple[int, int]]:
    """Spans of wildcard words whose stem is long enough once the phrase's earlier words count."""
    cleared, before = set(), 0
    for w in run:
        letters = sum(len(t) for t in normalize(w.stem or ""))
        if w.wildcard and before + letters >= MIN_STEM:
            cleared.add((w.start, w.end))
        before += letters
    return cleared


def group_phrases(
    q: str, lexemes: tuple[Lexeme, ...]
) -> tuple[tuple[Lexeme, ...], list[Diagnostic], set[tuple[int, int]]]:
    """Decision-002: juxtaposed words that form one `|`-separated item become a phrase. Also returns the
    spans whose WILDCARD_STEM_TOO_SHORT (judged by the lexer on the lone word) the phrase context clears."""
    out: list[Lexeme] = []
    notices: list[Diagnostic] = []
    cleared: set[tuple[int, int]] = set()
    i = 0
    while i < len(lexemes):
        j = i
        while j < len(lexemes) and _joins(lexemes[j]):
            j += 1
        before = lexemes[i - 1] if i else None
        after = lexemes[j] if j < len(lexemes) else None
        run = lexemes[i:j]
        if (
            len(run) >= 2
            and _bounds(before, Kind.LPAREN)
            and _bounds(after, Kind.RPAREN)
            and (_is_or(before) or _is_or(after))
        ):
            start, end = run[0].start, run[-1].end
            text = q[start:end]
            out.append(Lexeme(Kind.PHRASE, start, end, text, parts=tuple(run)))
            cleared |= _cleared(run)
            notices.append(
                Diagnostic(
                    code=DiagnosticCode.COMPAT_POP_PHRASE,
                    message=f'`{clip(text)}` is read as the phrase `"{clip(text)}"`, as the `|` list intends — Google Scholar '
                    "itself would have ORed only the neighbouring words.",
                    span=(start, end),
                )
            )
            i = j
        else:
            out.append(lexemes[i])
            i += 1
    return tuple(out), notices, cleared


def _search_terms(lexemes: tuple[Lexeme, ...]) -> list[Lexeme]:
    """WORDs and PHRASEs that are searched, skipping `source:` values (translated, never searched)."""
    out: list[Lexeme] = []
    skip_value, depth = False, 0
    for x in lexemes:
        if x.kind is Kind.FIELD and x.field == "source":
            skip_value = True
            continue
        if skip_value and x.kind is Kind.LPAREN:
            depth += 1
            continue
        if depth:
            depth += 1 if x.kind is Kind.LPAREN else -1 if x.kind is Kind.RPAREN else 0
            skip_value = depth > 0
            continue
        if skip_value:
            skip_value = False
            if x.kind in (Kind.WORD, Kind.PHRASE):
                continue
        if x.kind in (Kind.WORD, Kind.PHRASE):
            out.append(x)
    return out


def dollar_notices(lexemes: tuple[Lexeme, ...]) -> list[Diagnostic]:
    """A notice for every PoP `$` wildcard: it is read as zero-or-one character."""
    words = [p for x in _search_terms(lexemes) for p in (x.parts if x.kind is Kind.PHRASE else (x,))]
    return [
        Diagnostic(
            code=DiagnosticCode.COMPAT_POP_DOLLAR,
            message=f"`{w.text}`: PoP `$` is read as zero or one more character (Web of Science), so it matches "
            f"`{w.stem}` plus at most one character, e.g. a plural.",
            span=(w.start, w.end),
        )
        for w in words
        if w.wildcard == "$"
    ]
