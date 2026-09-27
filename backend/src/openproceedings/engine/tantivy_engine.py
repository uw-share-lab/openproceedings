"""TantivyEngine: the Engine protocol over a built index (spec 03; ast-compilation skill).

Matching is `compile.py`'s; this module wires it to an index: wildcard expansion from the term dictionary
(both text fields, the 200 cap enforced before compiling), match sets read back through the `ord` fast
column and `ids.txt`, disjunctive facets (decision-001 rule 6) counted by Tantivy's terms aggregation, and
the `--explain` rendering. `search` orders the whole match set (field-weighted BM25, or year, or title) with the id as
the last key, then pages it (task-025). The index is verified (every file re-hashed) when the engine opens it.
"""

from __future__ import annotations

import dataclasses
import heapq
from collections.abc import Iterator
from importlib.metadata import version
from pathlib import Path
from typing import Any

import tantivy

from openproceedings.diagnostics import DiagnosticCode
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
from openproceedings.query.ast import And, Filter, Node, Not, TextField, Wildcard
from openproceedings.query.normalize import TOKENIZER_VERSION

SORTS = ("relevance", "year_desc", "year_asc", "title")
# the Tantivy TANTIVY_BM25 was confirmed on; test_rank.py fails if the installed one drifts
TANTIVY_PINNED = "0.26.2"
TANTIVY_BM25 = {"b": 0.75, "k1": 1.2}  # Tantivy's fixed constants: an index can't claim others


class TantivyEngine:
    def __init__(self, path: Path) -> None:
        manifest = verify_index(path)
        self.index_version: str = manifest["index_version"]
        self.ranking: dict[str, Any] = manifest["ranking_params"]  # the params this index's id was built with
        stale = {
            "schema_version": (manifest.get("schema_version"), SCHEMA_VERSION),
            "tokenizer_version": (manifest.get("tokenizer_version"), TOKENIZER_VERSION),
            "tantivy_version": (manifest.get("tantivy_version"), version("tantivy")),  # scoring may differ
        }
        for name, (built, current) in stale.items():
            if built != current:  # queries are normalized and compiled for the current versions
                raise EngineInternalError(
                    DiagnosticCode.API_INTERNAL,
                    f"index {self.index_version} has {name} {built}, this code {current}: build a new index",
                )
        if self.ranking.get("bm25") != TANTIVY_BM25:
            raise EngineInternalError(
                DiagnosticCode.API_INTERNAL,
                f"index {self.index_version} records bm25 {self.ranking.get('bm25')}, but Tantivy applies {TANTIVY_BM25}",
            )
        self.index = open_index(path)
        self.searcher = self.index.searcher()
        self.ids = (path / IDS).read_text(encoding="utf-8").splitlines()
        self.compiled: dict[str, Compiled] = {}  # per tree (bounded), see compile()
        self.verified: dict[tuple[str, str], list[str]] = {}  # position-verified clauses, per engine
        # each wildcard's terms, or just the count of an over-cap one
        self.expanded: dict[tuple[str, str], tuple[str, ...] | int] = {}

    @property
    def universe(self) -> frozenset[str]:
        """Every id in the index (tests and facet checks; built on demand, not held for every engine)."""
        return frozenset(self.ids)

    # --- the Engine protocol -------------------------------------------------------------------------
    def expand(self, wildcard: Wildcard) -> list[str]:
        """Every indexed term (title or abstract) the wildcard matches, sorted; more than MAX_EXPANSIONS
        is an error, never a truncation. From the term dictionary, not a scan of the documents."""
        key = (wildcard.stem, wildcard.op)
        terms = self.expanded.get(key)  # the index is immutable, so a stem's terms are too
        if terms is None:
            found: set[str] = set()
            for f in FIELDS:
                for term, _count in self.searcher.terms_with_prefix(f, wildcard.stem):
                    if wildcard.op == "*" or term == wildcard.stem or len(term) == len(wildcard.stem) + 1:
                        found.add(term)
            # an over-cap stem keeps only its count: a refused query never holds its terms in memory
            terms = tuple(sorted(found)) if len(found) <= MAX_EXPANSIONS else len(found)
            if len(self.expanded) > 10_000:
                self.expanded.clear()  # bounded, like `verified`
            self.expanded[key] = terms
        if isinstance(terms, int) or len(terms) > MAX_EXPANSIONS:  # checked on every call, cached or not
            count = terms if isinstance(terms, int) else len(terms)
            raise EngineInputError(
                DiagnosticCode.WILDCARD_TOO_MANY_EXPANSIONS,
                f"`{wildcard.stem}{wildcard.op}` expands to {count} terms (more than {MAX_EXPANSIONS}) — use a "
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
        query without F's own top-level conjuncts (a filter on F, or NOT of one; nested ones stay)."""
        unknown = [f for f in fields if f not in FACET_FIELDS]
        if unknown:
            raise EngineInputError(DiagnosticCode.API_BAD_PARAM, f"facet fields must be among {FACET_FIELDS}")
        self.expansions(ast)  # the cap applies even when no facet field is asked for
        out: dict[str, dict[str, int]] = {}
        compiled: dict[str, tantivy.Query] = {}  # one compile per distinct kept set (verification is costly)
        for f in fields:
            kept = [c for c in _conjuncts(ast) if _filter_field(c) != f]
            key = "\x00".join(c.model_dump_json() for c in kept)
            if key not in compiled:
                node = kept[0] if len(kept) == 1 else And(span=(0, 0), children=tuple(kept)) if kept else None
                compiled[key] = tantivy.Query.all_query() if node is None else self.compile(node).query
            query = compiled[key]
            result = self.searcher.aggregate(query, {"f": {"terms": {"field": f, "size": 100_000}}})
            out[f] = dict(sorted((str(b["key"]), int(b["doc_count"])) for b in result["f"]["buckets"]))
        return out

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
        key = (
            ast.model_dump_json()
        )  # spans included: ` trust` and `trust` compile apart (a miss, never wrong)
        if key in self.compiled:
            return self._copy(self.compiled[key])
        if len(self.verified) > 1_000:
            self.verified.clear()  # bounded: a long-running API never grows it without limit
        if len(self.compiled) > 1_000:
            self.compiled.clear()
        compiled = Compiler(
            self.index.schema, self.expansions(ast), self.read, self.verified, self.ranking["field_weights"]
        ).compile(ast)
        self.compiled[key] = compiled
        return self._copy(compiled)

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


def _filter_field(n: Node) -> str | None:
    inner = n.child if isinstance(n, Not) else n
    return inner.field if isinstance(inner, Filter) else None


def _conforms(engine: TantivyEngine) -> Engine:
    return engine  # mypy fails `make lint` if TantivyEngine drifts from the Engine protocol
