"""`POST /api/v1/parse` and `GET /api/v1/search` (spec 04 §Endpoints, §SearchResponse).

Transport only: `/parse` is `query.parser.parse`, `/search` is `openproceedings.search.run`, the function
`op search` calls, on the one engine this request read. Nothing here decides what matches, how it ranks,
what the facets count or what the defaults removed. Each hit's `abstract_source` (TASK-134, decision-018) is
looked up in what the served snapshot's reader computed at load (`RecordFile.attributions`): the index's
display record keeps no provenance. Likewise each hit's `twins` (TASK-162, decision-029), from
`RecordFile.twins`.

A takedown (TASK-136, decision-022) changes what a hit shows, never whether it is one: a hit whose abstract this
instance withholds (`Served.withheld_in`) has `abstract` null, no abstract highlight spans, `abstract_source`
null and `abstract_withheld` true. Its title spans, its score, `total` and the facets are what the index gives.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from openproceedings.api.deps import (
    EngineDep,
    ServedDep,
    access_fields,
    annotate,
    check_candidates,
    parsed,
    searchable,
)
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
    GroupCount,
    GroupCounts,
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
from openproceedings.ingest.record import Urls
from openproceedings.ingest.snapshot import RecordFile
from openproceedings.query.clauses import filter_clauses
from openproceedings.query.parser import Mode
from openproceedings.query.wordforms import word_forms
from openproceedings.search import Hit as Found
from openproceedings.search import expansions_json, run

router = APIRouter(prefix=API_PREFIX)


@router.post("/parse", response_model=ParseResponse)
def parse_query(request: Request, engine: EngineDep, body: ParseRequest) -> ParseResponse:
    """02's ParseResult for `q` (debounced as the user types). It reports a parse: any well-formed body is
    a 200 whose `errors` say why the query doesn't parse (`PARSE_TOO_LONG` included); only a malformed body
    is refused (422 `API_BAD_PARAM`)."""
    result = parsed(request, body.q, body.mode, engine.tokenizer_version)
    return ParseResponse(
        **versions(engine.index_version, engine.tokenizer_version),
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
        word_forms=word_forms(body.q, result),
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
    result = searchable(request, q, mode, engine.tokenizer_version)
    assert result.effective_ast is not None  # searchable refuses a query that doesn't parse
    check_candidates(
        request, engine, result.effective_ast
    )  # 422 API_QUERY_TOO_COSTLY before any verification
    found = run(
        engine,
        result,
        sort=sort,
        offset=offset,
        limit=limit,
        facets=True,
        highlight=True,
        groups=request.app.state.config.max_counted_groups,
        groups_terms=request.app.state.config.max_counted_terms,
        groups_ids=request.app.state.config.max_counted_ids,
    )
    annotate(request, total=found.total)
    assert found.groups is not None  # asked for
    # the access line: how many groups the query has and how many were counted (two integers, never a span)
    access_fields(request).update(groups=found.groups.found, groups_counted=len(found.groups.counts))
    sources = page_attributions(served.records, [h.id for h in found.hits])
    hidden = served.withheld_in(served.records)  # the takedown list, as this bundle's load read it
    assert result.canonical is not None and result.canonical_hash is not None  # it parsed
    assert result.identification_query is not None and found.facets is not None
    return SearchResponse(
        **versions(engine.index_version, engine.tokenizer_version),
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
        groups=GroupCounts(
            counts=[
                GroupCount(span=span, total=alone, total_without=without)
                for span, alone, without in found.groups.counts
            ],
            groups_total=found.groups.found,
            limit=found.groups.limit,
            not_counted=found.groups.not_counted,
        ),
        hits=[
            _hit(h, sources[h.id], withheld=h.id in hidden, twins=served.records.twins.get(h.id, ()))
            for h in found.hits
        ],
    )


def page_attributions(records: RecordFile, ids: list[str]) -> dict[str, AbstractSource | None]:
    """Each hit's `abstract_source`, looked up in what the served snapshot's reader computed at load (no file
    I/O here). A hit the verified snapshot doesn't hold is an invariant broken (500), as on `/papers/{id}`."""
    out: dict[str, AbstractSource | None] = {}
    for i in ids:
        if i not in records.attributions:
            raise InternalError(
                DiagnosticCode.API_INTERNAL, "a paper the index holds is missing from its snapshot"
            )
        a = records.attributions[i]
        out[i] = None if a is None else AbstractSource(source=a.source, origin=a.origin, url=a.url)
    return out


def _hit(
    found: Found, abstract_source: AbstractSource | None, *, withheld: bool, twins: tuple[str, ...]
) -> Hit:
    """The API's hit; with `withheld`, without its abstract, the abstract's spans (they would say where the
    query matched the withheld text) and its source."""
    r: Any = found.record
    assert found.highlights is not None
    return Hit(
        id=found.id,
        title=r["title"],
        abstract=None if withheld else r["abstract"],
        authors=r["authors"],
        venue=r["venue"],
        year=r["year"],
        track=r["track"],
        status=r["status"],
        presentation=r["presentation"],
        score=found.score,
        highlights=Highlights(
            title=found.highlights["title"], abstract=[] if withheld else found.highlights["abstract"]
        ),
        urls=Urls.model_validate(r["urls"]),
        abstract_source=None if withheld else abstract_source,
        abstract_withheld=withheld,
        twins=list(twins),
    )
