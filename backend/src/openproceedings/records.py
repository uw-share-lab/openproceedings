"""Search records (spec 04 §Search records; search-records skill): freeze a search, store it append-only,
and replay it.

A record is the citable evidence for a PRISMA "records identified" number: the query as typed and as
canonicalised, the three versions and the index's inputs, the crawl dates (and what kind of dates they
are), sources and dedup counts of the snapshot the index was built from, whether its counts are citable as
PRISMA identification numbers (not on a bootstrap corpus), `total`, `excluded`, the interpretation
(expansions, translations, warnings) and the sorted matched ids with `ids_hash`. Written once, never edited.

- `ids_hash` is pinned here and only here: sha256 of the sorted ids joined by `\\n`, no trailing newline.
- `identify` is the one way a record's membership is computed, at save and at replay: `search.run` (what
  `op search` and `GET /search` run, so `total` and `excluded` are theirs) plus the engine's `match_ids`.
- `RecordStore` is `<data_dir>/records/records.sqlite` (its own 0700 directory, since WAL writes beside the
  file). Id lists are content-addressed in `id_sets` (a repeated set costs its body, ~1 KB, not another
  copy). INSERT only: `BEFORE UPDATE`/`BEFORE DELETE` triggers abort, and `BEFORE INSERT` triggers refuse an
  existing key (SQLite's REPLACE deletes without firing DELETE triggers unless `recursive_triggers` is on).
  The triggers stop mistakes, not an operator: they are not a security boundary. A save is refused (503
  `API_RECORDS_STORE_FULL`) above a size cap or below a free-space floor. One connection per call.
- Bodies carry `body_version` and are read back with frozen, tolerant types (a diagnostic's `code` is a
  plain string), so a later change to the live enums never makes an old record unreadable.
- `replay` re-parses the stored `canonical` (never `input`). On the record's own index when this instance
  has it (a loader's engine must *be* that version), else on the served one; `reproduced` / `mismatch`
  when the query version is also the record's, `drifted` otherwise. A mismatch breaks guarantee 4: ERROR
  `API_REPLAY_MISMATCH`, once per record per process (DEBUG after that).

Nothing here logs query text: the record stores it, the logs never do.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import threading
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError, model_validator

from openproceedings.diagnostics import DiagnosticCode, InternalError, OpenProceedingsError
from openproceedings.engine.index import index_version as index_version_of
from openproceedings.engine.protocol import EngineInputError
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query import QUERY_VERSION
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import ParseResult, parse
from openproceedings.search import run
from openproceedings.vocab import BOOTSTRAP_SOURCES, bootstrap_only

log = logging.getLogger(__name__)

RECORD_ID = re.compile(r"[A-Za-z0-9_-]{12}")  # secrets.token_urlsafe(9): 72 random bits, URL-safe
STORE_SCHEMA_VERSION = 1  # the records.sqlite layout; migrations only add columns or tables
BODY_VERSION = 2  # the stored record body's layout (`body_version` in the JSON); v1 bodies still read
RECORDS_DIR = "records"  # under the data directory: the one writable place on the data volume
RECORDS_FILE = "records.sqlite"
ALL_SOURCES = "*"  # `crawl_dates` key of the corpus-wide window (a reserved name no source can take)
VERSION_NAME = re.compile(r"[0-9a-f][0-9a-f-]{0,63}")  # an index directory's name (api/state.VERSION_DIR)
# `index_version`'s inputs, by kind of drift (spec 04: snapshot_hash = corpus drift; the rest = method drift)
INDEX_INPUTS = ("snapshot_hash", "tokenizer_version", "schema_version", "ranking_params")
CORPUS_INPUTS = frozenset({"snapshot_hash"})
Status = Literal["reproduced", "drifted", "mismatch"]


def ids_hash(ids: Iterable[str]) -> str:
    """`sha256("\\n".join(sorted(ids)))`, ids sorted as Python `str` (code points), no trailing newline.
    Membership only: sort, ranking and the semantic layer never enter it. Changing it turns every stored
    record into a mismatch, so it is pinned by known-answer tests."""
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


def new_record_id() -> str:
    return secrets.token_urlsafe(9)


def valid_record_id(value: str) -> bool:
    return RECORD_ID.fullmatch(value) is not None


# --- the record, as stored: frozen and tolerant ----------------------------------------------------------
class _Stored(BaseModel):
    """Stored bodies outlive the code that wrote them: plain types (no live enums), unknown keys ignored."""

    model_config = ConfigDict(frozen=True, extra="ignore")


class RecordExcluded(_Stored):
    """03's exclusion accounting, verbatim: buckets by count (largest first, ties by name), `unknown` last."""

    total: int
    track: dict[str, int]
    status: dict[str, int]


