"""Snapshots (spec 01 §Pipeline 5; snapshots skill): the immutable corpus the index is built from.

`ingest_ris` checks scholarmend outputs and copies them into the cache (`<cache>/ris/<name>/`, the
`mended.ris` and the `resolved.json` beside it). `build` imports everything cached, dedups, and writes
`<snapshots>/<crawl date>-<shorthash>/` with `records.jsonl`, `manifest.json`, `merges.csv` and
`conflicts.csv`. It never fetches, so it works offline.

Determinism: records sorted by id, one canonical JSON line each; `snapshot_hash` is the sha256 of the
`records.jsonl` bytes; the directory's date is the newest claim's fetch date (never the build clock); only
`manifest.json`'s `built_at` depends on when you build. Immutability: a build goes into a temporary
directory beside the target and is renamed into place; an existing target is never overwritten, and a
snapshot whose hash already exists is reported and not rebuilt.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import astuple, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openproceedings.ingest.dedup import Conflict, DedupResult, Merge, dedup
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.ris import ImportReport, import_ris

log = logging.getLogger("openproceedings.ingest.snapshot")

HASHED = ("title", "abstract", "venue", "year", "track", "status")  # content_hash's fields (record-schema)
DISPLAY = ("authors", "urls", "keywords", "presentation", "venue_id_raw")  # shown, never hashed
SHORT = 12


class SnapshotError(Exception):
    """A snapshot or cache operation refused: the message says why and what to do."""


@dataclass(frozen=True)
class BuildResult:
    path: Path
    snapshot_hash: str
    created: bool  # False when a snapshot with this hash already existed


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ingest_ris(mended: Sequence[Path], cache: Path) -> list[ImportReport]:
    """Check each scholarmend output imports cleanly, then copy it (and its resolved.json) into the cache
    under its directory's name. Re-ingesting identical files is a no-op; different files under a cached
    name are refused, since a snapshot may already cite them."""
    reports = []
    for path in mended:
        _, report = import_ris(path)
        target = cache / "ris" / path.parent.name
        pairs = [(path, target / "mended.ris"), (path.with_name("resolved.json"), target / "resolved.json")]
        if target.exists():
            if any(not dst.exists() or _sha256(src) != _sha256(dst) for src, dst in pairs):
                raise SnapshotError(
                    f"{target} holds different files; cache them under another directory name"
                )
        else:
            tmp = Path(tempfile.mkdtemp(dir=_mkdir(target.parent), prefix=".tmp-"))
            for src, dst in pairs:
                shutil.copyfile(src, tmp / dst.name)
            os.replace(tmp, target)
        log.info("ris_cached", extra={"file": report.file, "cache": str(target), "imported": report.imported})
        reports.append(report)
    return reports


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_cache(cache: Path) -> tuple[list[PaperRecord], list[ImportReport]]:
    """Every cached source, imported (M2: RIS only), in cached-name order."""
    records: list[PaperRecord] = []
    reports: list[ImportReport] = []
    for mended in sorted((cache / "ris").glob("*/mended.ris")):
        recs, report = import_ris(mended)
        records += recs
        reports.append(report)
    if not reports:
        raise SnapshotError(
            f"nothing cached under {cache / 'ris'}; run `op ingest ris <mended.ris>...` first"
        )
    return records, reports


def record_line(record: PaperRecord) -> str:
    return json.dumps(
        record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _csv(header: Iterable[str], rows: Iterable[tuple[Any, ...]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _nested(records: Iterable[PaperRecord], keep: Any = None) -> dict[str, Any]:
    """venue → year → track → status → count (or venue → year → count of records passing `keep`)."""
    out: dict[str, Any] = {}
    for r in records:
        year = out.setdefault(r.venue, {}).setdefault(str(r.year), {} if keep is None else 0)
        if keep is None:
            year.setdefault(r.track, Counter())[r.status] += 1
        elif keep(r):
            out[r.venue][str(r.year)] += 1
    plain: dict[str, Any] = json.loads(json.dumps(out, sort_keys=True))  # Counters → plain, keys sorted
    return plain


def render(result: DedupResult, reports: Sequence[ImportReport], built_at: datetime) -> dict[str, bytes]:
    """The snapshot's files. Everything but manifest.json's `built_at` is a function of the inputs."""
    records = sorted(result.records, key=lambda r: r.id)
    if not records:
        raise SnapshotError("no records to snapshot")
    lines = "".join(record_line(r) + "\n" for r in records).encode("utf-8")
    snapshot_hash = hashlib.sha256(lines).hexdigest()
    crawl = max(c.fetched_at for r in records for c in r.provenance).date().isoformat()
    manifest = {
        "snapshot_hash": snapshot_hash,
        "crawl_date": crawl,
        "built_at": built_at.astimezone(UTC).isoformat(),
        "record_count": len(records),
        "counts": _nested(records),
        "abstract_missing": _nested(records, lambda r: r.abstract is None),
        "unknown_track": _nested(records, lambda r: r.track == "unknown"),
        "merges": {"total": len(result.merges), **Counter(m.rule for m in result.merges)},
        "conflicts": {"total": len(result.conflicts), **Counter(c.resolution.split(":")[0] for c in result.conflicts)},
        "sources": {"ris": [r.to_manifest() for r in reports]},
    }  # fmt: skip
    return {
        "records.jsonl": lines,
        "manifest.json": (json.dumps(manifest, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode(
            "utf-8"
        ),
        "merges.csv": _csv((f.name for f in fields(Merge)), (astuple(m) for m in sorted(result.merges))),
        "conflicts.csv": _csv(
            (f.name for f in fields(Conflict)), (astuple(c) for c in sorted(result.conflicts))
        ),
    }


def build(cache: Path, snapshots: Path, built_at: datetime | None = None) -> BuildResult:
    """Import, dedup and write a new immutable snapshot (or report the one that already has this hash)."""
    records, reports = load_cache(cache)
    files = render(dedup(records), reports, built_at or datetime.now(UTC))
    manifest = json.loads(files["manifest.json"])
    snapshot_hash = manifest["snapshot_hash"]
    target = snapshots / f"{manifest['crawl_date']}-{snapshot_hash[:SHORT]}"
    for existing in sorted(snapshots.glob(f"*-{snapshot_hash[:SHORT]}")):
        if (
            json.loads((existing / "manifest.json").read_text(encoding="utf-8"))["snapshot_hash"]
            == snapshot_hash
        ):
            log.info("snapshot_exists", extra={"path": str(existing), "snapshot_hash": snapshot_hash})
            return BuildResult(existing, snapshot_hash, created=False)
    if target.exists():
        raise SnapshotError(f"{target} exists with other contents; snapshots are immutable")
    tmp = Path(tempfile.mkdtemp(dir=_mkdir(snapshots), prefix=".tmp-"))
    try:
        for name, data in files.items():
            (tmp / name).write_bytes(data)
        os.replace(tmp, target)  # a crash never leaves a half snapshot under the final name
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    log.info(
        "snapshot_built",
        extra={"path": str(target), "snapshot_hash": snapshot_hash, "records": manifest["record_count"],
               "merges": manifest["merges"]["total"], "conflicts": manifest["conflicts"]["total"]},
    )  # fmt: skip
    return BuildResult(target, snapshot_hash, created=True)


def load_records(snapshot: Path) -> dict[str, PaperRecord]:
    """A snapshot's records by id, each re-validated (so a stale content_hash is caught)."""
    with (snapshot / "records.jsonl").open(encoding="utf-8") as f:
        records = [PaperRecord.model_validate_json(line) for line in f]
    return {r.id: r for r in records}


def diff(a: Path, b: Path) -> dict[str, Any]:
    """Ids added, removed and changed from snapshot `a` to `b` (snapshots skill §CLI). `changed` names the
    hashed fields that differ; display-only and provenance-only changes are counted separately."""
    old, new = load_records(a), load_records(b)
    changed: dict[str, list[str]] = {}
    display_only = provenance_only = 0
    for rid in sorted(old.keys() & new.keys()):
        x, y = old[rid], new[rid]
        if x.content_hash != y.content_hash:
            changed[rid] = [f for f in HASHED if getattr(x, f) != getattr(y, f)]
        elif any(getattr(x, f) != getattr(y, f) for f in DISPLAY):
            display_only += 1
        elif x.provenance != y.provenance:
            provenance_only += 1
    return {
        "from": a.name,
        "to": b.name,
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "changed": changed,
        "display_only": display_only,
        "provenance_only": provenance_only,
    }
