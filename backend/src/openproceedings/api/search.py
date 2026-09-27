"""`POST /api/v1/parse` and `GET /api/v1/search` (spec 04 §Endpoints, §SearchResponse).

Transport only: `/parse` is `query.parser.parse`, `/search` is `openproceedings.search.run`, the function
`op search` calls, on the one engine this request read. Nothing here decides what matches, how it ranks,
what the facets count or what the defaults removed.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from openproceedings.api.deps import EngineDep, annotate, parsed, searchable
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    Excluded,
    Facets,
    Highlights,
    Hit,
    ParseRequest,
    ParseResponse,
    QueryInfo,
    SearchResponse,
    Sort,
    versions,
)
from openproceedings.ingest.record import Urls
from openproceedings.query.parser import Mode
from openproceedings.search import Hit as Found
from openproceedings.search import run

router = APIRouter(prefix=API_PREFIX)


@router.post("/parse", response_model=ParseResponse)
def parse_query(request: Request, engine: EngineDep, body: ParseRequest) -> ParseResponse:
    """02's ParseResult for `q` (debounced as the user types). A query that doesn't parse is a 200 whose
    `errors` say why; only an over-long query (`PARSE_TOO_LONG`) or a malformed body is refused."""
    result = parsed(request, body.q, body.mode)
    return ParseResponse(
        **versions(engine.index_version),
        mode=result.mode,
        ast=result.ast,
        effective_ast=result.effective_ast,
        canonical=result.canonical,
        canonical_hash=result.canonical_hash,
        identification_query=result.identification_query,
        defaults=result.defaults,
        warnings=result.warnings,
        errors=result.errors,
        translations=result.translations,
    )


@router.get("/search", response_model=SearchResponse)
def search(
    request: Request,
    engine: EngineDep,
    q: str,
    mode: Mode = "native",
    sort: Sort = "relevance",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> SearchResponse:
    """One page of the ranked matched set, with its total, exclusion accounting, disjunctive facets and
    highlights. `limit` over 200 is a 422 (never clamped); a query that doesn't parse is a 422 with its
    diagnostics."""
    result = searchable(request, q, mode)
    found = run(engine, result, sort=sort, offset=offset, limit=limit, facets=True, highlight=True)
    annotate(request, total=found.total)
    assert result.canonical is not None and result.canonical_hash is not None  # it parsed
    assert result.identification_query is not None and found.facets is not None
    return SearchResponse(
        **versions(engine.index_version),
        query=QueryInfo(
            input=q,
            canonical=result.canonical,
            canonical_hash=result.canonical_hash,
            identification_query=result.identification_query,
            warnings=result.warnings,
            translations=result.translations,
            expansions={f"{stem}{op}": list(terms) for (stem, op), terms in sorted(found.expansions.items())},
        ),
        total=found.total,
        excluded=Excluded.model_validate(found.excluded.to_json()),
        facets=Facets.model_validate(found.facets),
        hits=[_hit(h) for h in found.hits],
    )


def _hit(found: Found) -> Hit:
    r: Any = found.record
    assert found.highlights is not None
    return Hit(
        id=found.id,
        title=r["title"],
        abstract=r["abstract"],
        authors=r["authors"],
        venue=r["venue"],
        year=r["year"],
        track=r["track"],
        presentation=r["presentation"],
        score=found.score,
        highlights=Highlights(title=found.highlights["title"], abstract=found.highlights["abstract"]),
        urls=Urls.model_validate(r["urls"]),
    )