class Dedup(_Stored):
    """Corpus-wide ingest merges from the snapshot manifest (PRISMA-S item 16): a process statement, never a
    removal count of this search. The not-merged counts are the manifest's conflicts by resolution: pairs
    that looked alike but were kept apart (two candidates from one source; a track the proceedings never
    host; two records of one venue-year). The last two are None on a v1 body, which didn't record them."""

    merged: int
    ambiguous_not_merged: int
    track_not_merged: int | None = None
    venue_year_not_merged: int | None = None


class StoredDiagnostic(_Stored):
    """A diagnostic as the record saved it: its code is a string, so a retired code stays readable."""

    code: str
    message: str
    span: tuple[int, int] | None = None


class SearchRecord(_Stored):
    """Every field of spec 04 §Search records, plus `body_version`, `schema_version` and `ranking_params`
    (the index's other two inputs, so a drifted replay can name a method change after the pinned index is
    gone). `ids` is None when the caller didn't ask for them.

    Body version 2 adds `sources` (the snapshot manifest's source names, sorted), `identification_citable`
    (false when every source is a bootstrap one, `vocab.bootstrap_only`: the corpus is an earlier search's
    output, so `total` is not a PRISMA identification number) and `crawl_dates_kind` (per `crawl_dates` key:
    `crawl`, `scholar_query_dates` or `mixed`), and `dedup`'s two other not-merged counts. A v1 body has
    none of them: they read as None ("not recorded"), never as a guess."""

    body_version: int
    record_id: str
    input: str
    mode: str
    canonical: str
    canonical_hash: str
    identification_query: str
    index_version: str
    tokenizer_version: str
    query_version: str
    schema_version: str
    ranking_params: dict[str, JsonValue]
    snapshot_hash: str
    crawl_dates: dict[str, dict[str, str]]  # source → {"from", "to"}; "*" is the corpus-wide window
    searched_at: str  # UTC, ISO 8601 with Z
    total: int
    excluded: RecordExcluded
    expansions: dict[str, list[str]]
    translations: list[StoredDiagnostic]
    warnings: list[StoredDiagnostic]
    ids: list[str] | None = None  # sorted
    ids_hash: str
    dedup: Dedup
    semantic_version: str | None = None  # the near-miss panel (M5); never an input to ids_hash
    sources: list[str] | None = None  # v2: the snapshot manifest's source names, sorted
    identification_citable: bool | None = None  # v2: not bootstrap_only(sources)
    # v2, per crawl_dates key: "crawl" (fetch times, UTC), "scholar_query_dates" (Publish or Perish's query
    # dates: local wall time stored labelled UTC, so an end can be a day off) or "mixed" (`*` over both)
    crawl_dates_kind: dict[str, str] | None = None

    @model_validator(mode="after")
    def _v2_fields(self) -> SearchRecord:
        """A v2 body has every v2 field, and its citability is the one its sources give."""
        if self.body_version >= 2:
            if self.sources is None or self.identification_citable is None or self.crawl_dates_kind is None:
                raise ValueError("a v2 record body names its sources, citability and window kinds")
            if self.identification_citable == bootstrap_only(self.sources):
                raise ValueError("a record's identification_citable contradicts its sources")
            if set(self.crawl_dates_kind) != set(self.crawl_dates):
                raise ValueError("a record's crawl_dates_kind has other keys than its crawl_dates")
        return self


