"""Older index versions, loaded on demand and read-only, to replay a search record pinned to one
(fastapi-conventions §Index lifecycle 4; spec 04 §Search records).

A version is looked up by name exactly as the served index is (`state.index_path`: only an index_version,
resolved to a directory directly under `<data_dir>/indexes/`), never through `cli.resolve_snapshot`, and it
must resolve to *itself* (not `current`, not a symlink to another version). The engine opens it the way it
opens the served one (every file re-hashed; an index this code can't read, such as one built with another
tokenizer_version, is refused), so "available" means "loadable by this code".

At most `KEEP` engines are held, least recently used dropped first; loads are serialised by one lock. A
version that can't be loaded is `None` (one WARNING line with the error type), and the replay reports
`drifted` against the served index.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

from openproceedings.api.state import VERSION_DIR, IndexSelectionError, Opener, index_path
from openproceedings.diagnostics import OpenProceedingsError
from openproceedings.engine.index import IndexBuildError

if TYPE_CHECKING:
    from openproceedings.engine.tantivy_engine import TantivyEngine

log = logging.getLogger(__name__)
KEEP = 2  # pinned engines held besides the served one


class PinnedIndexes:
    def __init__(self, data_dir: Path, opener: Opener) -> None:
        self._data_dir = data_dir
        self._opener = opener
        self._lock = threading.Lock()
        self._engines: OrderedDict[str, TantivyEngine] = OrderedDict()

    def get(self, version: str) -> TantivyEngine | None:
        """The engine of index `version`, or None if this instance can't serve it."""
        if not VERSION_DIR.fullmatch(version):
            return None
        with self._lock:
            engine = self._engines.get(version)
            if engine is not None:
                self._engines.move_to_end(version)
                return engine
            try:
                path = index_path(self._data_dir, version)
                if path.name != version:
                    raise IndexSelectionError("the name resolves to another index")
                engine = self._opener(path)
            except (IndexSelectionError, OSError, OpenProceedingsError, IndexBuildError) as e:
                log.warning(
                    "pinned_index_unavailable", extra={"index_version": version, "error": type(e).__name__}
                )
                return None
            self._engines[version] = engine
            while len(self._engines) > KEEP:
                self._engines.popitem(last=False)
            return engine
