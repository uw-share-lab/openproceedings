"""`GET /api/v1/healthz`: liveness, and whether an index is loaded (spec 04 §Endpoints)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from openproceedings.api.middleware import API_PREFIX
from openproceedings.query import QUERY_VERSION
from openproceedings.query.normalize import TOKENIZER_VERSION

if TYPE_CHECKING:
    from openproceedings.api.state import IndexState

router = APIRouter(prefix=API_PREFIX)


class Health(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)

    index_loaded: bool
    index_version: str | None  # None until an index is loaded
    tokenizer_version: str
    query_version: str


@router.api_route("/healthz", methods=["GET", "HEAD"], response_model=Health)
def get_healthz(request: Request) -> Health:
    """Always 200 while the process serves requests; `index_loaded` is false until the first load succeeds
    (search routes answer 503 `API_INDEX_NOT_LOADED` meanwhile)."""
    state: IndexState = request.app.state.index
    engine = state.engine  # read once
    return Health(
        index_loaded=engine is not None,
        index_version=engine.index_version if engine is not None else None,
        # the loaded index's (what its queries are read with), else this code's current one
        tokenizer_version=engine.tokenizer_version if engine is not None else TOKENIZER_VERSION,
        query_version=QUERY_VERSION,
    )
