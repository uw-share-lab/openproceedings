"""ReferenceEngine: the definition of what a query matches (spec 03; reference-oracle skill).

Pure Python over each record's normalised token lists: no index, no postings, no caches beyond those token
lists, O(corpus) per query on purpose. It shares no code with the Tantivy compiler (it imports only the AST,
the token contract and the engine's type-only protocol) and is never mounted behind the API. Each node's
evaluation is a few lines that can be checked against spec 02 by eye:

| Node | A record matches when |
|---|---|
| Term t | t is a token of the field (title or abstract; either, if unfielded) |
| Wildcard | some token of the field is one of its expansions over the snapshot vocabulary |
| Phrase | its items match consecutive tokens of one field (a wildcard item at its position) |
| Near(a, b, n) | occurrences of a and b in one field don't overlap and have ≤ n tokens between them |
| Filter | the record's venue/track/status equals a value, or its year is in a range |
| And / Or / Not | intersection / union / complement in the snapshot |
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from openproceedings.diagnostics import DiagnosticCode, OpenProceedingsError
from openproceedings.engine.protocol import FACET_FIELDS, MAX_EXPANSIONS, Searchable, SearchResult
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
            raise OpenProceedingsError(
                DiagnosticCode.WILDCARD_TOO_MANY_EXPANSIONS,
                f"`{wildcard.stem}{wildcard.op}` expands to {len(terms)} terms (more than {MAX_EXPANSIONS}) — use a "
                "longer stem.",
            )
        return terms

    def match_ids(self, ast: Node) -> frozenset[str]:
        return frozenset(d.id for d in self.docs if self.matches(d, ast))

    def search(self, ast: Node, *, sort: str = "relevance", offset: int = 0, limit: int = 50) -> SearchResult:
        """The oracle does not rank: results are in id order whatever `sort` asks for."""
        ids = sorted(self.match_ids(ast))
        return SearchResult(total=len(ids), ids=tuple(ids[offset : offset + limit]))

    def facets(self, ast: Node, fields: tuple[str, ...] = FACET_FIELDS) -> dict[str, dict[str, int]]:
        """Disjunctive facets (spec 04, decision-001 rule 6): field F is counted over the matches of the query
        without F's own top-level conjuncts (a nested F filter stays)."""
        out: dict[str, dict[str, int]] = {}
        for field in fields:
            conjuncts = list(ast.children) if isinstance(ast, And) else [ast]
            kept = [c for c in conjuncts if _own_field(c) != field]
            ids = self.universe if not kept else self.match_ids(_and(kept))
            counts: dict[str, int] = {}
            for d in self.docs:
                if d.id in ids:
                    value = str(getattr(d, field))
                    counts[value] = counts.get(value, 0) + 1
            out[field] = dict(sorted(counts.items()))
        return out

    # --- evaluation ----------------------------------------------------------------------------------
    def matches(self, d: _Doc, n: Node) -> bool:
        if isinstance(n, And):
            return all(self.matches(d, c) for c in n.children)
        if isinstance(n, Or):
            return any(self.matches(d, c) for c in n.children)
        if isinstance(n, Not):
            return not self.matches(d, n.child)
        if isinstance(n, Filter):
            return _filter_matches(d, n)
        if isinstance(n, Near):
            return any(self._near_in(d.tokens[f], n) for f in _fields(n.field))
        return any(any(True for _ in self.occurrences(d.tokens[f], n)) for f in _fields(n.field))

    def occurrences(self, tokens: tuple[str, ...], leaf: Leaf) -> Iterator[tuple[int, int]]:
        """Half-open token spans in one field where `leaf` occurs."""
        items: tuple[Term | Wildcard, ...] = leaf.items if isinstance(leaf, Phrase) else (leaf,)
        allowed = [
            {i.token}
            if isinstance(i, Term)
            else set(self.expand(i))  # a wildcard: its expansions, cap enforced
            for i in items
        ]
        k = len(items)
        for start in range(len(tokens) - k + 1):
            if all(tokens[start + j] in allowed[j] for j in range(k)):
                yield (start, start + k)

    def _near_in(self, tokens: tuple[str, ...], n: Near) -> bool:
        a = list(self.occurrences(tokens, n.left))
        b = list(self.occurrences(tokens, n.right))
        for sa in a:
            for sb in b:
                first, second = (sa, sb) if sa[0] <= sb[0] else (sb, sa)
                if first[1] <= second[0] and second[0] - first[1] <= n.distance:
                    return True
        return False


def _fields(field: TextField | None) -> tuple[TextField, ...]:
    return (field,) if field else TEXT_FIELDS


def _filter_matches(d: _Doc, f: Filter) -> bool:
    if f.field == "year":
        return any(isinstance(v, YearRange) and v.lo <= d.year <= v.hi for v in f.values)
    record_value = getattr(d, f.field)
    return any(isinstance(v, str) and v.casefold() == record_value.casefold() for v in f.values)


def _own_field(n: Node) -> str | None:
    inner = n.child if isinstance(n, Not) else n
    return inner.field if isinstance(inner, Filter) else None


def _and(nodes: list[Node]) -> Node:
    if len(nodes) == 1:
        return nodes[0]
    return And(span=(0, 0), children=tuple(nodes))
