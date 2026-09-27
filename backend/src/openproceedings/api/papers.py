"""`GET /api/v1/papers/{id}`: the full record, provenance included (spec 04 §Endpoints).

The served index decides whether a paper exists (404 `API_PAPER_NOT_FOUND` otherwise), so the answer
belongs to the same `index_version` as a search. The index stores only the display record, so the full
record (per-field provenance claims, `content_hash`) is read from the snapshot the index was built from:
`<data_dir>/snapshots/<the index manifest's snapshot>`, which must hash to the manifest's `snapshot_hash`.
A missing or different snapshot is the instance's fault, a 500 `API_INTERNAL`, never a partial record.

`Papers` keeps one `ingest.snapshot.RecordFile` (byte ranges by id) per index_version, built on the first
request for it; only the served index and the one before it are kept, so a hot swap drops old ones.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Request

from openproceedings.api.deps import EngineDep
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import PaperResponse, versions
from openproceedings.diagnostics import DiagnosticCode, InternalError
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.snapshot import RecordFile, SnapshotError

log = logging.getLogger(__name__)
router = APIRouter(prefix=API_PREFIX)
KEEP = 2  # record files held: the served index's and the previous one (a request in flight across a swap)


class Papers:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._lock = threading.Lock()  # one build at a time; a build takes one pass over the snapshot
        self._files: dict[str, RecordFile] = {}

    def get(self, index_version: str, rid: str) -> PaperRecord | None:
        return self._file(index_version).get(rid)

    def records(self, index_version: str) -> RecordFile:
        """The verified record file of the snapshot `index_version` was built from (`GET /coverage`)."""
        return self._file(index_version)

    def _file(self, index_version: str) -> RecordFile:
        with self._lock:
            found = self._files.get(index_version)
            if found is None:
                found = self._open(index_version)
                self._files[index_version] = found
                while len(self._files) > KEEP:
                    del self._files[next(iter(self._files))]  # the oldest first
            return found

    def _open(self, index_version: str) -> RecordFile:
        started = time.perf_counter()
        try:
            manifest = json.loads(
                (self._data_dir / "indexes" / index_version / "manifest.json").read_text(encoding="utf-8")
            )
            name = manifest["snapshot"]
            if manifest["index_version"] != index_version:
                raise SnapshotError("the index directory's manifest names another index_version")
            if not isinstance(name, str) or not name or "/" in name or "\\" in name or name.startswith("."):
                raise SnapshotError("the index manifest's snapshot is not a directory name")
            records = RecordFile(self._data_dir / "snapshots" / name)
            if records.snapshot_hash != manifest["snapshot_hash"]:
                raise SnapshotError("the snapshot of that name is not the one the index was built from")
        except (OSError, ValueError, KeyError, TypeError, SnapshotError) as e:
            raise InternalError(
                DiagnosticCode.API_INTERNAL,
                "this instance doesn't hold the snapshot its index was built from",
            ) from e
        log.info(
            "paper_records_opened",
            extra={
                "index_version": index_version,
                "records": len(records),
                "ms": round((time.perf_counter() - started) * 1000),
            },
        )
        return records


@router.get("/papers/{id}", response_model=PaperResponse)
def paper(request: Request, engine: EngineDep, id: str) -> PaperResponse:
    """The paper with this id in the served index, as its snapshot holds it."""
    if id not in engine.display([id]):
        raise ApiError(
            DiagnosticCode.API_PAPER_NOT_FOUND, f"No paper with that id in index {engine.index_version}."
        )
    papers: Papers = request.app.state.papers
    record = papers.get(engine.index_version, id)
    if record is None:  # the index holds it, its own snapshot doesn't: not the snapshot it was built from
        raise InternalError(
            DiagnosticCode.API_INTERNAL, "a paper the index holds is missing from its snapshot"
        )
    return PaperResponse(**versions(engine.index_version), paper=record)
