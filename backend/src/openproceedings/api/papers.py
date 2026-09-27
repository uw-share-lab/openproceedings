"""`GET /api/v1/papers/{id}`: the full record, provenance included (spec 04 §Endpoints).

The served index decides whether a paper exists (404 `API_PAPER_NOT_FOUND` otherwise; an id that isn't
`op:<venue>:<year>:<native>` is refused before the index is asked), so the answer belongs to the same
`index_version` as a search. The index stores only the display record, so the full record (per-field
provenance claims, `content_hash`) is read from the snapshot the index was built from. That snapshot is
verified when the index is loaded (`api/state.py::snapshot_records`): an index without it is never served.
Only a snapshot file that disappears after the load is a per-request 500 `API_INTERNAL`.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from openproceedings.api.deps import EngineDep
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import PaperResponse, versions
from openproceedings.api.state import IndexState
from openproceedings.diagnostics import DiagnosticCode, InternalError
from openproceedings.ingest.record import is_paper_id
from openproceedings.ingest.snapshot import SnapshotError

router = APIRouter(prefix=API_PREFIX)


@router.get("/papers/{id}", response_model=PaperResponse)
def paper(request: Request, engine: EngineDep, id: str) -> PaperResponse:
    """The paper with this id in the served index, as its snapshot holds it."""
    if not is_paper_id(id) or id not in engine.display([id]):
        raise ApiError(
            DiagnosticCode.API_PAPER_NOT_FOUND, f"No paper with that id in index {engine.index_version}."
        )
    state: IndexState = request.app.state.index
    records = state.records(engine.index_version)
    try:
        record = records.get(id) if records is not None else None
    except (OSError, SnapshotError) as e:  # the file changed or vanished after it was verified at load
        raise InternalError(DiagnosticCode.API_INTERNAL, "the index's snapshot is unreadable") from e
    if record is None:  # the index holds it, its verified snapshot doesn't: an invariant broken
        raise InternalError(
            DiagnosticCode.API_INTERNAL, "a paper the index holds is missing from its snapshot"
        )
    return PaperResponse(**versions(engine.index_version), paper=record)
