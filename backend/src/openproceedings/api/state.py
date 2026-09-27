"""The served index: loaded once at startup, swapped atomically on SIGHUP (fastapi-conventions §Index
lifecycle, spec 04 §Implementation notes).

`IndexState.engine` is one reference. A reload builds (and so verifies) a new `TantivyEngine` off to the
side and replaces the reference in one assignment; the live engine is never mutated. A handler reads the
reference once (`api/deps.py::current_engine`) and uses that object for the whole request, streaming
included, so a request in flight finishes on the index it started on.

Loading an index also verifies the snapshot it was built from (`snapshot_records`: `/papers/{id}` reads
the full record, provenance included, from it) and computes its coverage (`api/coverage.py::compute`, the
manifest's counts checked against the records and the index), before the swap, so an index is served with
its snapshot and coverage or not at all. A failed load or reload keeps the engine already being served (and logs ERROR
`index_load_failed`); only when nothing was ever loaded do requests get 503 `API_INDEX_NOT_LOADED`.

Index selection is restricted (task-034 notes; `cli.resolve_snapshot` is not reused): the configured name
must match `config.INDEX_NAME`, and what it resolves to — through the `current` symlink — must be a
directory directly under `<data_dir>/indexes/` whose name is an index_version. A request pinned to another
index_version (`GET /export?index_version=`) gets it from `IndexState.pinned`, selected by the same rule.
"""

from __future__ import annotations

import json
import logging
import re
import signal
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING

from openproceedings.api.config import INDEX_NAME
from openproceedings.api.errors import frames
from openproceedings.diagnostics import OpenProceedingsError
from openproceedings.ingest.snapshot import RecordFile, SnapshotError

if TYPE_CHECKING:
    from openproceedings.api.models import CoverageResponse
    from openproceedings.engine.tantivy_engine import TantivyEngine

log = logging.getLogger(__name__)
VERSION_DIR = re.compile(r"[0-9a-f][0-9a-f-]{0,63}")
KEEP_PINNED = 1  # engines of other index_versions held open for pinned requests (besides the served one)

type Opener = Callable[[Path], TantivyEngine]  # TantivyEngine itself; tests wrap it to slow a load down


class IndexSelectionError(Exception):
    """The configured index name, or what it resolves to, is not an index under `<data_dir>/indexes`."""


def index_path(data_dir: Path, name: str) -> Path:
    """The resolved directory of index `name` under `<data_dir>/indexes/`, or IndexSelectionError."""
    if not INDEX_NAME.fullmatch(name):
        raise IndexSelectionError("the index name must be `current` or an index_version")
    indexes = (data_dir / "indexes").resolve()
    try:
        target = (indexes / name).resolve(strict=True)  # follows `current`
    except (OSError, RuntimeError):  # missing, or a symlink loop
        raise IndexSelectionError(f"no index `{name}` under the data directory's indexes/") from None
    if target.parent != indexes or not VERSION_DIR.fullmatch(target.name) or not target.is_dir():
        raise IndexSelectionError(f"`{name}` does not resolve to an index directory directly under indexes/")
    return target


def snapshot_records(data_dir: Path, index: Path, index_version: str) -> RecordFile:
    """The records of the snapshot index `index` was built from: `<data_dir>/snapshots/<its manifest's
    snapshot>`, which must hash to the manifest's `snapshot_hash` (one verifying pass). SnapshotError
    otherwise (missing, another snapshot under that name, or a manifest that names no plain directory)."""
    try:
        manifest = json.loads((index / "manifest.json").read_text(encoding="utf-8"))
        name, expected = manifest["snapshot"], manifest["snapshot_hash"]
        if manifest["index_version"] != index_version:
            raise SnapshotError(
                "the index directory's manifest names another index_version", reason="index_manifest_invalid"
            )
    except (OSError, ValueError, KeyError, TypeError):
        raise SnapshotError(
            "the index manifest doesn't name its snapshot", reason="index_manifest_invalid"
        ) from None
    if not isinstance(name, str) or not name or "/" in name or "\\" in name or name.startswith("."):
        raise SnapshotError(
            "the index manifest's snapshot is not a directory name", reason="index_manifest_invalid"
        )
    records = RecordFile(data_dir / "snapshots" / name)
    if records.snapshot_hash != expected:
        raise SnapshotError(
            "the snapshot of that name is not the one the index was built from",
            reason="snapshot_hash_mismatch",
        )
    return records


def coverage_of(engine: TantivyEngine, records: RecordFile) -> CoverageResponse:
    from openproceedings.api.coverage import compute  # the router module; imported here, not at the top

    return compute(engine, records)


