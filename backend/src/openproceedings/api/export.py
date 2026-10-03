"""`GET /api/v1/export`: the entire matched set as RIS, CSV, BibTeX or JSONL, ordered by id, from one index
(spec 04 §Exports; task-036).

Transport only: the bytes are `openproceedings.export`'s `header` and `entries`, the writers `op export`
runs, over `TantivyEngine.documents`, so the body equals `op export`'s output for the same query, index
and UTC date. The export is of `q` (with `mode` and an optional `index_version`) or of a stored search
record (`record_id` alone): exactly the record's stored ids, the set it cites, read from the index it names
(never a re-run query, so a later query_version doesn't change what is handed to screening), its provenance
naming the record and its search date; refused 409
`API_INDEX_VERSION_UNAVAILABLE` when that index isn't here and 409 `API_RECORD_MISMATCH` when the replay is
a mismatch. Each record names its abstract's source (decision-018, TASK-138) from the exported index's
snapshot records, computed when they were loaded (`RecordFile.attributions`, what `GET /search` sends as
`abstract_source`): the served bundle's, or a pinned index's (`IndexState.pinned_records`). When a pinned
index's snapshot can't be verified the same records are exported with every abstract withheld and marked so
in the file, and `X-Abstract-Source: unavailable` (decision-021): never an abstract without attribution.
Whatever index is exported, each record the takedown list names (as the served bundle's load read it), or that
index's snapshot withheld, goes out without its abstract, marked so (TASK-136, decision-022; `Served.withheld_in`),
and `X-Abstracts-Withheld` counts them before the body: for a record export, its stored ids on the list or
withheld by that index's snapshot; for a query, those of them the index holds that the query matches (`search.highlight`, the evaluation `/papers?q=`
uses, one per listed id: the list is short).

Everything that can refuse happens before the first byte: the parameters, the parse (422 with
diagnostics), the record's pin and replay, the pin (409 `API_INDEX_VERSION_UNAVAILABLE`), every wildcard's
expansion (422, located) and the one collection of the match set that gives `X-Total`. The exported index's
attributions are read before the first byte too, but never refuse: an unverifiable snapshot withholds. Then a sync
generator streams the records from the engine the request took, so an export started before a hot swap
finishes on its index. A failure after the first byte is logged by `LastCatch` and marks the access line
`aborted` (the client has its 200 by then); a stream that wrote fewer or more records than `X-Total` fails
the same way, never silently.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any, Literal, get_args

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from openproceedings.api.deps import AbstractSource, ServedDep, annotate, check_candidates, searchable
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import MODE_DOC, Q_DOC, VERSION_PARAM
from openproceedings.api.openapi import BUSY, response_header
from openproceedings.api.records import refuse_mismatch, stored_record
from openproceedings.api.state import IndexState, Served
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.highlight import Highlighter
from openproceedings.engine.protocol import EngineInternalError
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.export import Provenance, Sources, Twins, check_count, entries, header, utc_date
from openproceedings.query import QUERY_VERSION
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import Mode, ParseResult
from openproceedings.records import RECORD_ID, ids_hash
from openproceedings.search import Shown, expanded
from openproceedings.takedowns import NONE, Withheld

HEX = frozenset("0123456789abcdef")  # all a download name takes of a canonical_hash
router = APIRouter(prefix=API_PREFIX)

ExportFormat = Literal["ris", "csv", "bibtex", "jsonl"]  # export.FORMATS (a test pins them equal)
# media type and file extension per format (the filename is `openproceedings-<index_version>-<hash12>.<ext>`)
MEDIA: dict[str, tuple[str, str]] = {
    "ris": ("application/x-research-info-systems; charset=utf-8", "ris"),
    "csv": ("text/csv; charset=utf-8", "csv"),
    "bibtex": ("application/x-bibtex; charset=utf-8", "bib"),
    "jsonl": ("application/x-ndjson; charset=utf-8", "jsonl"),
}
# the `X-Abstract-Source` values, also the access line's `abstract_source` (decision-021)
ABSTRACT_SOURCE_STATES: tuple[AbstractSource, ...] = get_args(AbstractSource.__value__)
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


def sources_of(
    request: Request, served: Served, engine: TantivyEngine
) -> tuple[Sources | None, Withheld, Twins | None]:
    """Each record's abstract attribution in `engine`'s snapshot: the served bundle's when `engine` is the
    served one, else the pinned index's; None when that snapshot can't be verified, and the export then
    withholds every abstract (decision-021: an abstract never goes out without attribution, decision-018).
    With it, the ids whose abstracts a takedown withholds (TASK-136): the bundle's list, whatever index is
    exported, plus the ids that index's snapshot withheld. And each record's twins (TASK-162), from the same
    snapshot (None when it can't be verified: no twins are named)."""
    if engine is served.engine:
        return served.records.attributions, served.withheld_in(served.records), served.records.twins
    state: IndexState = request.app.state.index
    records = state.pinned_records(engine.index_version)
    if records is None:
        return None, served.withheld_in(None), None
    return records.attributions, served.withheld_in(records), records.twins


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
                    'attachment; filename="openproceedings-<index_version>-<the hex of the first 12 of canonical_hash>.<ext>"'
                ),
                "X-Abstract-Source": response_header(
                    "`attributed`: each abstract names its source (decision-018). `unavailable`: the exported "
                    "index's snapshot can't be verified on this instance, so every abstract is withheld and each "
                    "record says so (decision-021)",
                    {"type": "string", "enum": list(ABSTRACT_SOURCE_STATES)},
                ),
                "X-Abstracts-Withheld": response_header(
                    "How many records of the body have their abstract withheld at a rights holder's request (a "
                    "takedown, decision-022): each says so in the file; 0 when none",
                    {"type": "integer", "minimum": 0},
                ),
            },
        },
        **BUSY,
    },
)
def export(
    request: Request,
    bundle: ServedDep,
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
    index (for a record, its stored `total`). Each record names its abstract's source (decision-018), from the
    exported index's snapshot; for a pinned index whose snapshot this instance can't verify, the same records
    with every abstract withheld and `X-Abstract-Source: unavailable` (decision-021)."""
    served = bundle.engine  # the request's one read of the served index (its records are `bundle.records`)
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
        sources, withheld, twins = sources_of(
            request, bundle, engine
        )  # once nothing about the record can refuse
        # the cited set exactly: the record's stored ids, from the index it names (never a re-run query)
        canonical_hash = record.canonical_hash
        total, documents = len(ids), stored_documents(engine, ids)
        removed = sum(i in withheld for i in ids)
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
        sources, withheld, twins = sources_of(
            request, bundle, engine
        )  # once nothing about the query can refuse
        total, documents = engine.documents(ast)  # the one collection; records are read as they stream
        removed = matched_among(engine, result, withheld)
    abstract_source: AbstractSource = "unavailable" if sources is None else "attributed"
    annotate(request, total=total, abstract_source=abstract_source, abstracts_withheld=removed)
    provenance = Provenance(engine.index_version, canonical_hash, utc_date(), **pinned_by)
    media, ext = MEDIA[fmt]
    name = filename(engine.index_version, canonical_hash, ext)
    return StreamingResponse(
        _body(fmt, documents, provenance, total, sources, withheld, twins),
        media_type=media,
        headers={
            "X-Total": str(total),
            "X-Index-Version": engine.index_version,
            "X-Tokenizer-Version": TOKENIZER_VERSION,
            "X-Query-Version": QUERY_VERSION,
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Abstract-Source": abstract_source,
            "X-Abstracts-Withheld": str(removed),
        },
    )


def matched_among(engine: TantivyEngine, result: ParseResult, withheld: Withheld) -> int:
    """How many of `withheld` the query `result` matches on `engine`: each listed id the index holds, judged
    as `/papers/{id}?q=` judges it (`search.highlight`: the `Highlighter` over its display record, with the
    query's expansions computed once), so the count is the number of records in the body a takedown
    withholds."""
    shown = engine.display(sorted(withheld)) if withheld else {}
    if not shown:
        return 0
    if (
        result.effective_ast is None
    ):  # the caller's query parsed: an invariant, as `search.highlight` holds it
        raise EngineInternalError(
            DiagnosticCode.API_INTERNAL, "an export counted withheld records of no query"
        )
    lit = Highlighter(result.effective_ast, expanded(engine, result.effective_ast))
    return sum(lit.match(Shown.of(record)) is not None for record in shown.values())


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


def filename(index_version: str, canonical_hash: str, ext: str) -> str:
    """The export's download name: its index_version (a route-checked hex name) and the first 12 hex digits of
    its canonical_hash. A record's stored hash is only ever server-written hex, but only hex reaches the
    Content-Disposition header, whatever the store holds (TASK-067)."""
    return f"openproceedings-{index_version}-{''.join(c for c in canonical_hash[:12] if c in HEX)}.{ext}"


def _body(
    fmt: str,
    documents: Iterator[dict[str, Any]],
    provenance: Provenance,
    total: int,
    sources: Sources | None,
    withheld: Withheld = NONE,
    twins: Twins | None = None,
) -> Iterator[bytes]:
    """`header(fmt)` then every entry, UTF-8, in chunks of at most `CHUNK` characters plus one entry;
    counted against `total` at the end (a shortfall or an excess raises, after the last byte it has)."""
    first = header(fmt)
    parts, size, n = [first], len(first), 0
    for entry in entries(fmt, documents, provenance, sources=sources, withheld=withheld, twins=twins):
        n += 1
        parts.append(entry)
        size += len(entry)
        if size >= CHUNK:
            yield "".join(parts).encode("utf-8")
            parts, size = [], 0
    if parts:
        yield "".join(parts).encode("utf-8")
    check_count(n, total)
