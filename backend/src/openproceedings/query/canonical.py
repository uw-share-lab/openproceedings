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

`canonical_hash` = sha256 of the canonical string, TOKENIZER_VERSION and QUERY_VERSION joined by NUL bytes
(decision-003).
"""

from __future__ import annotations

import hashlib

from openproceedings.query import QUERY_VERSION
from openproceedings.query.ast import (
    MIN_YEAR,
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
    structure,
)
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.vocab import STATUSES, TRACKS, VENUES

FILTER_ORDER = ("venue", "year", "track", "status")
_OPERATOR_WORDS = frozenset({"and", "or", "not"})
_VALUE_WORDS = {  # tokens a bare word could be mistaken for, next to a filter of that field (WARN_FILTER_SCOPE)
    "venue": frozenset(VENUES),
    "track": frozenset(TRACKS),
    "status": frozenset(STATUSES),
}


def _filter_key(n: Node) -> tuple[int, int, str] | None:
    """Sort key for a filter conjunct, or None if `n` is not one."""
    f = n.child if isinstance(n, Not) else n
    if not isinstance(f, Filter):
        return None
    return (FILTER_ORDER.index(f.field), int(isinstance(n, Not)), render(f))


def _value_key(v: str | YearRange) -> tuple[int, int, str]:
    return (v.lo, v.hi, "") if isinstance(v, YearRange) else (0, 0, v)


def _sorted_values(values: tuple[str | YearRange, ...]) -> tuple[str | YearRange, ...]:
    ordered = sorted(set(values), key=_value_key)
    if not all(isinstance(v, YearRange) for v in ordered):
        return tuple(ordered)
    merged: list[YearRange] = []  # overlapping or adjacent year ranges are one range
    for v in ordered:
        assert isinstance(v, YearRange)
        if merged and v.lo <= merged[-1].hi + 1:
            merged[-1] = YearRange(lo=merged[-1].lo, hi=max(merged[-1].hi, v.hi))
        else:
            merged.append(v)
    return tuple(merged)


def _merge_filters(children: list[Node]) -> list[Node]:
    """In an OR, positive filters on one field become one filter, at the first one's position."""
    out: list[Node] = []
    first: dict[str, int] = {}
    for c in children:
        if isinstance(c, Filter) and c.field in first:
            i = first[c.field]
            prev = out[i]
            assert isinstance(prev, Filter)
            out[i] = prev.model_copy(update={"values": _sorted_values(prev.values + c.values)})
        else:
            if isinstance(c, Filter):
                first[c.field] = len(out)
            out.append(c)
    return out


def _dedupe(children: list[Node]) -> list[Node]:
    seen: list[object] = []
    out = []
    for c in children:
        key = structure(c)
        if key not in seen:
            seen.append(key)
            out.append(c)
    return out


def canonicalize(n: Node) -> Node:
    """The normal form of `n` (see the module docstring). Spans are kept from the input nodes."""
    if isinstance(n, Not):
        child = canonicalize(n.child)
        return child.child if isinstance(child, Not) else n.model_copy(update={"child": child})
    if isinstance(n, Filter):
        return n.model_copy(update={"values": _sorted_values(n.values)})
    if not isinstance(n, And | Or):
        return n
    children: list[Node] = []
    for c in (canonicalize(c) for c in n.children):
        children.extend(c.children if isinstance(c, And | Or) and type(c) is type(n) else (c,))
    if isinstance(n, Or):
        children = _merge_filters(children)
    else:
        text = [c for c in children if _filter_key(c) is None]
        filters = sorted(
            (c for c in children if _filter_key(c) is not None), key=lambda c: _filter_key(c) or ()
        )
        children = text + filters
    children = _dedupe(children)
    if len(children) == 1:
        return children[0]
    return n.model_copy(update={"children": tuple(children)})


def _prefix(field: TextField | str | None) -> str:
    return f"{field}:" if field else ""


def _phrase_body(items: tuple[Term | Wildcard, ...]) -> str:
    return " ".join(item.token if isinstance(item, Term) else item.stem + item.op for item in items)


def _render_value(v: str | YearRange) -> str:
    if isinstance(v, YearRange):
        return str(v.lo) if v.lo == v.hi else f"{v.lo}..{v.hi}"
    return v


def _mistakable(token: str, fields: set[str]) -> bool:
    """Whether a bare `token` next to filters on `fields` would re-parse with WARN_FILTER_SCOPE."""
    if (
        "year" in fields
        and token.isascii()
        and token.isdigit()
        and len(token) <= 4
        and int(token) >= MIN_YEAR
    ):
        return True
    return any(token in _VALUE_WORDS.get(f, ()) for f in fields)


def render(n: Node, quote: frozenset[str] = frozenset()) -> str:
    """The canonical string of an already canonicalized node. `quote`: filter fields among the node's OR
    siblings, whose values a bare term must be quoted to not be mistaken for."""
    if isinstance(n, Term):
        plain = n.token not in _OPERATOR_WORDS and not (n.field is None and _mistakable(n.token, set(quote)))
        return f"{_prefix(n.field)}{n.token if plain else f'"{n.token}"'}"
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
    if isinstance(n, And):
        return "(" + " AND ".join(render(c) for c in n.children) + ")"
    siblings = frozenset(str(c.field) for c in n.children if isinstance(c, Filter))
    return "(" + " OR ".join(render(c, siblings) for c in n.children) + ")"


def canonical_hash(canonical: str) -> str:
    """sha256 over the canonical string and both versions it depends on (decision-003)."""
    return hashlib.sha256(f"{canonical}\x00{TOKENIZER_VERSION}\x00{QUERY_VERSION}".encode()).hexdigest()
