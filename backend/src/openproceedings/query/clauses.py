"""Each filter field's top-level clause, for facet and include clicks (spec 02 §Filter clauses; spec 05 §URL is
state; decision-011).

A facet click rewrites `q` (guarantee 3). The UI must not re-parse filters, so the server reports, per filter
field, the one clause a click may edit: its code-point span in `q` and the values it admits.

"Top-level" is judged on the flattened canonical tree, the tree `defaults.py` reads (parenthesised AND groups
are flattened, `NOT NOT x` is `x`, an OR of one field's filters is one filter). For each field:
- **one top-level clause**: its span is the span of the written conjunct it came from (the whole
  `(track:a OR track:b)` group or `NOT NOT track:a`, so a splice replaces everything that clause was),
  its values are the canonical ones (sorted, merged). A negated clause (`NOT track:x`) is reported with
  `negated: true` and is not toggleable: adding a value inside it would flip what it removes;
- **more than one** (`track:workshop llm AND (venue:NeurIPS track:workshop)`, or two written copies of one
  clause that the canonical form deduplicates): no span, not toggleable (`multiple_clauses`): a splice over
  one would leave the other ANDed in, so the edit would silently change nothing;
- **none at the top level but some nested** under an OR or NOT: not toggleable, `mixed_fields` when a
  top-level OR joins filters of several fields (`track:workshop OR venue:ICLR`), else `nested`;
- **none at all**: the zero-width span `(len(q), len(q))`, the spot a default is inserted at, with the
  default's values (track, status) or every value the field can take (venue: the vocabulary; year: one
  range `1000..9999`). A click writes it out as `(q) AND field:(…)`.

An editable clause is then checked by making the widest edit a click can make (every vocabulary value; for
year, one `dddd..dddd` range) exactly as the reducer writes it, and parsing that with the parser itself, in
the query's mode, so the answer is the server's own. The clause is not toggleable when the edited `q` would
be `too_long` (over 2,000 code points raw or canonical, decision-008), `too_deep` (the wrap nests `q` one
level deeper; PARSE_TOO_DEEP), an `unparsable_edit` for another reason (a `q` ending in an escaping
backslash, which would escape the wrap's `)`), or would not end with exactly that one top-level clause of
the field (`multiple_clauses`: a written copy the canonical form deduplicated, `track:main NOT NOT
(track:main a)`, survives the splice).

`filter_clauses` is not part of `parse`: it parses up to four edited strings, which `/search` and replay do
not need, and `parse` calling it would recurse. `POST /parse` serves it as `filters`.
"""

from __future__ import annotations

from typing import Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query.ast import (
    FILTER_FIELDS,
    MAX_YEAR,
    MIN_YEAR,
    And,
    Filter,
    FilterField,
    Node,
    Not,
    Or,
    Span,
    YearRange,
)
from openproceedings.query.canonical import canonicalize
from openproceedings.query.defaults import DEFAULT_CLAUSES
from openproceedings.query.parser import ParseResult, parse
from openproceedings.vocab import STATUSES, TRACKS, VENUES

ClauseReason = Literal[
    "multiple_clauses", "nested", "mixed_fields", "negated", "too_long", "too_deep", "unparsable_edit"
]
CLAUSE_REASONS: tuple[ClauseReason, ...] = get_args(ClauseReason)
VOCABULARY: dict[FilterField, tuple[str, ...]] = {
    "venue": tuple(sorted(VENUES.values())),
    "track": tuple(sorted(TRACKS)),
    "status": tuple(sorted(STATUSES)),
}
EVERY_YEAR = YearRange(lo=MIN_YEAR, hi=MAX_YEAR)
_WIDEST_YEAR = f"year:{MIN_YEAR}..{MAX_YEAR}"  # the longest single range a click writes (`dddd..dddd`)


class _Clause(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)
    field: FilterField
    negated: bool = Field(description="The clause is `NOT field:…`. A negated clause is never toggleable.")
    span: Span | None = Field(
        description="Half-open code-point range of the clause in `q`. Zero-width at the end, `[len(q), len(q)]`, "
        "when the field has no clause of its own (an applied default, or no restriction): a click writes it out "
        "as `(q) AND field:(…)`. Null when the field has no single top-level clause (`reason` says why)."
    )
    toggleable: bool = Field(description="A facet or include click may rewrite this clause.")
    reason: ClauseReason | None = Field(description="Why it can't be, exactly when `toggleable` is false.")

    def _check(self, admitted: object) -> None:
        if (self.span is None) != (admitted is None):
            raise ValueError("a clause has both a span and its values, or neither")
        if self.toggleable == (self.reason is not None):
            raise ValueError("a clause has a reason exactly when it is not toggleable")
        if self.toggleable and (self.negated or self.span is None):
            raise ValueError("only a positive clause with a span is toggleable")


class ParsedClause(_Clause):
    """A `venue`, `track` or `status` clause."""

    values: list[str] | None = Field(
        description="The values the clause admits, sorted: an applied default's, or every value for an "
        "unrestricted field. Null exactly when `span` is."
    )

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        self._check(self.values)
        return self


class ParsedYearClause(_Clause):
    """The `year` clause. Years are ranges, not a value list."""

    ranges: list[YearRange] | None = Field(
        description="The year ranges the clause admits, sorted and merged; `1000..9999` for no restriction. "
        "Null exactly when `span` is."
    )

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        self._check(self.ranges)
        return self


class ParsedFilters(BaseModel):
    """Every filter field's clause (`POST /parse` `filters`)."""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)
    venue: ParsedClause
    year: ParsedYearClause
    track: ParsedClause
    status: ParsedClause


def _conjuncts(n: Node) -> list[Node]:
    return list(n.children) if isinstance(n, And) else [n]