class IndexState:
    def __init__(self, data_dir: Path, name: str, opener: Opener) -> None:
        self._data_dir = data_dir
        self._name = name
        self._opener = opener
        self._engine: TantivyEngine | None = None
        # the served index's snapshot records and coverage, and the previous one's (a request in flight
        # across a swap); both are built and checked at load, before the swap
        self._loaded: dict[str, tuple[RecordFile, CoverageResponse]] = {}
        self._reloading = threading.Lock()  # one load at a time; readers never take it
        self._pinned: dict[str, TantivyEngine] = {}  # engines of other versions opened for a pin (`pinned`)
        self._pinning = threading.Lock()  # one pinned open at a time

    @property
    def engine(self) -> TantivyEngine | None:
        """The engine being served, or None before the first successful load. Read it once per request."""
        return self._engine

    def load(self) -> bool:
        """Load the configured index and swap it in; True if an engine is being served afterwards and it is
        the configured one. Never raises: a failure is one ERROR line, and the previous engine stays."""
        with self._reloading:
            return self._load()

    def _load(self) -> bool:
        started = time.perf_counter()
        previous = self._engine
        kept = previous.index_version if previous is not None else None
        try:
            path = index_path(self._data_dir, self._name)
            if previous is not None and path.name == previous.index_version:
                log.info("index_unchanged", extra={"index_version": kept})
                return True
            engine = self._opener(path)  # verifies every file; the live engine is untouched meanwhile
            records = snapshot_records(self._data_dir, path, engine.index_version)
            coverage = coverage_of(engine, records)  # the manifest checked against the records and the index
        except Exception as e:  # the handling layer: logged once, and the service keeps what it has
            fields: dict[str, object] = {"error": type(e).__name__, "index_version_kept": kept}
            if isinstance(e, OpenProceedingsError):
                fields["code"] = str(e.code)
            if isinstance(e, SnapshotError):
                fields["reason"] = e.reason  # a constant (snapshot_missing, counts_mismatch, …), never a path
            if not isinstance(e, IndexSelectionError | OSError | OpenProceedingsError | SnapshotError):
                fields["frames"] = frames(e)
            log.error("index_load_failed", extra=fields)  # the type, never the message (it names paths)
            return False
        kept_loaded = {kept: self._loaded[kept]} if kept is not None and kept in self._loaded else {}
        self._loaded = {**kept_loaded, engine.index_version: (records, coverage)}  # before the swap
        self._engine = engine  # the atomic swap: one reference assignment
        log.info(
            "index_loaded" if previous is None else "index_swapped",
            extra={
                "index_version": engine.index_version,
                "previous_index_version": kept,
                "ms": round((time.perf_counter() - started) * 1000),
            },
        )
        return True

    def records(self, index_version: str) -> RecordFile | None:
        """The snapshot records loaded with index `index_version` (the served one or the one before)."""
        loaded = self._loaded.get(index_version)
        return loaded[0] if loaded is not None else None

    def coverage(self, index_version: str) -> CoverageResponse | None:
        """The coverage computed when index `index_version` was loaded (the served one or the one before)."""
        loaded = self._loaded.get(index_version)
        return loaded[1] if loaded is not None else None

    def available(self, engine: TantivyEngine | None) -> list[str]:
        """Every index_version on this instance (`GET /meta`), sorted: each directory directly under
        `<data_dir>/indexes/` named like one and holding a manifest (the `current` symlink and `.tmp-`
        leftovers are not versions), plus `engine`'s (the one this request read)."""
        indexes = self._data_dir / "indexes"
        try:
            found = {
                d.name
                for d in indexes.iterdir()
                if VERSION_DIR.fullmatch(d.name) and not d.is_symlink() and (d / "manifest.json").is_file()
            }
        except OSError:
            found = set()
        if engine is not None:
            found.add(engine.index_version)
        return sorted(found)

    def pinned(self, version: str) -> TantivyEngine | None:
        """The engine of index_version `version` (an export pinned by `index_version`; spec 04 §Exports), or
        None when this instance doesn't hold it. The served engine if it is that version; otherwise
        `<data_dir>/indexes/<version>`, validated exactly as the configured index is (`index_path`: an
        index_version name, a directory directly under `indexes/`; `current` and aliases are refused), opened
        read-only on first use and kept (`KEEP_PINNED` of them, the oldest dropped first)."""
        engine = self._engine
        if engine is not None and engine.index_version == version:
            return engine
        if not VERSION_DIR.fullmatch(version):
            return None
        with self._pinning:
            found = self._pinned.get(version)
            if found is not None:
                return found
            try:
                path = index_path(self._data_dir, version)
            except IndexSelectionError:
                return None
            if path.name != version:  # a symlink named like a version: not the version asked for
                return None
            started = time.perf_counter()
            found = self._opener(path)  # verifies every file, as a load does
            if found.index_version != version:  # a directory whose manifest names another version
                return None
            self._pinned[version] = found
            while len(self._pinned) > KEEP_PINNED:
                del self._pinned[next(iter(self._pinned))]
            log.info(
                "index_pinned_opened",
                extra={"index_version": version, "ms": round((time.perf_counter() - started) * 1000)},
            )
            return found

    def load_in_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.load, name="op-index-load", daemon=True)
        thread.start()
        return thread


def install_sighup(state: IndexState) -> Callable[[], None]:
    """SIGHUP reloads the index in a background thread (verifying it takes a while; the event loop keeps
    serving). Returns a function that restores the previous handler. Main thread only (Python's rule)."""

    def reload(signum: int, frame: FrameType | None) -> None:
        state.load_in_background()  # nothing else here: a signal handler must not log or block

    previous = signal.signal(signal.SIGHUP, reload)

    def restore() -> None:
        signal.signal(signal.SIGHUP, previous)

    return restore
