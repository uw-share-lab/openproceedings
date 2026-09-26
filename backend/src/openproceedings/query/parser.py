"""The query parser (spec 02 §Grammar, §Error handling; decision-001): lexemes → AST plus diagnostics.

Recursive descent over the EBNF, with NOT > AND > OR and juxtaposition as AND. `parse` never raises: every
problem is a Diagnostic with a span, `ast` is None exactly when there are errors (nothing to search), and
one mistake gives one error (an error already reported inside a span suppresses follow-on errors there).

- A level that mixes AND and OR without parentheses parses by precedence and raises WARN_MIXED_AND_OR,
  showing how it was read.
- A bare word or range OR-joined to a filter that is a valid value of that filter's field
  (`year:2023 OR 2024`) is searched as text, as written, and raises WARN_FILTER_SCOPE.
- A word that normalises to several tokens is a Phrase; a wildcard word's wildcard goes on its last token
  (`gpt-4*` → Phrase[gpt, Wildcard(4*)]). Phrase parts that normalise to nothing are skipped.
- `title:`/`abstract:` apply their field to every leaf of what follows; filter fields take one value or
  an OR group of values, checked against `vocab.py`. `source:` is Scholar syntax: FIELD_COMPAT_ONLY here.
- NEAR/n joins two leaves (words, wildcards or phrases; a one-word group counts as a word) in the same
  field, once.
- A query with no positive part (`NOT a`, `a OR NOT b`) is PARSE_ALL_NEGATIVE; `NOT NOT a` is positive.
  This is checked before default filters are added (task-014), which would otherwise hide it.

`ParseResult.canonical`/`.canonical_hash` come from `canonical.py` and the default filters, with
`effective_ast`, `identification_query` and `defaults`, from `defaults.py`. Scholar mode is task-015.
"""

