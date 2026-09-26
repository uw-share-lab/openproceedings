"""Default filters (spec 02 §Default filters, spec 03 §Exclusion accounting; default-filters skill).

On the canonical tree's top-level AND conjuncts (so `(a track:x) b` counts `track:x` as top-level):
- a field in DEFAULT_CLAUSES with no top-level clause of its own (a filter, or `NOT` of one) gets the
  default added. If that field appears only nested (under an OR or a NOT group), the default still
  applies and WARN_NESTED_FILTER says so, on the nested clause;
- a field whose only top-level clause equals the default, by content (sorted values), counts as the
  default whether the parser added it, the user typed it, or it came from a replayed canonical string. A
  default-equal clause next to another clause of its field is the user's own: the parser would not add it;
- `identification` is the tree without the default conjuncts: what PRISMA's "records identified" count
  is computed from. None means the whole corpus (the query was nothing but defaults).
"""

from __future__ import annotations

from dataclasses import dataclass

from openproceedings.diagnostics import Diagnostic, DiagnosticCode
from openproceedings.query.ast import And, Filter, FilterField, Node, Not, Or
from openproceedings.query.canonical import canonicalize

DEFAULT_CLAUSES: dict[FilterField, tuple[str, ...]] = {
    "track": ("datasets_benchmarks", "main", "position"),  # sorted, as canonical form stores values
    "status": ("accepted",),
}


@dataclass(frozen=True, slots=True)
class Defaulted:
    effective: Node  # canonical, with the defaults
    identification: (
        Node | None
    )  # canonical, without them; None = every record (ParseResult.identification_ast)
    defaults: tuple[
        FilterField, ...
    ]  # the fields whose top-level clause is the default, in DEFAULT_CLAUSES order
    warnings: tuple[Diagnostic, ...]


def _conjuncts(n: Node) -> list[Node]:
    return list(n.children) if isinstance(n, And) else [n]


def _combine(nodes: list[Node]) -> Node | None:
    if not nodes:
        return None
    if len(nodes) == 1:
        return nodes[0]
    return And(span=(min(c.span[0] for c in nodes), max(c.span[1] for c in nodes)), children=tuple(nodes))


def _clause_field(n: Node) -> str | None:
    """The field of a top-level filter clause (`track:x` or `NOT track:x`), else None."""
    inner = n.child if isinstance(n, Not) else n
    return inner.field if isinstance(inner, Filter) else None


def _nested_filters(n: Node, field: str) -> list[Filter]:
    """Every filter on `field` anywhere under `n`, in order."""
    if isinstance(n, Filter):
        return [n] if n.field == field else []
    if isinstance(n, Not):
        return _nested_filters(n.child, field)
    if isinstance(n, And | Or):
        return [f for c in n.children for f in _nested_filters(c, field)]
    return []


def _is_default(n: Node) -> bool:
    return isinstance(n, Filter) and n.field in DEFAULT_CLAUSES and n.values == DEFAULT_CLAUSES[n.field]


def apply_defaults(ast: Node, at: int) -> Defaulted:
    """The effective tree for `ast`; inserted clauses get the zero-width span `(at, at)`."""
    conjuncts = _conjuncts(canonicalize(ast))
    defaults: list[FilterField] = []
    added: list[Node] = []
    warnings: list[Diagnostic] = []
    for field, values in DEFAULT_CLAUSES.items():
        own = [c for c in conjuncts if _clause_field(c) == field]
        if len(own) == 1 and _is_default(own[0]):
            defaults.append(field)
        elif not own:
            defaults.append(field)
            added.append(Filter(span=(at, at), field=field, values=values))
        else:
            continue  # the user's own top-level clause decides; nested clauses are just part of the search
        # the default applies, whether inserted, typed or replayed: every nested clause of the field says so
        for nested in (f for c in conjuncts if c not in own for f in _nested_filters(c, field)):
            warnings.append(
                Diagnostic(
                    code=DiagnosticCode.WARN_NESTED_FILTER,
                    message=f"This `{field}:` clause is nested, so the default {field} filter still applies to "
                    f"the whole query — add a top-level `{field}:` clause to override it.",
                    span=nested.span,
                )
            )
    effective = canonicalize(_combine(conjuncts + added) or ast)
    kept = [c for c in _conjuncts(effective) if not (_is_default(c) and _clause_field(c) in defaults)]
    return Defaulted(effective, _combine(kept), tuple(defaults), tuple(warnings))
