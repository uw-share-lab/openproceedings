"""TantivyEngine: the Engine protocol over a built index (spec 03; ast-compilation skill).

Matching is `compile.py`'s; this module wires it to an index: wildcard expansion from the term dictionary
(both text fields, the 200 cap enforced before compiling), match sets read back through the `ord` fast
column and `ids.txt`, disjunctive facets (decision-001 rule 6) counted from one nested terms aggregation of the query without its top-level filters (task-086), and
the `--explain` rendering. `search` orders the whole match set (field-weighted BM25, or year, or title) with the id as
the last key, then pages it (task-025). The index is verified (every file re-hashed) when the engine opens it.
"""

from __future__ import annotations

import dataclasses
import heapq
import json
from collections.abc import Iterator
from importlib.metadata import version
from pathlib import Path
from typing import Any

import tantivy

from openproceedings.diagnostics import DiagnosticCode, clip
from openproceedings.engine.compile import FIELDS, Compiled, Compiler, Expansions, wildcards
from openproceedings.engine.index import IDS, SCHEMA_VERSION, open_index, record_of, verify_index
from openproceedings.engine.protocol import (
    FACET_FIELDS,
    MAX_EXPANSIONS,
    Engine,
    EngineInputError,
    EngineInternalError,
    SearchResult,
)
from openproceedings.query.ast import And, Filter, Node, Not, TextField, Wildcard, YearRange
from openproceedings.query.normalize import TOKENIZER_VERSION

SORTS = ("relevance", "year_desc", "year_asc", "title")
# a document's facet values, in this order: what every filter and facet depends on (task-086)
COMBO: tuple[str, ...] = ("venue", "year", "track", "status")
type Combo = tuple[str, int, str, str]
# the Tantivy TANTIVY_BM25 was confirmed on; test_rank.py fails if the installed one drifts
TANTIVY_PINNED = "0.26.2"
TANTIVY_BM25 = {"b": 0.75, "k1": 1.2}  # Tantivy's fixed constants: an index can't claim others


def unservable(manifest: dict[str, Any]) -> str | None:
    """Why this code can't serve an index with `manifest` (another schema, tokenizer or Tantivy version, or
    BM25 parameters Tantivy doesn't apply), or None. Read from the manifest alone, without re-hashing, so the
    API's `/meta` can leave such versions out (task-036 review)."""
    stale = {
        "schema_version": (manifest.get("schema_version"), SCHEMA_VERSION),
        "tokenizer_version": (manifest.get("tokenizer_version"), TOKENIZER_VERSION),
        "tantivy_version": (manifest.get("tantivy_version"), version("tantivy")),  # scoring may differ
    }
    name = manifest.get("index_version")
    for field, (built, current) in stale.items():
        if built != current:  # queries are normalized and compiled for the current versions
            return f"index {name} has {field} {built}, this code {current}: build a new index"
    ranking = manifest.get("ranking_params")
    bm25 = ranking.get("bm25") if isinstance(ranking, dict) else None
    if bm25 != TANTIVY_BM25:
        return f"index {name} records bm25 {bm25}, but Tantivy applies {TANTIVY_BM25}"
    return None


