"""TantivyEngine: the Engine protocol over a built index (spec 03; ast-compilation skill).

Matching is `compile.py`'s; this module wires it to an index: wildcard expansion from the term dictionary
(both text fields, the 200 cap enforced before compiling), match sets read back through the `ord` fast
column and `ids.txt`, disjunctive facets (decision-001 rule 6) counted by Tantivy's terms aggregation, and
the `--explain` rendering. Ranking is task-025: until then `search` returns id order, as ReferenceEngine
does. The index is verified (every file re-hashed) when the engine opens it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import tantivy

from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.compile import FIELDS, Compiled, Compiler, Expansions, wildcards
from openproceedings.engine.index import IDS, open_index, verify_index
from openproceedings.engine.protocol import (
    FACET_FIELDS,
    MAX_EXPANSIONS,
    Engine,
    EngineError,
    EngineInputError,
    SearchResult,
)
from openproceedings.query.ast import And, Filter, Node, Not, TextField, Wildcard


class TantivyEngine:
    def __init__(self, path: Path) -> None:
        manifest = verify_index(path)
        self.index_version: str = manifest["index_version"]
        self.index = open_index(path)
        self.searcher = self.index.searcher()
        self.ids = (path / IDS).read_text(encoding="utf-8").splitlines()
        self.universe = frozenset(self.ids)
        self.verified: dict[tuple[str, str], list[str]] = {}  # position-verified clauses, per engine

    # --- the Engine protocol -------------------------------------------------------------------------
    def expand(self, wildcard: Wildcard) -> list[str]:
        """Every indexed term (title or abstract) the wildcard matches, sorted; more than MAX_EXPANSIONS
        is an error, never a truncation. From the term dictionary, not a scan of the documents."""
        found: set[str] = set()
        for f in FIELDS:
            for term, _count in self.searcher.terms_with_prefix(f, wildcard.stem):
                if wildcard.op == "*" or term == wildcard.stem or len(term) == len(wildcard.stem) + 1:
                    found.add(term)
        if len(found) > MAX_EXPANSIONS:
            raise EngineInputError(
                DiagnosticCode.WILDCARD_TOO_MANY_EXPANSIONS,
                f"`{wildcard.stem}{wildcard.op}` expands to {len(found)} terms (more than {MAX_EXPANSIONS}) — use a "
                "longer stem.",
            )
        return sorted(found)

    def match_ids(self, ast: Node) -> frozenset[str]:
        return self.ids_of(self.compile(ast).query)

    def search(self, ast: Node, *, sort: str = "relevance", offset: int = 0, limit: int = 50) -> SearchResult:
        """Id order until ranking lands (task-025)."""
        if offset < 0 or limit < 0:
            raise EngineInputError(DiagnosticCode.API_BAD_PARAM, "offset and limit must be ≥ 0.")
        ids = sorted(self.match_ids(ast))
        return SearchResult(total=len(ids), ids=tuple(ids[offset : offset + limit]))

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
        if len(self.verified) > 1_000:
            self.verified.clear()  # bounded: a long-running API never grows it without limit
        return Compiler(self.index.schema, self.expansions(ast), self.read, self.verified).compile(ast)

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
        raise EngineError(
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