def _written(n: Node) -> list[Node]:
    """The top-level conjuncts as written: AND groups flattened, nothing else rewritten."""
    return [c for child in n.children for c in _written(child)] if isinstance(n, And) else [n]


def _clause_of(n: Node) -> tuple[FilterField, bool] | None:
    """(field, negated) if canonical node `n` is a filter clause (`field:…` or `NOT field:…`), else None."""
    inner = n.child if isinstance(n, Not) else n
    return (inner.field, isinstance(n, Not)) if isinstance(inner, Filter) else None


def _filters(n: Node, field: FilterField) -> bool:
    """Whether a filter on `field` occurs anywhere under `n`."""
    if isinstance(n, Filter):
        return n.field == field
    if isinstance(n, Not):
        return _filters(n.child, field)
    if isinstance(n, And | Or):
        return any(_filters(c, field) for c in n.children)
    return False


def _mixed(n: Node, field: FilterField) -> bool:
    """Whether `n` is an OR of filter clauses on several fields, `field` among them."""
    if not isinstance(n, Or):
        return False
    clauses = [_clause_of(c) for c in n.children]
    fields = {c[0] for c in clauses if c is not None}
    return None not in clauses and field in fields and len(fields) > 1


def _format(field: FilterField, values: tuple[str, ...]) -> str:
    """A clause as the reducer writes it (`search-state.ts::formatClause`)."""
    return f"{field}:{values[0]}" if len(values) == 1 else f"{field}:({' OR '.join(values)})"


def _widest(q: str, field: FilterField, span: Span) -> str:
    """`q` after the longest edit a click can make to `field`'s clause at `span` (the reducer's own splice)."""
    clause = _WIDEST_YEAR if field == "year" else _format(field, VOCABULARY[field])
    start, end = span
    if start == end == len(q):
        return f"({q}) AND {clause}"
    return q[:start] + clause + q[end:]


def _check_edit(q: str, result: ParseResult, field: FilterField, span: Span) -> ClauseReason | None:
    """Why the widest click on `field`'s clause at `span` can't be made, or None if it can: the edited `q`
    parses (in the query's mode) and has exactly one top-level `field` clause, the one written."""
    edited = parse(_widest(q, field, span), result.mode)
    codes = {e.code for e in edited.errors}
    if DiagnosticCode.PARSE_TOO_DEEP in codes:
        return "too_deep"
    if DiagnosticCode.PARSE_TOO_LONG in codes:
        return "too_long"
    if edited.effective_ast is None:
        return "unparsable_edit"  # e.g. a q ending in an escaping backslash, which would escape the `)`
    widest = (EVERY_YEAR,) if field == "year" else VOCABULARY[field]
    top = [c for c in _conjuncts(edited.effective_ast) if (k := _clause_of(c)) is not None and k[0] == field]
    if len(top) != 1 or not isinstance(top[0], Filter) or top[0].values != widest:
        return "multiple_clauses"  # another written clause of the field survives the splice
    return None


def _report(
    q: str, result: ParseResult, typed: list[tuple[Node, Node]], canon: list[Node], field: FilterField
) -> tuple[bool, Span | None, tuple[str | YearRange, ...] | None, ClauseReason | None]:
    """(negated, span, values, reason) for `field`; reason None = toggleable. `typed`: the written top-level
    conjuncts, each with its canonical form; `canon`: the canonical tree's top-level conjuncts."""
    own = [c for c in canon if (k := _clause_of(c)) is not None and k[0] == field]
    written = [c for c, k in ((c, _clause_of(n)) for c, n in typed) if k is not None and k[0] == field]
    if len(own) > 1 or len(written) > 1:
        return False, None, None, "multiple_clauses"
    if own:
        negated = isinstance(own[0], Not)
        clause = own[0].child if isinstance(own[0], Not) else own[0]
        assert isinstance(clause, Filter)
        if not written:  # it is top-level only once canonicalised (`NOT NOT (a track:x)`): written nested
            return False, None, None, "nested"
        span = written[0].span
        if negated:
            return True, span, clause.values, "negated"
        reason = _check_edit(q, result, field, span)
        if reason == "multiple_clauses":  # another written copy survives the splice: no single clause
            return False, None, None, reason
        return False, span, clause.values, reason
    holders = [c for c in canon if _filters(c, field)]
    if holders:
        return False, None, None, "mixed_fields" if any(_mixed(c, field) for c in holders) else "nested"
    span = (len(q), len(q))
    admitted: tuple[str | YearRange, ...] = (
        (EVERY_YEAR,) if field == "year" else DEFAULT_CLAUSES.get(field, VOCABULARY[field])
    )
    return False, span, admitted, _check_edit(q, result, field, span)


def filter_clauses(q: str, result: ParseResult) -> ParsedFilters | None:
    """Each filter field's clause in `q`, as `parse(q, mode)` read it (`result`); None when it has errors."""
    if result.ast is None:
        return None
    canon = _conjuncts(canonicalize(result.ast))
    typed = [(c, canonicalize(c)) for c in _written(result.ast)]
    reports: dict[str, ParsedClause | ParsedYearClause] = {}
    for field in FILTER_FIELDS:
        negated, span, values, reason = _report(q, result, typed, canon, field)
        common = {
            "field": field,
            "negated": negated,
            "span": span,
            "toggleable": reason is None,
            "reason": reason,
        }
        if field == "year":
            ranges = None if values is None else [v for v in values if isinstance(v, YearRange)]
            reports[field] = ParsedYearClause(**common, ranges=ranges)
        else:
            strings = None if values is None else [v for v in values if isinstance(v, str)]
            reports[field] = ParsedClause(**common, values=strings)
    return ParsedFilters.model_validate(reports)