# --- the index and snapshot a record pins -----------------------------------------------------------------
def index_inputs(data_dir: Path, version: str) -> dict[str, Any]:
    """The manifest of index `version` under `<data_dir>/indexes/`: its four inputs, checked to give that
    version, and its snapshot's directory name. An instance that can't show them is broken (500)."""
    try:
        if not VERSION_NAME.fullmatch(version):
            raise ValueError("not an index_version")
        manifest = json.loads((data_dir / "indexes" / version / "manifest.json").read_text(encoding="utf-8"))
        inputs = {k: manifest[k] for k in INDEX_INPUTS}
        if not index_version_of(*(inputs[k] for k in INDEX_INPUTS)) == version == manifest["index_version"]:
            raise ValueError("the manifest's inputs don't give its index_version")
        return {**inputs, "snapshot": manifest["snapshot"]}
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise InternalError(
            DiagnosticCode.API_INTERNAL, "this instance can't read the manifest of an index it serves"
        ) from e


def _window(value: Any) -> dict[str, str]:
    """A crawl window `{"from", "to"}` of ISO 8601 date-times (never "None" or free text)."""
    if not isinstance(value, dict) or set(value) != {"from", "to"}:
        raise ValueError("a crawl window is {from, to}")
    for v in value.values():
        if not isinstance(v, str):
            raise ValueError("a crawl window's ends are ISO 8601 strings")
        datetime.fromisoformat(v)  # ValueError unless ISO 8601
    return {"from": value["from"], "to": value["to"]}


NOT_MERGED = (
    "ambiguous_not_merged",
    "track_not_merged",
    "venue_year_not_merged",
)  # conflicts.csv resolutions
CRAWL = "crawl"  # a window of fetch times (UTC)
SCHOLAR_QUERY_DATES = "scholar_query_dates"  # Publish or Perish's query dates: local time labelled UTC
MIXED = "mixed"  # the corpus-wide window over both kinds


def _kind(sources: Iterable[str]) -> str:
    kinds = {SCHOLAR_QUERY_DATES if s in BOOTSTRAP_SOURCES else CRAWL for s in sources}
    return kinds.pop() if len(kinds) == 1 else MIXED if kinds else CRAWL


@dataclass(frozen=True, slots=True)
class SnapshotFacts:
    """What a record freezes from the snapshot manifest (spec 04 §Search records)."""

    crawl_dates: dict[str, dict[str, str]]
    crawl_dates_kind: dict[str, str]
    sources: list[str]
    identification_citable: bool
    dedup: Dedup


