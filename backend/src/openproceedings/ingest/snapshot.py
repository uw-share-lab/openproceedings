"""Snapshots (spec 01 §Pipeline 5; snapshots skill): the immutable corpus the index is built from.

`ingest_ris` checks scholarmend outputs and copies them into the cache (`<cache>/ris/<name>/`, the
`mended.ris` and the `resolved.json` beside it); `op ingest openreview` caches its crawls under
`<cache>/openreview/{v2,v1}/` (`sources/openreview_v2.py`, `sources/openreview_v1.py`); `op ingest iclr|neurips|pmlr`
cache proceedings pages (`sources/crawl.py`). `build` imports everything cached (the RIS files, each finished
OpenReview crawl replayed from its cached responses, and each finished ICLR/NeurIPS/PMLR crawl re-mined from its cached
pages), dedups, reconciles OpenReview acceptance against the crawled proceedings (`reconcile.py`: an
OpenReview-accepted paper a complete listing doesn't hold becomes `unknown`, decision-005), adds the conflicts a
crawl found inside one source (`with_crawl_conflicts`), and writes
`<snapshots>/<crawl date>-<shorthash>/` with `records.jsonl`, `manifest.json`, `merges.csv` and
`conflicts.csv`. It never fetches, so it works offline. It also reports (and logs) each venue-year status
its records hold that their sources can't supply (`status_check`, TASK-109), without changing the snapshot.

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
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import astuple, dataclass, field, fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import ValidationError

from openproceedings import __version__, storage
from openproceedings.ingest.caps import cap_records, is_trimmed
from openproceedings.ingest.dedup import Attribution, Conflict, DedupResult, Merge, attribution, dedup
from openproceedings.ingest.reconcile import crawled, reconcile
from openproceedings.ingest.record import DERIVED, RECORD_SCHEMA_VERSION, PaperRecord
from openproceedings.ingest.ris import ImportReport, import_ris
from openproceedings.ingest.sources.common import Report, sources_manifest
from openproceedings.ingest.status_check import UnexpectedStatus, unexpected_statuses
from openproceedings.ingest.statuses import statuses_indexed
from openproceedings.logs import elapsed_ms
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.takedowns import NONE, Withheld, global_native, withhold_record
from openproceedings.vocab import BOOTSTRAP_SOURCES

log = logging.getLogger(__name__)

# the snapshot directory's layout and manifest keys. 2 (TASK-082) adds `crawl_windows`, `abstract_missing_by_track`,
# `sources_by_track` and `statuses_indexed`; a format-1 manifest still loads (`GET /coverage` then takes the
# per-track facts from the records it verified, and names no per-source window)
FORMAT_VERSION = "2"
READABLE_FORMATS = ("1", FORMAT_VERSION)
# the manifest keys a takedown adds (TASK-136, decision-022), written only when a record is withheld: a snapshot
# withholding nothing has the manifest it had before, so a format-2 reader of it sees no difference
WITHHELD_KEYS = ("withheld", "abstract_withheld", "abstract_withheld_by_track")
# manifest `query_dates` (TASK-077, decision-025): per bootstrap source, whether its window's ends (Publish or
# Perish query dates) were converted to UTC with a recorded offset, or are local wall time with no known offset.
# Written with any RIS report; a manifest without it (built before TASK-077) holds local times. Additive, like
# WITHHELD_KEYS: no format bump
UTC_QUERY_DATES = "utc"
LOCAL = "local"
HASHED = ("title", "abstract", "venue", "year", "track", "status")  # content_hash's fields (record-schema)
DISPLAY = ("authors", "urls", "keywords", "presentation", "venue_id_raw")  # shown, never hashed
SHORT = 12


class SnapshotError(Exception):
    """A snapshot or cache operation refused: the message says why and what to do (never record text).
    `reason` is a short constant a log line may carry (never a path), e.g. `snapshot_missing`; `snapshot`, when
    set, the snapshot directory's name (never a path), which a log line may carry too."""

    def __init__(
        self, message: str, *, reason: str = "snapshot_invalid", snapshot: str | None = None
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.snapshot = snapshot


def indexed_snapshot(data_dir: Path, index_manifest: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    """The snapshot an index was built from, and that snapshot's manifest: `<data_dir>/snapshots/<name>`,
    `name` being the index manifest's `snapshot` (a plain directory name), whose manifest names the index
    manifest's `snapshot_hash`. The one rule for the API's load (`api/state.snapshot_records`, which then
    re-hashes the records with `RecordFile`) and a search record's facts (`records.snapshot_facts`).
    SnapshotError otherwise, reason `index_manifest_invalid`, `snapshot_missing`, `snapshot_unreadable` or
    `snapshot_hash_mismatch`."""
    name, expected = index_manifest.get("snapshot"), index_manifest.get("snapshot_hash")
    plain = (
        isinstance(name, str) and name and "/" not in name and "\\" not in name and not name.startswith(".")
    )
    if not plain or not isinstance(expected, str):
        raise SnapshotError(
            "the index manifest doesn't name its snapshot by a directory name and hash",
            reason="index_manifest_invalid",
        )
    path = data_dir / "snapshots" / str(name)
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SnapshotError(f"{name} is not on this instance", reason="snapshot_missing") from None
    except (OSError, ValueError) as e:
        raise SnapshotError(
            f"{name}'s manifest is unreadable ({type(e).__name__})", reason="snapshot_unreadable"
        ) from None
    if not isinstance(manifest, dict) or manifest.get("snapshot_hash") != expected:
        raise SnapshotError(
            "the snapshot of that name is not the one the index was built from",
            reason="snapshot_hash_mismatch",
        )
    return path, manifest


@dataclass(frozen=True)
class BuildResult:
    path: Path
    snapshot_hash: str
    created: bool  # False when this snapshot already existed
    # each (venue, year, status) its records hold that their sources can't supply (TASK-109): reported and
    # logged, never written into the snapshot
    unexpected_statuses: tuple[UnexpectedStatus, ...] = ()
    # the takedown list's effect (TASK-136): ids withheld, listed ids followed to a new id, listed ids not held
    withheld: tuple[str, ...] = ()
    takedowns_followed: Mapping[str, str] = field(default_factory=dict)
    takedowns_unmatched: tuple[str, ...] = ()


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
                _, report = import_ris(tmp / "mended.ris", name=f"{name}/mended.ris", cache_entry=name)
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


def _load_ris(cache: Path) -> tuple[list[PaperRecord], list[ImportReport]]:
    records: list[PaperRecord] = []
    reports: list[ImportReport] = []
    for entry in sorted((cache / "ris").glob("*/mended.ris")):
        if entry.parent.name.startswith("."):
            continue
        recs, report = import_ris(entry)
        records += recs
        reports.append(report)
    return records, reports


def load_cache(cache: Path) -> tuple[list[PaperRecord], list[ImportReport]]:
    """Every cached RIS source, imported, in cached-name order. Hidden and `.tmp-` entries are never
    sources."""
    records, reports = _load_ris(cache)
    if not reports:
        raise SnapshotError(
            f"nothing cached under {cache.name}/ris; run `op ingest ris <mended.ris>...` first"
        )
    return records, reports


def load_sources(cache: Path) -> tuple[list[PaperRecord], list[ImportReport], list[Report]]:
    """Every cached source, with no network: the RIS imports, then every finished crawl of every crawler
    (OpenReview API v2 and v1, ICLR, NeurIPS, PMLR) re-run from its cache (`sources/crawl.replay_all`). Returns the
    records (under the ingest caps, `caps.cap_records`), the RIS reports and the crawl reports. Refuses an empty
    cache, and a crawl that can't be replayed (a `SourceError`: a marked crawl whose responses are gone, an
    unreadable cache entry or marker)."""
    from openproceedings.ingest.sources.crawl import replay_all
    from openproceedings.ingest.sources.http import SourceError

    records, reports = _load_ris(cache)
    try:
        mined, crawls = replay_all(cache)
    except SourceError as e:
        raise SnapshotError(f"the crawl cache can't be replayed: {e}", reason=e.reason) from e
    records = cap_records([*records, *mined])  # the ingest caps, before dedup (decision-026)
    if not reports and not crawls:
        raise SnapshotError(
            f"nothing cached under {cache.name}; run `op ingest ris <mended.ris>...`, "
            "`op ingest openreview --venue <V> --years <Y>` or `op ingest iclr|neurips|pmlr ...` first"
        )
    return records, reports, crawls


def record_line(record: PaperRecord) -> str:
    return json.dumps(
        record.model_dump(mode="json", exclude={*DERIVED}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
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


def _plain(value: dict[str, Any]) -> dict[str, Any]:
    """`value` as plain JSON values, keys sorted at every level."""
    plain: dict[str, Any] = json.loads(json.dumps(value, sort_keys=True))
    return plain


def _by_track(records: Iterable[PaperRecord], keep: Callable[[PaperRecord], bool]) -> dict[str, Any]:
    """venue → year → track → count of its records passing `keep` (0 included)."""
    out: dict[str, Any] = {}
    for r in records:
        at = out.setdefault(r.venue, {}).setdefault(str(r.year), {})
        at[r.track] = at.get(r.track, 0) + keep(r)
    return _plain(out)


def _per_track(
    records: Iterable[PaperRecord], withheld: Withheld = NONE
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """venue → year → track → missing abstracts (0 included; a withheld one is not missing), → the claim
    sources of its records (sorted), and venue → year → the statuses those sources can contain, those its
    records hold included (`statuses.statuses_indexed`)."""
    missing: dict[str, Any] = {}
    sources: dict[str, Any] = {}
    present: dict[tuple[str, str], set[str]] = {}
    for r in records:
        present.setdefault((r.venue, str(r.year)), set()).add(r.status)
        at = missing.setdefault(r.venue, {}).setdefault(str(r.year), {})
        at[r.track] = at.get(r.track, 0) + (r.abstract is None and r.id not in withheld)
        sources.setdefault(r.venue, {}).setdefault(str(r.year), {}).setdefault(r.track, set()).update(
            c.source for c in r.provenance
        )
    statuses = {
        venue: {
            year: statuses_indexed(set().union(*tracks.values()), venue, int(year), present[(venue, year)])
            for year, tracks in years.items()
        }
        for venue, years in sources.items()
    }
    named = {
        v: {y: {t: sorted(s) for t, s in ts.items()} for y, ts in ys.items()} for v, ys in sources.items()
    }
    return _plain(missing), _plain(named), _plain(statuses)


def utc_query_sources(manifest: Mapping[str, Any]) -> frozenset[str]:
    """The bootstrap sources whose query dates the manifest says were converted to UTC (`query_dates`); none
    for a manifest without the key, whose RIS dates are local wall time."""
    zones = manifest.get("query_dates", {})
    if (
        not isinstance(zones, Mapping)
        or not set(zones) <= BOOTSTRAP_SOURCES
        or not all(v in (UTC_QUERY_DATES, LOCAL) for v in zones.values())
    ):
        raise SnapshotError("the snapshot manifest's query_dates is malformed")
    return frozenset(s for s, v in zones.items() if v == UTC_QUERY_DATES)


def _windows(records: Iterable[PaperRecord]) -> dict[str, dict[str, str]]:
    """Per claim source, its crawl window: the first and last `fetched_at` of its claims."""
    by_source: dict[str, list[datetime]] = {}
    for r in records:
        for c in r.provenance:
            by_source.setdefault(c.source, []).append(c.fetched_at)
    return {
        s: {"from": min(ts).isoformat(), "to": max(ts).isoformat()} for s, ts in sorted(by_source.items())
    }


def _sources(reports: Sequence[ImportReport], crawls: Sequence[Report]) -> dict[str, Any]:
    """manifest.json's `sources`: `ris` (the import reports; always present when no crawl is), then one entry
    per crawler source (`openreview_v2`, `openreview_v1`, `iclr_archive`, `neurips_proceedings`, `pmlr`), each
    with its reports and its own `crawl_window` (records.py and coverage.py read it; absent when its crawls
    fetched nothing; `common.sources_manifest`)."""
    sources: dict[str, Any] = {}
    if reports or not crawls:
        sources["ris"] = [r.to_manifest() for r in reports]
    sources.update(sources_manifest(crawls))
    return sources


def with_crawl_conflicts(result: DedupResult, crawls: Sequence[Report]) -> DedupResult:
    """`result` plus the disagreements a crawl found inside one source (a v1 note whose withdrawn invitation and
    `content.venue` disagree: `unresolved:openreview_v1`), each pointed at the output record its paper ended
    in (following `merges.csv`), so conflicts.csv holds every conflict, not only dedup's."""
    found = [c for r in crawls for c in getattr(r, "conflicts", ())]
    if not found:
        return result
    survivor = {m.merged_id: m.survivor_id for m in result.merges if m.merged_id != m.survivor_id}

    def final(rid: str) -> str:
        seen = {rid}
        while (nxt := survivor.get(rid)) is not None and nxt not in seen:
            rid = nxt
            seen.add(rid)
        return rid

    moved = {replace(c, id=final(c.id)) for c in found}
    return replace(result, conflicts=tuple(sorted({*result.conflicts, *moved})))


WITHHELD_VALUE = "(withheld: takedown)"  # what conflicts.csv says in place of a withheld abstract's text


@dataclass(frozen=True)
class Withholding:
    """What `withhold` did: the result with the abstracts withheld; `withheld`, the ids whose record lost an
    abstract or an abstract claim (what the manifest names); `followed`, each listed id this build holds under
    another id (merged into a survivor, or rekeyed: the same native id under a corrected venue or year) → the
    id it withheld instead; and `unmatched`, the listed ids no record of this build has or leads to."""

    result: DedupResult
    withheld: Withheld
    followed: Mapping[str, str]
    unmatched: tuple[str, ...]


def _successor(rid: str, result: DedupResult, held: set[str]) -> str | None:
    """The id this build holds `rid`'s paper under, when it holds it under another: the survivor it merged into
    (following merges.csv), else the one record with its native id (a rekey, the rule `diff` uses) when that
    native id is globally unique (`takedowns.global_native`)."""
    survivor = {m.merged_id: m.survivor_id for m in result.merges if m.merged_id != m.survivor_id}
    native = global_native(rid)  # None for a proceedings hash: in another year it is another paper (TASK-067)

    def follow(start: str) -> str:
        seen, at = {start}, start
        while (nxt := survivor.get(at)) is not None and nxt not in seen:
            at = nxt
            seen.add(at)
        return at

    if (at := follow(rid)) != rid and at in held:
        return at
    if native is None:
        return None
    same = [h for h in held if global_native(h) == native]
    if len(same) == 1:
        return same[0]
    # rekeyed *and* merged: the one merged-away id with its native id leads to the survivor
    merged = [m for m in survivor if global_native(m) == native]
    if not same and len(merged) == 1 and (at := follow(merged[0])) in held:
        return at
    return None


def withhold(result: DedupResult, ids: Withheld) -> Withholding:
    """`result` with the abstract of every record in `ids` (the takedown list) withheld: `abstract` null and its
    abstract claims dropped (`takedowns.withhold_record`), and the abstract texts of its conflicts.csv rows
    replaced by `WITHHELD_VALUE`. Applied after dedup and reconcile, so whatever the sources supply, the
    snapshot never holds a listed abstract. A listed id this build holds under another id (merged, or rekeyed
    by a corrected venue or year) is followed: its successor is withheld too, so the abstract never comes back
    under a new id (the list keeps the old id, which older index versions still hold). A listed id no record
    has or leads to is reported, never refused: a paper gone from its sources stays listed for the versions
    that still hold it (a typo is what `op takedown check` reports)."""
    if not ids:
        return Withholding(result, NONE, {}, ())
    held = {r.id for r in result.records}
    followed = {rid: nxt for rid in sorted(ids - held) if (nxt := _successor(rid, result, held)) is not None}
    unmatched = tuple(sorted(ids - held - followed.keys()))
    targets = (ids & held) | set(followed.values())
    changed = frozenset(
        r.id for r in result.records if r.id in targets and (r.abstract is not None or r.claims("abstract"))
    )
    records = tuple(withhold_record(r) if r.id in changed else r for r in result.records)
    conflicts = result.conflicts
    if any(
        c.id in targets and c.field == "abstract" for c in conflicts
    ):  # else left exactly as dedup wrote it
        conflicts = tuple(
            sorted(
                {  # a set: rows that differed only by their abstract texts are one row now
                    replace(c, value_a=WITHHELD_VALUE, value_b=WITHHELD_VALUE)
                    if c.id in targets and c.field == "abstract"
                    else c
                    for c in conflicts
                }
            )
        )
    return Withholding(replace(result, records=records, conflicts=conflicts), changed, followed, unmatched)


def render(
    result: DedupResult,
    reports: Sequence[ImportReport],
    built_at: datetime,
    crawls: Sequence[Report] = (),
    withheld: Withheld = NONE,
) -> dict[str, bytes]:
    """The snapshot's files. Everything but manifest.json's `built_at` is a function of the inputs.
    `crawls` are the crawlers' reports (OpenReview v2 and v1, ICLR, NeurIPS, PMLR). `withheld` are the ids
    whose abstracts `withhold` took out (`Withholding.withheld`: each a record of `result` with no abstract and
    no abstract claim left): the manifest then names them and counts them per venue-year and track, and they
    are not counted as missing abstracts (TASK-136). A listed record that had nothing to withhold is not
    named, so listing it leaves the snapshot byte-identical."""
    records = sorted(result.records, key=lambda r: r.id)
    if not records:
        raise SnapshotError("no records to snapshot")
    if any(not r.provenance for r in records):
        raise SnapshotError("a record has no provenance claims; every value must say where it came from")
    by_id = {r.id: r for r in records}
    if any(t not in by_id for r in records for c in r.claims("twin") for t in c.value or ()):  # type: ignore[union-attr]
        raise SnapshotError("a twin claim names a record this snapshot doesn't hold (TASK-159)")
    if any(i not in by_id or by_id[i].abstract is not None or by_id[i].claims("abstract") for i in withheld):
        raise SnapshotError("a withheld id is not a record whose abstract and abstract claims are gone")
    fetched = [c.fetched_at for r in records for c in r.provenance]
    lines = "".join(record_line(r) + "\n" for r in records).encode("utf-8")
    missing_by_track, sources_by_track, statuses = _per_track(records, withheld)
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
        "abstract_missing": _nested(records, lambda r: r.abstract is None and r.id not in withheld),
        "unknown_track": _nested(records, lambda r: r.track == "unknown"),
        "abstract_missing_by_track": missing_by_track,
        "sources_by_track": sources_by_track,
        "statuses_indexed": statuses,
        "crawl_windows": _windows(records),
        "merges": {"total": len(result.merges), **Counter(m.rule for m in result.merges)},
        "conflicts": {"total": len(result.conflicts), **Counter(c.resolution.split(":")[0] for c in result.conflicts)},
        "files": {"merges.csv": _sha256(merges), "conflicts.csv": _sha256(conflicts)},
        "sources": _sources(reports, crawls),
    }  # fmt: skip
    # what the RIS window's ends are (TASK-077, decision-025): converted to UTC, or (any entry) local wall time
    if reports:
        manifest["query_dates"] = {"ris": UTC_QUERY_DATES if all(r.utc_offset for r in reports) else LOCAL}
    # the records whose title or abstract the ingest caps trimmed (decision-026), written only when there are
    # any: a snapshot trimming nothing has the manifest it had before. Additive, like WITHHELD_KEYS
    if trimmed := [r.id for r in records if is_trimmed(r)]:
        manifest["trimmed"] = trimmed
    if withheld:
        manifest["withheld"] = sorted(withheld)
        manifest["abstract_withheld"] = _nested(records, lambda r: r.id in withheld)
        manifest["abstract_withheld_by_track"] = _by_track(records, lambda r: r.id in withheld)
    return {
        "records.jsonl": lines,
        "manifest.json": (json.dumps(manifest, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode(
            "utf-8"
        ),
        "merges.csv": merges,
        "conflicts.csv": conflicts,
    }


# what a rebuild must reproduce exactly: `withheld` too, since a listed record that never had an abstract leaves
# records.jsonl (and so the hash) as it was
AUDITED = ("files", "tokenizer_version", "record_schema_version", "withheld")
AUDIT_FILES = ("merges.csv", "conflicts.csv")


def _audit(snapshot: Path) -> dict[str, str]:
    """The audit files' hashes, as a manifest's `files` records them (both, always)."""
    return {f: _sha256((snapshot / f).read_bytes()) for f in AUDIT_FILES}


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


def build(
    cache: Path, snapshots: Path, built_at: datetime | None = None, takedowns: Withheld = NONE
) -> BuildResult:
    """Import, dedup and write a new immutable snapshot (or report the one that already has this hash), with
    every abstract `takedowns` lists withheld (`withhold`)."""
    began = time.monotonic()
    records, reports, crawls = load_sources(cache)
    result = with_crawl_conflicts(reconcile(dedup(records), crawled(crawls)).result, crawls)
    withholding = withhold(result, takedowns)
    result = withholding.result
    unexpected = tuple(unexpected_statuses(result.records))
    files = render(result, reports, built_at or datetime.now(UTC), crawls, withholding.withheld)

    def result_at(target: Path, created: bool) -> BuildResult:
        return BuildResult(target, snapshot_hash, created, unexpected, tuple(sorted(withholding.withheld)),
                           dict(withholding.followed), withholding.unmatched)  # fmt: skip

    manifest = json.loads(files["manifest.json"])
    snapshot_hash = manifest["snapshot_hash"]
    target = snapshots / f"{manifest['crawl_date']}-{snapshot_hash[:SHORT]}"
    trimmed = len(manifest.get("trimmed", ()))
    if trimmed:  # the build changed source text (decision-026): worth a look, once per build, never the ids
        log.warning("snapshot_trimmed", extra={"snapshot": target.name, "trimmed": trimmed})
    with storage.exclusive(snapshots):
        storage.sweep(snapshots)
        if target.exists():
            if not _holds(target, snapshot_hash, manifest):
                if _holds(target, snapshot_hash, {**manifest, "withheld": _withheld_or_none(target)}):
                    raise SnapshotError(
                        f"{target.name} holds these very records but names other withheld abstracts (a listed "
                        "record's abstract went from its sources since it was built): serve it as it is (the "
                        "API applies the takedown list to it), or build from a cache that changes a record",
                        reason="takedown_differs",
                    )
                raise SnapshotError(
                    f"{target.name} exists but isn't this snapshot in the current format; snapshots are "
                    "immutable: retire it (release-manager prune path) and build again"
                )
            storage.lock(target)  # a crash between placing and locking left it writable
            log.info(
                "snapshot_exists",
                extra={"snapshot": target.name, "snapshot_hash": snapshot_hash, "trimmed": trimmed,
                       "abstracts_withheld": len(withholding.withheld),
                       "takedowns_followed": len(withholding.followed),
                       "takedowns_unmatched": len(withholding.unmatched)},
            )  # fmt: skip
            return result_at(target, created=False)
        with storage.staging(snapshots) as tmp:
            for name, data in files.items():
                (tmp / name).write_bytes(data)
            created = _place_or_refuse(tmp, target, lambda t: _holds(t, snapshot_hash, manifest))
    log.info(
        "snapshot_built" if created else "snapshot_exists",
        extra={"snapshot": target.name, "snapshot_hash": snapshot_hash, "records": manifest["record_count"],
               "merges": manifest["merges"]["total"], "conflicts": manifest["conflicts"]["total"],
               "trimmed": trimmed, "abstracts_withheld": len(withholding.withheld),
               "takedowns_followed": len(withholding.followed),
               "takedowns_unmatched": len(withholding.unmatched),
               "unexpected_statuses": len(unexpected), "ms": elapsed_ms(began, time.monotonic)},
    )  # fmt: skip
    return result_at(target, created=created)


class _OnePass:
    """One read of a snapshot, shared by `iter_records` and `RecordFile`: its parsed manifest, then
    `records.jsonl` line by line (numbered from 1), each line hashed as it is read, so the file checked
    against `snapshot_hash` is the file read. Errors (OSError, ValueError) are the caller's to word."""

    def __init__(self, snapshot: Path) -> None:
        self.manifest: Any = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        self.path = snapshot / "records.jsonl"
        self._digest = hashlib.sha256()

    def lines(self) -> Iterator[tuple[int, bytes]]:
        with self.path.open("rb") as fh:
            for n, raw in enumerate(fh, start=1):
                self._digest.update(raw)
                yield n, raw

    def hexdigest(self) -> str:
        """The sha256 of the lines read so far (all of them, once `lines()` is exhausted)."""
        return self._digest.hexdigest()


def _id_order(previous: str, rid: str) -> str | None:
    """Why `rid` can't follow `previous` in a snapshot (ids strictly ascending, so unique), or None."""
    if rid == previous:
        return "duplicate id"
    if rid < previous:
        return "records are not sorted by id"
    return None


# RecordFile's cheap per-line check, named in pydantic's words as iter_records' full validation names them
_LINE_KIND = {
    "JSONDecodeError": "json_invalid",
    "ValueError": "json_invalid",
    "KeyError": "missing",
    "TypeError": "type_error",
}


def iter_records(snapshot: Path) -> Iterator[PaperRecord]:
    """A snapshot's records in file order, streamed in one pass. It must be a snapshot: every record valid
    (so a stale content_hash is caught), ids strictly ascending (so unique), and the bytes read hashing to
    the manifest's `snapshot_hash`, checked when the file ends (one read, so the file checked is the file
    read). A caller must not act on the records until iteration finishes without raising: `load_records`
    and `build_index` (which commits only after the last record) don't. Errors name the line only."""
    try:
        read = _OnePass(snapshot)
        manifest = read.manifest
        expected = manifest["snapshot_hash"] if isinstance(manifest, dict) else None
        previous = ""
        for n, raw in read.lines():
            try:
                r = PaperRecord.model_validate_json(raw)
            except ValidationError as e:
                kinds = sorted({str(err["type"]) for err in e.errors(include_input=False)})
                raise SnapshotError(
                    f"{snapshot.name} line {n}: invalid record ({', '.join(kinds)})"
                ) from None
            if out_of_order := _id_order(previous, r.id):
                raise SnapshotError(f"{snapshot.name} line {n}: {out_of_order}")
            previous = r.id
            yield r
    except (OSError, ValueError, KeyError) as e:
        if isinstance(e, SnapshotError):
            raise
        raise SnapshotError(f"{snapshot.name} is not a snapshot ({type(e).__name__})") from None
    if expected != read.hexdigest():
        raise SnapshotError(f"{snapshot.name}: records.jsonl doesn't match its manifest's snapshot_hash")
    try:  # the audit files, both of them, exactly as the manifest hashed them (the check _holds makes too)
        matches = manifest.get("files") == _audit(snapshot)
    except OSError:
        matches = False
    if not matches:
        raise SnapshotError(f"{snapshot.name}: merges.csv or conflicts.csv doesn't match its manifest")


def merges_on_disk(
    snapshots: Path, on_damaged: Callable[[SnapshotError], None] | None = None
) -> tuple[tuple[str, str], ...]:
    """Every (survivor, merged) pair the merges.csv of any snapshot under `snapshots` records, sorted: what
    the takedown list follows to the other ids a paper has had (TASK-067, `takedowns.same_paper`). Each file
    must hash to its manifest's `files` entry, else that snapshot is damaged (SnapshotError, reason
    `merges_mismatch`, naming it): raised, or, given `on_damaged`, handed to it and that snapshot alone skipped,
    so one damaged snapshot never drops the others' merges. A directory being written (a dot name: `.tmp-…`,
    `.lock`) or with no manifest.json is not a snapshot and is skipped."""

    def damaged(snapshot: Path, message: str) -> None:
        error = SnapshotError(message, reason="merges_mismatch", snapshot=snapshot.name)
        if on_damaged is None:
            raise error
        on_damaged(error)

    pairs: set[tuple[str, str]] = set()
    try:
        dirs = sorted(d for d in snapshots.iterdir() if not d.name.startswith(".") and d.is_dir())
    except FileNotFoundError:
        return ()
    for snapshot in dirs:
        try:
            manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            damaged(snapshot, f"{snapshot.name}'s manifest can't be read")
            continue
        try:
            blob = (snapshot / "merges.csv").read_bytes()
            if not isinstance(manifest, dict) or manifest["files"]["merges.csv"] != _sha256(blob):
                raise KeyError("merges.csv")
            rows = csv.DictReader(io.StringIO(blob.decode("utf-8")))
            found = {(row["survivor_id"], row["merged_id"]) for row in rows}
        except (OSError, ValueError, KeyError, TypeError):
            damaged(snapshot, f"{snapshot.name}: merges.csv doesn't match its manifest")
            continue
        pairs |= found
    return tuple(sorted(pairs))


def any_withheld(snapshots: Path) -> bool:
    """Whether any snapshot under `snapshots` withheld an abstract (its manifest names `withheld` ids): proof
    this deployment has takedowns, so a missing takedown list is a failure, never "nothing listed" (TASK-067).
    A manifest that can't be read counts as one that did (fail closed); a directory being written (a dot name)
    or with no manifest.json is skipped."""
    try:
        dirs = [d for d in snapshots.iterdir() if not d.name.startswith(".") and d.is_dir()]
    except FileNotFoundError:
        return False
    for snapshot in dirs:
        try:
            manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            return True
        if not isinstance(manifest, dict) or manifest.get("withheld", []) != []:
            return True
    return False


def load_records(snapshot: Path) -> dict[str, PaperRecord]:
    """A snapshot's records by id (all in memory; `iter_records` streams them)."""
    return {r.id: r for r in iter_records(snapshot)}


class _Claim(NamedTuple):
    """An abstract claim as `attribution` reads it, from a record line's raw JSON."""

    source: Any
    value: Any
    url: Any
    evidence: Any


class RecordFile:
    """Random access by id to a snapshot's records, holding only each line's byte range in memory (the API's
    `GET /papers/{id}`: the full record, provenance included, which the index doesn't store).

    Opening makes one pass over `records.jsonl`: ids strictly ascending, and the bytes hashing to the
    manifest's `snapshot_hash` (so the file indexed is the snapshot named). The same pass counts the records
    per (venue, year, track, status), the missing abstracts per (venue, year) and per (venue, year, track), and
    the claim sources per (venue, year, track), and keeps the manifest it read, so `GET /coverage` checks the
    manifest's counts against the records; and each record's abstract attribution (`attributions`, TASK-134),
    which `GET /search` reads per hit with no file I/O. The ids the manifest names as `withheld` (a takedown,
    TASK-136) must each be a record with no abstract and no abstract claim; they are counted per venue-year and
    per track as withheld, never as missing. A lookup reads its one line and
    validates it as a `PaperRecord`, which re-checks its `content_hash`. Snapshots are sealed read-only, so
    the bytes can't change underneath. Thread-safe: every lookup opens the file itself."""

    def __init__(self, snapshot: Path) -> None:
        self.path = snapshot / "records.jsonl"
        self.cells: Counter[tuple[str, int, str, str]] = Counter()  # (venue, year, track, status) → records
        self.abstract_missing: Counter[tuple[str, int]] = Counter()  # (venue, year) → no abstract
        # (venue, year, track) → no abstract (0 included), and the claim sources of its records (TASK-082)
        self.track_missing: Counter[tuple[str, int, str]] = Counter()
        self.track_sources: dict[tuple[str, int, str], set[str]] = {}
        # id → its abstract's attribution (TASK-134): computed here, once, so a search page is dict lookups
        self.attributions: dict[str, Attribution | None] = {}
        # the abstracts a takedown withheld (TASK-136): (venue, year) and (venue, year, track) → withheld
        self.abstract_withheld: Counter[tuple[str, int]] = Counter()
        self.track_withheld: Counter[tuple[str, int, str]] = Counter()
        try:
            read = _OnePass(snapshot)
            manifest = read.manifest
            self.manifest: dict[str, Any] = manifest
            self.snapshot_hash: str = manifest["snapshot_hash"]
            listed = manifest.get("withheld", [])
            if not isinstance(listed, list) or not all(isinstance(i, str) for i in listed):
                raise SnapshotError(
                    f"{snapshot.name}'s manifest names its withheld ids other than as a list",
                    reason="withheld_invalid",
                )
            self.withheld: frozenset[str] = frozenset(listed)
            found: set[str] = set()
            self._at: dict[str, tuple[int, int]] = {}
            previous, offset = "", 0
            for n, raw in read.lines():
                # no full PaperRecord validation here (a lookup validates its one line), but a bad line is
                # named the way iter_records names it: "line N: invalid record (<kind>)" / its id-order reason
                try:
                    line = json.loads(raw)
                    rid = line["id"]
                    cell = (line["venue"], line["year"], line["track"], line["status"])
                    withheld = rid in self.withheld
                    no_abstract = line["abstract"] is None and not withheld
                    claimed = {c["source"] for c in line["provenance"]}
                    if not isinstance(rid, str) or not all(isinstance(c, str) for c in claimed):
                        raise TypeError(rid)
                    about = [_Claim(c["source"], c["value"], c.get("url"), c.get("evidence"))
                             for c in line["provenance"] if c["field"] == "abstract"]  # fmt: skip
                    urls = line["urls"]
                    credit = attribution(
                        line["abstract"],
                        about,
                        forum=urls["forum"],
                        proceedings=urls["proceedings"],
                        native=rid.split(":", 3)[-1],  # a malformed id matches no page
                    )
                except (ValueError, KeyError, TypeError) as e:
                    raise SnapshotError(
                        f"{snapshot.name} line {n}: invalid record ({_LINE_KIND[type(e).__name__]})"
                    ) from None
                if out_of_order := _id_order(previous, rid):
                    raise SnapshotError(f"{snapshot.name} line {n}: {out_of_order}")
                if withheld:
                    if line["abstract"] is not None or about:
                        raise SnapshotError(
                            f"{snapshot.name} line {n}: a withheld record still holds its abstract",
                            reason="withheld_abstract_present",
                        )
                    found.add(rid)
                    self.abstract_withheld[(line["venue"], line["year"])] += 1
                    self.track_withheld[(line["venue"], line["year"], line["track"])] += 1
                self._at[rid] = (offset, len(raw))
                self.attributions[rid] = credit
                self.cells[cell] += 1
                track = (line["venue"], line["year"], line["track"])
                self.track_missing[track] += no_abstract
                self.track_sources.setdefault(track, set()).update(claimed)
                if no_abstract:
                    self.abstract_missing[(line["venue"], line["year"])] += 1
                previous, offset = rid, offset + len(raw)
        except FileNotFoundError:
            raise SnapshotError(
                f"{snapshot.name} is not on this instance", reason="snapshot_missing"
            ) from None
        except SnapshotError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise SnapshotError(
                f"{snapshot.name} is not a snapshot ({type(e).__name__})", reason="snapshot_unreadable"
            ) from None
        if found != self.withheld:
            raise SnapshotError(
                f"{snapshot.name}'s manifest names a withheld id it has no record of",
                reason="withheld_invalid",
            )
        if read.hexdigest() != self.snapshot_hash:
            raise SnapshotError(
                f"{snapshot.name}: records.jsonl doesn't match its manifest's snapshot_hash",
                reason="snapshot_hash_mismatch",
            )

    def __len__(self) -> int:
        return len(self._at)

    def ids(self) -> Iterable[str]:
        """Every record id the snapshot holds, ascending."""
        return self._at.keys()

    def __contains__(self, rid: object) -> bool:
        return rid in self._at

    def get(self, rid: str) -> PaperRecord | None:
        """The record with id `rid`, or None if the snapshot has none."""
        at = self._at.get(rid)
        if at is None:
            return None
        with self.path.open("rb") as fh:
            fh.seek(at[0])
            raw = fh.read(at[1])
        try:
            return PaperRecord.model_validate_json(raw)
        except ValidationError:
            raise SnapshotError(f"{self.path.parent.name}: the record at byte {at[0]} is invalid") from None


def diff(a: Path, b: Path) -> dict[str, Any]:
    """From snapshot `a` to `b` (snapshots skill §CLI): ids added and removed; `rekeyed` ids (the same
    paper, its venue or year corrected so its id changed), with the fields that differ; `changed` ids
    naming the hashed fields that differ; counts of display-only and provenance-only changes; and
    `abstract_withheld`, the ids whose abstract a takedown withheld in `b` but not `a` (`added`) and the reverse
    (`lifted`), from the manifests' `withheld` (TASK-136)."""
    old, new = load_records(a), load_records(b)  # each verified against its manifest's snapshot_hash
    was, now = _withheld(a), _withheld(b)
    added, removed = new.keys() - old.keys(), old.keys() - new.keys()
    # a rekey only when exactly one removed and one added id share a globally unique native id: anything else
    # (two papers into one, one into two, a proceedings hash, which in another year is another paper; TASK-067)
    # is reported as added and removed, so a lost record is never hidden
    gone_by_native = Counter(old[i].native for i in removed)
    new_by_native: dict[str, list[str]] = {}
    for i in added:
        new_by_native.setdefault(new[i].native, []).append(i)
    rekeyed = {
        i: new_by_native[old[i].native][0]
        for i in sorted(removed)
        if global_native(i) is not None  # the one place the rule is applied: a hash never rekeys
        and gone_by_native[old[i].native] == 1
        and len(new_by_native.get(old[i].native, [])) == 1
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
        "abstract_withheld": {"added": sorted(now - was), "lifted": sorted(was - now)},
    }


def _withheld_or_none(snapshot: Path) -> list[str] | None:
    """A snapshot's manifest `withheld` as written (None when it has none), for comparing with a fresh one."""
    try:
        listed = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8")).get("withheld")
    except (OSError, ValueError, AttributeError):
        return None
    return listed if isinstance(listed, list) else None


def _withheld(snapshot: Path) -> frozenset[str]:
    """The ids a snapshot's manifest names as `withheld` (none when it has no such key)."""
    try:
        listed = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8")).get("withheld", [])
    except (OSError, ValueError, AttributeError):
        raise SnapshotError(f"{snapshot.name}'s manifest is unreadable") from None
    if not isinstance(listed, list) or not all(isinstance(i, str) for i in listed):
        raise SnapshotError(f"{snapshot.name}'s manifest names its withheld ids other than as a list")
    return frozenset(listed)
