"""Snapshots (spec 01 §Pipeline 5; snapshots skill): the immutable corpus the index is built from.

`ingest_ris` checks scholarmend outputs and copies them into the cache (`<cache>/ris/<name>/`, the
`mended.ris` and the `resolved.json` beside it). `build` imports everything cached, dedups, and writes
`<snapshots>/<crawl date>-<shorthash>/` with `records.jsonl`, `manifest.json`, `merges.csv` and
`conflicts.csv`. It never fetches, so it works offline.

Determinism: records sorted by id, one canonical JSON line each; `snapshot_hash` is the sha256 of the
`records.jsonl` bytes; the directory's date is the newest claim's fetch date (never the build clock); only
`manifest.json`'s `built_at` depends on when you build.

Immutability: a run holds an exclusive lock on the directory it writes into (`.lock`), so concurrent
builds or ingests take turns; every write goes into a `.tmp-` directory beside its target, is synced to
disk, renamed into place, checked, and made read-only, so a crash never leaves a half snapshot or cache
entry under its final name (the next run sweeps the leftovers, under the lock). An existing snapshot is never overwritten: if the target exists
and its `records.jsonl` hashes to this snapshot's hash it is reported, otherwise the build is refused.
Errors never quote record text (logging-standards skill).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import tempfile
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import astuple, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from openproceedings import __version__, storage
from openproceedings.ingest.dedup import Conflict, DedupResult, Merge, dedup
from openproceedings.ingest.record import RECORD_SCHEMA_VERSION, PaperRecord
from openproceedings.ingest.ris import ImportReport, import_ris
from openproceedings.query.normalize import TOKENIZER_VERSION

log = logging.getLogger(__name__)

FORMAT_VERSION = "1"  # the snapshot directory's layout and manifest keys
HASHED = ("title", "abstract", "venue", "year", "track", "status")  # content_hash's fields (record-schema)
DISPLAY = ("authors", "urls", "keywords", "presentation", "venue_id_raw")  # shown, never hashed
SHORT = 12


class SnapshotError(Exception):
    """A snapshot or cache operation refused: the message says why and what to do (never record text)."""


@dataclass(frozen=True)
class BuildResult:
    path: Path
    snapshot_hash: str
    created: bool  # False when this snapshot already existed


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _place_or_refuse(tmp: Path, target: Path, same: Callable[[Path], bool]) -> bool:
    try:
        return storage.place(tmp, target, same)
    except storage.PlacementError as e:
        raise SnapshotError(str(e)) from None


def _same_files(data: dict[str, bytes]) -> Callable[[Path], bool]:
    def same(target: Path) -> bool:
        return all((target / f).is_file() and (target / f).read_bytes() == blob for f, blob in data.items())

    return same


def ingest_ris(mended: Sequence[Path], cache: Path) -> list[ImportReport]:
    """Check every scholarmend output, then cache them all or none. Each goes to `<cache>/ris/<its
    directory's name>/`, as the exact bytes that were checked. Re-ingesting identical files is a no-op;
    different files under a cached name are refused, since a snapshot may already cite them."""
    root = cache / "ris"
    staged: list[tuple[Path, Path, dict[str, bytes], ImportReport]] = []
    with storage.exclusive(root):
        storage.sweep(root)
        paths = [p.resolve() for p in mended]  # a symlink: both files come from where it points
        names = [p.parent.name for p in paths]
        if any(not n or n.startswith(".") for n in names):
            raise SnapshotError(
                "a mended.ris must sit in a named directory (its name becomes the cache name)"
            )
        # names clash when they differ only in case or Unicode form (macOS's filesystem folds both)
        keys = [unicodedata.normalize("NFC", n).casefold() for n in names]
        if len(set(keys)) != len(keys):
            raise SnapshotError("two inputs share a directory name (ignoring case); the cache is keyed by it")
        cached = {
            unicodedata.normalize("NFC", d.name).casefold(): d.name for d in root.iterdir() if d.is_dir()
        }
        for name, key in zip(names, keys, strict=True):
            if key in cached and cached[key] != name:
                raise SnapshotError(f"cache entry {cached[key]} differs from {name} only in case; rename one")
        try:
            for path, name in zip(paths, names, strict=True):
                data = {
                    "mended.ris": path.read_bytes(),
                    "resolved.json": path.with_name("resolved.json").read_bytes(),
                }
                tmp = Path(tempfile.mkdtemp(dir=root, prefix=storage.TMP))
                for fname, blob in data.items():
                    (tmp / fname).write_bytes(blob)
                # what is checked is what gets cached; reports and errors name the cache entry
                _, report = import_ris(tmp / "mended.ris", name=f"{name}/mended.ris")
                staged.append((tmp, root / name, data, report))
            for _, target, data, _ in staged:  # refuse before placing anything: all or none
                if target.exists() and not _same_files(data)(target):
                    raise SnapshotError(
                        f"cache entry {target.name} holds different files; use another directory name"
                    )
            for tmp, target, data, report in staged:
                placed = _place_or_refuse(tmp, target, _same_files(data))
                log.info(
                    "ris_cached", extra={"cache": target.name, "new": placed, "imported": report.imported}
                )
        finally:
            storage.sweep(root)
    return [report for *_, report in staged]


def load_cache(cache: Path) -> tuple[list[PaperRecord], list[ImportReport]]:
    """Every cached source, imported (M2: RIS only), in cached-name order. Hidden and `.tmp-` entries are
    never sources."""
    records: list[PaperRecord] = []
    reports: list[ImportReport] = []
    for entry in sorted((cache / "ris").glob("*/mended.ris")):
        if entry.parent.name.startswith("."):
            continue
        recs, report = import_ris(entry)
        records += recs
        reports.append(report)
    if not reports:
        raise SnapshotError(
            f"nothing cached under {cache.name}/ris; run `op ingest ris <mended.ris>...` first"
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


def _nested(
    records: Iterable[PaperRecord], keep: Callable[[PaperRecord], bool] | None = None
) -> dict[str, Any]:
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
    if any(not r.provenance for r in records):
        raise SnapshotError("a record has no provenance claims; every value must say where it came from")
    fetched = [c.fetched_at for r in records for c in r.provenance]
    lines = "".join(record_line(r) + "\n" for r in records).encode("utf-8")
    merges = _csv((f.name for f in fields(Merge)), (astuple(m) for m in sorted(result.merges)))
    conflicts = _csv((f.name for f in fields(Conflict)), (astuple(c) for c in sorted(result.conflicts)))
    manifest = {
        "format_version": FORMAT_VERSION,
        "record_schema_version": RECORD_SCHEMA_VERSION,
        "tokenizer_version": TOKENIZER_VERSION,  # dedup's title keys depend on it
        "openproceedings_version": __version__,
        "snapshot_hash": _sha256(lines),
        "crawl_date": max(fetched).date().isoformat(),
        "crawl_window": {"from": min(fetched).isoformat(), "to": max(fetched).isoformat()},
        "built_at": built_at.astimezone(UTC).isoformat(),
        "record_count": len(records),
        "counts": _nested(records),
        "abstract_missing": _nested(records, lambda r: r.abstract is None),
        "unknown_track": _nested(records, lambda r: r.track == "unknown"),
        "merges": {"total": len(result.merges), **Counter(m.rule for m in result.merges)},
        "conflicts": {"total": len(result.conflicts), **Counter(c.resolution.split(":")[0] for c in result.conflicts)},
        "files": {"merges.csv": _sha256(merges), "conflicts.csv": _sha256(conflicts)},
        "sources": {"ris": [r.to_manifest() for r in reports]},
    }  # fmt: skip
    return {
        "records.jsonl": lines,
        "manifest.json": (json.dumps(manifest, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode(
            "utf-8"
        ),
        "merges.csv": merges,
        "conflicts.csv": conflicts,
    }


AUDITED = ("files", "tokenizer_version", "record_schema_version")
AUDIT_FILES = ("merges.csv", "conflicts.csv")


def _audit(snapshot: Path) -> dict[str, str]:
    """The audit files' hashes, as a manifest's `files` records them (both, always)."""
    return {
        f: _sha256((snapshot / f).read_bytes()) for f in AUDIT_FILES
    }  # what a rebuild must reproduce exactly


def _holds(snapshot: Path, snapshot_hash: str, fresh: dict[str, Any] | None = None) -> bool:
    """Is `snapshot` this snapshot, complete and current? Its records re-hash to `snapshot_hash` (never
    trusted from the manifest); its manifest parses and names that hash and this format version; its audit
    files (merges.csv, conflicts.csv) re-hash to the manifest's `files`; and, against `fresh` (the manifest
    this build rendered), its audit hashes and versions are the ones this code produces, so a dedup change
    that keeps the records but changes merges or conflicts is never passed off as the old snapshot."""
    try:
        manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        records = (snapshot / "records.jsonl").read_bytes()
        audit = _audit(snapshot)
    except (OSError, ValueError):
        return False
    return (
        _sha256(records) == snapshot_hash
        and isinstance(manifest, dict)
        and manifest.get("snapshot_hash") == snapshot_hash
        and manifest.get("format_version") == FORMAT_VERSION
        and manifest.get("files") == audit
        and (fresh is None or all(manifest.get(k) == fresh.get(k) for k in AUDITED))
    )


def build(cache: Path, snapshots: Path, built_at: datetime | None = None) -> BuildResult:
    """Import, dedup and write a new immutable snapshot (or report the one that already has this hash)."""
    began = time.monotonic()
    records, reports = load_cache(cache)
    files = render(dedup(records), reports, built_at or datetime.now(UTC))
    manifest = json.loads(files["manifest.json"])
    snapshot_hash = manifest["snapshot_hash"]
    target = snapshots / f"{manifest['crawl_date']}-{snapshot_hash[:SHORT]}"
    with storage.exclusive(snapshots):
        storage.sweep(snapshots)
        if target.exists():
            if not _holds(target, snapshot_hash, manifest):
                raise SnapshotError(
                    f"{target.name} exists but isn't this snapshot in the current format; snapshots are "
                    "immutable: retire it (release-manager prune path) and build again"
                )
            storage.lock(target)  # a crash between placing and locking left it writable
            log.info("snapshot_exists", extra={"snapshot": target.name, "snapshot_hash": snapshot_hash})
            return BuildResult(target, snapshot_hash, created=False)
        with storage.staging(snapshots) as tmp:
            for name, data in files.items():
                (tmp / name).write_bytes(data)
            created = _place_or_refuse(tmp, target, lambda t: _holds(t, snapshot_hash, manifest))
    log.info(
        "snapshot_built" if created else "snapshot_exists",
        extra={"snapshot": target.name, "snapshot_hash": snapshot_hash, "records": manifest["record_count"],
               "merges": manifest["merges"]["total"], "conflicts": manifest["conflicts"]["total"],
               "ms": round((time.monotonic() - began) * 1000)},
    )  # fmt: skip
    return BuildResult(target, snapshot_hash, created=created)


def iter_records(snapshot: Path) -> Iterator[PaperRecord]:
    """A snapshot's records in file order, streamed in one pass. It must be a snapshot: every record valid
    (so a stale content_hash is caught), ids strictly ascending (so unique), and the bytes read hashing to
    the manifest's `snapshot_hash`, checked when the file ends (one read, so the file checked is the file
    read). A caller must not act on the records until iteration finishes without raising: `load_records`
    and `build_index` (which commits only after the last record) don't. Errors name the line only."""
    try:
        manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        expected = manifest["snapshot_hash"] if isinstance(manifest, dict) else None
        digest = hashlib.sha256()
        previous = ""
        with (snapshot / "records.jsonl").open("rb") as fh:
            for n, raw in enumerate(fh, start=1):
                digest.update(raw)
                try:
                    r = PaperRecord.model_validate_json(raw)
                except ValidationError as e:
                    kinds = sorted({str(err["type"]) for err in e.errors(include_input=False)})
                    raise SnapshotError(
                        f"{snapshot.name} line {n}: invalid record ({', '.join(kinds)})"
                    ) from None
                if r.id == previous:
                    raise SnapshotError(f"{snapshot.name} line {n}: duplicate id")
                if r.id < previous:
                    raise SnapshotError(f"{snapshot.name} line {n}: records are not sorted by id")
                previous = r.id
                yield r
    except (OSError, ValueError, KeyError) as e:
        if isinstance(e, SnapshotError):
            raise
        raise SnapshotError(f"{snapshot.name} is not a snapshot ({type(e).__name__})") from None
    if expected != digest.hexdigest():
        raise SnapshotError(f"{snapshot.name}: records.jsonl doesn't match its manifest's snapshot_hash")
    try:  # the audit files, both of them, exactly as the manifest hashed them (the check _holds makes too)
        matches = manifest.get("files") == _audit(snapshot)
    except OSError:
        matches = False
    if not matches:
        raise SnapshotError(f"{snapshot.name}: merges.csv or conflicts.csv doesn't match its manifest")


