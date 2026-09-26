"""The query parser (spec 02 §Grammar, §Error handling; decision-001): lexemes → AST plus diagnostics.

Recursive descent over the EBNF, with NOT > AND > OR and juxtaposition as AND. `parse` never raises: every
problem is a Diagnostic with a span, and `ast` is None exactly when there are errors (nothing to search).

- A level that mixes AND and OR without parentheses parses by precedence and raises WARN_MIXED_AND_OR.
- A word that normalises to several tokens is a Phrase; a wildcard word's wildcard goes on its last token
  (`gpt-4*` → Phrase[gpt, Wildcard(4*)]). Phrase parts that normalise to nothing are skipped.
- `title:`/`abstract:` push their field down to every leaf of what follows; filter fields take one value
  or an OR group of values, checked against `vocab.py`.
- NEAR/n joins two leaves (words, wildcards or phrases) in the same field, once.
- A query with no positive part (`NOT a`, `a OR NOT b`) is PARSE_ALL_NEGATIVE. This is checked before
  default filters are added (task-014), which would otherwise hide it.

`ParseResult.canonical` and `.canonical_hash` come from `canonical.py`. Default filters and Scholar mode
are layered on top (tasks 014–015).
"""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from openproceedings.diagnostics import Diagnostic, DiagnosticCode
from openproceedings.query.ast import (
    And,
    Filter,
    FilterField,
    Leaf,
    Near,
    Node,
    Not,
    Or,
    Phrase,
    Term,
    TextField,
    Wildcard,
    YearRange,
)
from openproceedings.query.canonical import canonical_hash, canonicalize, render
from openproceedings.query.lexer import FIELDS, Kind, Lexeme, lex
from openproceedings.query.normalize import tokenize
from openproceedings.vocab import STATUSES, TEXT_FIELDS, TRACKS, VENUES

MAX_DEPTH = 64  # nested groups and NOTs; deeper is PARSE_TOO_DEEP, so recursion can never overflow
_STARTS = frozenset({Kind.WORD, Kind.PHRASE, Kind.LPAREN, Kind.FIELD, Kind.NOT, Kind.RANGE})
_EXAMPLES = {
    "venue": "venue:NeurIPS",
    "year": "year:2020..2026",
    "track": "track:main",
    "status": "status:accepted",
    "source": 'source:"neural information processing systems"',
}


class ParseResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ast: Node | None
    canonical: str | None = None  # None exactly when there are errors
    canonical_hash: str | None = None
    warnings: list[Diagnostic]
    errors: list[Diagnostic]
    translations: list[Diagnostic] = []


class _TooDeep(Exception):
    """Unwinds the parser once MAX_DEPTH is exceeded; never escapes `parse`."""


def _positive(n: Node) -> bool:
    """Whether `n` restricts the corpus to something (rather than matching everything except something)."""
    if isinstance(n, Not):
        return False
    if isinstance(n, And):
        return any(_positive(c) for c in n.children)
    if isinstance(n, Or):
        return all(_positive(c) for c in n.children)
    return True


def _leaf_field(n: Leaf) -> TextField | None:
    return n.items[0].field if isinstance(n, Phrase) else n.field


