"""Exclusion accounting (spec 03 §Exclusion accounting, guarantee 6; default-filters and prisma-reporting skills).

`excluded(engine, parsed)` says how many records the default filters removed, and why, using nothing but the
Engine protocol, so ReferenceEngine and TantivyEngine compute it the same way and can be compared.

- The counts come from `ParseResult.identification_ast` (None = every record) and `defaults`, never from
  re-parsing `identification_query`, which can be `""` or all-negative.
- Buckets are assigned track first, then status: a record that fails both defaults (a rejected workshop
  paper) counts once, under its track. So the buckets always sum to `total`.
- Both counts are disjunctive facets. The track bucket counts `identification ∧ track-default` by track, so
  the facet drops the track clause and counts every identified record. The status bucket counts the
  effective query by status, so it counts every identified record that passed the track default. A default
  field has no other top-level clause in the identification tree (defaults.py), so nothing else is dropped.
- `unknown` is always its own key, even at 0: unclassified is not ineligible.
"""

from __future__ import annotations

from dataclasses import dataclass

from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.protocol import Engine, EngineError, EngineInputError
from openproceedings.query.ast import And, Filter, FilterField, Node
from openproceedings.query.defaults import DEFAULT_CLAUSES
from openproceedings.query.parser import ParseResult

ORDER: tuple[FilterField, ...] = ("track", "status")  # the fixed bucket order (spec 03)


@dataclass(frozen=True, slots=True)
class Excluded:
    total: int
    track: dict[str, int]
    status: dict[str, int]

    def to_json(self) -> dict[str, object]:
        """The shape pinned in spec 04: `{"total": n, "track": {...}, "status": {...}}`."""
        return {"total": self.total, "track": dict(self.track), "status": dict(self.status)}


def excluded(engine: Engine, parsed: ParseResult) -> Excluded:
    """The records the default filters removed from `parsed`'s search, bucketed track first, then status."""
    if parsed.effective_ast is None:
        raise EngineInputError(DiagnosticCode.API_BAD_PARAM, "exclusions need a query that parses.")
    defaults = [f for f in ORDER if f in parsed.defaults]
    identified = parsed.identification_ast
    buckets: dict[FilterField, dict[str, int]] = {f: {} for f in ORDER}
    passed = identified  # the identified records still in, before each field's default is applied
    size: int | None = None  # |identified|, from the first default's facet (each record has one value)
    for field in defaults:
        default = Filter(span=(0, 0), field=field, values=DEFAULT_CLAUSES[field])
        # over `passed`: the facet drops `default`, its own field's top-level clause
        counts = engine.facets(_and(passed, default), (field,))[field]
        if size is None:
            size = sum(counts.values())
        buckets[field] = {v: n for v, n in counts.items() if v not in DEFAULT_CLAUSES[field]}
        passed = _and(passed, default)
    total = len(engine.match_ids(parsed.effective_ast))
    removed = 0 if size is None else size - total
    if sum(n for b in buckets.values() for n in b.values()) != removed:
        raise EngineError(
            DiagnosticCode.API_INTERNAL,
            f"exclusion buckets don't sum to the {removed} records the defaults removed",
        )
    return Excluded(removed, _shaped(buckets["track"]), _shaped(buckets["status"]))


def _and(a: Node | None, b: Node) -> Node:
    if a is None:
        return b
    children = (*a.children, b) if isinstance(a, And) else (a, b)
    return And(span=(0, 0), children=children)


def _shaped(bucket: dict[str, int]) -> dict[str, int]:
    """Buckets by name (facets only count values that occur), then `unknown` last, always present."""
    out = {v: n for v, n in sorted(bucket.items()) if v != "unknown"}
    out["unknown"] = bucket.get("unknown", 0)
    return out
