"""Search records (spec 04 §Search records; search-records skill): freeze a search, store it append-only,
and replay it.

A record is the citable evidence for a PRISMA "records identified" number: the query as typed and as
canonicalised, the three versions and the index's inputs, the crawl dates and dedup counts of the snapshot
the index was built from, `total`, `excluded`, the interpretation (expansions, translations, warnings) and
the sorted matched ids with `ids_hash`. Written once, never edited.

- `ids_hash` is pinned here and only here: sha256 of the sorted ids joined by `\\n`, no trailing newline.
- `identify` is the one way a record's membership is computed, at save and at replay: `search.run` (what
  `op search` and `GET /search` run, so `total` and `excluded` are theirs) plus the engine's `match_ids`.
- `RecordStore` is `<data_dir>/records.sqlite`: INSERT only. `BEFORE UPDATE`/`BEFORE DELETE` triggers abort,
  a `BEFORE INSERT` trigger refuses an existing id (so `INSERT OR REPLACE` can't delete-then-insert, from any
  client), every app connection also turns on `recursive_triggers` (belt and braces), and
  no code path here issues anything but CREATE ... IF NOT EXISTS, INSERT and SELECT. One connection per
  call, so it is safe from the API's thread pool.
- `replay` re-parses the stored `canonical` (never `input`), runs it on the pinned index when that index and
  the record's `query_version` are both available here, and reports `reproduced`, `drifted` or `mismatch`
  (all HTTP 200). A mismatch breaks guarantee 4: it is logged once at ERROR, code `API_REPLAY_MISMATCH`.

Nothing here logs query text: the record stores it, the logs never do.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import sqlite3
import threading
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, JsonValue

from openproceedings.diagnostics import Diagnostic, DiagnosticCode, InternalError
from openproceedings.engine.index import index_version as index_version_of
from openproceedings.engine.protocol import EngineInputError
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query import QUERY_VERSION
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import Mode, ParseResult, parse
from openproceedings.search import run

log = logging.getLogger(__name__)

RECORD_ID = re.compile(r"[A-Za-z0-9_-]{12}")  # secrets.token_urlsafe(9): 72 random bits, URL-safe
STORE_SCHEMA_VERSION = 1  # the records.sqlite layout; migrations only add columns or tables
RECORDS_FILE = "records.sqlite"
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


# --- the record -------------------------------------------------------------------------------------------
class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RecordExcluded(_Model):
    """03's exclusion accounting, verbatim: buckets by count (largest first, ties by name), `unknown` last."""

    total: int
    track: dict[str, int]
    status: dict[str, int]


class Dedup(_Model):
    """Corpus-wide ingest merges from the snapshot manifest (PRISMA-S item 16): a process statement, never a
    removal count of this search."""

    merged: int
    ambiguous_not_merged: int


class SearchRecord(_Model):
    """Every field of spec 04 §Search records, plus `schema_version` and `ranking_params` (the index's other
    two inputs), so a drifted replay can name a method change even after the pinned index is gone."""

    record_id: str
    input: str
    mode: Mode
    canonical: str
    canonical_hash: str
    identification_query: str
    index_version: str
    tokenizer_version: str
    query_version: str
    schema_version: str
    ranking_params: dict[str, JsonValue]
    snapshot_hash: str
    crawl_dates: dict[str, dict[str, str]]  # source → {"from", "to"}; "all" is the corpus-wide window
    searched_at: str  # UTC, ISO 8601 with Z
    total: int
    excluded: RecordExcluded
    expansions: dict[str, list[str]]
    translations: list[Diagnostic]
    warnings: list[Diagnostic]
    ids: list[str]  # sorted
    ids_hash: str
    dedup: Dedup
    semantic_version: str | None = None  # the near-miss panel (M5); never an input to ids_hash


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


