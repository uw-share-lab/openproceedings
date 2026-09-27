"""`POST /api/v1/records`, `GET /api/v1/records/{id}` and `GET /api/v1/records/{id}/diff` (spec 04 §Search
records; search-records skill).

Transport only: freezing, the store and the replay are `openproceedings.records`, which a future `op record`
(spec 08) calls too. A record is saved from the query re-run here (never the client's counts), on the one
engine this request read; a replay loads the record's pinned index read-only on demand (`IndexState.pinned`,
the one loader).

Every replay is a 200 whose `replay.status` is `reproduced`, `drifted` or `mismatch`. A malformed record id
is 422 `API_BAD_PARAM`; an unknown one 404 `API_RECORD_NOT_FOUND` (the message never repeats it). A save
into a full store is 503 `API_RECORDS_STORE_FULL`. All three routes cost the export weight in the rate
limit (each runs a whole query), and a replay's position-verified clauses are charged and capped as a
search's are (`deps.charge_verified`, on the record's re-parsed canonical). Saves are held to two ceilings
(`SaveCeiling`): each client network (IPv4 /24, IPv6 /48) to `ApiConfig.record_saves_network_burst` at once,
refilled at `record_saves_network_per_hour`, and every client together to `record_saves_burst`, refilled at
`record_saves_per_hour` (429 `API_RATE_LIMITED` with `Retry-After` beyond either): the store is
append-only, so its growth is bounded in time as well as in bytes, and one network can't spend the
instance's ceiling for everyone. A save whose query then fails to run (or whose store is full) is refunded.
A ceiling's first refusal logs `record_saves_throttled` (WARNING) and its next allowed save
`record_saves_recovered` (INFO), with `scope` (`instance` or `network`, never the network itself).

What `GET /export?record_id=` (task-036) calls: `stored_record(request, record_id)` (the stored record,
ids included; the 422/404 above), then, after pinning the record's index, `refuse_mismatch(request, record,
engine)` (409 `API_RECORD_MISMATCH` when its replay is a `mismatch`).
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, Query, Request, Response
from fastapi import Path as PathParam

from openproceedings.api.config import ApiConfig
from openproceedings.api.deps import EngineDep, annotate, charge_verified, searchable
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import (
    API_PREFIX,
    Network,
    TokenBucket,
    client_key,
    network_key,
    rate_limited,
    take_each,
)
from openproceedings.api.models import (
    DEFAULT_LIMIT,
    DIFF_LIMIT_DOC,
    DIFF_OFFSET_DOC,
    MAX_LIMIT,
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
from openproceedings.api.openapi import BUSY, response_header
from openproceedings.api.state import IndexState
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.parser import parse
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

log = logging.getLogger(__name__)
router = APIRouter(prefix=API_PREFIX)
RECORD_PAGE = "/record/{record_id}"  # the frontend's record page (spec 05 §Pages)
RECORD_RESOURCE = API_PREFIX + "/records/{record_id}"  # the 201's `Location`
RecordId = Annotated[str, PathParam(pattern=RECORD_ID, description=RECORD_ID_DOC)]


INSTANCE = "*"  # the instance bucket's one key
MAX_THROTTLED_NETWORKS = 10_000  # networks remembered as throttled (for their `recovered` line)


@dataclass
class SaveCeiling:
    """The two save ceilings (module docstring): `instance` (one key, `*`) and `networks` (per client
    network), taken together, so a refusal by one spends nothing from the other."""

    instance: TokenBucket
    networks: TokenBucket
    trusted: tuple[Network, ...]
    limits: dict[str, tuple[int, float]]  # scope -> (burst, per_hour), for the log lines
    _throttled: OrderedDict[str, None] = field(default_factory=OrderedDict)  # INSTANCE or network keys
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def of(cls, config: ApiConfig) -> SaveCeiling:
        return cls(
            TokenBucket(config.record_saves_burst, config.record_saves_per_hour / 3600, max_clients=1),
            TokenBucket(
                config.record_saves_network_burst,
                config.record_saves_network_per_hour / 3600,
                max_clients=config.rate_limit.max_clients,
            ),
            tuple(config.trusted_proxies),
            {
                "instance": (config.record_saves_burst, config.record_saves_per_hour),
                "network": (config.record_saves_network_burst, config.record_saves_network_per_hour),
            },
        )

    def take(self, request: Request) -> str:
        """Take one save from both ceilings: the request's network key (for `refund`), or 429
        `API_RATE_LIMITED` with `Retry-After`, naming the ceiling that refused."""
        network = network_key(client_key(request.scope, self.trusted))
        waits = take_each([(self.instance, INSTANCE), (self.networks, network)], 1)
        with self._lock:  # the throttled/recovered lines: one per change of state
            for scope, key, wait in (("instance", INSTANCE, waits[0]), ("network", network, waits[1])):
                if wait > 0 and key not in self._throttled:
                    self._throttled[key] = None
                    while len(self._throttled) > MAX_THROTTLED_NETWORKS:
                        self._throttled.popitem(last=False)
                    self._log(logging.WARNING, "record_saves_throttled", scope)
                elif max(waits) == 0 and key in self._throttled:
                    del self._throttled[key]
                    self._log(logging.INFO, "record_saves_recovered", scope)
        if max(waits) > 0:
            who = "This instance is" if waits[0] > 0 else "Your network is"
            raise rate_limited(max(waits), f"{who} saving search records as fast as it allows")
        return network

    def refund(self, network: str) -> None:
        """Give back a save that `take` allowed but that saved nothing."""
        self.instance.refund(INSTANCE, 1)
        self.networks.refund(network, 1)

    def _log(self, level: int, event: str, scope: str) -> None:
        burst, per_hour = self.limits[scope]
        log.log(level, event, extra={"scope": scope, "burst": burst, "per_hour": per_hour})


@dataclass(frozen=True)
class Records:
    """What the record routes share, on `app.state.records`."""

    data_dir: Path
    store: RecordStore
    pinned: PinnedLoader  # `IndexState.pinned(v).engine`
    saves: SaveCeiling


def install(app: FastAPI, config: ApiConfig, state: IndexState) -> None:
    """Give `app` its record store (`<data_dir>/records/records.sqlite`, created on the first save, with the
    configured size cap and free-space floor), its save ceilings and the on-demand loader of pinned indexes
    (`state.pinned`)."""
    store = RecordStore(
        config.data_dir / RECORDS_DIR,
        max_bytes=config.records_max_bytes,
        min_free_bytes=config.records_min_free_bytes,
    )
    app.state.records = Records(
        config.data_dir, store, lambda version: state.pinned(version).engine, SaveCeiling.of(config)
    )


def _records(request: Request) -> Records:
    records: Records = request.app.state.records
    return records


def stored_record(request: Request, record_id: str) -> SearchRecord:
    """The stored record, ids included (422 on a malformed id, 404 on an unknown one); no replay. What
    `/export?record_id=` calls first (task-036)."""
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
    # charged and capped like a search's, before the replay compiles anything: the replay runs this very
    # parse of the stored canonical (`records._run`); its refusals, if any, are the replay's to report
    charge_verified(request, parse(record.canonical, "native").effective_ast, located=False)
    result = replay(record, engine, records.pinned, records.data_dir)
    annotate(
        request,
        index_version=result.engine.index_version,
        canonical_hash=record.canonical_hash,
        total=len(result.identified.ids) if result.identified is not None else None,
    )
    return result


# --- what /export?record_id= calls (task-036) ----------------------------------------------------------
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
        },
        **BUSY,
    },
)
def create_record(
    request: Request, response: Response, engine: EngineDep, body: RecordRequest
) -> RecordCreated:
    """Freeze a search as an immutable record: re-run here on the served index, then one transaction."""
    parsed = searchable(request, body.q, body.mode)
    records = _records(request)
    network = records.saves.take(request)  # after the parse (a refused query costs no save), before it runs
    try:
        fields, found = freeze(engine, parsed, body.q, records.data_dir)
        record = records.store.insert(fields, found.ids)
    except BaseException:  # nothing was saved (API_BUSY, a wildcard refusal, a full store): give it back
        records.saves.refund(network)
        raise
    annotate(request, total=record.total)
    response.headers["Location"] = RECORD_RESOURCE.format(record_id=record.record_id)
    return RecordCreated(
        **versions(engine.index_version),
        record_id=record.record_id,
        page=RECORD_PAGE.format(record_id=record.record_id),
    )


@router.get("/records/{id}", response_model=RecordResponse, responses=BUSY)
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
    record = stored_record(request, id)
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


@router.get("/records/{id}/diff", response_model=RecordDiff, responses=BUSY)
def get_record_diff(
    request: Request,
    engine: EngineDep,
    id: RecordId,
    offset: Annotated[int, Query(ge=0, description=DIFF_OFFSET_DOC)] = 0,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT, description=DIFF_LIMIT_DOC)] = DEFAULT_LIMIT,
) -> RecordDiff:
    """The ids a replay now adds and removes, with titles, and which `index_version` inputs changed. Each
    list is paged by `offset`/`limit` (≤ 200, never clamped); `added_total`/`removed_total` are in full. A
    title comes from the index the replay ran on, null if it doesn't hold the paper. A refused replay
    compared nothing: empty lists, null totals."""
    record = stored_record(request, id)
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
