"""Canonical form and canonical_hash (spec 02 §Outputs; decision-001 rule 5).

`canonicalize` puts an AST in normal form without changing what it matches:
- nested AND in AND (and OR in OR) is flattened;
- in every AND, text conjuncts keep their order and filter conjuncts (`venue:x`, `NOT track:y`) follow,
  ordered venue, year, track, status, then other fields alphabetically, a positive filter before a
  negated one of the same field;
- an OR whose branches are all filters of one field becomes one filter; filter values are sorted and
  deduplicated.

`render` prints it fully parenthesised with uppercase operators and a field prefix on every leaf, in a
form that re-parses to the same tree: `parse(canonical).canonical == canonical` (property-tested).
`gpt-4*` prints as `"gpt 4*"` (in a phrase the earlier words count toward a wildcard's stem), and a lone
token that spells an operator in lowercase is quoted (`"and"`), so re-parsing raises no warning.

`canonical_hash` = sha256 of the canonical string and TOKENIZER_VERSION joined by a NUL byte.
"""

from __future__ import annotations

import hashlib

from openproceedings.query.ast import (
    And,
    Filter,
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
from openproceedings.query.normalize import TOKENIZER_VERSION

FILTER_ORDER = ("venue", "year", "track", "status")
_OPERATOR_WORDS = frozenset({"and", "or", "not"})


def _filter_key(n: Node) -> tuple[int, str, int, str] | None:
    """Sort key for a filter conjunct, or None if `n` is not one."""
    neg = isinstance(n, Not)
    f = n.child if isinstance(n, Not) else n
    if not isinstance(f, Filter):
        return None
    rank = FILTER_ORDER.index(f.field) if f.field in FILTER_ORDER else len(FILTER_ORDER)
    return (rank, f.field, int(neg), render(f))


def _value_key(v: str | YearRange) -> tuple[int, int, str]:
    return (v.lo, v.hi, "") if isinstance(v, YearRange) else (0, 0, v)


def _sorted_values(values: tuple[str | YearRange, ...]) -> tuple[str | YearRange, ...]:
    return tuple(sorted(set(values), key=_value_key))


def canonicalize(n: Node) -> Node:
    """The normal form of `n` (see the module docstring). Spans are kept from the input nodes."""
    if isinstance(n, Not):
        return n.model_copy(update={"child": canonicalize(n.child)})
    if isinstance(n, Filter):
        return n.model_copy(update={"values": _sorted_values(n.values)})
    if not isinstance(n, And | Or):
        return n
    children: list[Node] = []
    for c in (canonicalize(c) for c in n.children):
        children.extend(c.children if isinstance(c, And | Or) and type(c) is type(n) else (c,))
    if isinstance(n, Or) and all(isinstance(c, Filter) for c in children):
        fields = {c.field for c in children if isinstance(c, Filter)}
        if len(fields) == 1:
            values = tuple(v for c in children if isinstance(c, Filter) for v in c.values)
            return Filter(span=n.span, field=fields.pop(), values=_sorted_values(values))
    if isinstance(n, And):
        text = [c for c in children if _filter_key(c) is None]
        filters = sorted(
            (c for c in children if _filter_key(c) is not None), key=lambda c: _filter_key(c) or ()
        )
        children = text + filters
    return n.model_copy(update={"children": tuple(children)})


def _prefix(field: TextField | str | None) -> str:
    return f"{field}:" if field else ""


def _phrase_body(items: tuple[Term | Wildcard, ...]) -> str:
    return " ".join(item.token if isinstance(item, Term) else item.stem + item.op for item in items)


def _render_value(v: str | YearRange) -> str:
    if isinstance(v, YearRange):
        return str(v.lo) if v.lo == v.hi else f"{v.lo}..{v.hi}"
    return v


def render(n: Node) -> str:
    """The canonical string of an already canonicalized node."""
    if isinstance(n, Term):
        token = f'"{n.token}"' if n.token in _OPERATOR_WORDS else n.token
        return f"{_prefix(n.field)}{token}"
    if isinstance(n, Wildcard):
        return (
            f"{_prefix(n.field)}{n.stem}{n.op}"  # a lone wildcard always has a full stem (the lexer checks)
        )
    if isinstance(n, Phrase):
        return f'{_prefix(n.field)}"{_phrase_body(n.items)}"'
    if isinstance(n, Near):
        return f"({render(n.left)} NEAR/{n.distance} {render(n.right)})"
    if isinstance(n, Not):
        return f"NOT {render(n.child)}"
    if isinstance(n, Filter):
        values = [_render_value(v) for v in n.values]
        return f"{n.field}:{values[0]}" if len(values) == 1 else f"{n.field}:({' OR '.join(values)})"
    op = " AND " if isinstance(n, And) else " OR "
    return "(" + op.join(render(c) for c in n.children) + ")"


def canonical_hash(canonical: str) -> str:
    return hashlib.sha256(f"{canonical}\x00{TOKENIZER_VERSION}".encode()).hexdigest()
