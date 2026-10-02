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
| Phrase with a wildcard item; Near of a phrase, a wildcard or a term with itself | verified: the candidates (every item present in the field) are fetched and their stored token streams checked by position in Python; the verified ids become a `TermSetQuery` on `id` (with the candidate query kept for scoring), or the candidates that failed, excluded, when they are fewer (`Compiler.exact`) |
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
# candidates between two deadline checks in a verification: ~40-56 ms of work at 40-56 µs a candidate, so
# a deadline is overshot by well under a tenth of a second, and a check costs nothing measurable
CHECK_EVERY = 1_000
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
    # (field, clause) -> the ids each verified clause matched: a compiled-memo hit hands them to the request's
    # scope (`TantivyEngine.compile`), so its later compiles of other trees never verify them again
    ids: dict[tuple[str, str], list[str]] = field(default_factory=dict)


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
        count: Callable[[tantivy.Query], int] | None = None,
        members: Callable[[tantivy.Query], frozenset[str]] | None = None,
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
        self.count = (
            count  # how many documents a query matches (the engine's): a clause with none takes no slot
        )
        # the ids a query matches (the engine's): with `count`, lets a verified clause name the candidates that
        # don't hold it instead of the ids that do, when they are fewer (`exact`)
        self.members = members
        self.out = Compiled(tantivy.Query.empty_query())
        self._allowed: dict[tuple[str, str], frozenset[str]] = {}  # per item: `allowed`

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
            ids = self.verify(n, f, candidates)
            self.store(key, ids)  # stored complete, never changed after
        # the Python list `Compiled.ids` keeps (round 5); the Tantivy query's own id set is charged by `exact`
        self.out.held += len(ids)
        self.out.ids[key] = ids
        what = f"NEAR/{n.distance}" if isinstance(n, Near) else "phrase"
        self.line(depth, f"{f}: {what} verified by position ({len(ids)} documents)")
        self.out.verified.append(f"{f}: {what}")
        if not ids:
            return tantivy.Query.empty_query()
        return self.exact(candidates, ids)

    def exact(self, candidates: tantivy.Query, ids: list[str]) -> tantivy.Query:
        """`candidates` narrowed to the verified `ids`, naming whichever list is shorter (TASK-076): Tantivy
        resolves an id term set on every search, so a clause most of whose candidates hold it would pay for
        every id it matched. The ids are a subset of the candidates, so the candidates less those that failed
        the check are exactly the ids; the exclusion adds no score and the term set adds 0.0, so either form
        scores each match as its candidate query alone."""
        if self.count is not None and self.members is not None and self.count(candidates) - len(ids) < len(ids):
            failed = sorted(self.members(candidates).difference(ids))
            self.out.held += len(failed)
            if not failed:
                return candidates
            return tantivy.Query.boolean_query(
                [(tantivy.Occur.Must, candidates), (tantivy.Occur.MustNot, id_set(self.schema, failed))]
            )
        self.out.held += len(ids)
        exact = tantivy.Query.const_score_query(id_set(self.schema, ids), 0.0)
        return tantivy.Query.boolean_query([(tantivy.Occur.Must, candidates), (tantivy.Occur.Must, exact)])

    def verify(self, n: Phrase | Near, f: TextField, candidates: tantivy.Query) -> list[str]:
        """The ids of `candidates` whose `f` tokens hold `n`, checked under the gate (one verification slot). A
        clause with no candidate (`count`, from the inverted index) takes no slot and reads nothing. The gate
        may yield a deadline check (the API's `max_verification_seconds`), called before the clause and every
        `CHECK_EVERY` candidates: when it raises, the partial list is dropped with this frame, never returned or
        stored, so no memo, scope or compiled query ever holds part of a clause."""
        if self.count is not None and self.count(candidates) == 0:
            return []
        holds = self.holder(n)  # the clause's sets, built once, not per candidate
        ids: list[str] = []
        with self.gate() as check:
            deadline = check if callable(check) else None
            if deadline is not None:
                deadline()  # a request whose earlier clauses used its time up stops before this one
            for count, (doc_id, tokens) in enumerate(self.read(candidates, f), 1):
                if holds(tokens):
                    ids.append(doc_id)
                if deadline is not None and count % CHECK_EVERY == 0:
                    deadline()
        return ids

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
        """The tokens item `i` allows, built once per compile (a wildcard's up to 200 expansions): a phrase
        of many wildcard items would otherwise rebuild them per item, per candidate (M3a round 4)."""
        key = (i.token, "") if isinstance(i, Term) else (i.stem, i.op)
        hit = self._allowed.get(key)
        if hit is None:
            hit = frozenset((i.token,)) if isinstance(i, Term) else frozenset(self.expansions[(i.stem, i.op)])
            self._allowed[key] = hit
        return hit

    def parts(self, n: Node) -> Parts:
        """Each item's allowed tokens, in order: what an operand (a term, wildcard or phrase) must match at
        consecutive positions."""
        return tuple(self.allowed(i) for i in self.items(n))

    def holder(self, n: Phrase | Near) -> Callable[[list[str]], bool]:
        """`holds` for clause `n` with everything that doesn't depend on the document computed once: each
        operand's `parts`, their widths and the distance. The per-document work is then the token->positions
        map and the checks from each first-item occurrence, so a clause's cost per candidate no longer grows
        with its expansions (round 4: a 300-item `rel*` phrase took 84 s at 80k, rebuilding 186-term sets per
        item per candidate)."""
        if isinstance(n, Phrase):
            parts = self.parts(n)
            return lambda tokens: bool(_starts(parts, tokens, _positions(tokens)))
        left, right = self.parts(n.left), self.parts(n.right)
        wl, wr, distance = len(left), len(right), n.distance

        def near(tokens: list[str]) -> bool:
            positions = _positions(tokens)
            lefts, rights = _starts(left, tokens, positions), _starts(right, tokens, positions)
            for a in lefts:
                # right after: b in [a + wl, a + wl + n]; right before: b + wr in [a - n, a], i.e. b in [a - n - wr, a - wr]
                for lo, hi in ((a + wl, a + wl + distance), (a - distance - wr, a - wr)):
                    k = bisect_left(rights, lo)
                    if k < len(rights) and rights[k] <= hi:
                        return True
            return False

        return near

    def holds(self, n: Phrase | Near, tokens: list[str]) -> bool:
        """Whether `tokens` hold clause `n` (one document; `holder` is the form a verification loops with)."""
        return self.holder(n)(tokens)


type Parts = tuple[frozenset[str], ...]


def _positions(tokens: list[str]) -> dict[str, list[int]]:
    positions: dict[str, list[int]] = {}
    for at, token in enumerate(tokens):
        positions.setdefault(token, []).append(at)
    return positions


def _starts(parts: Parts, tokens: list[str], positions: dict[str, list[int]]) -> list[int]:
    """Sorted start positions where an operand of `parts` occurs (its width is its item count). Found from
    where its first item occurs, never by scanning every window."""
    first = sorted(p for t in parts[0] & positions.keys() for p in positions[t])
    width = len(parts)
    return [
        at
        for at in first
        if at + width <= len(tokens) and all(tokens[at + k] in parts[k] for k in range(1, width))
    ]


def id_set(schema: tantivy.Schema, ids: list[str]) -> tantivy.Query:
    """The documents with these ids (a term set on `id`)."""
    return tantivy.Query.term_set_query(schema, "id", ids)


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
