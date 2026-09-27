"""`GET /api/v1/healthz`: liveness, and whether an index is loaded (spec 04 §Endpoints)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from openproceedings.query import QUERY_VERSION
from openproceedings.query.normalize import TOKENIZER_VERSION

if TYPE_CHECKING:
    from openproceedings.api.state import IndexState

router = APIRouter()


class Health(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    index_loaded: bool
    index_version: str | None  # None until an index is loaded
    tokenizer_version: str
    query_version: str


@router.get("/healthz", response_model=Health)
def healthz(request: Request) -> Health:
    """Always 200 while the process serves requests; `index_loaded` is false until the first load succeeds
    (search routes answer 503 `API_INDEX_NOT_LOADED` meanwhile)."""
    state: IndexState = request.app.state.index
    engine = state.engine  # read once
    return Health(
        index_loaded=engine is not None,
        index_version=engine.index_version if engine is not None else None,
        tokenizer_version=TOKENIZER_VERSION,
        query_version=QUERY_VERSION,
    )