def snapshot_facts(data_dir: Path, inputs: Mapping[str, Any]) -> SnapshotFacts:
    """`crawl_dates` (with each key's kind), `sources`, `identification_citable` and `dedup` from the manifest
    of the snapshot the index was built from (which must name the index's `snapshot_hash`). The manifest's
    corpus-wide window is key `*`; a source entry that carries its own `crawl_window` (the M4 crawlers) adds
    a key of its own. A bootstrap source's window (RIS: when the Scholar searches were run) is
    `scholar_query_dates`, not a crawl; `*` over bootstrap sources alone is too, over both is `mixed`."""
    try:
        name = inputs["snapshot"]
        if not isinstance(name, str) or not name or "/" in name or "\\" in name or name.startswith("."):
            raise ValueError("the index manifest's snapshot is not a directory name")
        manifest = json.loads((data_dir / "snapshots" / name / "manifest.json").read_text(encoding="utf-8"))
        if manifest["snapshot_hash"] != inputs["snapshot_hash"]:
            raise ValueError("the snapshot of that name is not the one the index was built from")
        sources = sorted(manifest.get("sources", {}))
        crawl = {ALL_SOURCES: _window(manifest["crawl_window"])}
        kinds = {ALL_SOURCES: _kind(sources)}
        for source, entry in sorted(manifest.get("sources", {}).items()):
            if source == ALL_SOURCES:
                raise ValueError("a source can't be named `*`")
            if isinstance(entry, dict) and "crawl_window" in entry:
                crawl[source] = _window(entry["crawl_window"])
                kinds[source] = _kind([source])
        conflicts = manifest["conflicts"]
        dedup = Dedup(
            merged=int(manifest["merges"]["total"]),
            **{k: int(conflicts.get(k, 0)) for k in NOT_MERGED},
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise InternalError(
            DiagnosticCode.API_INTERNAL, "this instance doesn't hold the snapshot its index was built from"
        ) from e
    return SnapshotFacts(crawl, kinds, sources, not bootstrap_only(sources), dedup)


# --- membership -------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Identified:
    ids: tuple[str, ...]  # sorted
    ids_hash: str
    excluded: dict[str, Any]  # Excluded.to_json(): the order spec 04 pins
    expansions: dict[str, list[str]]


def identify(engine: TantivyEngine, parsed: ParseResult) -> Identified:
    """The matched set of `parsed` on `engine`, with the `total`, `excluded` and expansions `GET /search`
    reports for it (the same `search.run`), and every matched id. A query that doesn't parse, or that the
    engine refuses (a wildcard over the cap), raises as it would for a search."""
    found = run(engine, parsed, limit=0)  # refuses a query that didn't parse
    if parsed.effective_ast is None:
        raise InternalError(DiagnosticCode.API_INTERNAL, "a search ran on a query that didn't parse")
    ids = tuple(sorted(engine.match_ids(parsed.effective_ast)))
    if len(ids) != found.total:
        raise InternalError(DiagnosticCode.API_INTERNAL, "a query's matched ids and its total disagree")
    return Identified(
        ids=ids,
        ids_hash=ids_hash(ids),
        excluded=found.excluded.to_json(),
        expansions={f"{stem}{op}": list(terms) for (stem, op), terms in sorted(found.expansions.items())},
    )


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def freeze(
    engine: TantivyEngine,
    parsed: ParseResult,
    q: str,
    data_dir: Path,
    *,
    searched_at: str | None = None,
) -> tuple[dict[str, Any], Identified]:
    """Every field of a new record but its id: re-runs the query server-side (never trusting a client's
    counts). `parsed` is `parse(q, mode)` and must have parsed."""
    if parsed.canonical is None or parsed.canonical_hash is None or parsed.identification_query is None:
        raise InternalError(DiagnosticCode.API_INTERNAL, "a record needs a query that parsed")
    inputs = index_inputs(data_dir, engine.index_version)  # the instance's own facts first: no search on a
    if inputs["tokenizer_version"] != TOKENIZER_VERSION:  # broken instance (the engine refuses such an index)
        raise InternalError(DiagnosticCode.API_INTERNAL, "the served index has another tokenizer_version")
    facts = snapshot_facts(data_dir, inputs)
    found = identify(engine, parsed)
    fields: dict[str, Any] = {
        "body_version": BODY_VERSION,
        "input": q,
        "mode": parsed.mode,
        "canonical": parsed.canonical,
        "canonical_hash": parsed.canonical_hash,
        "identification_query": parsed.identification_query,
        "index_version": engine.index_version,
        "tokenizer_version": TOKENIZER_VERSION,
        "query_version": QUERY_VERSION,
        "schema_version": inputs["schema_version"],
        "ranking_params": inputs["ranking_params"],
        "snapshot_hash": inputs["snapshot_hash"],
        "crawl_dates": facts.crawl_dates,
        "crawl_dates_kind": facts.crawl_dates_kind,
        "sources": facts.sources,
        "identification_citable": facts.identification_citable,
        "searched_at": searched_at or utc_now(),
        "total": len(found.ids),
        "excluded": found.excluded,
        "expansions": found.expansions,
        "translations": [d.model_dump(mode="json") for d in parsed.translations],
        "warnings": [d.model_dump(mode="json") for d in parsed.warnings],
        "ids_hash": found.ids_hash,
        "dedup": facts.dedup.model_dump(),
        "semantic_version": None,
    }
    return fields, found


# --- the store --------------------------------------------------------------------------------------------
def _append_only(table: str, key: str) -> list[str]:
    abort = f"SELECT RAISE(ABORT, '{table} is append-only');"
    return [
        f"CREATE TRIGGER IF NOT EXISTS {table}_no_replace BEFORE INSERT ON {table} "
        f"WHEN EXISTS (SELECT 1 FROM {table} WHERE {key} = NEW.{key}) BEGIN {abort} END",
        f"CREATE TRIGGER IF NOT EXISTS {table}_no_update BEFORE UPDATE ON {table} BEGIN {abort} END",
        f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table} BEGIN {abort} END",
    ]


