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

A click always writes the grouped form, `field:(v)` even for one value, so the clause's `)` ends every edit
and no edit can touch a group that follows it (a bare `track:workshop(x)` is PARSE_PAREN_TOUCHES_WORD); the
canonical form is the same either way. An editable clause is then checked by making the widest edit a click
can make (every vocabulary value; for year, one `(dddd..dddd)` range) exactly as the reducer writes it, and
parsing that with the parser itself, in the query's mode, so the answer is the server's own. The clause is not toggleable when the edited `q` would
be `too_long` (over 2,000 code points raw or canonical, decision-008), `too_deep` (the wrap nests `q` one
level deeper; PARSE_TOO_DEEP), an `unparsable_edit` for another reason (a `q` ending in an escaping
backslash, which would escape the wrap's `)`), or would not end with exactly that one top-level clause of
the field (`multiple_clauses`: a written copy the canonical form deduplicated, `track:main NOT NOT
(track:main a)`, survives the splice).

Every field with no clause is checked by one parse that writes them all out at once, and only when that edit
can't be made is each checked alone; a typed clause is checked by its own splice. So `filter_clauses` parses
one edited string for a query with no typed clauses and at most one more per typed clause, and never more
than five (`test_clauses.py` counts them).

`filter_clauses` is not part of `parse`: the edited strings are work `/search` and replay do not need, and
`parse` calling it would recurse. `POST /parse` serves it as `filters`.
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
from openproceedings.query.parser import Mode, ParseResult, parse
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
# the longest single range a click writes, grouped as every clause is
_WIDEST_YEAR = f"year:({MIN_YEAR}..{MAX_YEAR})"


class _Clause(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)
    field: FilterField = Field(
        description="The filter field: always equal to this clause's key in `filters`."
    )
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


def _clause_field(n: Node) -> FilterField | None:
    """The field if canonical node `n` is a filter clause (`field:…` or `NOT field:…`), else None."""
    inner = n.child if isinstance(n, Not) else n
    return inner.field if isinstance(inner, Filter) else None


def _filters(n: Node, field: FilterField) -> bool:
    """Whether a filter on `field` occurs anywhere under `n`."""
    if isinstance(n, Filter):
        return n.field == field
    if isinstance(n, Not):
        return _filters(n.child, field)
    if isinstance(n, And | Or):
        return any(_filters(c, field) for c in n.children)
    return False


def _mixed(n: Node) -> bool:
    """Whether `n` is an OR of filter clauses (`field:…` or `NOT field:…`) on several fields. The caller only
    asks about a conjunct that holds a filter of its field, so that field is always among them."""
    if not isinstance(n, Or):
        return False
    fields = [_clause_field(c) for c in n.children]
    return None not in fields and len(set(fields)) > 1


def _format(field: FilterField, values: tuple[str, ...]) -> str:
    """A clause as the reducer writes it (`search-state.ts::formatClause`): always grouped, `field:(v)` even for
    one value, so a splice before a group never touches it (`track:workshop(x)` is PARSE_PAREN_TOUCHES_WORD).
    The canonical form, and so the hash, is the same as the bare `field:v`'s."""
    return f"{field}:({' OR '.join(values)})"


def _widest_clause(field: FilterField) -> str:
    """The longest clause a click can write for `field`: every vocabulary value, or one `(dddd..dddd)` range.
    Its `)` ends every edit, so the one check covers every edit shape: none can touch what follows."""
    return _WIDEST_YEAR if field == "year" else _format(field, VOCABULARY[field])


def _edit_reason(edited: str, mode: Mode, fields: tuple[FilterField, ...]) -> ClauseReason | None:
    """Why `edited` (q after the widest click on each of `fields`) can't be written, or None if it can: it
    parses in the query's mode and has exactly one top-level clause of each field, the widest one written."""
    parsed = parse(edited, mode)
    codes = {e.code for e in parsed.errors}
    if DiagnosticCode.PARSE_TOO_DEEP in codes:
        return "too_deep"
    if DiagnosticCode.PARSE_TOO_LONG in codes:
        return "too_long"
    if parsed.effective_ast is None:
        return "unparsable_edit"  # e.g. a q ending in an escaping backslash, which would escape the `)`
    conjuncts = _conjuncts(parsed.effective_ast)
    for field in fields:
        top = [c for c in conjuncts if _clause_field(c) == field]
        widest = (EVERY_YEAR,) if field == "year" else VOCABULARY[field]
        # Only `len(top) != 1` is reachable today: the canonical form never merges two clauses of a field, so
        # the one left is the clause written. The rest is defence against a canonical rule that would.
        if len(top) != 1 or not isinstance(top[0], Filter) or top[0].values != widest:
            return "multiple_clauses"  # another written clause of the field survives the splice
    return None


def _check_splice(q: str, mode: Mode, field: FilterField, span: Span) -> ClauseReason | None:
    """Why the widest click on the typed clause of `field` at `span` can't be made, or None if it can."""
    start, end = span
    return _edit_reason(q[:start] + _widest_clause(field) + q[end:], mode, (field,))


def _check_wrap(q: str, mode: Mode, fields: tuple[FilterField, ...]) -> ClauseReason | None:
    """Why writing each of `fields` out as `(q) AND field:(…)`, all at once, can't be done, or None if it can."""
    return _edit_reason(" AND ".join((f"({q})", *map(_widest_clause, fields))), mode, fields)


def _check_wraps(
    q: str, mode: Mode, fields: tuple[FilterField, ...]
) -> dict[FilterField, ClauseReason | None]:
    """The reason for each field with no clause (a zero-width span), from as few parses as the answer allows.

    One parse writes every such field out at once (`/parse` pays one extra parse, not four, in the common
    case). When that edit can be made, so can each field's own: each is the same wrap with a subset of its
    conjuncts, so never longer, raw or canonical (a default the parser would add is a subset of the widest
    clause written), and never deeper. When it is too deep, so is each: the wrap's `(…)` is the only nesting
    it adds, the same in each. Otherwise each field is checked alone. The answer is exactly the per-field one
    (`test_clauses.py` compares them over generated queries)."""
    if not fields:
        return {}
    together = _check_wrap(q, mode, fields)
    if together is None or together == "too_deep" or len(fields) == 1:
        return dict.fromkeys(fields, together)
    return {f: _check_wrap(q, mode, (f,)) for f in fields}


_Report = tuple[bool, Span | None, tuple[str | YearRange, ...] | None, ClauseReason | None]


def _report(
    q: str, mode: Mode, typed: list[tuple[Node, Node]], canon: list[Node], field: FilterField
) -> _Report | None:
    """(negated, span, values, reason) for `field`; reason None = toggleable. None when the field has no
    clause at all, so its report is the wrap's (`_check_wraps`). `typed`: the written top-level conjuncts,
    each with its canonical form; `canon`: the canonical tree's top-level conjuncts."""
    own = [c for c in canon if _clause_field(c) == field]
    written = [c for c, n in typed if _clause_field(n) == field]
    # Two written copies the canonical form deduplicated are two clauses (spec 02 §Filter clauses), even when
    # a splice over one would leave the other harmless (both already every value): the rule, not a shortcut.
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
        reason = _check_splice(q, mode, field, span)
        if reason == "multiple_clauses":  # another written copy survives the splice: no single clause
            return False, None, None, reason
        return False, span, clause.values, reason
    if any(_filters(c, field) for c in canon):
        return (
            False,
            None,
            None,
            "mixed_fields" if any(_mixed(c) for c in canon if _filters(c, field)) else "nested",
        )
    return None


def filter_clauses(q: str, result: ParseResult) -> ParsedFilters | None:
    """Each filter field's clause in `q`, as `parse(q, mode)` read it (`result`); None when it has errors."""
    if result.ast is None:
        return None
    canon = _conjuncts(canonicalize(result.ast))
    typed = [(c, canonicalize(c)) for c in _written(result.ast)]
    found = {field: _report(q, result.mode, typed, canon, field) for field in FILTER_FIELDS}
    wraps = _check_wraps(q, result.mode, tuple(f for f, r in found.items() if r is None))
    end = (len(q), len(q))
    reports: dict[str, ParsedClause | ParsedYearClause] = {}
    for field, report in found.items():
        # No clause at all: the zero-width span at the end, where a click writes it out as `(q) AND field:(…)`,
        # admitting the default's values (track, status) or every value the field can take.
        admitted = (EVERY_YEAR,) if field == "year" else DEFAULT_CLAUSES.get(field, VOCABULARY[field])
        negated, span, values, reason = report or (False, end, admitted, wraps[field])
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
