"""One ranked search, as `op search` and `GET /api/v1/search` both run it (spec 04 §SearchResponse; task-035).

The API adds transport, not behaviour: both callers pass a parsed query and an engine to `run`, so a page's
ids, scores, `total` and `excluded` are the same for the same query and `index_version`. The API also asks
for the disjunctive facets and each hit's highlights; the CLI, which prints neither, doesn't pay for them.

Order of work, on one engine: every wildcard is expanded first (the 200-term cap refuses a query before
anything is compiled), then one collection of the match set gives `total` and the page, then exclusion
accounting reuses that `total`, then the page's display records are read.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.exclusions import Excluded, excluded
from openproceedings.engine.highlight import highlights
from openproceedings.engine.protocol import EngineInputError, Expansions
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.ast import TextField
from openproceedings.query.parser import ParseResult

type Spans = Mapping[TextField, list[tuple[int, int]]]


@dataclass(frozen=True, slots=True)
class Shown:
    """A display record as `engine/highlight.py` reads it (the `Searchable` protocol)."""

    id: str
    title: str
    abstract: str | None
    venue: str
    year: int
    track: str
    status: str

    @classmethod
    def of(cls, record: Mapping[str, Any]) -> Shown:
        return cls(**{f: record[f] for f in ("id", "title", "abstract", "venue", "year", "track", "status")})


@dataclass(frozen=True, slots=True)
class Hit:
    id: str
    score: float  # the exact field-weighted BM25 score (0.0-based sorts keep it too)
    record: Mapping[str, Any]  # the stored display record (`TantivyEngine.display`)
    highlights: Spans | None  # None unless asked for


@dataclass(frozen=True, slots=True)
class Search:
    total: int  # |match_ids(effective_ast)|: independent of sort, offset and limit (guarantee 5)
    hits: tuple[Hit, ...]  # the page, in the engine's order
    excluded: Excluded
    expansions: Expansions  # every wildcard's terms (guarantee 6)
    facets: dict[str, dict[str, int]] | None  # None unless asked for


def run(
    engine: TantivyEngine,
    parsed: ParseResult,
    *,
    sort: str = "relevance",
    offset: int = 0,
    limit: int = 50,
    facets: bool = False,
    highlight: bool = False,
) -> Search:
    """One page of `parsed`'s search on `engine`, with its total, exclusion accounting and expansions (and,
    when asked, the disjunctive facets and each hit's code-point highlight spans). `parsed` must have
    parsed: a query with errors never reaches an engine (spec 03 §Error handling)."""
    ast = parsed.effective_ast
    if ast is None:
        raise EngineInputError(DiagnosticCode.API_BAD_PARAM, "a search needs a query that parses.")
    expansions = engine.expansions(ast)
    total, page = engine.page(ast, sort=sort, offset=offset, limit=limit)  # one collection: ids and scores
    gone = excluded(engine, parsed, total)
    shown = engine.display([i for i, _score in page])
    hits = tuple(
        Hit(
            id=i,
            score=score,
            record=shown[i],
            highlights=highlights(ast, Shown.of(shown[i]), expansions) if highlight else None,
        )
        for i, score in page
    )
    return Search(total, hits, gone, expansions, engine.facets(ast) if facets else None)