_SCHEMA: tuple[str, ...] = (
    "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL) STRICT",
    "CREATE TABLE IF NOT EXISTS id_sets (ids_hash TEXT PRIMARY KEY NOT NULL, ids BLOB NOT NULL) STRICT",
    "CREATE TABLE IF NOT EXISTS records ("
    " record_id TEXT PRIMARY KEY NOT NULL,"
    " index_version TEXT NOT NULL,"
    " searched_at TEXT NOT NULL,"
    " id_set TEXT NOT NULL REFERENCES id_sets (ids_hash),"
    " body TEXT NOT NULL) STRICT",
    "CREATE INDEX IF NOT EXISTS records_by_index_version ON records (index_version)",
    *_append_only("records", "record_id"),
    *_append_only("id_sets", "ids_hash"),
    "CREATE TRIGGER IF NOT EXISTS schema_version_no_update BEFORE UPDATE ON schema_version "
    "BEGIN SELECT RAISE(ABORT, 'schema_version is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS schema_version_no_delete BEFORE DELETE ON schema_version "
    "BEGIN SELECT RAISE(ABORT, 'schema_version is append-only'); END",
)
_INSERT_TRIES = 5


class RecordStoreFull(OpenProceedingsError):
    """The store is over its size cap, or its disk under the free-space floor: a save is refused (503)."""


