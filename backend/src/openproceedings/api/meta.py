"""`GET /api/v1/meta`: the served and available index_versions, and the field and value vocabularies that
feed the UI's autocomplete (spec 04 §Endpoints). The vocabularies are the ones the parser checks filter
values against (`vocab.py`, `query/ast.py`), so autocomplete never offers a value the parser refuses."""

from __future__ import annotations

from fastapi import APIRouter, Request

from openproceedings.api.deps import EngineDep
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import MetaResponse, Vocabularies, versions
from openproceedings.api.state import IndexState
from openproceedings.query.ast import FILTER_FIELDS
from openproceedings.vocab import STATUSES, TEXT_FIELDS, TRACKS, VENUES

router = APIRouter(prefix=API_PREFIX)


@router.get("/meta", response_model=MetaResponse)
def meta(request: Request, engine: EngineDep) -> MetaResponse:
    state: IndexState = request.app.state.index
    return MetaResponse(
        **versions(engine.index_version),
        index_versions=state.available(engine),
        text_fields=list(TEXT_FIELDS),
        filter_fields=list(FILTER_FIELDS),
        values=Vocabularies.model_validate(
            {"venue": list(VENUES.values()), "track": list(TRACKS), "status": list(STATUSES)}
        ),
    )
