"""`POST /api/v1/parse` and `GET /api/v1/search` (spec 04 §Endpoints, §SearchResponse).

Transport only: `/parse` is `query.parser.parse`, `/search` is `openproceedings.search.run`, the function
`op search` calls, on the one engine this request read. Nothing here decides what matches, how it ranks,
what the facets count or what the defaults removed. Each hit's `abstract_source` (TASK-134, decision-018) is
read from the served snapshot's records for the page's ids alone: the index's display record keeps no
provenance.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from openproceedings.api.deps import EngineDep, ServedDep, annotate, check_candidates, parsed, searchable
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import (
    DEFAULT_LIMIT,
    LIMIT_DOC,
    MAX_LIMIT,
    MODE_DOC,
    OFFSET_DOC,
    Q_DOC,
    SORT_DOC,
    AbstractSource,
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
from openproceedings.api.openapi import BUSY
from openproceedings.diagnostics import DiagnosticCode, InternalError
from openproceedings.engine.exclusions import identified_total, unclassified_total
from openproceedings.ingest.dedup import abstract_claim
from openproceedings.ingest.record import PaperRecord, Urls
from openproceedings.ingest.snapshot import RecordFile, SnapshotError
from openproceedings.query.clauses import filter_clauses
from openproceedings.query.parser import Mode
from openproceedings.search import Hit as Found
from openproceedings.search import expansions_json, run

router = APIRouter(prefix=API_PREFIX)


@router.post("/parse", response_model=ParseResponse)
def parse_query(request: Request, engine: EngineDep, body: ParseRequest) -> ParseResponse:
    """02's ParseResult for `q` (debounced as the user types). It reports a parse: any well-formed body is
    a 200 whose `errors` say why the query doesn't parse (`PARSE_TOO_LONG` included); only a malformed body
    is refused (422 `API_BAD_PARAM`)."""
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
        filters=filter_clauses(body.q, result),
    )


@router.get("/search", response_model=SearchResponse, responses=BUSY)
def search(
    request: Request,
    served: ServedDep,
    q: Annotated[str, Query(description=Q_DOC)],
    mode: Annotated[Mode, Query(description=MODE_DOC)] = "native",
    sort: Annotated[Sort, Query(description=SORT_DOC)] = "relevance",
    offset: Annotated[int, Query(ge=0, description=OFFSET_DOC)] = 0,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT, description=LIMIT_DOC)] = DEFAULT_LIMIT,
) -> SearchResponse:
    """One page of the ranked matched set, with its total, exclusion accounting, disjunctive facets and
    highlights. `limit` over 200 is a 422 (never clamped); a query that doesn't parse is a 422 with its
    diagnostics."""
    engine = served.engine  # the request's one read of the served index: its records are this engine's
    result = searchable(request, q, mode)
    assert result.effective_ast is not None  # searchable refuses a query that doesn't parse
    check_candidates(
        request, engine, result.effective_ast
    )  # 422 API_QUERY_TOO_COSTLY before any verification
    found = run(engine, result, sort=sort, offset=offset, limit=limit, facets=True, highlight=True)
    annotate(request, total=found.total)
    records = page_records(served.records, [h.id for h in found.hits])
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
            expansions=expansions_json(found.expansions),
        ),
        total=found.total,
        excluded=Excluded.model_validate(found.excluded.to_json()),
        identified_total=identified_total(found.total, found.excluded.total),
        unclassified_total=unclassified_total(found.excluded.track, found.excluded.status),
        facets=Facets.model_validate(found.facets),
        hits=[_hit(h, records[h.id]) for h in found.hits],
    )


def page_records(records: RecordFile, ids: list[str]) -> dict[str, PaperRecord]:
    """The snapshot records of a page's hits (one read of the file), for what the index's display record
    lacks: each abstract's provenance. A hit the verified snapshot doesn't hold is an invariant broken (500),
    as on `/papers/{id}`."""
    try:
        found = records.get_many(ids)
    except (OSError, SnapshotError) as e:  # the file changed or vanished after it was verified at load
        raise InternalError(DiagnosticCode.API_INTERNAL, "the index's snapshot is unreadable") from e
    if len(found) != len(set(ids)):
        raise InternalError(
            DiagnosticCode.API_INTERNAL, "a paper the index holds is missing from its snapshot"
        )
    return found


_OPENREVIEW = frozenset({"openreview_v1", "openreview_v2"})


def abstract_source(record: PaperRecord) -> AbstractSource | None:
    """Where `record`'s abstract came from, to attribute it (decision-018): the claim precedence chose it from,
    and the paper's page at that source. An OpenReview claim's url is the API listing it was read from, so the
    page is the record's forum; a proceedings claim's url is the paper's own page (PMLR's CC BY 4.0 terms ask
    for that link); `ris` has none."""
    claim = abstract_claim(record)
    if claim is None:
        return None
    url = record.urls.forum if claim.source in _OPENREVIEW else claim.url
    return AbstractSource(source=claim.source, url=url)


def _hit(found: Found, record: PaperRecord) -> Hit:
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
        status=r["status"],
        presentation=r["presentation"],
        score=found.score,
        highlights=Highlights(title=found.highlights["title"], abstract=found.highlights["abstract"]),
        urls=Urls.model_validate(r["urls"]),
        abstract_source=abstract_source(record),
    )