class RecordStore:
    """`<directory>/records.sqlite`, append-only (spec 04 §Search records). `records.body` is the record's
    JSON without `ids`; `records.id_set` names its row in `id_sets`, whose `ids` is the zlib-compressed
    `"\\n"`-joined list keyed by its own `ids_hash` (checked on every read). `index_version` and
    `searched_at` are columns so retention checks (`pinned`) needn't parse bodies."""

    def __init__(self, directory: Path, *, max_bytes: int | None = None, min_free_bytes: int = 0) -> None:
        self.directory = directory
        self.path = directory / RECORDS_FILE
        self.max_bytes = max_bytes
        self.min_free_bytes = min_free_bytes
        self._ready = False
        self._init = threading.Lock()

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            conn = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True, timeout=10)
        else:
            conn = sqlite3.connect(self.path, timeout=10)
        conn.isolation_level = None  # explicit transactions only
        # defence in depth only: the BEFORE INSERT triggers already refuse a REPLACE of an existing key; with
        # this on, a REPLACE issued through this connection would also fire the BEFORE DELETE trigger
        conn.execute("PRAGMA recursive_triggers = ON")
        return conn

    def _ensure(self) -> None:
        with self._init:
            if self._ready and self.path.exists():  # re-created if someone removed the file meanwhile
                return
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(self.directory, 0o700)
            os.close(os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600))
            os.chmod(self.path, 0o600)
            conn = self._connect()
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("BEGIN IMMEDIATE")  # another process initialising the file waits for this one
                try:
                    for statement in _SCHEMA:
                        conn.execute(statement)
                    row = conn.execute("SELECT max(version) FROM schema_version").fetchone()
                    if row[0] is None:
                        conn.execute(
                            "INSERT INTO schema_version (version) VALUES (?)", (STORE_SCHEMA_VERSION,)
                        )
                    elif row[0] > STORE_SCHEMA_VERSION:
                        raise InternalError(
                            DiagnosticCode.API_INTERNAL, "records.sqlite is from a newer openproceedings"
                        )
                    conn.execute("COMMIT")
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
            finally:
                conn.close()
            self._ready = True

    def _used_bytes(self) -> int:
        return sum(p.stat().st_size for p in (self.path, Path(f"{self.path}-wal")) if p.exists())

    def _check_room(self) -> None:
        full = self.max_bytes is not None and self._used_bytes() >= self.max_bytes
        if not full and self.min_free_bytes:
            at = next(p for p in (self.directory, *self.directory.parents) if p.exists())
            full = shutil.disk_usage(at).free < self.min_free_bytes
        if full:
            log.warning(
                "records_store_full",
                extra={
                    "bytes": self._used_bytes(),
                    "max_bytes": self.max_bytes,
                    "min_free_bytes": self.min_free_bytes,
                },
            )
            raise RecordStoreFull(
                DiagnosticCode.API_RECORDS_STORE_FULL,
                "The search-record store on this instance is full, so the record wasn't saved. Your search "
                "still works; try saving again later.",
            )

    def insert(self, fields: Mapping[str, Any], ids: Sequence[str]) -> SearchRecord:
        """Store a new record under a fresh random id (redrawn only when that id is taken), with its id set
        added unless an identical one is already stored. One transaction. `fields["ids_hash"]` must be the
        hash of `ids`: a record that names another set could only ever replay as a mismatch."""
        if any(b <= a for a, b in pairwise(ids)) or any("\n" in i for i in ids):
            raise InternalError(
                DiagnosticCode.API_INTERNAL, "a record's ids must be strictly increasing, one line each"
            )
        key = ids_hash(ids)
        if fields.get("ids_hash") != key:
            raise InternalError(
                DiagnosticCode.API_INTERNAL, "a record's ids_hash must be the hash of its ids"
            )
        self._check_room()  # before the file exists, so an empty store always takes its first record
        self._ensure()
        blob = zlib.compress("\n".join(ids).encode("utf-8"))
        for _ in range(_INSERT_TRIES):
            record = SearchRecord.model_validate({**fields, "record_id": new_record_id(), "ids": list(ids)})
            body = record.model_dump_json(exclude={"ids"})
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    taken = conn.execute(
                        "SELECT 1 FROM records WHERE record_id = ?", (record.record_id,)
                    ).fetchone()
                    if taken is None:
                        conn.execute(
                            "INSERT INTO id_sets (ids_hash, ids) SELECT ?, ? "
                            "WHERE NOT EXISTS (SELECT 1 FROM id_sets WHERE ids_hash = ?)",
                            (key, blob, key),
                        )
                        conn.execute(
                            "INSERT INTO records (record_id, index_version, searched_at, id_set, body) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (record.record_id, record.index_version, record.searched_at, key, body),
                        )
                    conn.execute("COMMIT" if taken is None else "ROLLBACK")
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
            finally:
                conn.close()
            if taken is None:
                return record
        raise InternalError(DiagnosticCode.API_INTERNAL, "could not draw an unused record id")

    def get(self, record_id: str, *, with_ids: bool = True) -> SearchRecord | None:
        """The record with this id (its `ids` None unless `with_ids`), or None (also when no record was ever
        saved: a read never creates the file). A row that doesn't hold a valid record is the instance's
        fault (500)."""
        if not valid_record_id(record_id) or not self.path.exists():
            return None
        conn = self._connect(read_only=True)
        try:
            row = conn.execute(
                "SELECT r.body, r.id_set, s.ids FROM records r JOIN id_sets s ON s.ids_hash = r.id_set "
                "WHERE r.record_id = ?",
                (record_id,),
            ).fetchone()
        except sqlite3.OperationalError as e:  # e.g. the tables aren't there yet
            if "no such table" in str(e):
                return None
            raise
        finally:
            conn.close()
        if row is None:
            return None
        try:
            text = zlib.decompress(row[2]).decode("utf-8")
            ids = text.split("\n") if text else []
            if ids_hash(ids) != row[1]:
                raise ValueError("an id set doesn't hash to its key")
            body = json.loads(row[0])
            if not isinstance(body, dict) or not isinstance(body.get("body_version"), int):
                raise ValueError("a record body without a body_version")
            if body["body_version"] > BODY_VERSION:
                raise ValueError("a record body from a newer openproceedings")
            record = SearchRecord.model_validate({**body, "ids": ids if with_ids else None})
        except (ValueError, ValidationError, zlib.error, TypeError, UnicodeDecodeError) as e:
            raise InternalError(DiagnosticCode.API_INTERNAL, "a stored search record is unreadable") from e
        if record.record_id != record_id:
            raise InternalError(DiagnosticCode.API_INTERNAL, "a stored search record names another id")
        return record

    def pinned(self, index_version: str) -> int:
        """How many records pin `index_version` (check before retiring an index; index-versioning skill)."""
        if not self.path.exists():
            return 0
        conn = self._connect(read_only=True)
        try:
            row = conn.execute(
                "SELECT count(*) FROM records WHERE index_version = ?", (index_version,)
            ).fetchone()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                return 0
            raise
        finally:
            conn.close()
        return int(row[0])


