"""AST → Tantivy compilation (spec 03 §AST → Tantivy compilation; ast-compilation skill).

We never use Tantivy's query parser. Each AST node becomes Tantivy query objects; the definition of correct
is `ReferenceEngine`, with which this module shares no matching code (only the AST and the index's field
names), so the differential suite (task-028) compares two independent implementations.

| AST | Tantivy |
|---|---|
| Term t (field f, or both) | `TermQuery(f, t)`, per field, SHOULD |
| Wildcard | `SHOULD` of a `TermQuery` per expansion, per field (each scores as its own term); no expansions → `EmptyQuery` (never a dropped clause) |
| Phrase of terms | `PhraseQuery(f, tokens, slop=0)`, per field: never across fields |
| Near(a, b, n), a ≠ b single terms | `PhraseQuery([a,b], slop=n) OR PhraseQuery([b,a], slop=n)`, per field |
| Phrase with a wildcard item; Near of a phrase, a wildcard or a term with itself | verified: the candidates (every item present in the field) are fetched and their stored token streams checked by position in Python; the verified ids become a `TermSetQuery` on `id` (with the candidate query kept for scoring) |
| Filter | `ConstScoreQuery(0)` of a `TermSetQuery` on the facet, or of year `RangeQuery`s: never scores |
| And / Or / Not | `BooleanQuery` MUST / SHOULD; Not → `MUST const-score-0 all_docs, MUST_NOT x` (a MUST_NOT-only query matches nothing; the all-docs clause adds no score) |

Slop was measured on tantivy 0.26.2: an in-order pair at slop n matches ≤ n tokens between them; a
reversed pair costs 2 more, so the reversed pairs slop admits are within NEAR/n anyway and the union
above is exact. A term paired with itself at slop ≥ 1 also matches ONE occurrence, so `a NEAR a` is
always verified (two distinct occurrences, as spec 02 says).
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from typing import Protocol

import tantivy

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
from openproceedings.vocab import TEXT_FIELDS

FIELDS = TEXT_FIELDS  # the searched fields (vocab)
# (stem, op) → the sorted expanded terms: the concrete form protocol.Expansions narrows to, as the compiler reads it
Expansions = dict[tuple[str, str], tuple[str, ...]]


class VerifiedCache(Protocol):
    """Where a compile looks up a clause's verified ids: one `.get` (task-080), None on a miss. A dict, or the
    engine's request-scoped overlay (`tantivy_engine.Overlay`)."""

    def get(self, key: tuple[str, str], /) -> list[str] | None: ...


# A field's stored token stream for each candidate document: (doc address, field) → tokens
TokenReader = Callable[[tantivy.Query, TextField], Iterator[tuple[str, list[str]]]]


@dataclass
class Compiled:
    query: tantivy.Query
    explain: list[str] = field(default_factory=list)  # the readable tree, one line per clause
    verified: list[str] = field(default_factory=list)  # which clauses took the position-verified fallback
    # what the engine's compiled memo charges against its budget (TantivyEngine.MAX_COMPILED_UNITS): what
    # this compiled query keeps alive (ids in its verified term sets, terms in its expansions, one per
    # explain line). The verified memo is charged clause by clause, as each is stored (`Compiler.store`)
    held: int = 0


def wildcards(n: Node) -> Iterator[Wildcard]:
    """Every wildcard in a tree, phrase items and NEAR operands included."""
    if isinstance(n, Wildcard):
        yield n
    elif isinstance(n, Phrase):
        yield from (i for i in n.items if isinstance(i, Wildcard))
    elif isinstance(n, Near):
        yield from wildcards(n.left)
        yield from wildcards(n.right)
    elif isinstance(n, Not):
        yield from wildcards(n.child)
    elif isinstance(n, And | Or):
        for c in n.children:
            yield from wildcards(c)