def snapshot_facts(data_dir: Path, inputs: Mapping[str, Any]) -> tuple[dict[str, dict[str, str]], Dedup]:
    """`crawl_dates` and `dedup` from the manifest of the snapshot the index was built from (which must
    name the index's `snapshot_hash`). The manifest has one corpus-wide crawl window (`all`); a source entry
    that carries its own `crawl_window` (the M4 crawlers) adds a key of its own."""
    try:
        name = inputs["snapshot"]
        if not isinstance(name, str) or not name or "/" in name or "\\" in name or name.startswith("."):
            raise ValueError("the index manifest's snapshot is not a directory name")
        manifest = json.loads((data_dir / "snapshots" / name / "manifest.json").read_text(encoding="utf-8"))
        if manifest["snapshot_hash"] != inputs["snapshot_hash"]:
            raise ValueError("the snapshot of that name is not the one the index was built from")
        window = manifest["crawl_window"]
        crawl = {"all": {"from": str(window["from"]), "to": str(window["to"])}}
        for source, entry in sorted(manifest.get("sources", {}).items()):
            own = entry.get("crawl_window") if isinstance(entry, dict) else None
            if isinstance(own, dict):
                crawl[source] = {"from": str(own["from"]), "to": str(own["to"])}
        dedup = Dedup(
            merged=int(manifest["merges"]["total"]),
            ambiguous_not_merged=int(manifest["conflicts"].get("ambiguous_not_merged", 0)),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise InternalError(
            DiagnosticCode.API_INTERNAL, "this instance doesn't hold the snapshot its index was built from"
        ) from e
    return crawl, dedup


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
    found = run(engine, parsed, limit=0)
    assert parsed.effective_ast is not None  # run refuses one that didn't parse
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
    assert parsed.canonical is not None and parsed.canonical_hash is not None
    assert parsed.identification_query is not None
    found = identify(engine, parsed)
    inputs = index_inputs(data_dir, engine.index_version)
    crawl, dedup = snapshot_facts(data_dir, inputs)
    if inputs["tokenizer_version"] != TOKENIZER_VERSION:  # the engine refuses to open such an index
        raise InternalError(DiagnosticCode.API_INTERNAL, "the served index has another tokenizer_version")
    fields: dict[str, Any] = {
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
        "crawl_dates": crawl,
        "searched_at": searched_at or utc_now(),
        "total": len(found.ids),
        "excluded": found.excluded,
        "expansions": found.expansions,
        "translations": [d.model_dump(mode="json") for d in parsed.translations],
        "warnings": [d.model_dump(mode="json") for d in parsed.warnings],
        "ids_hash": found.ids_hash,
        "dedup": dedup.model_dump(),
        "semantic_version": None,
    }
    return fields, found


# --- the store --------------------------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS records (
    record_id TEXT PRIMARY KEY NOT NULL,
    index_version TEXT NOT NULL,
    searched_at TEXT NOT NULL,
    body TEXT NOT NULL,
    ids BLOB NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS records_by_index_version ON records (index_version);
CREATE TRIGGER IF NOT EXISTS records_no_replace BEFORE INSERT ON records
    WHEN EXISTS (SELECT 1 FROM records WHERE record_id = NEW.record_id)
    BEGIN SELECT RAISE(ABORT, 'search records are append-only'); END;
CREATE TRIGGER IF NOT EXISTS records_no_update BEFORE UPDATE ON records
    BEGIN SELECT RAISE(ABORT, 'search records are append-only'); END;
CREATE TRIGGER IF NOT EXISTS records_no_delete BEFORE DELETE ON records
    BEGIN SELECT RAISE(ABORT, 'search records are append-only'); END;
CREATE TRIGGER IF NOT EXISTS schema_version_no_update BEFORE UPDATE ON schema_version
    BEGIN SELECT RAISE(ABORT, 'schema_version is append-only'); END;
CREATE TRIGGER IF NOT EXISTS schema_version_no_delete BEFORE DELETE ON schema_version
    BEGIN SELECT RAISE(ABORT, 'schema_version is append-only'); END;
"""
_INSERT_TRIES = 5


class RecordStore:
    """`records.sqlite`: append-only (spec 04 §Search records). `body` is the record's JSON without `ids`;
    `ids` is zlib-compressed `"\\n".join(ids)` (the diff needs the list, not only its hash); `index_version`
    and `searched_at` are columns so retention checks (`pinned`) needn't parse bodies."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._ready = False
        self._init = threading.Lock()

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            conn = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True, timeout=10)
        else:
            conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA recursive_triggers = ON")  # INSERT OR REPLACE's implicit delete hits the trigger
        return conn

    def _ensure(self) -> None:
        with self._init:
            if self._ready:
                return
            conn = self._connect()
            conn.isolation_level = None  # explicit transactions: the check and the insert below are one
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("BEGIN IMMEDIATE")  # another process initialising the file waits for this one
                try:
                    for statement in _SCHEMA.split(";\n"):
                        if statement.strip():
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

    def insert(self, fields: Mapping[str, Any], ids: Sequence[str]) -> SearchRecord:
        """Store a new record under a fresh random id (retried on the unlikely collision). One INSERT, in
        its own transaction."""
        if list(ids) != sorted(ids) or any("\n" in i for i in ids):
            raise InternalError(DiagnosticCode.API_INTERNAL, "a record's ids must be sorted and one-line")
        self._ensure()
        blob = zlib.compress("\n".join(ids).encode("utf-8"))
        for _ in range(_INSERT_TRIES):
            record = SearchRecord.model_validate({**fields, "record_id": new_record_id(), "ids": list(ids)})
            body = record.model_dump_json(exclude={"ids"})
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO records (record_id, index_version, searched_at, body, ids) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (record.record_id, record.index_version, record.searched_at, body, blob),
                    )
                return record
            except sqlite3.IntegrityError:
                continue  # the id was taken: draw another
            finally:
                conn.close()
        raise InternalError(DiagnosticCode.API_INTERNAL, "could not draw an unused record id")

    def get(self, record_id: str) -> SearchRecord | None:
        """The record with this id, or None (also when no record was ever saved: the file isn't created by a
        read). A row that doesn't hold a valid record is the instance's fault (500)."""
        if not valid_record_id(record_id) or not self.path.exists():
            return None
        conn = self._connect(read_only=True)
        try:
            row = conn.execute("SELECT body, ids FROM records WHERE record_id = ?", (record_id,)).fetchone()
        except sqlite3.OperationalError as e:  # e.g. the table isn't there yet
            if "no such table" in str(e):
                return None
            raise
        finally:
            conn.close()
        if row is None:
            return None
        try:
            text = zlib.decompress(row[1]).decode("utf-8")
            ids = text.split("\n") if text else []
            record = SearchRecord.model_validate({**json.loads(row[0]), "ids": ids})
        except (ValueError, zlib.error, TypeError) as e:
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
    added: tuple[str, ...]  # ids the replay matched that the record doesn't hold
    removed: tuple[str, ...]  # ids the record holds that the replay didn't match
    ids_match: bool
    excluded_match: bool

    @property
    def membership_identical(self) -> bool:
        return not self.added and not self.removed


