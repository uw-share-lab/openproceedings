"""`GET /api/v1/meta`: the served and available index_versions, the field and value vocabularies that feed
the UI's autocomplete, and this instance's query limits (spec 04 §Endpoints). The vocabularies are the ones
the parser checks filter values against (`vocab.py`, `query/ast.py`), so autocomplete never offers a value
the parser refuses; the limits are the parser's caps (length and depth) and the served config's, the values
the routes enforce."""

from __future__ import annotations

from fastapi import APIRouter, Request

from openproceedings.api.config import ApiConfig
from openproceedings.api.deps import EngineDep
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import Limits, MetaResponse, Vocabularies, versions
from openproceedings.api.state import IndexState
from openproceedings.query.ast import FILTER_FIELDS
from openproceedings.query.parser import MAX_DEPTH, MAX_QUERY_LENGTH
from openproceedings.vocab import STATUSES, TEXT_FIELDS, TRACKS, VENUES

router = APIRouter(prefix=API_PREFIX)


@router.get("/meta", response_model=MetaResponse)
def get_meta(request: Request, engine: EngineDep) -> MetaResponse:
    state: IndexState = request.app.state.index
    config: ApiConfig = request.app.state.config
    return MetaResponse(
        **versions(engine.index_version, engine.tokenizer_version),
        index_versions=state.available(engine),
        text_fields=list(TEXT_FIELDS),
        filter_fields=list(FILTER_FIELDS),
        values=Vocabularies.model_validate(
            {"venue": list(VENUES.values()), "track": list(TRACKS), "status": list(STATUSES)}
        ),
        limits=Limits(
            max_query_length=MAX_QUERY_LENGTH,
            max_query_depth=MAX_DEPTH,
            max_verified_clauses=config.max_verified_clauses,
            max_verification_candidates=config.max_verification_candidates,
            max_counted_groups=config.max_counted_groups,
            max_counted_terms=config.max_counted_terms,
            max_counted_ids=config.max_counted_ids,
        ),
    )
