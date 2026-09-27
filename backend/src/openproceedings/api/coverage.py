"""`GET /api/v1/coverage`: what the served index holds, per venue × year × track × status, with missing
abstracts, unknowns and the crawl dates (spec 04 §Endpoints, spec 07 §C; coverage-reporting skill).

The numbers are the manifest of the snapshot the served index was built from, reshaped by
`openproceedings.coverage.breakdown` (no second count). The snapshot is the one `/papers/{id}` reads:
`Papers.records` finds it through the index manifest and checks, in one pass, that its records hash to the
index's `snapshot_hash`. The records must also number exactly the index's documents. A missing, different
or inconsistent snapshot is a 500 `API_INTERNAL`, never partial coverage.

Computed once per index_version and kept in `Coverages` (task-080's rule: one `.get()` per read, only a
complete value stored, and a lost race only recomputes the same value). A hot swap serves a new
index_version, so it gets its own entry; only the last `KEEP` are held.
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Request

from openproceedings.api.deps import EngineDep
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import CoverageResponse, versions
from openproceedings.api.papers import Papers
from openproceedings.coverage import breakdown
from openproceedings.diagnostics import DiagnosticCode, InternalError
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.ingest.snapshot import SnapshotError

log = logging.getLogger(__name__)
router = APIRouter(prefix=API_PREFIX)
KEEP = 2  # the served index's coverage and the previous one's (a request in flight across a swap)


class Coverages:
    def __init__(self) -> None:
        self._memo: dict[str, CoverageResponse] = {}  # index_version → its coverage (frozen, complete)

    def get(self, engine: TantivyEngine, papers: Papers) -> CoverageResponse:
        found = self._memo.get(engine.index_version)  # one read (task-080)
        if found is None:
            found = compute(engine, papers)
            if len(self._memo) >= KEEP:
                self._memo.clear()  # not atomic with the check: at worst a recomputation
            self._memo[engine.index_version] = found
        return found


def compute(engine: TantivyEngine, papers: Papers) -> CoverageResponse:
    """The coverage of `engine`'s index, from its snapshot's manifest."""
    started = time.perf_counter()
    records = papers.records(engine.index_version)  # 500 API_INTERNAL if it isn't the index's snapshot
    snapshot = records.path.parent
    try:
        manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("snapshot_hash") != records.snapshot_hash:
            raise SnapshotError("the snapshot's manifest changed after its records were verified")
        data = breakdown(manifest, snapshot.name)
        if not data["totals"]["records"] == len(records) == len(engine.ids):
            raise SnapshotError("the snapshot's counts, its records and the index's documents differ")
        coverage = CoverageResponse.model_validate({**versions(engine.index_version), **data})
    except (OSError, ValueError, TypeError, SnapshotError) as e:
        raise InternalError(
            DiagnosticCode.API_INTERNAL, "this instance's snapshot manifest doesn't describe its index"
        ) from e
    log.info(
        "coverage_computed",
        extra={
            "index_version": engine.index_version,
            "records": coverage.totals.records,
            "venue_years": len(coverage.venue_years),
            "ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return coverage


@router.get("/coverage", response_model=CoverageResponse)
def coverage(request: Request, engine: EngineDep) -> CoverageResponse:
    """The served index's coverage, as the snapshot it was built from counts it."""
    coverages: Coverages = request.app.state.coverage
    return coverages.get(engine, request.app.state.papers)