type PinnedLoader = Callable[[str], TantivyEngine | None]


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

    - its `index_version` and `query_version` are both available here → run on that index; `reproduced` if
      `ids_hash` and `excluded` both match, else `mismatch` (ERROR `API_REPLAY_MISMATCH`, logged once);
    - otherwise → `drifted`, run on the served index with this code's query version, naming each input
      that changed, with the ids added and removed (`+0/−0` is membership-identical, not hidden).
    """
    same_query = record.query_version == QUERY_VERSION
    engine = served if served.index_version == record.index_version else pinned(record.index_version)
    if same_query and engine is not None:
        parsed, found, refused = _run(engine, record.canonical)
        canonical_match = (
            parsed.canonical == record.canonical and parsed.canonical_hash == record.canonical_hash
        )
        ids_match = found is not None and found.ids_hash == record.ids_hash
        excluded_match = found is not None and found.excluded == record.excluded.model_dump()
        status: Status = "reproduced" if canonical_match and ids_match and excluded_match else "mismatch"
        changed: tuple[Changed, ...] = ()
        if status == "mismatch":
            log.error(
                "replay_mismatch",
                extra={
                    "code": str(DiagnosticCode.API_REPLAY_MISMATCH),
                    "record_id": record.record_id,
                    "index_version": record.index_version,
                    "query_version": record.query_version,
                    "ids_match": ids_match,
                    "excluded_match": excluded_match,
                    "canonical_match": canonical_match,
                    "refused": str(refused) if refused is not None else None,
                },
            )
    else:
        engine = served
        _parsed, found, refused = _run(engine, record.canonical)
        changed = changed_inputs(record, index_inputs(data_dir, engine.index_version), QUERY_VERSION)
        if not changed:  # a different index_version always has different inputs; anything else is a bug
            raise InternalError(DiagnosticCode.API_INTERNAL, "a drifted replay found no changed input")
        status = "drifted"
        ids_match = found is not None and found.ids_hash == record.ids_hash
        excluded_match = found is not None and found.excluded == record.excluded.model_dump()
    now = set(found.ids) if found is not None else set()
    then = set(record.ids)
    return Replay(
        status=status,
        engine=engine,
        query_version=QUERY_VERSION,
        identified=found,
        refused=refused,
        changed=changed,
        added=tuple(sorted(now - then)),
        removed=tuple(sorted(then - now)),
        ids_match=ids_match,
        excluded_match=excluded_match,
    )
