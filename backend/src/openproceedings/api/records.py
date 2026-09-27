"""`POST /api/v1/records`, `GET /api/v1/records/{id}` and `GET /api/v1/records/{id}/diff` (spec 04 §Search
records; search-records skill).

Transport only: freezing, the store and the replay are `openproceedings.records`, which a future `op record`
(spec 08) calls too. A record is saved from the query re-run here (never the client's counts), on the one
engine this request read; a replay loads the record's pinned index read-only on demand (`IndexState.pinned`,
the one loader).

Every replay is a 200 whose `replay.status` is `reproduced`, `drifted` or `mismatch`. A malformed record id
is 422 `API_BAD_PARAM`; an unknown one 404 `API_RECORD_NOT_FOUND` (the message never repeats it). A save
into a full store is 503 `API_RECORDS_STORE_FULL`. All three routes cost the export weight in the rate
limit (each runs a whole query), and saves from every client together are held to
`ApiConfig.record_saves_burst` at once, refilled at `record_saves_per_hour` (429 `API_RATE_LIMITED` with
`Retry-After` beyond it): the store is append-only, so its growth is bounded in time as well as in bytes.

What `GET /export?record_id=` (task-036) calls: `stored_record(request, record_id)` (the stored record,
ids included; the 422/404 above), then, after pinning the record's index, `refuse_mismatch(request, record,
engine)` (409 `API_RECORD_MISMATCH` when its replay is a `mismatch`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, Query, Request, Response
from fastapi import Path as PathParam

from openproceedings.api.config import ApiConfig
from openproceedings.api.deps import EngineDep, annotate, searchable
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import API_PREFIX, TokenBucket, take_all
from openproceedings.api.models import (
    DEFAULT_LIMIT,
    LIMIT_DOC,
    MAX_LIMIT,
    OFFSET_DOC,
    RECORD_ID,
    RECORD_ID_DOC,
    ChangedInput,
    DiffEntry,
    Excluded,
    RecordCreated,
    RecordDiff,
    RecordRequest,
    RecordResponse,
    ReplayInfo,
    versions,
)
from openproceedings.api.openapi import response_header
from openproceedings.api.state import IndexState
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.records import (
    RECORDS_DIR,
    PinnedLoader,
    RecordStore,
    Replay,
    SearchRecord,
    freeze,
    replay,
    valid_record_id,
)

router = APIRouter(prefix=API_PREFIX)
RECORD_PAGE = "/record/{record_id}"  # the frontend's record page (spec 05 §Pages)
RECORD_RESOURCE = API_PREFIX + "/records/{record_id}"  # the 201's `Location`
RecordId = Annotated[str, PathParam(pattern=RECORD_ID, description=RECORD_ID_DOC)]


@dataclass(frozen=True)
class Records:
    """What the record routes share, on `app.state.records`."""

    data_dir: Path
    store: RecordStore
    pinned: PinnedLoader  # `IndexState.pinned(v).engine`
    saves: TokenBucket  # one bucket, key `*`: every client's saves together


SAVES = "*"  # the save bucket's one key


def install(app: FastAPI, config: ApiConfig, state: IndexState) -> None:
    """Give `app` its record store (`<data_dir>/records/records.sqlite`, created on the first save, with the
    configured size cap and free-space floor) and the on-demand loader of pinned indexes (`state.pinned`)."""
    store = RecordStore(
        config.data_dir / RECORDS_DIR,
        max_bytes=config.records_max_bytes,
        min_free_bytes=config.records_min_free_bytes,
    )
    saves = TokenBucket(config.record_saves_burst, config.record_saves_per_hour / 3600, max_clients=1)
    app.state.records = Records(config.data_dir, store, lambda version: state.pinned(version).engine, saves)


def _save_allowed(records: Records) -> None:
    """Take one save from the instance-wide bucket, or 429 `API_RATE_LIMITED` with `Retry-After`."""
    wait = take_all([(records.saves, SAVES)], 1)
    if wait > 0:
        seconds = max(1, math.ceil(wait))
        raise ApiError(
            DiagnosticCode.API_RATE_LIMITED,
            f"This instance is saving search records as fast as it allows; try again in {seconds} s.",
            headers={"Retry-After": str(seconds)},
        )


def _records(request: Request) -> Records:
    records: Records = request.app.state.records
    return records


def _stored(request: Request, record_id: str) -> SearchRecord:
    if not valid_record_id(record_id):
        raise ApiError(
            DiagnosticCode.API_BAD_PARAM, "A record id is 12 characters from A–Z, a–z, 0–9, `-` and `_`."
        )
    record = _records(request).store.get(record_id)
    if record is None:
        raise ApiError(DiagnosticCode.API_RECORD_NOT_FOUND, "No search record with that id on this instance.")
    return record


def _replayed(request: Request, engine: TantivyEngine, record: SearchRecord) -> Replay:
    records = _records(request)
    result = replay(record, engine, records.pinned, records.data_dir)
    annotate(
        request,
        index_version=result.engine.index_version,
        canonical_hash=record.canonical_hash,
        total=len(result.identified.ids) if result.identified is not None else None,
    )
    return result


# --- what /export?record_id= calls (task-036) ----------------------------------------------------------
def stored_record(request: Request, record_id: str) -> SearchRecord:
    """The stored record, ids included (422 on a malformed id, 404 on an unknown one); no replay."""
    return _stored(request, record_id)


def refuse_mismatch(request: Request, record: SearchRecord, served: TantivyEngine) -> None:
    """409 `API_RECORD_MISMATCH` if `record`'s replay is a `mismatch` (logged by the replay): a set that
    breaks guarantee 4 is never handed to screening (spec 04 §Error handling). `served` is the request's
    `EngineDep` engine, so the request never reads the served index twice."""
    if _replayed(request, served, record).status == "mismatch":
        raise ApiError(
            DiagnosticCode.API_RECORD_MISMATCH,
            "This search record no longer reproduces on the index it names (replay mismatch), so it can't be "
            "exported. Do not cite it; the mismatch has been logged for the maintainers.",
        )


# --- routes -----------------------------------------------------------------------------------------------
@router.post(
    "/records",
    response_model=RecordCreated,
    status_code=201,
    responses={
        201: {
            "headers": {"Location": response_header("The new record's API resource, `/api/v1/records/<id>`")}
        }
    },
)
def create_record(
    request: Request, response: Response, engine: EngineDep, body: RecordRequest
) -> RecordCreated:
    """Freeze a search as an immutable record: re-run here on the served index, then one transaction."""
    parsed = searchable(request, body.q, body.mode)
    records = _records(request)
    _save_allowed(records)  # after the parse (a refused query costs no save), before the query runs
    fields, found = freeze(engine, parsed, body.q, records.data_dir)
    record = records.store.insert(fields, found.ids)
    annotate(request, total=record.total)
    response.headers["Location"] = RECORD_RESOURCE.format(record_id=record.record_id)
    return RecordCreated(
        **versions(engine.index_version),
        record_id=record.record_id,
        page=RECORD_PAGE.format(record_id=record.record_id),
    )


@router.get("/records/{id}", response_model=RecordResponse)
def get_record(
    request: Request,
    engine: EngineDep,
    id: RecordId,
    include: Annotated[
        Literal["ids"] | None, Query(description="`ids` to include the record's sorted id list.")
    ] = None,
) -> RecordResponse:
    """The stored record and a replay of it now (HTTP 200 whatever the status). `ids` is null unless
    `include=ids`; `/export?record_id=` streams the papers themselves."""
    record = _stored(request, id)
    result = _replayed(request, engine, record)
    found = result.identified
    return RecordResponse(
        **versions(result.engine.index_version),
        record=record if include == "ids" else record.model_copy(update={"ids": None}),
        replay=ReplayInfo(
            status=result.status,
            index_version=result.engine.index_version,
            query_version=result.query_version,
            total=len(found.ids) if found is not None else None,
            excluded=Excluded.model_validate(found.excluded) if found is not None else None,
            ids_hash=found.ids_hash if found is not None else None,
            ids_match=result.ids_match,
            excluded_match=result.excluded_match,
            refused=result.refused,
            changed=_changed(result),
            added_total=len(result.added) if result.added is not None else None,
            removed_total=len(result.removed) if result.removed is not None else None,
            membership_identical=result.membership_identical,
        ),
    )


@router.get("/records/{id}/diff", response_model=RecordDiff)
def get_record_diff(
    request: Request,
    engine: EngineDep,
    id: RecordId,
    offset: Annotated[int, Query(ge=0, description=OFFSET_DOC)] = 0,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT, description=LIMIT_DOC)] = DEFAULT_LIMIT,
) -> RecordDiff:
    """The ids a replay now adds and removes, with titles, and which `index_version` inputs changed. Each
    list is paged by `offset`/`limit` (≤ 200, never clamped); `added_total`/`removed_total` are in full. A
    title comes from the index the replay ran on, null if it doesn't hold the paper. A refused replay
    compared nothing: empty lists, null totals."""
    record = _stored(request, id)
    result = _replayed(request, engine, record)
    added = list(result.added[offset : offset + limit]) if result.added is not None else []
    removed = list(result.removed[offset : offset + limit]) if result.removed is not None else []
    wanted = [*added, *removed]
    titles = {i: str(r["title"]) for i, r in result.engine.display(wanted).items()} if wanted else {}
    return RecordDiff(
        **versions(result.engine.index_version),
        record_id=record.record_id,
        status=result.status,
        recorded_index_version=record.index_version,
        refused=result.refused,
        changed=_changed(result),
        offset=offset,
        limit=limit,
        added_total=len(result.added) if result.added is not None else None,
        removed_total=len(result.removed) if result.removed is not None else None,
        added=[DiffEntry(id=i, title=titles.get(i)) for i in added],
        removed=[DiffEntry(id=i, title=titles.get(i)) for i in removed],
        membership_identical=result.membership_identical,
    )


def _changed(result: Replay) -> list[ChangedInput]:
    return [
        ChangedInput(input=c.input, kind=c.kind, recorded=c.recorded, current=c.current)
        for c in result.changed
    ]
