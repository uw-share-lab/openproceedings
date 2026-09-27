"""`GET /api/v1/coverage`: what the served index holds, per venue × year × track × status, with missing
abstracts, unknowns and the crawl dates (spec 04 §Endpoints, spec 07 §C; coverage-reporting skill).

The numbers are the manifest of the snapshot the served index was built from, reshaped by
`openproceedings.coverage.breakdown` (no second count). `compute` runs once per index, when it is loaded
(`api/state.py`, before the swap), on the `RecordFile` the load already verified: the manifest it read
with the records (so no second read to re-check), and the counts that one pass took of the records. Every
cell, every venue-year's missing abstracts, and every track's missing abstracts and claim sources must equal
the records' own count, and the records must number exactly the index's documents. Anything else fails the load (`index_load_failed` with a `reason`):
503 at startup, the old index kept on SIGHUP. Coverage is never partial, never recomputed per request.
"""

from __future__ import annotations

import logging
import time
from collections import Counter

from fastapi import APIRouter

from openproceedings.api.deps import ServedDep
from openproceedings.api.middleware import API_PREFIX
from openproceedings.api.models import CoverageResponse, versions
from openproceedings.coverage import TrackFacts, breakdown
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.ingest.snapshot import RecordFile, SnapshotError
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)
router = APIRouter(prefix=API_PREFIX)


def compute(engine: TantivyEngine, records: RecordFile) -> CoverageResponse:
    """The coverage of `engine`'s index from its verified snapshot's manifest, checked against the records
    and the index. SnapshotError (with a `reason`) if they disagree."""
    started = time.perf_counter()
    observed = TrackFacts(records.track_missing, records.track_sources)
    try:
        data = breakdown(records.manifest, records.path.parent.name, observed)
    except (TypeError, ValueError) as e:
        raise SnapshotError(
            f"the snapshot manifest is malformed ({type(e).__name__})", reason="manifest_invalid"
        ) from None
    except SnapshotError as e:
        raise SnapshotError(str(e), reason="manifest_invalid") from None
    cells = Counter(
        {
            (vy["venue"], vy["year"], c["track"], c["status"]): c["count"]
            for vy in data["venue_years"]
            for c in vy["cells"]
        }
    )
    if cells != records.cells:
        raise SnapshotError(
            "the manifest's cells don't count the snapshot's records", reason="counts_mismatch"
        )
    missing = {(vy["venue"], vy["year"]): vy["abstract_missing"] for vy in data["venue_years"]}
    if {k: n for k, n in missing.items() if n} != dict(records.abstract_missing):
        raise SnapshotError(
            "the manifest's abstract_missing doesn't count the records", reason="abstract_missing_mismatch"
        )
    per_track = {(vy["venue"], vy["year"], t["track"]): t for vy in data["venue_years"] for t in vy["tracks"]}
    if {k: t["abstract_missing"] for k, t in per_track.items()} != dict(records.track_missing) or {
        k: t["sources"] for k, t in per_track.items()
    } != {k: sorted(v) for k, v in records.track_sources.items()}:
        raise SnapshotError(
            "the manifest's per-track missing abstracts or sources don't match the records",
            reason="track_facts_mismatch",
        )
    if len(records) != len(engine.ids):  # the cells sum to record_count and to the records (checked above)
        raise SnapshotError(
            "the snapshot's records and the index's documents differ", reason="doc_count_mismatch"
        )
    coverage = CoverageResponse.model_validate({**versions(engine.index_version), **data})
    log.info(
        "coverage_computed",
        extra={
            "index_version": engine.index_version,
            "records": coverage.totals.records,
            "venue_years": len(coverage.venue_years),
            "ms": elapsed_ms(started),
        },
    )
    return coverage


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage(served: ServedDep) -> CoverageResponse:
    """The served index's coverage, computed and checked when it was loaded (with the engine, one bundle)."""
    return served.coverage
