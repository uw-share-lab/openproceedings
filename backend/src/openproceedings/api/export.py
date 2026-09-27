"""`GET /api/v1/export`: the entire matched set as RIS, CSV, BibTeX or JSONL, ordered by id, from one index
(spec 04 §Exports; task-036).

Transport only: the bytes are `openproceedings.export`'s `header` and `entries`, the writers `op export`
runs, over `TantivyEngine.documents`, so the body equals `op export`'s output for the same query, index
and UTC date. The export is of `q` (with `mode` and an optional `index_version`) or of a stored search
record (`record_id` alone: its canonical query on its index_version, refused 409 `API_RECORD_MISMATCH` if
its replay is a mismatch).

Everything that can refuse happens before the first byte: the parameters, the parse (422 with
diagnostics), the record's replay, the pin (409 `API_INDEX_VERSION_UNAVAILABLE`), every wildcard's
expansion (422, located) and the one collection of the match set that gives `X-Total`. Then a sync
generator streams the records from the engine the request took, so an export started before a hot swap
finishes on its index. A failure after the first byte is logged by `LastCatch` and marks the access line
`aborted` (the client has its 200 by then); a stream that wrote fewer or more records than `X-Total` fails
the same way, never silently.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from openproceedings.api.deps import EngineDep, annotate, searchable
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.records import require_citable
from openproceedings.api.state import VERSION_DIR, IndexState
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.protocol import EngineInternalError
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.export import Provenance, entries, header, utc_date
from openproceedings.query import QUERY_VERSION
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import Mode
from openproceedings.records import RECORD_ID
from openproceedings.search import expanded

router = APIRouter(prefix=API_PREFIX)

ExportFormat = Literal["ris", "csv", "bibtex", "jsonl"]  # export.FORMATS (a test pins them equal)
# media type and file extension per format (the filename is `openproceedings-<index_version>-<hash12>.<ext>`)
MEDIA: dict[str, tuple[str, str]] = {
    "ris": ("application/x-research-info-systems; charset=utf-8", "ris"),
    "csv": ("text/csv; charset=utf-8", "csv"),
    "bibtex": ("application/x-bibtex; charset=utf-8", "bib"),
    "jsonl": ("application/x-ndjson; charset=utf-8", "jsonl"),
}
CHUNK = 64 * 1024  # characters per body chunk (64 Ki): whole records, never split or reordered
VERSION_PARAM = f"^(?:{VERSION_DIR.pattern})$"
RECORD_PARAM = f"^(?:{RECORD_ID.pattern})$"


def pinned_engine(request: Request, served: TantivyEngine, index_version: str | None) -> TantivyEngine:
    """The engine an export reads: `index_version`'s if one is pinned (409 `API_INDEX_VERSION_UNAVAILABLE`
    when this instance can't serve it: absent, unloadable or tampered with), else the served one this
    request took."""
    if index_version is None or index_version == served.index_version:
        return served
    state: IndexState = request.app.state.index
    pinned = state.pinned(index_version)
    if pinned.engine is None:
        raise ApiError(
            DiagnosticCode.API_INDEX_VERSION_UNAVAILABLE,
            "That index_version is not available on this instance; GET /api/v1/meta lists the ones that are.",
        )
    annotate(request, index_version=pinned.engine.index_version)
    return pinned.engine


def _bad(message: str) -> ApiError:
    return ApiError(DiagnosticCode.API_BAD_PARAM, message)


@router.get(
    "/export",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "The entire matched set, ordered by id, with `X-Total`, `X-Index-Version`, "
            "`X-Tokenizer-Version` and `X-Query-Version`.",
            "content": {media.split(";")[0]: {} for media, _ext in MEDIA.values()},
        }
    },
)
def export(
    request: Request,
    served: EngineDep,
    fmt: Annotated[ExportFormat, Query(alias="format")],
    q: str | None = None,
    mode: Mode | None = None,
    index_version: Annotated[str | None, Query(pattern=VERSION_PARAM)] = None,
    record_id: Annotated[str | None, Query(pattern=RECORD_PARAM)] = None,
) -> StreamingResponse:
    """Every record the query matches, in `format`: of `q` (with `mode`, default `native`) on the pinned
    `index_version` (else the served index), or of the stored search record `record_id` (alone: its query,
    mode and index_version). Never paginated or truncated; `X-Total` equals `/search`'s `total` for the same
    query and index."""
    if record_id is not None:
        if q is not None or mode is not None or index_version is not None:
            raise _bad("Pass either q (with mode and index_version) or record_id alone, not both.")
        record = require_citable(request, record_id, served)  # 404, or 409 on a mismatch replay
        # the record's canonical string, native syntax (what its replay runs), on the index it names
        result = searchable(request, record.canonical, "native")
        engine = pinned_engine(request, served, record.index_version)
    else:
        if q is None:
            raise _bad("Pass q (the query to export) or record_id (a saved search record).")
        result = searchable(request, q, mode or "native")
        engine = pinned_engine(request, served, index_version)
    ast = result.effective_ast
    assert ast is not None and result.canonical_hash is not None  # it parsed
    expanded(engine, ast)  # an over-cap wildcard is a located 422 before anything is compiled
    total, documents = engine.documents(ast)  # the one collection; records are read as they stream
    annotate(request, total=total)
    provenance = Provenance(engine.index_version, result.canonical_hash, utc_date())
    media, ext = MEDIA[fmt]
    filename = f"openproceedings-{engine.index_version}-{result.canonical_hash[:12]}.{ext}"
    return StreamingResponse(
        _body(fmt, documents, provenance, total),
        media_type=media,
        headers={
            "X-Total": str(total),
            "X-Index-Version": engine.index_version,
            "X-Tokenizer-Version": TOKENIZER_VERSION,
            "X-Query-Version": QUERY_VERSION,
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


def _body(
    fmt: str, documents: Iterator[dict[str, Any]], provenance: Provenance, total: int
) -> Iterator[bytes]:
    """`header(fmt)` then every entry, UTF-8, in chunks of at most `CHUNK` characters plus one entry;
    counted against `total` at the end (a shortfall or an excess raises, after the last byte it has)."""
    first = header(fmt)
    parts, size, n = [first], len(first), 0
    for entry in entries(fmt, documents, provenance):
        n += 1
        parts.append(entry)
        size += len(entry)
        if size >= CHUNK:
            yield "".join(parts).encode("utf-8")
            parts, size = [], 0
    if parts:
        yield "".join(parts).encode("utf-8")
    if n != total:
        raise EngineInternalError(DiagnosticCode.API_INTERNAL, f"exported {n} records, but {total} match")
