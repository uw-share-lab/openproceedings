"""One snapshot built from every crawler's recorded fixtures at once: OpenReview API v2 (ICLR 2024), API v1 (ICLR
2021 and the 2015 coverage gap), the NeurIPS proceedings (2013) and PMLR (ICML 2013 and 2024), all crawled into
one cache and replayed offline by `op snapshot build`.

The expected hashes were recorded before TASK-103 unified the crawlers' HTTP layer: the snapshot is a function
of the cache, so a refactor of the fetch, cache, retry or replay code must leave every byte of it unchanged.
Change them only with a deliberate change to what a crawl records (and say so in the commit)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from openproceedings.ingest import snapshot as snap
from openproceedings.ingest.sources import openreview_v1 as v1
from openproceedings.ingest.sources import openreview_v2 as orv
from openproceedings.ingest.sources.crawl import ingest_neurips, ingest_pmlr

from tests.unit.ingest.openreview_fakes import FakeOpenReviewV1
from tests.unit.ingest.test_neurips import seed_2013
from tests.unit.ingest.test_openreview_v1 import client as v1_client
from tests.unit.ingest.test_openreview_v1 import world_2021
from tests.unit.ingest.test_openreview_v2 import client as v2_client
from tests.unit.ingest.test_openreview_v2 import world
from tests.unit.ingest.test_pmlr import seed_v28, seed_v235

BUILT = datetime(2026, 9, 28, tzinfo=UTC)
# recorded on feat/m4-crawlers at b766727, before TASK-103 touched the HTTP layer
SNAPSHOT_HASH = "ff71377d8f7d1e7cbbd3d0797e758588e3039886481c7aa58c1eb10cd4db9df4"
FILES_HASH = "9c8e9f9cdbbfc3302e18aad12fbd10b185eceb1606774d24088153a13567a15f"


def combined(tmp_path: Path) -> snap.BuildResult:
    cache = tmp_path / "cache"
    orv.ingest(v2_client(cache, world()), cache, "ICLR", [2024])
    v1.ingest(v1_client(cache, world_2021()), cache, "ICLR", [2021])
    v1.ingest(v1_client(cache, FakeOpenReviewV1()), cache, "ICLR", [2015])
    seed_2013(cache)
    ingest_neurips([2013], cache, offline=True)
    seed_v28(cache)
    seed_v235(cache)
    ingest_pmlr([2013, 2024], cache, offline=True)
    return snap.build(cache, tmp_path / "snapshots", BUILT)


def files_hash(directory: Path) -> str:
    """sha256 over every file's name and bytes, in name order: the whole snapshot directory."""
    h = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        h.update(path.relative_to(directory).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def test_the_combined_snapshot_is_byte_identical_to_the_recorded_one(tmp_path: Path) -> None:
    result = combined(tmp_path)
    assert result.path.name.startswith("2026-09-27-")
    assert (result.snapshot_hash, files_hash(result.path)) == (SNAPSHOT_HASH, FILES_HASH)
