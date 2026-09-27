"""The served index: loaded once at startup, swapped atomically on SIGHUP (fastapi-conventions §Index
lifecycle, spec 04 §Implementation notes).

`IndexState.engine` is one reference. A reload builds (and so verifies) a new `TantivyEngine` off to the
side and replaces the reference in one assignment; the live engine is never mutated. A handler reads the
reference once (`api/deps.py::current_engine`) and uses that object for the whole request, streaming
included, so a request in flight finishes on the index it started on.

A failed reload keeps the engine already being served (and logs ERROR); only when nothing was ever loaded
do requests get 503 `API_INDEX_NOT_LOADED`.

Index selection is restricted (task-034 notes; `cli.resolve_snapshot` is not reused): the configured name
must match `config.INDEX_NAME`, and what it resolves to — through the `current` symlink — must be a
directory directly under `<data_dir>/indexes/` whose name is an index_version.
"""

from __future__ import annotations

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

if TYPE_CHECKING:
    from openproceedings.engine.tantivy_engine import TantivyEngine

log = logging.getLogger(__name__)
VERSION_DIR = re.compile(r"[0-9a-f][0-9a-f-]{0,63}")

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


class IndexState:
    def __init__(self, data_dir: Path, name: str, opener: Opener) -> None:
        self._data_dir = data_dir
        self._name = name
        self._opener = opener
        self._engine: TantivyEngine | None = None
        self._reloading = threading.Lock()  # one load at a time; readers never take it

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
        except Exception as e:  # the handling layer: logged once, and the service keeps what it has
            fields: dict[str, object] = {"error": type(e).__name__, "index_version_kept": kept}
            if isinstance(e, OpenProceedingsError):
                fields["code"] = str(e.code)
            if not isinstance(e, IndexSelectionError | OSError | OpenProceedingsError):
                fields["frames"] = frames(e)
            log.error("index_load_failed", extra=fields)  # the type, never the message (it names paths)
            return False
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

    def available(self) -> list[str]:
        """Every index_version on this instance (`GET /meta`), sorted: each directory directly under
        `<data_dir>/indexes/` named like one and holding a manifest (the `current` symlink and `.tmp-`
        leftovers are not versions), plus the one being served."""
        indexes = self._data_dir / "indexes"
        try:
            found = {
                d.name
                for d in indexes.iterdir()
                if VERSION_DIR.fullmatch(d.name) and not d.is_symlink() and (d / "manifest.json").is_file()
            }
        except OSError:
            found = set()
        engine = self._engine
        if engine is not None:
            found.add(engine.index_version)
        return sorted(found)

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
