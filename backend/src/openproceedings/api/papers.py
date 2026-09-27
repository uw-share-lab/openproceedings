"""`GET /api/v1/papers/{id}`: the full record, provenance included (spec 04 §Endpoints).

The served index decides whether a paper exists (404 `API_PAPER_NOT_FOUND` otherwise; an id that isn't
`op:<venue>:<year>:<native>` is 422 `API_BAD_PARAM`, the path parameter's pattern, as a malformed record id
is), so the answer belongs to the same
`index_version` as a search. The index stores only the display record, so the full record (per-field
provenance claims, `content_hash`) is read from the snapshot the index was built from. That snapshot is
verified when the index is loaded (`api/state.py::snapshot_records`): an index without it is never served.
Only a snapshot file that disappears after the load is a per-request 500 `API_INTERNAL`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path

from openproceedings.api.deps import ServedDep
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import PAPER_ID, PAPER_ID_DOC, PaperResponse, versions
from openproceedings.diagnostics import DiagnosticCode, InternalError
from openproceedings.ingest.record import is_paper_id
from openproceedings.ingest.snapshot import SnapshotError

router = APIRouter(prefix=API_PREFIX)


@router.get("/papers/{id}", response_model=PaperResponse)
def get_paper(
    served: ServedDep, id: Annotated[str, Path(pattern=PAPER_ID, description=PAPER_ID_DOC)]
) -> PaperResponse:
    """The paper with this id in the served index, as its snapshot holds it (the records loaded with that
    very engine: one bundle, whatever swaps happen meanwhile)."""
    engine = served.engine
    # the pattern admits any venue (an open enum); one this code doesn't know is no paper here: 404
    if not is_paper_id(id) or id not in engine.display([id]):
        raise ApiError(
            DiagnosticCode.API_PAPER_NOT_FOUND, f"No paper with that id in index {engine.index_version}."
        )
    try:
        record = served.records.get(id)
    except (OSError, SnapshotError) as e:  # the file changed or vanished after it was verified at load
        raise InternalError(DiagnosticCode.API_INTERNAL, "the index's snapshot is unreadable") from e
    if record is None:  # the index holds it, its verified snapshot doesn't: an invariant broken
        raise InternalError(
            DiagnosticCode.API_INTERNAL, "a paper the index holds is missing from its snapshot"
        )
    return PaperResponse(**versions(engine.index_version), paper=record)