# --- replay -----------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Changed:
    input: str  # snapshot_hash | tokenizer_version | schema_version | ranking_params | query_version
    kind: Literal["corpus", "method"]
    recorded: JsonValue
    current: JsonValue


@dataclass(frozen=True, slots=True)
class Replay:
    status: Status
    engine: TantivyEngine  # the index it ran on
    query_version: str
    identified: Identified | None  # None when the canonical string no longer runs (see `refused`)
    refused: DiagnosticCode | None  # the first error, when the canonical doesn't parse or is refused
    changed: tuple[Changed, ...]  # empty unless drifted
    added: tuple[str, ...] | None  # ids the replay matched that the record doesn't hold; None if refused
    removed: tuple[str, ...] | None  # ids the record holds that the replay didn't match; None if refused
    ids_match: bool
    excluded_match: bool

    @property
    def membership_identical(self) -> bool | None:
        """True on +0/−0, None when no comparison happened (`refused`)."""
        if self.added is None or self.removed is None:
            return None
        return not self.added and not self.removed


type PinnedLoader = Callable[[str], TantivyEngine | None]
MAX_MISMATCHES_REMEMBERED = 10_000
_mismatched: set[str] = set()  # record ids already logged at ERROR by this process
_mismatched_lock = threading.Lock()


def _first_mismatch(record_id: str) -> bool:
    with _mismatched_lock:
        if record_id in _mismatched:
            return False
        if len(_mismatched) >= MAX_MISMATCHES_REMEMBERED:
            _mismatched.clear()
        _mismatched.add(record_id)
        return True


def _run(
    engine: TantivyEngine, canonical: str
) -> tuple[ParseResult, Identified | None, DiagnosticCode | None]:
    parsed = parse(canonical, "native")  # the canonical string is native syntax, translations applied
    if parsed.effective_ast is None:
        return parsed, None, parsed.errors[0].code
    try:
        return parsed, identify(engine, parsed), None
    except EngineInputError as e:
        return parsed, None, e.code