def load_records(snapshot: Path) -> dict[str, PaperRecord]:
    """A snapshot's records by id (all in memory; `iter_records` streams them)."""
    return {r.id: r for r in iter_records(snapshot)}


def diff(a: Path, b: Path) -> dict[str, Any]:
    """From snapshot `a` to `b` (snapshots skill §CLI): ids added and removed; `rekeyed` ids (the same
    paper, its venue or year corrected so its id changed), with the fields that differ; `changed` ids
    naming the hashed fields that differ; and counts of display-only and provenance-only changes."""
    old, new = load_records(a), load_records(b)
    added, removed = new.keys() - old.keys(), old.keys() - new.keys()
    # a rekey only when exactly one removed and one added id share a native id: anything else (two papers
    # into one, one into two) is reported as added and removed, so a lost record is never hidden
    gone_by_native = Counter(old[i].native for i in removed)
    new_by_native: dict[str, list[str]] = {}
    for i in added:
        new_by_native.setdefault(new[i].native, []).append(i)
    rekeyed = {
        i: new_by_native[old[i].native][0]
        for i in sorted(removed)
        if gone_by_native[old[i].native] == 1 and len(new_by_native.get(old[i].native, [])) == 1
    }

    def hashed_diff(x: PaperRecord, y: PaperRecord) -> list[str]:
        return [f for f in HASHED if getattr(x, f) != getattr(y, f)]  # a hash change is always one of these

    changed: dict[str, list[str]] = {}
    display_only = provenance_only = 0
    for rid in sorted(old.keys() & new.keys()):
        x, y = old[rid], new[rid]
        if x.content_hash != y.content_hash:
            changed[rid] = hashed_diff(x, y)
        elif any(getattr(x, f) != getattr(y, f) for f in DISPLAY):
            display_only += 1
        elif x.provenance != y.provenance:
            provenance_only += 1
    return {
        "from": a.name,
        "to": b.name,
        "added": sorted(added - set(rekeyed.values())),
        "removed": sorted(removed - rekeyed.keys()),
        "rekeyed": {o: {"to": n, "fields": hashed_diff(old[o], new[n])} for o, n in rekeyed.items()},
        "changed": changed,
        "display_only": display_only,
        "provenance_only": provenance_only,
    }
