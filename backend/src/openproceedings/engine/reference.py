"""ReferenceEngine: the definition of what a query matches (spec 03; reference-oracle skill).

Pure Python over each record's normalised token lists: no index, no postings, no caches beyond those token
lists and one query's expansions, O(corpus) per query on purpose. It shares no code with the Tantivy compiler (it imports only the AST,
the token contract and the engine's type-only protocol) and is never mounted behind the API. Each node's
evaluation is a few lines that can be checked against spec 02 by eye:

| Node | A record matches when |
|---|---|
| Term t | t is a token of the field (title or abstract; either, if unfielded) |
| Wildcard | some token of the field is one of its expansions over the snapshot vocabulary (every wildcard in the query is expanded first, so the 200 cap never depends on which records are reached) |
| Phrase | its items match consecutive tokens of one field (a wildcard item at its position) |
| Near(a, b, n) | occurrences of a and b in one field don't overlap and have ≤ n tokens between them |
| Filter | the record's venue/track/status equals a value, or its year is in a range |
| And / Or / Not | intersection / union / complement in the snapshot |
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.protocol import (
    FACET_FIELDS,
    MAX_EXPANSIONS,
    Engine,
    EngineInputError,
    Searchable,
    SearchResult,
)
from openproceedings.query.ast import (
    And,
    Filter,
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
from openproceedings.query.normalize import normalize

TEXT_FIELDS: tuple[TextField, ...] = ("title", "abstract")


@dataclass(frozen=True, slots=True)
class _Doc:
    id: str
    tokens: dict[str, tuple[str, ...]]  # "title" / "abstract" → normalised tokens, list index = position
    venue: str
    year: int
    track: str
    status: str


def _matches_wildcard(token: str, w: Wildcard) -> bool:
    if w.op == "*":
        return token.startswith(w.stem)
    return token == w.stem or (len(token) == len(w.stem) + 1 and token.startswith(w.stem))


class ReferenceEngine:
    def __init__(self, records: Iterable[Searchable], index_version: str = "reference") -> None:
        self.index_version = index_version
        self.docs = tuple(
            _Doc(
                r.id,
                {"title": tuple(normalize(r.title)), "abstract": tuple(normalize(r.abstract or ""))},
                r.venue,
                r.year,
                r.track,
                r.status,
            )
            for r in records
        )
        self.universe = frozenset(d.id for d in self.docs)
        self.vocabulary = frozenset(t for d in self.docs for f in TEXT_FIELDS for t in d.tokens[f])

    # --- the Engine protocol -------------------------------------------------------------------------
    def expand(self, wildcard: Wildcard) -> list[str]:
        """Every vocabulary token the wildcard matches, sorted; more than MAX_EXPANSIONS is an error."""
        terms = sorted(t for t in self.vocabulary if _matches_wildcard(t, wildcard))
        if len(terms) > MAX_EXPANSIONS:
            raise EngineInputError(
                DiagnosticCode.WILDCARD_TOO_MANY_EXPANSIONS,
                f"`{wildcard.stem}{wildcard.op}` expands to {len(terms)} terms (more than {MAX_EXPANSIONS}) — use a "
                "longer stem.",
            )
        return terms

    def match_ids(self, ast: Node) -> frozenset[str]:
        expansions = self.expansions(ast)  # every wildcard, before any record: the cap never depends on data
        return frozenset(d.id for d in self.docs if self.matches(d, ast, expansions))

    def search(self, ast: Node, *, sort: str = "relevance", offset: int = 0, limit: int = 50) -> SearchResult:
        """The oracle does not rank: results are in id order whatever `sort` asks for."""
        if offset < 0 or limit < 0:
            raise EngineInputError(DiagnosticCode.API_BAD_PARAM, "offset and limit must be ≥ 0.")
        ids = sorted(self.match_ids(ast))
        return SearchResult(total=len(ids), ids=tuple(ids[offset : offset + limit]))

    def facets(self, ast: Node, fields: tuple[str, ...] = FACET_FIELDS) -> dict[str, dict[str, int]]:
        """Disjunctive facets (spec 04, decision-001 rule 6): field F is counted over the matches of the query
        without F's own top-level conjuncts (a filter or NOT of one; nested ones stay). Top-level is judged
        after flattening nested ANDs, as on the canonical tree."""
        unknown = [f for f in fields if f not in FACET_FIELDS]
        if unknown:
            raise EngineInputError(DiagnosticCode.API_BAD_PARAM, f"facet fields must be among {FACET_FIELDS}")
        self.expansions(ast)  # the cap applies even when no facet field is asked for (`fields=()`)
        out: dict[str, dict[str, int]] = {}
        for field in fields:
            kept = [c for c in _conjuncts(ast) if _own_field(c) != field]
            ids = self.universe if not kept else self.match_ids(_and(kept))
            counts: dict[str, int] = {}
            for d in self.docs:
                if d.id in ids:
                    value = str(getattr(d, field))
                    counts[value] = counts.get(value, 0) + 1
            out[field] = dict(sorted(counts.items()))
        return out

    # --- evaluation ----------------------------------------------------------------------------------
    def expansions(self, n: Node) -> dict[tuple[str, str], frozenset[str]]:
        """Every wildcard in the tree (phrase items and NEAR operands too), expanded once, cap enforced."""
        found: dict[tuple[str, str], frozenset[str]] = {}
        for w in _wildcards(n):
            if (w.stem, w.op) not in found:
                found[(w.stem, w.op)] = frozenset(self.expand(w))
        return found

    def matches(self, d: _Doc, n: Node, exp: dict[tuple[str, str], frozenset[str]]) -> bool:
        if isinstance(n, And):
            return all(self.matches(d, c, exp) for c in n.children)
        if isinstance(n, Or):
            return any(self.matches(d, c, exp) for c in n.children)
        if isinstance(n, Not):
            return not self.matches(d, n.child, exp)
        if isinstance(n, Filter):
            return _filter_matches(d, n)
        if isinstance(n, Near):
            return any(_near_in(d.tokens[f], n, exp) for f in _fields(n.field))
        return any(_occurrences(d.tokens[f], n, exp) for f in _fields(n.field))


def _occurrences(
    tokens: tuple[str, ...], leaf: Leaf, exp: dict[tuple[str, str], frozenset[str]]
) -> list[tuple[int, int]]:
    """Half-open token spans in one field where `leaf` occurs."""
    items: tuple[Term | Wildcard, ...] = leaf.items if isinstance(leaf, Phrase) else (leaf,)
    allowed = [{i.token} if isinstance(i, Term) else exp[(i.stem, i.op)] for i in items]
    k = len(items)
    return [
        (start, start + k)
        for start in range(len(tokens) - k + 1)
        if all(tokens[start + j] in allowed[j] for j in range(k))
    ]


def _near_in(tokens: tuple[str, ...], n: Near, exp: dict[tuple[str, str], frozenset[str]]) -> bool:
    for sa in _occurrences(tokens, n.left, exp):
        for sb in _occurrences(tokens, n.right, exp):
            first, second = (sa, sb) if sa[0] <= sb[0] else (sb, sa)
            if first[1] <= second[0] and second[0] - first[1] <= n.distance:
                return True
    return False


def _wildcards(n: Node) -> Iterator[Wildcard]:
    if isinstance(n, Wildcard):
        yield n
    elif isinstance(n, Phrase):
        yield from (i for i in n.items if isinstance(i, Wildcard))
    elif isinstance(n, Near):
        yield from _wildcards(n.left)
        yield from _wildcards(n.right)
    elif isinstance(n, Not):
        yield from _wildcards(n.child)
    elif isinstance(n, And | Or):
        for c in n.children:
            yield from _wildcards(c)


def _conjuncts(n: Node) -> list[Node]:
    """Top-level AND conjuncts, with nested ANDs flattened."""
    return [x for c in n.children for x in _conjuncts(c)] if isinstance(n, And) else [n]


def _fields(field: TextField | None) -> tuple[TextField, ...]:
    return (field,) if field else TEXT_FIELDS


def _filter_matches(d: _Doc, f: Filter) -> bool:
    """Exact equality with the record's value; years inclusive."""
    if f.field == "year":
        return any(isinstance(v, YearRange) and v.lo <= d.year <= v.hi for v in f.values)
    return getattr(d, f.field) in f.values  # values are canonical vocabulary (the AST validates them)


def _own_field(n: Node) -> str | None:
    inner = n.child if isinstance(n, Not) else n
    return inner.field if isinstance(inner, Filter) else None


def _and(nodes: list[Node]) -> Node:
    if len(nodes) == 1:
        return nodes[0]
    return And(span=(0, 0), children=tuple(nodes))


def _conforms(engine: ReferenceEngine) -> Engine:
    return engine  # mypy fails `make lint` if ReferenceEngine drifts from the Engine protocol
