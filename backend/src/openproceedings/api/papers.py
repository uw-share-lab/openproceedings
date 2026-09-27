"""`GET /api/v1/papers/{id}`: the full record, provenance included (spec 04 §Endpoints).

The served index decides whether a paper exists (404 `API_PAPER_NOT_FOUND` otherwise; an id that isn't
`op:<venue>:<year>:<native>` is 422 `API_BAD_PARAM`, the path parameter's pattern, as a malformed record id
is), so the answer belongs to the same
`index_version` as a search. The index stores only the display record, so the full record (per-field
provenance claims, `content_hash`) is read from the snapshot the index was built from. That snapshot is
verified when the index is loaded (`api/state.py::snapshot_records`): an index without it is never served.
Only a snapshot file that disappears after the load is a per-request 500 `API_INTERNAL`.

With `q` (and `mode`), the paper page's highlights (task-087; spec 04 §Endpoints): the query is admitted as
`/search` admits it (`searchable`: the length cap, the parse, the verified-clause cap and charge; then
`check_candidates`), so a `q` this route runs is one `/search` runs, and the spans are
`openproceedings.search.highlight`'s, the ones `/search` gives this paper as a hit. A query that doesn't
match the paper is `matched: false` with empty highlights, not an error.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from openproceedings.api.deps import ServedDep, check_candidates, searchable
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import (
    PAPER_ID,
    PAPER_ID_DOC,
    PAPER_MODE_DOC,
    PAPER_Q_DOC,
    Highlights,
    PaperResponse,
    versions,
)
from openproceedings.api.openapi import BUSY
from openproceedings.diagnostics import DiagnosticCode, InternalError
from openproceedings.ingest.record import is_paper_id
from openproceedings.ingest.snapshot import SnapshotError
from openproceedings.query.parser import Mode
from openproceedings.search import highlight

router = APIRouter(prefix=API_PREFIX)


@router.get("/papers/{id}", response_model=PaperResponse, responses=BUSY)
def get_paper(
    request: Request,
    served: ServedDep,
    id: Annotated[str, Path(pattern=PAPER_ID, description=PAPER_ID_DOC)],
    q: Annotated[str | None, Query(description=PAPER_Q_DOC)] = None,
    mode: Annotated[Mode, Query(description=PAPER_MODE_DOC)] = "native",
) -> PaperResponse:
    """The paper with this id in the served index, as its snapshot holds it (the records loaded with that
    very engine: one bundle, whatever swaps happen meanwhile); with `q`, whether that query matches it and
    its highlights, as `/search` gives them."""
    engine = served.engine
    if q is None and mode != "native":
        raise ApiError(
            DiagnosticCode.API_BAD_PARAM, "`mode` applies to `q`: give `q` too, or leave `mode` out."
        )
    result = searchable(request, q, mode) if q is not None else None  # refused before the index is asked
    # the pattern admits any venue (an open enum); one this code doesn't know is no paper here: 404
    shown = engine.display([id]).get(id) if is_paper_id(id) else None  # read once: highlight reuses it
    if shown is None:
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
    if result is None:
        return PaperResponse(**versions(engine.index_version), paper=record, matched=None, highlights=None)
    assert result.effective_ast is not None  # searchable refuses a query that doesn't parse
    check_candidates(request, engine, result.effective_ast)  # 422 API_QUERY_TOO_COSTLY, as /search
    spans = highlight(engine, result, shown)
    return PaperResponse(
        **versions(engine.index_version),
        paper=record,
        matched=spans is not None,
        highlights=Highlights(title=[], abstract=[])
        if spans is None
        else Highlights(title=spans["title"], abstract=spans["abstract"]),
    )