class Compiler:
    """Compiles one query against one index. `expansions` holds every wildcard's terms (computed before
    compiling, so the 200 cap never depends on which documents are reached); `read` streams candidate
    documents' stored token streams for position verification."""

    def __init__(
        self,
        schema: tantivy.Schema,
        expansions: Expansions,
        read: TokenReader,
        verified_cache: VerifiedCache | None = None,
        weights: dict[str, float] | None = None,
        gate: Callable[[], AbstractContextManager[object]] = nullcontext,
        store: Callable[[tuple[str, str], list[str]], None] | None = None,
    ) -> None:
        self.schema = schema
        self.weights = weights if weights is not None else dict.fromkeys(FIELDS, 1.0)
        self.expansions = expansions
        self.read = read
        # (field, clause) → the ids it verified: an index never changes, so a clause is checked once per
        # engine, however many times facets or later queries recompile it
        plain: dict[tuple[str, str], list[str]] = {}
        self.verified_cache: VerifiedCache = plain if verified_cache is None else verified_cache
        # how a newly verified clause is stored: the engine's keeps the cache's budget as each clause is
        # stored (trim, store, charge), so no single compile, however many clauses it verifies, overshoots
        # the budget by more than one clause's ids; with no cache given, a plain store into a fresh one
        if store is None and verified_cache is not None:
            raise TypeError("a Compiler given a verified cache needs its `store`")
        self.store = store if store is not None else plain.__setitem__
        # entered around each cold verification (a cache miss), the one slow path: the API bounds how many
        # run at once and refuses one more (503 API_BUSY) rather than queueing it
        self.gate = gate
        self.out = Compiled(tantivy.Query.empty_query())

    def compile(self, n: Node) -> Compiled:
        self.out.query = self.node(n, 0)
        self.out.held += len(self.out.explain)
        return self.out

    def line(self, depth: int, text: str) -> None:
        self.out.explain.append("  " * depth + text)

    # --- boolean structure and filters ---------------------------------------------------------------
    def node(self, n: Node, depth: int) -> tantivy.Query:
        if isinstance(n, And | Or):
            self.line(depth, "AND" if isinstance(n, And) else "OR")
            occur = tantivy.Occur.Must if isinstance(n, And) else tantivy.Occur.Should
            return combine(occur, [self.node(c, depth + 1) for c in n.children])
        if isinstance(n, Not):
            self.line(depth, "NOT (all documents, minus:)")
            return tantivy.Query.boolean_query(
                [
                    (tantivy.Occur.Must, tantivy.Query.const_score_query(tantivy.Query.all_query(), 0.0)),
                    (tantivy.Occur.MustNot, self.node(n.child, depth + 1)),
                ]
            )
        if isinstance(n, Filter):
            return self.filter(n, depth)
        fields = (n.field,) if n.field else FIELDS
        if len(fields) == 1:
            return self.weighted(n, fields[0], depth)
        self.line(depth, "OR (per field)")
        return combine(tantivy.Occur.Should, [self.weighted(n, f, depth + 1) for f in fields])

    def filter(self, f: Filter, depth: int) -> tantivy.Query:
        if f.field == "year":
            ranges = [v for v in f.values if isinstance(v, YearRange)]
            self.line(depth, f"filter year in {', '.join(f'{r.lo}..{r.hi}' for r in ranges)} (non-scoring)")
            inner = combine(
                tantivy.Occur.Should,
                [
                    tantivy.Query.range_query(self.schema, "year", tantivy.FieldType.Unsigned, r.lo, r.hi)
                    for r in ranges
                ],
            )
        else:
            values = sorted(str(v) for v in f.values)
            self.line(depth, f"filter {f.field} in {{{', '.join(values)}}} (non-scoring)")
            inner = tantivy.Query.term_set_query(self.schema, f.field, values)
        return tantivy.Query.const_score_query(inner, 0.0)

    # --- text leaves, one field at a time ------------------------------------------------------------
    def weighted(self, n: Node, f: TextField, depth: int) -> tantivy.Query:
        """A text leaf in one field, boosted by the field's weight (field-weighted BM25: title 2.0,
        abstract 1.0), so score = Σ weight_f · BM25_f over the positive clauses."""
        weight = self.weights[f]
        query = self.leaf(n, f, depth)
        return query if weight == 1.0 else tantivy.Query.boost_query(query, weight)

    def leaf(self, n: Node, f: TextField, depth: int) -> tantivy.Query:
        if isinstance(n, Term):
            self.line(depth, f"{f}: term {n.token}")
            return tantivy.Query.term_query(self.schema, f, n.token)
        if isinstance(n, Wildcard):
            terms = self.expansions[(n.stem, n.op)]
            self.line(depth, f"{f}: wildcard {n.stem}{n.op} → {len(terms)} terms")
            return self.term_set(f, terms)
        if isinstance(n, Phrase) and all(isinstance(i, Term) for i in n.items):
            words = [i.token for i in n.items if isinstance(i, Term)]
            self.line(depth, f'{f}: phrase "{" ".join(words)}" slop 0')
            return tantivy.Query.phrase_query(self.schema, f, list[str | tuple[int, str]](words), 0)
        if isinstance(n, Near) and _distinct_terms(n):
            a, b = n.left.token, n.right.token  # type: ignore[union-attr]
            self.line(depth, f"{f}: NEAR/{n.distance} {a} {b} as phrase slop {n.distance}, both orders")
            return tantivy.Query.boolean_query(
                [(tantivy.Occur.Should, tantivy.Query.phrase_query(self.schema, f, [a, b], n.distance)),
                 (tantivy.Occur.Should, tantivy.Query.phrase_query(self.schema, f, [b, a], n.distance))]
            )  # fmt: skip
        if isinstance(n, Phrase | Near):
            return self.verified(n, f, depth)
        raise TypeError(f"not a text leaf: {type(n).__name__}")  # pragma: no cover — the AST has no others

    def term_set(self, f: TextField, terms: tuple[str, ...]) -> tantivy.Query:
        if not terms:
            return tantivy.Query.empty_query()  # matches nothing: never a dropped (widening) clause
        self.out.held += len(terms)
        # SHOULD of term queries (not a TermSetQuery, which scores every match 1): each expansion scores as
        # its own term (field-weighted-bm25 skill)
        return combine(tantivy.Occur.Should, [tantivy.Query.term_query(self.schema, f, t) for t in terms])

    def item(self, i: Term | Wildcard, f: TextField) -> tantivy.Query:
        if isinstance(i, Term):
            return tantivy.Query.term_query(self.schema, f, i.token)
        return self.term_set(f, self.expansions[(i.stem, i.op)])

    def items(self, n: Node) -> list[Term | Wildcard]:
        if isinstance(n, Term | Wildcard):
            return [n]
        if isinstance(n, Phrase):
            return list(n.items)
        assert isinstance(n, Near)
        return self.items(n.left) + self.items(n.right)

    def verified(self, n: Phrase | Near, f: TextField, depth: int) -> tantivy.Query:
        """Candidates (every distinct item present in the field), then their stored token streams checked by
        position; the verified ids are what matches. The candidate query stays in, for scoring (each
        distinct item once)."""
        candidates = self.candidates(n, f)
        key = (f, n.model_dump_json())
        # one read, then the local list: the cache is an engine's, shared across threads, and may be cleared
        # between any two operations on it (task-080); a miss recomputes the same ids from the immutable index
        ids = self.verified_cache.get(key)
        if ids is None:
            with self.gate():
                ids = [doc_id for doc_id, tokens in self.read(candidates, f) if self.holds(n, tokens)]
            self.store(key, ids)  # stored complete, never changed after
        self.out.held += len(ids)
        what = f"NEAR/{n.distance}" if isinstance(n, Near) else "phrase"
        self.line(depth, f"{f}: {what} verified by position ({len(ids)} documents)")
        self.out.verified.append(f"{f}: {what}")
        if not ids:
            return tantivy.Query.empty_query()
        exact = tantivy.Query.const_score_query(tantivy.Query.term_set_query(self.schema, "id", ids), 0.0)
        return tantivy.Query.boolean_query([(tantivy.Occur.Must, candidates), (tantivy.Occur.Must, exact)])

    def candidates(self, n: Phrase | Near, f: TextField) -> tantivy.Query:
        """What a verified clause's candidates must hold in `f`: every distinct item (the non-positional
        superset its position check reads, and what `TantivyEngine.candidates` counts)."""
        return combine(tantivy.Occur.Must, [self.item(i, f) for i in self.distinct(n)])

    def distinct(self, n: Node) -> list[Term | Wildcard]:
        """The items a candidate must hold, each once: an item whose allowed tokens include another's is
        implied by it (`trust` implies `trust*`), so only the narrower one is kept, and a term is scored once."""
        items = {self.allowed(i): i for i in self.items(n)}  # equal token sets are one item
        return [i for s, i in items.items() if not any(other < s for other in items)]

    # --- position checks (spec 02 semantics, written independently of ReferenceEngine) --------------
    def allowed(self, i: Term | Wildcard) -> frozenset[str]:
        return frozenset((i.token,)) if isinstance(i, Term) else frozenset(self.expansions[(i.stem, i.op)])

    def starts(self, n: Node, tokens: list[str], positions: dict[str, list[int]]) -> list[int]:
        """Sorted start positions where a term, wildcard or phrase occurs (its width is its item count).
        Found from where its first item occurs, never by scanning every window."""
        parts = [self.allowed(i) for i in self.items(n)]
        first = sorted(p for t in parts[0] & positions.keys() for p in positions[t])
        width = len(parts)
        return [
            at
            for at in first
            if at + width <= len(tokens) and all(tokens[at + k] in parts[k] for k in range(1, width))
        ]

    def holds(self, n: Phrase | Near, tokens: list[str]) -> bool:
        positions: dict[str, list[int]] = {}
        for at, token in enumerate(tokens):
            positions.setdefault(token, []).append(at)
        if isinstance(n, Phrase):
            return bool(self.starts(n, tokens, positions))
        left, right = self.starts(n.left, tokens, positions), self.starts(n.right, tokens, positions)
        wl, wr = len(self.items(n.left)), len(self.items(n.right))
        for a in left:
            # right after: b in [a + wl, a + wl + n]; right before: b + wr in [a - n, a], i.e. b in [a - n - wr, a - wr]
            for lo, hi in ((a + wl, a + wl + n.distance), (a - n.distance - wr, a - wr)):
                k = bisect_left(right, lo)
                if k < len(right) and right[k] <= hi:
                    return True
        return False