class _Parser:
    def __init__(self, q: str, lexemes: list[Lexeme]) -> None:
        self.q = q
        self.toks = lexemes
        self.i = 0
        self.depth = 0
        self.errors: list[Diagnostic] = []
        self.warnings: list[Diagnostic] = []

    # --- cursor -------------------------------------------------------------------------------------
    def peek(self) -> Lexeme | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def at(self, *kinds: Kind) -> bool:
        tok = self.peek()
        return tok is not None and tok.kind in kinds

    def starts(self) -> bool:
        return self.at(*_STARTS)

    def advance(self) -> Lexeme:
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def error(self, code: DiagnosticCode, message: str, start: int, end: int) -> None:
        self.errors.append(Diagnostic(code=code, message=message, span=(start, end)))

    def enter(self, tok: Lexeme) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            self.error(
                DiagnosticCode.PARSE_TOO_DEEP,
                f"The query nests groups or `NOT`s more than {MAX_DEPTH} deep here — simplify it.",
                tok.start,
                tok.end,
            )
            raise _TooDeep

    # --- grammar ------------------------------------------------------------------------------------
    def run(self, lex_errors: bool) -> Node | None:
        if not self.toks:
            self.error(
                DiagnosticCode.PARSE_EXPECTED_TERM,
                "The query is empty — type a word or phrase to search for.",
                0,
                len(self.q),
            )
            return None
        node = self.or_expr(None)
        while self.i < len(self.toks):
            tok = self.advance()
            if tok.kind is Kind.RPAREN:
                self.error(
                    DiagnosticCode.PARSE_UNBALANCED_PAREN,
                    "This `)` has no matching `(` — remove it or add a `(`.",
                    tok.start,
                    tok.end,
                )
            else:
                self.error(
                    DiagnosticCode.PARSE_EXPECTED_TERM, f"Unexpected `{tok.text}` here.", tok.start, tok.end
                )
            if self.starts():
                self.or_expr(None)  # keep going, so later errors are reported too
        if node is not None and not self.errors and not lex_errors and not _positive(node):
            self.error(
                DiagnosticCode.PARSE_ALL_NEGATIVE,
                "Every part of this query is excluded (`NOT …`), so it would match almost everything — add something "
                "to search for, e.g. `trust NOT bias`.",
                *node.span,
            )
        return node

    def or_expr(self, field: TextField | None) -> Node | None:
        branches = [self.and_expr(field)]
        while self.at(Kind.OR):
            op = self.advance()
            if not self.starts() and not self.expected_after(op):
                break
            branches.append(self.and_expr(field))
        nodes = [n for n, _ in branches if n is not None]
        if len(branches) > 1 and any(compound for _, compound in branches) and nodes:
            reading = " OR ".join(
                f"({self.q[slice(*n.span)]})" if compound else self.q[slice(*n.span)]
                for n, compound in branches
                if n
            )
            self.warnings.append(
                Diagnostic(
                    code=DiagnosticCode.WARN_MIXED_AND_OR,
                    message=f"AND binds tighter than OR, so this is read as `{reading}` — add parentheses if you "
                    "meant something else.",
                    span=(nodes[0].span[0], nodes[-1].span[1]),
                )
            )
        return self.combine(Or, nodes)

    def and_expr(self, field: TextField | None) -> tuple[Node | None, bool]:
        children = [self.not_expr(field)]
        while True:
            if self.at(Kind.AND):
                op = self.advance()
                if not self.starts() and not self.expected_after(op):
                    break
            elif not self.starts():
                break
            children.append(self.not_expr(field))
        return self.combine(And, [c for c in children if c is not None]), len(children) > 1

    def not_expr(self, field: TextField | None) -> Node | None:
        if not self.at(Kind.NOT):
            return self.near_or_primary(field)
        op = self.advance()
        self.enter(op)
        try:
            if not self.starts():
                self.error(
                    DiagnosticCode.PARSE_EXPECTED_TERM,
                    f"`{op.text}` needs something to exclude after it, e.g. `trust NOT bias`.",
                    op.start,
                    op.end,
                )
                return None
            child = self.not_expr(field)
        finally:
            self.depth -= 1
        return Not(span=(op.start, child.span[1]), child=child) if child is not None else None

    def near_or_primary(self, field: TextField | None) -> Node | None:
        left = self.primary(field)
        if not self.at(Kind.NEAR):
            return left
        op = self.advance()
        right = self.primary(field) if self.starts() else None
        node: Node | None = None
        leaves = (Term, Wildcard, Phrase)
        if not isinstance(left, leaves) or not isinstance(right, leaves):
            if left is not None or right is not None or not self.errors:
                self.error(
                    DiagnosticCode.PARSE_BAD_NEAR,
                    f"`{op.text}` joins two words or phrases, e.g. `trust {op.text} calibration`; it can't take a "
                    "group, a filter or nothing.",
                    op.start,
                    op.end,
                )
        elif _leaf_field(left) != _leaf_field(right):
            self.error(
                DiagnosticCode.PARSE_BAD_NEAR,
                f"Both sides of `{op.text}` must be in the same field — write e.g. `title:(a {op.text} b)`.",
                op.start,
                op.end,
            )
        else:
            assert op.near is not None
            node = Near(span=(left.span[0], right.span[1]), left=left, right=right, distance=op.near)
        if self.at(Kind.NEAR):
            op2 = self.advance()
            self.error(
                DiagnosticCode.PARSE_BAD_NEAR,
                f"`NEAR` can't be chained — join the pairs with AND, e.g. `(a {op.text} b) AND (b {op2.text} c)`.",
                op2.start,
                op2.end,
            )
            if self.starts():
                self.primary(field)
            return None
        return node

    def primary(self, field: TextField | None) -> Node | None:
        tok = self.peek()
        if tok is None:
            return None
        if tok.kind is Kind.LPAREN:
            return self.group(field)
        if tok.kind is Kind.FIELD:
            return self.field_term(field)
        if tok.kind is Kind.WORD:
            return self.word(self.advance(), field)
        if tok.kind is Kind.PHRASE:
            return self.phrase(self.advance(), field)
        if tok.kind is Kind.RANGE:
            self.advance()
            self.error(
                DiagnosticCode.PARSE_EXPECTED_TERM,
                f"A range needs a field — write `year:{tok.text}`.",
                tok.start,
                tok.end,
            )
            return None
        if tok.kind is Kind.NEAR:
            self.advance()
            self.error(
                DiagnosticCode.PARSE_BAD_NEAR,
                f"`{tok.text}` needs a word or phrase on both sides, e.g. `trust {tok.text} calibration`.",
                tok.start,
                tok.end,
            )
            return None
        if tok.kind in (Kind.AND, Kind.OR):
            self.error(
                DiagnosticCode.PARSE_EXPECTED_TERM,
                f"`{tok.text}` needs a word, phrase or group before it — add one, or remove `{tok.text}`.",
                tok.start,
                tok.end,
            )
        return None  # `)` is reported by whoever owns the group (or by `run` if nobody does)

    def group(self, field: TextField | None) -> Node | None:
        lp = self.advance()
        self.enter(lp)
        try:
            if self.at(Kind.RPAREN):
                rp = self.advance()
                self.error(
                    DiagnosticCode.PARSE_EMPTY_GROUP,
                    "Empty parentheses `()` — remove them or put a term inside.",
                    lp.start,
                    rp.end,
                )
                return None
            node = self.or_expr(field)
            if self.at(Kind.RPAREN):
                end = self.advance().end
            else:
                self.error(
                    DiagnosticCode.PARSE_UNBALANCED_PAREN,
                    "This `(` is never closed — add a `)`.",
                    lp.start,
                    lp.end,
                )
                end = node.span[1] if node is not None else lp.end
        finally:
            self.depth -= 1
        return node.model_copy(update={"span": (lp.start, end)}) if node is not None else None

    def field_term(self, outer: TextField | None) -> Node | None:
        tok = self.advance()
        name = tok.field or ""
        if name not in FIELDS:  # the lexer has reported FIELD_UNKNOWN; parse what follows for more errors
            if self.starts():
                self.primary(outer)
            return None
        if name not in TEXT_FIELDS:
            return self.filter(tok, cast(FilterField, name))
        if outer is not None and name != outer:
            self.error(
                DiagnosticCode.PARSE_NESTED_FIELD,
                f"`{tok.text}` can't be used inside `{outer}:(…)`: a term is searched in one field — move it out of "
                "the group.",
                tok.start,
                tok.end,
            )
        if not self.at(Kind.WORD, Kind.PHRASE, Kind.LPAREN):
            self.error(
                DiagnosticCode.PARSE_EXPECTED_TERM,
                f"`{tok.text}` must be followed by a word, a phrase or a (group), e.g. `{tok.text}trust`.",
                tok.start,
                tok.end,
            )
            return None
        node = self.primary(cast(TextField, name))
        return node.model_copy(update={"span": (tok.start, node.span[1])}) if node is not None else None

    def filter(self, tok: Lexeme, name: FilterField) -> Node | None:
        syntax = f"`{tok.text}(…)` takes values joined by OR, e.g. `{tok.text}(a OR b)`."
        if not self.at(Kind.LPAREN):
            v = self.peek()
            if v is None or v.kind not in (Kind.WORD, Kind.PHRASE, Kind.RANGE):
                self.error(
                    DiagnosticCode.PARSE_EXPECTED_TERM,
                    f"`{tok.text}` must be followed by a value, e.g. `{_EXAMPLES[name]}`.",
                    tok.start,
                    tok.end,
                )
                return None
            value = self.value(name, self.advance())
            return Filter(span=(tok.start, v.end), field=name, values=(value,)) if value is not None else None
        lp = self.advance()
        if self.at(Kind.RPAREN):
            rp = self.advance()
            self.error(
                DiagnosticCode.PARSE_EMPTY_GROUP,
                "Empty parentheses `()` — put a value inside.",
                lp.start,
                rp.end,
            )
            return None
        values: list[str | YearRange] = []
        ok = True
        while True:
            v = self.peek()
            if v is None:
                self.error(
                    DiagnosticCode.PARSE_UNBALANCED_PAREN,
                    "This `(` is never closed — add a `)`.",
                    lp.start,
                    lp.end,
                )
                return None
            if v.kind not in (Kind.WORD, Kind.PHRASE, Kind.RANGE):
                self.error(DiagnosticCode.FIELD_FILTER_SYNTAX, syntax, v.start, v.end)
                self.skip_group()
                return None
            value = self.value(name, self.advance())
            if value is None:
                ok = False
            else:
                values.append(value)
            nxt = self.peek()
            if nxt is None:
                self.error(
                    DiagnosticCode.PARSE_UNBALANCED_PAREN,
                    "This `(` is never closed — add a `)`.",
                    lp.start,
                    lp.end,
                )
                return None
            if nxt.kind is Kind.RPAREN:
                end = self.advance().end
                break
            if nxt.kind is not Kind.OR:
                self.error(DiagnosticCode.FIELD_FILTER_SYNTAX, syntax, nxt.start, nxt.end)
                self.skip_group()
                return None
            self.advance()
        return Filter(span=(tok.start, end), field=name, values=tuple(values)) if ok else None

    def value(self, name: FilterField, v: Lexeme) -> str | YearRange | None:
        if name == "year":
            if v.kind is Kind.RANGE and v.range is not None:
                lo, hi = v.range
                if lo <= hi:
                    return YearRange(lo=lo, hi=hi)
                self.error(
                    DiagnosticCode.FIELD_RANGE_INVERTED,
                    f"`{v.text}` runs backwards — write `{hi}..{lo}`.",
                    v.start,
                    v.end,
                )
                return None
            if v.kind is Kind.WORD and v.wildcard is None and v.text.isascii() and v.text.isdigit():
                return YearRange(lo=int(v.text), hi=int(v.text))
            self.error(
                DiagnosticCode.FIELD_UNKNOWN_VALUE,
                f"`{v.text}` is not a year — `year:` takes a year or an inclusive range, e.g. `year:2024` or "
                "`year:2020..2026`.",
                v.start,
                v.end,
            )
            return None
        if name == "source" and v.kind is Kind.PHRASE:
            return " ".join(p.text for p in v.parts)
        if v.kind is Kind.WORD and v.wildcard is None:
            key = v.text.lower()
            if name == "source":
                return v.text
            if name == "venue" and key in VENUES:
                return VENUES[key]
            if (name == "track" and key in TRACKS) or (name == "status" and key in STATUSES):
                return key
        valid = {"venue": tuple(VENUES.values()), "track": TRACKS, "status": STATUSES, "source": ()}[name]
        self.error(
            DiagnosticCode.FIELD_UNKNOWN_VALUE,
            f"`{v.text}` is not a {name} (values take no wildcards or quotes) — use one of "
            + ", ".join(f"`{x}`" for x in valid)
            + ".",
            v.start,
            v.end,
        )
        return None

    def skip_group(self) -> None:
        """Skip to just past the `)` that closes the group we are in (or to the end)."""
        depth = 0
        while self.i < len(self.toks):
            tok = self.advance()
            if tok.kind is Kind.LPAREN:
                depth += 1
            elif tok.kind is Kind.RPAREN:
                if depth == 0:
                    return
                depth -= 1

    # --- leaves -------------------------------------------------------------------------------------
    def items(self, w: Lexeme, field: TextField | None) -> list[Term | Wildcard]:
        """The normalised tokens of one word, with the wildcard (if any) on the last."""
        toks = tokenize(w.stem)
        items: list[Term | Wildcard] = [
            Term(span=(w.start + t.start, w.start + t.end), token=t.text, field=field) for t in toks
        ]
        if w.wildcard and toks:
            last = toks[-1]
            op = cast(Literal["*", "$"], w.wildcard)
            items[-1] = Wildcard(span=(w.start + last.start, w.end), stem=last.text, op=op, field=field)
        return items

    def leaf(self, tok: Lexeme, items: list[Term | Wildcard]) -> Leaf:
        if len(items) == 1:
            return items[0].model_copy(update={"span": (tok.start, tok.end)})
        return Phrase(span=(tok.start, tok.end), items=tuple(items))

    def word(self, tok: Lexeme, field: TextField | None) -> Node | None:
        items = self.items(tok, field)
        if items:
            return self.leaf(tok, items)
        if not tok.wildcard:  # a wildcard with no stem was already reported by the lexer
            self.error(
                DiagnosticCode.PARSE_EMPTY_TERM,
                f"`{tok.text}` has no letters or digits, so it can't match anything — remove it (to exclude a word, "
                "write `-word` with no space).",
                tok.start,
                tok.end,
            )
        return None

    def phrase(self, tok: Lexeme, field: TextField | None) -> Node | None:
        items = [item for part in tok.parts for item in self.items(part, field)]
        if items:
            return self.leaf(tok, items)
        self.error(
            DiagnosticCode.PARSE_EMPTY_TERM,
            f"The phrase `{tok.text}` has no letters or digits — put words inside the quotes.",
            tok.start,
            tok.end,
        )
        return None

    # --- helpers ------------------------------------------------------------------------------------
    def expected_after(self, op: Lexeme) -> bool:
        """Report `op` missing its right operand, skip any operators straight after it (one mistake, one
        error), and say whether an operand follows after all."""
        self.error(
            DiagnosticCode.PARSE_EXPECTED_TERM,
            f"`{op.text}` needs a word, phrase or group after it — add one, or remove `{op.text}`.",
            op.start,
            op.end,
        )
        while self.at(Kind.AND, Kind.OR):
            self.advance()
        return self.starts()

    @staticmethod
    def combine(cls: type[And] | type[Or], nodes: list[Node]) -> Node | None:
        if not nodes:
            return None
        if len(nodes) == 1:
            return nodes[0]
        return cls(span=(nodes[0].span[0], nodes[-1].span[1]), children=tuple(nodes))


def _by_position(d: Diagnostic) -> tuple[int, int]:
    return d.span or (0, 0)


def parse(q: str) -> ParseResult:
    """Parse `q`. Never raises; `ast` is None exactly when `errors` is non-empty."""
    lexed = lex(q)
    p = _Parser(q, lexed.lexemes)
    try:
        ast = p.run(bool(lexed.errors))
    except _TooDeep:
        ast = None
    errors = sorted(lexed.errors + p.errors, key=_by_position)
    warnings = sorted(lexed.warnings + p.warnings, key=_by_position)
    if ast is None and not errors:  # defensive: every path that drops the tree reports why
        errors = [
            Diagnostic(
                code=DiagnosticCode.PARSE_EXPECTED_TERM,
                message="Nothing here can be searched.",
                span=(0, len(q)),
            )
        ]
    if errors or ast is None:
        return ParseResult(ast=None, warnings=warnings, errors=errors)
    canonical = render(canonicalize(ast))
    return ParseResult(
        ast=ast,
        canonical=canonical,
        canonical_hash=canonical_hash(canonical),
        warnings=warnings,
        errors=errors,
    )