class TantivyEngine:
    """One engine serves every request of the API, from FastAPI's thread pool (task-080). Its only mutable
    state is four memos (`compiled`, `verified`, `expanded`, `faceted`), each a pure function of its key and
    the immutable index, and each touched without a lock under two rules: an entry is read with one `.get()`
    (never `in` then `[key]`, since another thread may clear the memo in between), and an entry is stored
    only once it is complete, never mutated after. A clear or a lost race only costs a recomputation, which
    gives the same value, so concurrent searches never see each other's partial work (guarantee 4).
    The design relies only on each single dict operation being atomic, which holds under the GIL and on
    free-threaded builds (3.13t) alike; never iterate a memo, or check-then-act across two operations.
    Each memo's size budget is kept by an append-only ledger (`charges`), lock-free as well: see `_trim`."""

    # Each memo is bounded by what it holds, not by its entry count (a verified entry can hold every id in the
    # index, ~5 MB on 80k): it is cleared once the weights charged to it since its last clear pass its budget.
    # Weights, in ids/terms (~60 bytes each as Python strings): a verified clause, its ids + 1; an expansion,
    # its terms + 1 (an over-cap count, 1); a compiled query, `Compiled.held` + 1 (the ids and terms inside its
    # Tantivy query, plus its explain lines); a base's facet combos, their number + 1. So ≲ 30 + 30 + 6 + a few MB per
    # engine, and the API holds the served engine plus `pinned_indexes` more. A memo exceeds its budget only by
    # what the computations in flight store (one entry per thread), never more: see `_trim`.
    MAX_COMPILED_UNITS = 500_000
    MAX_VERIFIED_IDS = 500_000
    MAX_EXPANDED_TERMS = 100_000
    MAX_FACET_COMBOS = 100_000  # `faceted`: a base's (venue, year, track, status) combos, + 1 (a few hundred)

    def __init__(self, path: Path) -> None:
        manifest = verify_index(path)
        self.index_version: str = manifest["index_version"]
        self.ranking: dict[str, Any] = manifest["ranking_params"]  # the params this index's id was built with
        why = unservable(manifest)
        if why is not None:
            raise EngineInternalError(DiagnosticCode.API_INTERNAL, why)
        self.index = open_index(path)
        self.searcher = self.index.searcher()
        self.ids = (path / IDS).read_text(encoding="utf-8").splitlines()
        self.compiled: dict[str, Compiled] = {}  # per tree (bounded), see compile()
        self.verified: dict[tuple[str, str], list[str]] = {}  # position-verified clauses, per engine
        # each wildcard's terms, or just the count of an over-cap one
        self.expanded: dict[tuple[str, str], tuple[str, ...] | int] = {}
        # each memo's ledger: the weight of every entry stored since its last clear (see `_trim`)
        # each kept set's facet counts, per field (see `facets`)
        self.faceted: dict[str, tuple[tuple[Combo, int], ...]] = {}
        self.charges: dict[str, list[int]] = {"compiled": [], "verified": [], "expanded": [], "faceted": []}
        self.tallied: dict[str, tuple[list[int], int, int]] = {}  # each ledger's running sum (see `_trim`)

    @property
    def universe(self) -> frozenset[str]:
        """Every id in the index (tests and facet checks; built on demand, not held for every engine)."""
        return frozenset(self.ids)

    # --- the Engine protocol -------------------------------------------------------------------------
    def expand(self, wildcard: Wildcard) -> list[str]:
        """Every indexed term (title or abstract) the wildcard matches, sorted; more than MAX_EXPANSIONS
        is an error, never a truncation. From the term dictionary, not a scan of the documents."""
        key = (wildcard.stem, wildcard.op)
        # one read (task-080: never `in` then `[key]`); the index is immutable, so a stem's terms are too
        terms = self.expanded.get(key)
        if terms is None:
            found: set[str] = set()
            for f in FIELDS:
                for term, _count in self.searcher.terms_with_prefix(f, wildcard.stem):
                    if wildcard.op == "*" or term == wildcard.stem or len(term) == len(wildcard.stem) + 1:
                        found.add(term)
            # an over-cap stem keeps only its count: a refused query never holds its terms in memory
            terms = tuple(sorted(found)) if len(found) <= MAX_EXPANSIONS else len(found)
            self._trim("expanded", self.expanded, self.MAX_EXPANDED_TERMS)
            self.expanded[key] = terms
            self.charges["expanded"].append(1 if isinstance(terms, int) else len(terms) + 1)
        if isinstance(terms, int) or len(terms) > MAX_EXPANSIONS:  # checked on every call, cached or not
            count = terms if isinstance(terms, int) else len(terms)
            raise EngineInputError(
                DiagnosticCode.WILDCARD_TOO_MANY_EXPANSIONS,
                f"`{clip(wildcard.stem + wildcard.op)}` expands to {count} terms (more than {MAX_EXPANSIONS}) — use a "
                "longer stem.",
            )
        return list(terms)

    def match_ids(self, ast: Node) -> frozenset[str]:
        return self.ids_of(self.compile(ast).query)

    def search(self, ast: Node, *, sort: str = "relevance", offset: int = 0, limit: int = 50) -> SearchResult:
        """One page of the fully ordered match set (field-weighted-bm25 skill), so pages are stable and
        their union is `match_ids` for every sort."""
        total, page = self.page(ast, sort=sort, offset=offset, limit=limit)
        return SearchResult(total=total, ids=tuple(i for i, _score in page))

    def page(
        self, ast: Node, *, sort: str = "relevance", offset: int = 0, limit: int = 50
    ) -> tuple[int, list[tuple[str, float]]]:
        """`search`'s page with each hit's exact score, from one collection of the match set."""
        if offset < 0 or limit < 0:
            raise EngineInputError(DiagnosticCode.API_BAD_PARAM, "offset and limit must be ≥ 0.")
        keyed = self.keyed(ast, sort)
        # top offset+limit of the full order: keys end in the unique id, so ties at a page boundary are exact
        top = heapq.nsmallest(offset + limit, keyed)
        return len(keyed), [(i, score) for _key, i, score in top[offset:]]

    def ranked(self, ast: Node, sort: str = "relevance") -> list[tuple[str, float]]:
        """(Tests' whole-order view; searches use `page`.) Every match with its exact score, in `sort` order, ties always broken by id: `relevance` is
        (-score, id), `year_desc`/`year_asc` (∓year, id), `title` (casefold(NFKC(display title)), id). Ranking
        only orders: the set is the same for every sort."""
        return [(i, score) for _key, i, score in sorted(self.keyed(ast, sort))]

    def keyed(self, ast: Node, sort: str) -> list[tuple[float, str, float]]:
        """Every match as (sort key, id, score): ordering by the tuple orders by the key, then the id (unique,
        so the score after it never decides anything).
        For relevance the key is -score; year sorts ∓year; title the build-time title rank."""
        if sort not in SORTS:
            hint = " (semantic ordering needs embeddings: task-059)" if sort == "semantic" else ""
            raise EngineInputError(
                DiagnosticCode.API_BAD_PARAM, f"sort must be one of {', '.join(SORTS)}{hint}."
            )
        hits = self.searcher.search(self.compile(ast).query, max(1, self.searcher.num_docs)).hits
        if not hits:
            return []
        addresses = [address for _score, address in hits]
        ids = [self.ids[_ord(o)] for o in self.searcher.fast_field_values("ord", addresses)]
        scores = [score for score, _address in hits]
        if sort == "relevance":
            return [(-s, i, s) for s, i in zip(scores, ids, strict=True)]
        column = "title_rank" if sort == "title" else "year"
        values = [_ord(v) for v in self.searcher.fast_field_values(column, addresses)]
        sign = -1 if sort == "year_desc" else 1
        return [(float(sign * v), i, s) for v, s, i in zip(values, scores, ids, strict=True)]

    def documents(self, ast: Node) -> tuple[int, Iterator[dict[str, Any]]]:
        """How many documents match, and every match's display record (id, venue, year, track, status, and
        the stored title, abstract, authors, urls, presentation, keywords, venue_id_raw) in id order, read
        one at a time: what an export streams (spec 04 §Exports). One collection of the match set."""
        addresses = self.hits(self.compile(ast).query)
        if not addresses:
            return 0, iter(())
        ords = [_ord(o) for o in self.searcher.fast_field_values("ord", addresses)]  # ord order is id order
        ordered = [a for _o, a in sorted(zip(ords, addresses, strict=True), key=lambda pair: pair[0])]
        return len(ordered), map(self._display, ordered)

    def display(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        """The display records of `ids` (a page of hits), by id."""
        if not ids:
            return {}
        query = tantivy.Query.term_set_query(self.index.schema, "id", ids)
        return {r["id"]: r for r in map(self._display, self.hits(query))}

    def _display(self, address: tantivy.DocAddress) -> dict[str, Any]:
        doc = self.searcher.doc(address).to_dict()
        return {
            "id": doc["id"][0],
            **{f: doc[f][0] for f in ("venue", "track", "status", "year")},
            **record_of(doc["record"][0]),
        }

    def facets(self, ast: Node, fields: tuple[str, ...] = FACET_FIELDS) -> dict[str, dict[str, int]]:
        """Disjunctive facets (spec 04, decision-001 rule 6): field F is counted over the matches of the
        query without F's own top-level conjuncts (a filter on F, or NOT of one; nested ones stay).

        One collection serves every field (task-086). The query's top-level facet-field filters (`Filter`,
        or `NOT` of one) are set aside, and the rest (the *base*) is collected once, counting its matches
        per combination of (venue, year, track, status) with one nested terms aggregation over those fast
        columns. A filter depends only on its field's value, so field F's count is exact from the combos:
        those passing every set-aside filter not on F, summed by their F value. The combos are memoised per
        base (`faceted`, by its span-less, sorted conjuncts), so another page, exclusion accounting (whose
        trees differ only in top-level filters) and a later query with the same base never collect again.
        Proved equal to one collection per kept set, and to ReferenceEngine (`test_facets_equal.py`)."""
        unknown = [f for f in fields if f not in FACET_FIELDS]
        if unknown:
            raise EngineInputError(DiagnosticCode.API_BAD_PARAM, f"facet fields must be among {FACET_FIELDS}")
        self.expansions(ast)  # the cap applies even when no facet field is asked for
        conjuncts = _conjuncts(ast)
        filters = [c for c in conjuncts if _filter_field(c) in FACET_FIELDS]
        base = [c for c in conjuncts if _filter_field(c) not in FACET_FIELDS]
        combos = self.combos(base)
        # per field, whether each value that occurs passes every set-aside filter on that field
        ok = [
            {
                v: all(_passes(c, v) for c in filters if _filter_field(c) == g)
                for v in {c[i] for c, _n in combos}
            }
            for i, g in enumerate(COMBO)
        ]
        out: dict[str, dict[str, int]] = {}
        for f in fields:
            at = COMBO.index(f)
            others = [i for i in range(len(COMBO)) if i != at]  # every other field's filters apply; F's don't
            counts: dict[str, int] = {}
            for combo, n in combos:
                if all(ok[i][combo[i]] for i in others):
                    value = str(combo[at])
                    counts[value] = counts.get(value, 0) + n
            out[f] = dict(sorted(counts.items()))
        return out

    def combos(self, base: list[Node]) -> tuple[tuple[Combo, int], ...]:
        """How many matches of `base`'s conjunction (every document when empty) have each (venue, year,
        track, status), from one collection; memoised per base under task-080's rules."""
        key = "\x00".join(sorted(_spanless(c) for c in base))
        hit = self.faceted.get(key)  # one read (task-080)
        if hit is not None:
            return hit
        node = base[0] if len(base) == 1 else And(span=(0, 0), children=tuple(base)) if base else None
        query = tantivy.Query.all_query() if node is None else self.compile(node).query
        aggs: dict[str, Any] = {}
        for f in reversed(COMBO):  # venue → year → track → status, innermost last
            aggs = {f: {"terms": {"field": f, "size": 100_000}, **({"aggs": aggs} if aggs else {})}}
        found: list[tuple[Combo, int]] = []
        _walk(self.searcher.aggregate(query, aggs), (), found)
        combos = tuple(sorted(found))
        self._trim("faceted", self.faceted, self.MAX_FACET_COMBOS)
        self.faceted[key] = combos  # stored complete (an immutable tuple), never changed after
        self.charges["faceted"].append(len(combos) + 1)
        return combos

    # --- compilation and explain ---------------------------------------------------------------------
    def expansions(self, ast: Node) -> Expansions:
        """Every wildcard in the query, expanded once, before anything is compiled."""
        out: Expansions = {}
        for w in wildcards(ast):
            if (w.stem, w.op) not in out:
                out[(w.stem, w.op)] = tuple(self.expand(w))
        return out

    def compile(self, ast: Node) -> Compiled:
        """The compiled query, memoised per tree: the index is immutable, so a tree compiles the same way every
        time, and a search, its pages and its facets needn't build the Boolean again (task-076 headroom)."""
        # spans included: ` trust` and `trust` compile apart (a miss, never wrong)
        key = ast.model_dump_json()
        hit = self.compiled.get(key)  # one read: the memo may be cleared by another thread at any time
        if hit is not None:
            return self._copy(hit)
        self._trim("verified", self.verified, self.MAX_VERIFIED_IDS)
        self._trim("compiled", self.compiled, self.MAX_COMPILED_UNITS)
        compiled = Compiler(
            self.index.schema, self.expansions(ast), self.read, self.verified, self.ranking["field_weights"]
        ).compile(ast)
        self.compiled[key] = compiled
        self.charges["compiled"].append(compiled.held + 1)
        if compiled.stored:
            self.charges["verified"].append(compiled.stored)
        return self._copy(compiled)

    def _trim(self, name: str, memo: dict[Any, Any], budget: int) -> None:
        """Clear `memo` once the weights charged to it since its last clear pass `budget`.

        Lock-free, under task-080's rules, and every race errs towards clearing early, never towards holding
        more than the budget plus what the compiles in flight store: a charge is one `list.append` (atomic, so
        concurrent charges are never lost, as `+=` on a counter can be), made after its entry is stored; a
        clear swaps in a new ledger *before* clearing the memo, so an entry stored in between is charged to the
        new ledger although the clear removes it (an over-count), and one stored after is charged normally. Two
        threads may both see the ledger over budget and clear twice, which only costs recomputation. The ledger
        is a list, not a memo: slicing it while another thread appends sees that charge or doesn't. The sum is
        kept incrementally, so a check costs only the charges since the last one: `tallied` holds (ledger,
        items summed, their sum), one tuple rebound whole, so a thread that stores an older tally only makes
        the next check sum more; a tally of a swapped-out ledger is ignored."""
        ledger = self.charges[name]
        seen, count, total = self.tallied.get(name, (None, 0, 0))
        if seen is not ledger:
            count, total = 0, 0
        new = ledger[count:]  # one slice: charges appended after it are summed by the next check
        count, total = count + len(new), total + sum(new)
        self.tallied[name] = (ledger, count, total)
        if total > budget:
            self.charges[name] = []  # first: see above
            memo.clear()

    @staticmethod
    def _copy(compiled: Compiled) -> Compiled:
        """The memo's entry with its own lists, so a caller can't change what later callers get."""
        return dataclasses.replace(compiled, explain=list(compiled.explain), verified=list(compiled.verified))

    def explain(self, ast: Node) -> str:
        """The compiled query as a readable tree, its wildcard expansions and verified clauses (op search
        --explain)."""
        compiled = self.compile(ast)
        lines = ["compiled query:", *("  " + line for line in compiled.explain)]
        expansions = self.expansions(ast)
        if expansions:
            lines.append("wildcard expansions:")
            lines += [
                f"  {stem}{op}: {', '.join(terms) or '(none)'}"
                for (stem, op), terms in sorted(expansions.items())
            ]
        lines.append("verified by position: " + ("; ".join(compiled.verified) or "none"))
        return "\n".join(lines)

    # --- reading the index ---------------------------------------------------------------------------
    def hits(self, query: tantivy.Query) -> list[tantivy.DocAddress]:
        limit = max(1, self.searcher.num_docs)
        return [address for _score, address in self.searcher.search(query, limit).hits]

    def ids_of(self, query: tantivy.Query) -> frozenset[str]:
        addresses = self.hits(query)
        if not addresses:
            return frozenset()
        return frozenset(self.ids[_ord(o)] for o in self.searcher.fast_field_values("ord", addresses))

    def read(self, query: tantivy.Query, field: TextField) -> Iterator[tuple[str, list[str]]]:
        """Each candidate's id and one field's stored token stream (the indexed text, split on spaces)."""
        for address in self.hits(query):
            doc = self.searcher.doc(address).to_dict()
            text = doc[field][0] if doc.get(field) else ""
            yield doc["id"][0], text.split(" ") if text else []


def _ord(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise EngineInternalError(
            DiagnosticCode.API_INTERNAL, "a document has no ord: the index predates it; build it again"
        )
    return value


def _conjuncts(n: Node) -> list[Node]:
    """Top-level AND conjuncts, nested ANDs flattened."""
    return [x for c in n.children for x in _conjuncts(c)] if isinstance(n, And) else [n]


def _walk(result: dict[str, Any], prefix: tuple[str | int, ...], out: list[tuple[Combo, int]]) -> None:
    """The leaves of a nested terms aggregation over COMBO, as ((venue, year, track, status), count)."""
    field = COMBO[len(prefix)]
    for bucket in result[field]["buckets"]:
        key = (*prefix, int(bucket["key"]) if field == "year" else str(bucket["key"]))
        if len(key) == len(COMBO):
            out.append((key, int(bucket["doc_count"])))  # type: ignore[arg-type]
        else:
            _walk(bucket, key, out)


def _passes(n: Node, value: str | int) -> bool:
    """Whether a document whose value in `n`'s field is `value` passes the top-level filter `n` (a `Filter` or
    `NOT` of one), as the compiled query decides it (compile.py `filter`): years in any range, inclusive;
    other fields equal to one of the values."""
    inner = n.child if isinstance(n, Not) else n
    assert isinstance(inner, Filter)
    if inner.field == "year":
        hit = any(isinstance(v, YearRange) and v.lo <= value <= v.hi for v in inner.values)  # type: ignore[operator]
    else:
        hit = str(value) in {str(v) for v in inner.values}
    return not hit if isinstance(n, Not) else hit


def _spanless(n: Node) -> str:
    """`n` as JSON without its spans (anywhere in the tree): what a kept conjunct means, not where it was
    written, so an inserted default and the same filter built by exclusion accounting key alike."""
    return json.dumps(_drop_spans(n.model_dump(mode="json")), sort_keys=True, ensure_ascii=False)


def _drop_spans(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _drop_spans(v) for k, v in value.items() if k != "span"}
    if isinstance(value, list):
        return [_drop_spans(v) for v in value]
    return value


def _filter_field(n: Node) -> str | None:
    inner = n.child if isinstance(n, Not) else n
    return inner.field if isinstance(inner, Filter) else None


def _conforms(engine: TantivyEngine) -> Engine:
    return engine  # mypy fails `make lint` if TantivyEngine drifts from the Engine protocol
