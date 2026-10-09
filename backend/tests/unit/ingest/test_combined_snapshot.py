"""One snapshot built from every crawler's recorded fixtures at once: OpenReview API v2 (ICLR 2024), API v1
(ICLR 2021 and the 2015 coverage gap), the ICLR accepted-paper archive (2015), the NeurIPS proceedings (2013)
and PMLR (ICML 2013 and 2024), all crawled into one cache and replayed offline by `op snapshot build`.

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
from openproceedings.ingest.sources.crawl import ingest_iclr, ingest_neurips, ingest_pmlr

from tests.unit.ingest.openreview_fakes import FakeOpenReviewV1
from tests.unit.ingest.test_iclr import seed_year as seed_iclr
from tests.unit.ingest.test_neurips import seed_2013
from tests.unit.ingest.test_openreview_v1 import client as v1_client
from tests.unit.ingest.test_openreview_v1 import world_2021
from tests.unit.ingest.test_openreview_v2 import client as v2_client
from tests.unit.ingest.test_openreview_v2 import world
from tests.unit.ingest.test_pmlr import seed_v28, seed_v235

BUILT = datetime(2026, 9, 28, tzinfo=UTC)
# Re-recorded by TASK-096 when the ICLR archive became a crawler and record schema v2 added its source;
# the files hash was updated by TASK-115 when manifest format 2 added per-track coverage metadata, and by
# TASK-118 when record schema v3 (round-qualified 2021 D&B ids) changed the manifest's record_schema_version;
# no fixture here is on the D&B host, so the records, and SNAPSHOT_HASH, are unchanged. TASK-125 changed it again:
# every API v1 crawl report's `skipped` gained `duplicate_submission` (0 for both v1 crawls here; records unchanged).
# TASK-101 changed both: the ICLR 2024 v2 accepted records now carry `presentation` (`ICLR 2024 poster`) and its
# claim, and the v2 crawl report gained `presentation_unmapped` (0 here). content_hash doesn't cover presentation.
# TASK-113 changed FILES_HASH again: every API v1 crawl report gained `authors_split` (decision-019; 0 here). Its
# records here are unchanged (no fixture in this build has a split author list or a withdrawn twin), so
# SNAPSHOT_HASH is TASK-101's. TASK-159/157 changed FILES_HASH: record schema v4 (the `twin` and `invitation`
# claim fields, decision-029) changed the manifest's record_schema_version, and the RIS report's parser_version
# is scholarmend 0.1.5. No record here is a twin or carries an invitation, so SNAPSHOT_HASH is unchanged.
# Tokenizer 3 changed FILES_HASH: the manifest's tokenizer_version is "3"; with it set back to "2" the files hash to
# the hash before (checked when it changed). Dedup's title keys here are the same under both tokenizers.
# Release 0.1.0 changed only the manifest's openproceedings_version from "0.0.0" to "0.1.0";
# reverting that one value in memory restores the prior files hash. The corpus hash is unchanged.
# Release 0.2.0 likewise changed only openproceedings_version, "0.1.0" to "0.2.0": setting it back to "0.1.0" in
# memory returns the files hash to ce0f3eba… (checked 2026-10-06), and SNAPSHOT_HASH is unchanged.
# TASK-205/206 changed FILES_HASH: record schema v5 (the `dblp` and `icml_site` sources and the `dblp-<key>` native
# id, decision-047) changed the manifest's record_schema_version, from e0caaefc…, and each proceedings listing's
# report gained `abstract_short` (abstracts under 5 words: the scrubbed fixtures' synthetic ones); no record changed.
SNAPSHOT_HASH = "94c07048e05de79db6c622f6e266195ef698d1ac6a82bc68aab9cd7213168bdd"
# Task 2 of the new-venues milestone changed FILES_HASH: record schema v6 (the `ojs` source, decision-049) changed the
# manifest's record_schema_version, from 964d2bd7…; with it set back to "5" the files hash to that (checked 2026-10-09).
FILES_HASH = "7d722589b19c3a79c4ca2b49e1f29e362e9bb95051e8d0f3a1498f873a27d100"


def combined(tmp_path: Path) -> snap.BuildResult:
    cache = tmp_path / "cache"
    orv.ingest(v2_client(cache, world()), cache, "ICLR", [2024])
    v1.ingest(v1_client(cache, world_2021()), cache, "ICLR", [2021])
    v1.ingest(v1_client(cache, FakeOpenReviewV1()), cache, "ICLR", [2015])
    seed_iclr(cache, 2015)
    ingest_iclr([2015], cache, offline=True)
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
