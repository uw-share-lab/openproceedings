"""A frozen copy of `TantivyEngine.facets` before task-086 (one `aggregate` per distinct kept set, each kept set
compiled and collected whole), without its memo: the implementation the fast-column counting must equal,
facet for facet (`test_facets_equal.py`). Never edit it to make a test pass."""

from __future__ import annotations

import tantivy
from openproceedings.engine.protocol import FACET_FIELDS
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.ast import And, Filter, Node, Not


def facets_before(
    engine: TantivyEngine, ast: Node, fields: tuple[str, ...] = FACET_FIELDS
) -> dict[str, dict[str, int]]:
    engine.expansions(ast)
    out: dict[str, dict[str, int]] = {}
    for f in fields:
        kept = [c for c in _conjuncts(ast) if _filter_field(c) != f]
        node = kept[0] if len(kept) == 1 else And(span=(0, 0), children=tuple(kept)) if kept else None
        query = tantivy.Query.all_query() if node is None else engine.compile(node).query
        result = engine.searcher.aggregate(query, {"f": {"terms": {"field": f, "size": 100_000}}})
        out[f] = dict(sorted((str(b["key"]), int(b["doc_count"])) for b in result["f"]["buckets"]))
    return out


def _conjuncts(n: Node) -> list[Node]:
    return [x for c in n.children for x in _conjuncts(c)] if isinstance(n, And) else [n]


def _filter_field(n: Node) -> str | None:
    inner = n.child if isinstance(n, Not) else n
    return inner.field if isinstance(inner, Filter) else None