def changed_inputs(
    record: SearchRecord, inputs: Mapping[str, Any], query_version: str
) -> tuple[Changed, ...]:
    """Which of `index_version`'s inputs, and the query version, differ between `record` and what ran."""
    out = [
        Changed(k, "corpus" if k in CORPUS_INPUTS else "method", getattr(record, k), inputs[k])
        for k in INDEX_INPUTS
        if getattr(record, k) != inputs[k]
    ]
    if record.query_version != query_version:
        out.append(Changed("query_version", "method", record.query_version, query_version))
    return tuple(out)


def replay(record: SearchRecord, served: TantivyEngine, pinned: PinnedLoader, data_dir: Path) -> Replay:
    """Re-run `record` (spec 04 §Search records):

    - on the record's own index if this instance has it (the served one, or `pinned`'s engine, which must
      be that very version: any other counts as unavailable); else on the served index;
    - `reproduced` when it ran on its own index under its own query version and `ids_hash`, `excluded` and
      the canonical re-parse all match; `mismatch` when those versions match but something else doesn't
      (ERROR `API_REPLAY_MISMATCH`, once per record per process, then DEBUG);
    - otherwise `drifted`, naming each changed input (only the query version, when its own index is here).
    A canonical that no longer runs (`refused`) compares nothing: `added` and `removed` are None.
    """
    engine = served if served.index_version == record.index_version else pinned(record.index_version)
    if engine is not None and engine.index_version != record.index_version:
        log.warning(
            "pinned_index_wrong_version",
            extra={"index_version": record.index_version, "got": engine.index_version},
        )
        engine = None
    on_own_index = engine is not None
    ran_on = engine if engine is not None else served
    parsed, found, refused = _run(ran_on, record.canonical)
    ids_match = found is not None and found.ids_hash == record.ids_hash
    excluded_match = found is not None and found.excluded == record.excluded.model_dump()
    status: Status
    if on_own_index and record.query_version == QUERY_VERSION:
        changed: tuple[Changed, ...] = ()
        canonical_match = (
            parsed.canonical == record.canonical and parsed.canonical_hash == record.canonical_hash
        )
        # the stored list is the one `ids_hash` names (an export hands over that list, not the replay's)
        stored_match = record.ids is not None and ids_hash(record.ids) == record.ids_hash
        matched = canonical_match and ids_match and excluded_match and stored_match
        status = "reproduced" if matched else "mismatch"
        if status == "mismatch":
            fields = {
                "code": str(DiagnosticCode.API_REPLAY_MISMATCH),
                "record_id": record.record_id,
                "index_version": record.index_version,
                "query_version": record.query_version,
                "ids_match": ids_match,
                "excluded_match": excluded_match,
                "canonical_match": canonical_match,
                "stored_ids_match": stored_match,
                "refused": str(refused) if refused is not None else None,
            }
            if _first_mismatch(record.record_id):
                log.error("replay_mismatch", extra=fields)
            else:
                log.debug("replay_mismatch", extra=fields)
    else:
        changed = changed_inputs(record, index_inputs(data_dir, ran_on.index_version), QUERY_VERSION)
        if not changed:  # a different index_version always has different inputs; anything else is a bug
            raise InternalError(DiagnosticCode.API_INTERNAL, "a drifted replay found no changed input")
        status = "drifted"
    added = removed = None
    if found is not None:
        if record.ids is None:
            raise InternalError(DiagnosticCode.API_INTERNAL, "a replay needs the record's ids")
        now, then = set(found.ids), set(record.ids)
        added, removed = tuple(sorted(now - then)), tuple(sorted(then - now))
    return Replay(
        status=status,
        engine=ran_on,
        query_version=QUERY_VERSION,
        identified=found,
        refused=refused,
        changed=changed,
        added=added,
        removed=removed,
        ids_match=ids_match,
        excluded_match=excluded_match,
    )
