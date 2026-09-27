"""`POST /api/v1/records`, `GET /api/v1/records/{id}` and `GET /api/v1/records/{id}/diff` (spec 04 §Search
records; search-records skill).

Transport only: freezing, the store and the replay are `openproceedings.records`, which a future `op record`
(spec 08) calls too. A record is saved from the query re-run here (never the client's counts), on the one
engine this request read; a replay loads the record's pinned index read-only on demand (`IndexState.pinned`).

Every replay is a 200 whose `replay.status` is `reproduced`, `drifted` or `mismatch`. A malformed record id
is 422 `API_BAD_PARAM`; an unknown one 404 `API_RECORD_NOT_FOUND` (the message never repeats it).

The hook for `GET /export?record_id=` (task-036): `require_citable(request, record_id)` returns the stored
record, or raises 409 `API_RECORD_MISMATCH` when its replay is a `mismatch` (and the 422/404 above); it
reads the served engine itself, so it can run before the export streams anything. `replay_status` answers
just the status.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request

from openproceedings.api.deps import EngineDep, annotate, current_engine, searchable
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import (
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
from openproceedings.api.state import IndexState
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.records import (
    RECORDS_FILE,
    PinnedLoader,
    RecordStore,
    Replay,
    SearchRecord,
    Status,
    freeze,
    replay,
    valid_record_id,
)

router = APIRouter(prefix=API_PREFIX)
RECORD_PAGE = "/record/{record_id}"  # the frontend's record page (spec 05 §Pages)


@dataclass(frozen=True)
class Records:
    """What the record routes share, on `app.state.records`."""

    data_dir: Path
    store: RecordStore
    pinned: PinnedLoader  # `IndexState.pinned(v).engine`


def install(app: FastAPI, data_dir: Path, state: IndexState) -> None:
    """Give `app` its record store (`<data_dir>/records.sqlite`, created on the first save) and the
    on-demand loader of pinned indexes (`state.pinned`, the one loader)."""
    app.state.records = Records(
        data_dir, RecordStore(data_dir / RECORDS_FILE), lambda version: state.pinned(version).engine
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


# --- the hook for /export (task-036) ------------------------------------------------------------------
def replay_status(request: Request, record_id: str, engine: TantivyEngine | None = None) -> Status:
    """The replay status of record `record_id` on this instance now (422/404 as the record routes). Pass the
    request's engine (`EngineDep`) if the route has one, so the request never reads the served index twice."""
    served = engine if engine is not None else current_engine(request)
    return _replayed(request, served, _stored(request, record_id)).status


def require_citable(request: Request, record_id: str, engine: TantivyEngine | None = None) -> SearchRecord:
    """The stored record, if its replay isn't a `mismatch`; else 409 `API_RECORD_MISMATCH` (spec 04 §Error
    handling: a set that breaks guarantee 4 is never handed to screening). The mismatch itself is logged
    once, at ERROR, by the replay. Pass the request's engine as for `replay_status`."""
    served = engine if engine is not None else current_engine(request)
    record = _stored(request, record_id)
    if _replayed(request, served, record).status == "mismatch":
        raise ApiError(
            DiagnosticCode.API_RECORD_MISMATCH,
            "This search record no longer reproduces on the index it names (replay mismatch), so it can't be "
            "exported. Do not cite it; the mismatch has been logged for the maintainers.",
        )
    return record


# --- routes -----------------------------------------------------------------------------------------------
@router.post("/records", response_model=RecordCreated, status_code=201)
def create_record(request: Request, engine: EngineDep, body: RecordRequest) -> RecordCreated:
    """Freeze a search as an immutable record: re-run here on the served index, then one INSERT."""
    parsed = searchable(request, body.q, body.mode)
    records = _records(request)
    fields, found = freeze(engine, parsed, body.q, records.data_dir)
    record = records.store.insert(fields, found.ids)
    annotate(request, total=record.total)
    return RecordCreated(
        **versions(engine.index_version),
        record_id=record.record_id,
        url=RECORD_PAGE.format(record_id=record.record_id),
    )


@router.get("/records/{id}", response_model=RecordResponse)
def get_record(request: Request, engine: EngineDep, id: str) -> RecordResponse:
    """The stored record and a replay of it now (HTTP 200 whatever the status)."""
    record = _stored(request, id)
    result = _replayed(request, engine, record)
    found = result.identified
    return RecordResponse(
        **versions(result.engine.index_version),
        record=record,
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
            added=len(result.added),
            removed=len(result.removed),
            membership_identical=result.membership_identical,
        ),
    )


@router.get("/records/{id}/diff", response_model=RecordDiff)
def diff_record(request: Request, engine: EngineDep, id: str) -> RecordDiff:
    """The ids a replay now adds and removes, with titles, and which `index_version` inputs changed. A
    title comes from the index the replay ran on, else the record's pinned index; null if neither holds it."""
    record = _stored(request, id)
    result = _replayed(request, engine, record)
    titles = _titles(request, result, record)
    return RecordDiff(
        **versions(result.engine.index_version),
        record_id=record.record_id,
        status=result.status,
        recorded_index_version=record.index_version,
        changed=_changed(result),
        added=[DiffEntry(id=i, title=titles.get(i)) for i in result.added],
        removed=[DiffEntry(id=i, title=titles.get(i)) for i in result.removed],
        membership_identical=result.membership_identical,
    )


def _changed(result: Replay) -> list[ChangedInput]:
    return [
        ChangedInput(input=c.input, kind=c.kind, recorded=c.recorded, current=c.current)
        for c in result.changed
    ]


def _titles(request: Request, result: Replay, record: SearchRecord) -> dict[str, str]:
    wanted = [*result.added, *result.removed]
    if not wanted:
        return {}
    titles = {i: str(r["title"]) for i, r in result.engine.display(wanted).items()}
    missing = [i for i in result.removed if i not in titles]
    if missing and record.index_version != result.engine.index_version:
        old = _records(request).pinned(record.index_version)
        if old is not None:
            titles.update({i: str(r["title"]) for i, r in old.display(missing).items()})
    return titles
