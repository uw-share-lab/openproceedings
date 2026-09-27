"""`GET /api/v1/export`: the entire matched set as RIS, CSV, BibTeX or JSONL, ordered by id, from one index
(spec 04 §Exports; task-036).

Transport only: the bytes are `openproceedings.export`'s `header` and `entries`, the writers `op export`
runs, over `TantivyEngine.documents`, so the body equals `op export`'s output for the same query, index
and UTC date. The export is of `q` (with `mode` and an optional `index_version`) or of a stored search
record (`record_id` alone): exactly the record's stored ids, the set it cites, read from the index it names
(never a re-run query, so a later query_version doesn't change what is handed to screening), its provenance
naming the record and its search date; refused 409
`API_INDEX_VERSION_UNAVAILABLE` when that index isn't here and 409 `API_RECORD_MISMATCH` when the replay is
a mismatch.

Everything that can refuse happens before the first byte: the parameters, the parse (422 with
diagnostics), the record's pin and replay, the pin (409 `API_INDEX_VERSION_UNAVAILABLE`), every wildcard's
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

from openproceedings.api.deps import EngineDep, annotate, check_candidates, searchable
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import MODE_DOC, Q_DOC, VERSION_PARAM
from openproceedings.api.openapi import BUSY, response_header
from openproceedings.api.records import refuse_mismatch, stored_record
from openproceedings.api.state import IndexState
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.protocol import EngineInternalError
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.export import Provenance, check_count, entries, header, utc_date
from openproceedings.query import QUERY_VERSION
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import Mode
from openproceedings.records import RECORD_ID, ids_hash
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
            "description": "The entire matched set, ordered by id.",
            "content": {media.split(";")[0]: {} for media, _ext in MEDIA.values()},
            "headers": {
                "X-Total": response_header(
                    "How many records the body holds: `/search`'s `total` for the same query and index (for "
                    "a search record, the number of its stored ids, which its `total` must equal: 409 "
                    "`API_RECORD_MISMATCH` otherwise)",
                    {"type": "integer", "minimum": 0},
                ),
                "X-Index-Version": response_header("The index the records were read from"),
                "X-Tokenizer-Version": response_header("This code's tokenizer_version"),
                "X-Query-Version": response_header(
                    "This code's query_version (on a `record_id` export too, whatever the record's own)"
                ),
                "Content-Disposition": response_header(
                    'attachment; filename="openproceedings-<index_version>-<first 12 of canonical_hash>.<ext>"'
                ),
            },
        },
        **BUSY,
    },
)
def export(
    request: Request,
    served: EngineDep,
    fmt: Annotated[ExportFormat, Query(alias="format", description="The file format.")],
    q: Annotated[str | None, Query(description=Q_DOC + " Required unless `record_id` is given.")] = None,
    mode: Annotated[
        Mode,
        Query(
            description=MODE_DOC + " With `record_id`, only `native` (a record's canonical string is native "
            "syntax); `scholar` there is 422 `API_BAD_PARAM`."
        ),
    ] = "native",
    index_version: Annotated[
        str | None,
        Query(
            pattern=VERSION_PARAM,
            description="Export from this index (409 `API_INDEX_VERSION_UNAVAILABLE` if this instance can't "
            "serve it); the served one if absent. Only with `q`.",
        ),
    ] = None,
    record_id: Annotated[
        str | None,
        Query(
            pattern=RECORD_PARAM,
            description="Export exactly this search record's stored ids, from the index it names. Not with "
            "`q` or `index_version`; `mode`, if sent, must be `native`.",
        ),
    ] = None,
) -> StreamingResponse:
    """Every record the query matches, in `format`: of `q` (with `mode`, default `native`) on the pinned
    `index_version` (else the served index), or the stored ids of search record `record_id` (alone) from the
    index it names. Never paginated or truncated; `X-Total` equals `/search`'s `total` for the same query and
    index (for a record, its stored `total`)."""
    if record_id is not None:
        # `mode=native` (the declared default) is accepted: a record replays its canonical string natively
        if q is not None or index_version is not None:
            raise _bad("Pass either q (with mode and index_version) or record_id, not both.")
        if mode != "native":
            raise _bad(
                "With record_id, mode may only be native (a record's canonical string is native syntax)."
            )
        record = stored_record(request, record_id)  # 422, 404
        engine = pinned_engine(request, served, record.index_version)  # 409 unless its own index is here
        refuse_mismatch(request, record, served)  # 409 on a mismatch replay (it runs on that same index)
        ids = record.ids
        # the replay refuses these too; never stream them (X-Total is the list's length, its `total`)
        if ids is None or ids_hash(ids) != record.ids_hash or record.total != len(ids):
            raise ApiError(
                DiagnosticCode.API_RECORD_MISMATCH, "This search record's stored ids don't match it."
            )
        # the cited set exactly: the record's stored ids, from the index it names (never a re-run query)
        canonical_hash = record.canonical_hash
        total, documents = len(ids), stored_documents(engine, ids)
        pinned_by = {"record_id": record.record_id, "searched_at": record.searched_at}  # in the provenance
        annotate(request, canonical_hash=canonical_hash)
    else:
        if q is None:
            raise _bad("Pass q (the query to export) or record_id (a saved search record).")
        result = searchable(request, q, mode)
        engine = pinned_engine(request, served, index_version)
        ast = result.effective_ast
        if ast is None or result.canonical_hash is None:  # searchable refuses a query that didn't parse
            raise EngineInternalError(
                DiagnosticCode.API_INTERNAL, "an export ran on a query that didn't parse"
            )
        canonical_hash = result.canonical_hash
        pinned_by = {}
        expanded(engine, ast)  # an over-cap wildcard is a located 422 before anything is compiled
        check_candidates(request, engine, ast)  # 422 API_QUERY_TOO_COSTLY before any verification
        total, documents = engine.documents(ast)  # the one collection; records are read as they stream
    annotate(request, total=total)
    provenance = Provenance(engine.index_version, canonical_hash, utc_date(), **pinned_by)
    media, ext = MEDIA[fmt]
    filename = f"openproceedings-{engine.index_version}-{canonical_hash[:12]}.{ext}"
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


STORED_CHUNK = 1_000  # stored ids read per index lookup while a record's export streams


def stored_documents(engine: TantivyEngine, ids: list[str]) -> Iterator[dict[str, Any]]:
    """The display record of each of `ids` (sorted), in that order, read from `engine` a chunk at a time. An
    id the index doesn't hold ends the stream short, which `_body`'s count against `X-Total` turns into a
    logged failure (never a silently smaller file)."""
    for start in range(0, len(ids), STORED_CHUNK):
        chunk = ids[start : start + STORED_CHUNK]
        shown = engine.display(chunk)
        for i in chunk:
            if i not in shown:
                return
            yield shown[i]


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
    check_count(n, total)