from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from openproceedings.diagnostics import Diagnostic, DiagnosticCode
from openproceedings.query.ast import (
    MAX_YEAR,
    MIN_YEAR,
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
from openproceedings.query.canonical import canonical_hash, render
from openproceedings.query.compat import (
    PARTIAL_SOURCES,
    SOURCE_ALIASES,
    dollar_notices,
    group_phrases,
    source_key,
)
from openproceedings.query.defaults import apply_defaults
from openproceedings.query.lexer import FIELDS, Kind, Lexeme, lex
from openproceedings.query.normalize import tokenize
from openproceedings.vocab import STATUSES, TEXT_FIELDS, TRACKS, VENUES

Mode = Literal["native", "scholar"]
MAX_DEPTH = 64  # nested groups and NOTs; deeper is PARSE_TOO_DEEP, so recursion can never overflow
_STARTS = frozenset({Kind.WORD, Kind.PHRASE, Kind.LPAREN, Kind.FIELD, Kind.NOT, Kind.RANGE})
_EXAMPLES = {
    "venue": "venue:NeurIPS",
    "year": "year:2020..2026",
    "track": "track:main",
    "status": "status:accepted",
}
_VALID: dict[str, tuple[str, ...]] = {"venue": tuple(VENUES.values()), "track": TRACKS, "status": STATUSES}


class ParseResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Mode = "native"
    ast: Node | None  # the tree as typed, spans into q (the UI's parse tree)
    effective_ast: Node | None = None  # canonical, with default filters: what the engine runs
    canonical: str | None = (
        None  # render(effective_ast); every Optional here is None exactly when there are errors
    )
    canonical_hash: str | None = None
    identification_query: str | None = None  # canonical without the default conjuncts; "" = every record
    defaults: list[
        FilterField
    ] = []  # fields whose top-level clause is the default (spec 03 §Exclusion accounting)
    warnings: list[Diagnostic]
    errors: list[Diagnostic]
    translations: list[Diagnostic] = []


class _TooDeep(Exception):
    """Unwinds the parser once MAX_DEPTH is exceeded; never escapes `parse`."""


def _positive(n: Node) -> bool:
    """Whether `n` restricts the corpus to something (rather than matching everything except something)."""
    if isinstance(n, Not):
        return isinstance(n.child, Not) and _positive(n.child.child)
    if isinstance(n, And):
        return any(_positive(c) for c in n.children)
    if isinstance(n, Or):
        return all(_positive(c) for c in n.children)
    return True


def filter_value(field: FilterField, v: Lexeme) -> str | YearRange | None:
    """The canonical value `v` spells for `field`, or None if it is not a valid one."""
    if field == "year":
        if v.kind is Kind.RANGE and v.range is not None:
            lo, hi = v.range
        elif v.kind is Kind.WORD and v.wildcard is None and v.text.isascii() and v.text.isdigit():
            lo = hi = int(v.text)
        else:
            return None
        return YearRange(lo=lo, hi=hi) if MIN_YEAR <= lo <= hi <= MAX_YEAR else None
    if v.kind is not Kind.WORD or v.wildcard is not None:
        return None
    key = v.text.lower()
    if field == "venue":
        return VENUES.get(key)
    return key if key in _VALID[field] else None


class _Parser:
    def __init__(
        self, q: str, lexemes: tuple[Lexeme, ...], lex_errors: tuple[Diagnostic, ...], mode: Mode = "native"
    ) -> None:
        self.q = q
        self.mode = mode
        self.in_source = False  # parsing a Scholar `source:` clause: values translate to venues
        self.translations: list[Diagnostic] = []
        self.toks = lexemes
        self.i = 0
        self.depth = 0
        self.lex_errors = lex_errors
        self.errors: list[Diagnostic] = []
        self.warnings: list[Diagnostic] = []

    # --- cursor and diagnostics ---------------------------------------------------------------------
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

    def reported(self, start: int, end: int) -> bool:
        """Whether an error already covers part of [start, end), so a second one would repeat it."""
        return any(
            e.span is not None and e.span[0] < max(end, start + 1) and start < max(e.span[1], e.span[0] + 1)
            for e in (*self.lex_errors, *self.errors)
        )

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
    def run(self) -> Node | None:
        if not self.toks:
            if not self.lex_errors:
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
            elif not self.reported(tok.start, tok.end):  # never drop part of a query silently
                self.error(
                    DiagnosticCode.PARSE_EXPECTED_TERM, f"Unexpected `{tok.text}` here.", tok.start, tok.end
                )
            if self.starts():
                self.or_expr(None)  # keep going, so later errors are reported too
        if node is not None and not self.errors and not self.lex_errors and not _positive(node):
            self.error(
                DiagnosticCode.PARSE_ALL_NEGATIVE,
                "Every part of this query is excluded (`NOT …`), so it would match almost everything — add "
                "something to search for, e.g. `trust NOT bias`.",
                *node.span,
            )
        return node

    def or_expr(self, field: TextField | None) -> Node | None:
        start = self.i
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
        if len(branches) > 1:
            self.filter_scope(self.toks[start : self.i], nodes)
        return self.combine(Or, nodes)

    def filter_scope(self, toks: tuple[Lexeme, ...], nodes: list[Node]) -> None:
        """WARN_FILTER_SCOPE for `year:2023 OR 2024`: an OR branch that is just a bare value of the field of
        a filter in another branch of the same OR."""
        fields = sorted({n.field for n in nodes if isinstance(n, Filter)})
        words = [t for t in toks if t.kind is Kind.WORD]
        for n in nodes:
            inside = [t for t in words if n.span[0] <= t.start and t.end <= n.span[1]]  # `2024` or `(2024)`
            tok = inside[0] if isinstance(n, Term) and n.field is None and len(inside) == 1 else None
            f = next((f for f in fields if tok and filter_value(f, tok) is not None), None)
            if tok and f:
                self.warnings.append(
                    Diagnostic(
                        code=DiagnosticCode.WARN_FILTER_SCOPE,
                        message=f"`{tok.text}` is searched as text in any paper, not as a {f} — to OR it into the "
                        f"filter, write `{f}:(… OR {tok.text})`.",
                        span=(tok.start, tok.end),
                    )
                )

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

    def operand(self, field: TextField | None) -> tuple[Node | None, bool]:
        """A primary, and whether it failed with an error already reported (so NEAR needn't add one)."""
        i0, n0 = self.i, len(self.errors)
        node = self.primary(field)
        if node is not None or self.i == i0:
            return node, False
        return None, len(self.errors) > n0 or self.reported(self.toks[i0].start, self.toks[self.i - 1].end)

    def near_or_primary(self, field: TextField | None) -> Node | None:
        left, left_failed = self.operand(field)
        if not self.at(Kind.NEAR):
            return left
        op = self.advance()
        right, right_failed = self.operand(field) if self.starts() else (None, False)
        node: Node | None = None
        leaves = (Term, Wildcard, Phrase)
        if not isinstance(left, leaves) or not isinstance(right, leaves):
            if not (left_failed or right_failed):
                self.error(
                    DiagnosticCode.PARSE_BAD_NEAR,
                    f"`{op.text}` joins two words or phrases, e.g. `trust {op.text} calibration`; it can't take a "
                    "group, a filter or nothing.",
                    op.start,
                    op.end,
                )
        elif left.field != right.field:
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
            op2 = self.peek()
            assert op2 is not None
            self.error(
                DiagnosticCode.PARSE_BAD_NEAR,
                f"`NEAR` can't be chained — join the pairs with AND, e.g. `(a {op.text} b) AND (b {op2.text} c)`.",
                op2.start,
                op2.end,
            )
            while self.at(Kind.NEAR):
                self.advance()
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
            self.advance()  # consumed here, so the operator loops don't report it a second time
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
        if name not in FIELDS:  # FIELD_UNKNOWN is the lexer's; what follows is parsed by the caller's loop
            return None
        if name == "source" and self.mode == "scholar":
            self.in_source = True
            try:
                return self.filter(tok, "venue")
            finally:
                self.in_source = False
        if name == "source":
            self.error(
                DiagnosticCode.FIELD_COMPAT_ONLY,
                f"`{tok.text}` is Google Scholar syntax — write `venue:NeurIPS`, `venue:ICLR` or `venue:ICML` "
                "(Scholar-mode input translates it automatically).",
                tok.start,
                tok.end,
            )
            if self.at(Kind.WORD, Kind.PHRASE, Kind.RANGE):
                self.advance()  # its value: not a mistake of its own (a group is parsed for real errors)
            return None
        if name not in TEXT_FIELDS:
            if outer is not None:
                self.warnings.append(
                    Diagnostic(
                        code=DiagnosticCode.WARN_FILTER_SCOPE,
                        message=f"`{tok.text}` inside `{outer}:(…)` filters whole papers, not the {outer} — move it "
                        "out of the group to make that clear.",
                        span=(tok.start, tok.end),
                    )
                )
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
            follows = "another field" if self.at(Kind.FIELD) else "an operator" if self.peek() else "nothing"
            self.error(
                DiagnosticCode.PARSE_EXPECTED_TERM,
                f"`{tok.text}` must be followed by a word, a phrase or a (group), not {follows} — e.g. "
                f"`{tok.text}trust`.",
                tok.start,
                tok.end,
            )
            return None
        node = self.primary(cast(TextField, name))
        return node.model_copy(update={"span": (tok.start, node.span[1])}) if node is not None else None

    def filter(self, tok: Lexeme, name: FilterField) -> Node | None:
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
        syntax = f"`{tok.text}(…)` takes values joined by OR, e.g. `{tok.text}(a OR b)`."
        values: list[str | YearRange] = []
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
            if value is not None:
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
        if self.reported(lp.start, end):
            return None
        return Filter(span=(tok.start, end), field=name, values=tuple(values))

    def source_value(self, v: Lexeme) -> str | None:
        """A Scholar `source:` value translated to a venue through the alias table (exact, never substring)."""
        text = (
            " ".join(p.text for p in v.parts)
            if v.kind is Kind.PHRASE
            else v.text
            if v.kind is Kind.WORD
            else ""
        )
        key = source_key(text) if v.wildcard is None else ""
        venue = SOURCE_ALIASES.get(key)
        if venue is None:
            if not self.reported(v.start, v.end):
                known = ", ".join(f"`{k}`" for k in SOURCE_ALIASES)
                self.error(
                    DiagnosticCode.FIELD_UNKNOWN_VALUE,
                    f"`{v.text}` is not a known `source:` (matched exactly, not as a substring) — use one of {known}, "
                    "or write `venue:` directly.",
                    v.start,
                    v.end,
                )
            return None
        self.translations.append(
            Diagnostic(
                code=DiagnosticCode.COMPAT_SOURCE_ALIAS,
                message=f"`source:{v.text}` is read as `venue:{venue}`.",
                span=(v.start, v.end),
            )
        )
        if key in PARTIAL_SOURCES:
            self.warnings.append(
                Diagnostic(
                    code=DiagnosticCode.WARN_SOURCE_PARTIAL,
                    message=f"`{v.text}` also hosts other venues; only ICML is indexed, so it matches ICML papers only.",
                    span=(v.start, v.end),
                )
            )
        return venue

    def value(self, name: FilterField, v: Lexeme) -> str | YearRange | None:
        if self.in_source:
            return self.source_value(v)
        found = filter_value(name, v)
        if found is not None or self.reported(v.start, v.end):
            return found
        if name == "year":
            if v.kind is Kind.RANGE and v.range is not None and v.range[0] > v.range[1]:
                lo, hi = v.range
                self.error(
                    DiagnosticCode.FIELD_RANGE_INVERTED,
                    f"`{v.text}` runs backwards — write `{hi}..{lo}`.",
                    v.start,
                    v.end,
                )
            else:
                self.error(
                    DiagnosticCode.FIELD_UNKNOWN_VALUE,
                    f"`{v.text}` is not a year — `year:` takes a four-digit year or an inclusive range, e.g. "
                    "`year:2024` or `year:2020..2026`.",
                    v.start,
                    v.end,
                )
            return None
        self.error(
            DiagnosticCode.FIELD_UNKNOWN_VALUE,
            f"`{v.text}` is not a {name} (values take no wildcards or quotes) — use one of "
            + ", ".join(f"`{x}`" for x in _VALID[name])
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
        toks = tokenize(w.stem or "")
        items: list[Term | Wildcard] = [
            Term(span=(w.start + t.start, w.start + t.end), token=t.text, field=field) for t in toks
        ]
        if w.wildcard and toks:
            last = toks[-1]
            op = cast(Literal["*", "$"], w.wildcard)
            items[-1] = Wildcard(span=(w.start + last.start, w.end), stem=last.text, op=op, field=field)
        return items

    def leaf(self, tok: Lexeme, items: list[Term | Wildcard], field: TextField | None) -> Leaf:
        if len(items) == 1:
            return items[0].model_copy(update={"span": (tok.start, tok.end), "field": field})
        return Phrase(span=(tok.start, tok.end), items=tuple(items), field=field)

    def word(self, tok: Lexeme, field: TextField | None) -> Node | None:
        items = self.items(tok, None)
        if items:
            return self.leaf(tok, items, field)
        if not self.reported(tok.start, tok.end):
            self.error(
                DiagnosticCode.PARSE_EMPTY_TERM,
                f"`{tok.text}` has no letters or digits, so it can't match anything — remove it (to exclude a word, "
                "write `-word` with no space).",
                tok.start,
                tok.end,
            )
        return None

    def phrase(self, tok: Lexeme, field: TextField | None) -> Node | None:
        items = [item for part in tok.parts for item in self.items(part, None)]
        if items:
            return self.leaf(tok, items, field)
        if not self.reported(tok.start, tok.end):
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


def parse(q: str, mode: Mode = "native") -> ParseResult:
    """Parse `q`. Never raises; `ast`, `canonical` and `canonical_hash` are None exactly when `errors` is
    non-empty. `mode="scholar"` accepts Scholar/PoP syntax and reports every rewrite in `translations`."""
    lexed = lex(q)
    lexemes, lex_errors = lexed.lexemes, lexed.errors
    translations: list[Diagnostic] = []
    if mode == "scholar":
        lexemes, translations, cleared = group_phrases(q, lexemes)
        lex_errors = tuple(
            e
            for e in lex_errors
            if not (e.code is DiagnosticCode.WILDCARD_STEM_TOO_SHORT and e.span in cleared)
        )
        translations += dollar_notices(lexemes)
    p = _Parser(q, lexemes, lex_errors, mode)
    try:
        ast = p.run()
    except _TooDeep:
        ast = None
    errors = sorted([*lex_errors, *p.errors], key=_by_position)
    warnings = sorted([*lexed.warnings, *p.warnings], key=_by_position)
    notes = sorted([*translations, *p.translations], key=_by_position)
    if ast is None and not errors:  # defensive: every path that drops the tree reports why
        errors = [
            Diagnostic(
                code=DiagnosticCode.PARSE_EXPECTED_TERM,
                message="Nothing here can be searched.",
                span=(0, len(q)),
            )
        ]
    if errors or ast is None:
        return ParseResult(mode=mode, ast=None, warnings=warnings, errors=errors, translations=notes)
    d = apply_defaults(ast, len(q))
    canonical = render(d.effective)
    return ParseResult(
        mode=mode,
        translations=notes,
        ast=ast,
        effective_ast=d.effective,
        canonical=canonical,
        canonical_hash=canonical_hash(canonical),
        identification_query=render(d.identification) if d.identification is not None else "",
        defaults=list(d.defaults),
        warnings=sorted([*warnings, *d.warnings], key=_by_position),
        errors=errors,
    )