def combine(occur: tantivy.Occur, queries: list[tantivy.Query]) -> tantivy.Query:
    """`queries` joined by `occur` as a balanced binary tree. Tantivy adds a union's clause scores in an
    order that shifts from one document to the next, so a flat union of three or more gives identical texts
    scores 1 ulp apart and their order would follow the segment layout, not the id. A sum of two is the same
    in either order, so with at most two clauses per node every score depends only on the text."""
    if not queries:
        raise ValueError("combine needs at least one query")
    if len(queries) == 1:
        return queries[0]
    if len(queries) == 2:
        return tantivy.Query.boolean_query([(occur, queries[0]), (occur, queries[1])])
    half = len(queries) // 2
    return tantivy.Query.boolean_query(
        [(occur, combine(occur, queries[:half])), (occur, combine(occur, queries[half:]))]
    )


def verifies(n: Node) -> bool:
    """Whether compiling `n` takes the position-verified path for some clause (`Compiler.leaf`: a phrase
    with a wildcard item, a NEAR that isn't two distinct terms). From the AST alone, before compiling, so the
    API can charge for it first (spec 04 §Rate limit); a test holds it equal to `Compiled.verified`."""
    if isinstance(n, And | Or):
        return any(verifies(c) for c in n.children)
    if isinstance(n, Not):
        return verifies(n.child)
    if isinstance(n, Phrase):
        return not all(isinstance(i, Term) for i in n.items)
    if isinstance(n, Near):
        return not _distinct_terms(n)
    return False


def verified_clauses(node: Node | None) -> list[Phrase | Near]:
    """Every clause of `node` that compiles to the position-verified path, in query order: `verifies`'s rule,
    counted rather than tested (what the API caps and charges, and costs by its candidates:
    `TantivyEngine.candidates`). A test holds `bool(verified_clauses(n)) == verifies(n)` and the count equal
    to the compiler's own."""
    if isinstance(node, Phrase):
        return [] if all(isinstance(i, Term) for i in node.items) else [node]
    if isinstance(node, Near):
        return [] if _distinct_terms(node) else [node]
    if isinstance(node, Not):
        return verified_clauses(node.child)
    if isinstance(node, And | Or):
        return [clause for c in node.children for clause in verified_clauses(c)]
    return []


def _distinct_terms(n: Near) -> bool:
    return isinstance(n.left, Term) and isinstance(n.right, Term) and n.left.token != n.right.token
