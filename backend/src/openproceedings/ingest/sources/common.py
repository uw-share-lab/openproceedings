"""What the proceedings miners share: the per-listing report, the title check before an abstract is taken,
records built from their own claims, and the crawl markers that tell `op snapshot build` a listing's crawl
finished (spec 01 §Pipeline; snapshots skill §manifest.json `sources`).

A miner turns one listing (a NeurIPS year page, a PMLR volume index) into records. It runs twice: online
under `op ingest` (fetching into the page cache), and offline under `op snapshot build` (the cache only),
so a snapshot is a function of the cache. A listing counts only once its crawl finished and wrote its
marker (`<cache>/<source>/crawls/<name>.json`); a crawl that stopped half-way resumes from the cache.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from openproceedings import storage
from openproceedings.ingest.dedup import resolve, title_key
from openproceedings.ingest.record import Claim, PaperRecord

_LEADING_MATH = re.compile(r"^\s*\$[^$]+\$[\s:,.-]*")
SNIPPET = "…"


class MinerError(Exception):
    """A listing can't be mined as it stands (not published, a heading the table doesn't name, a volume
    outside the table): the message says why; `reason` is a constant for the log."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


def titles_match(listed: str, page: str | None) -> bool:
    """Is the abstract page about the listed paper? The same title key (the token contract), tolerating a
    leading `$…$` formula that one side drops."""
    if not page:
        return False

    def keys(t: str) -> set[str]:
        return {k for k in (title_key(t), title_key(_LEADING_MATH.sub("", t))) if k}

    return bool(keys(listed) & keys(page))


def clean_abstract(text: str | None) -> str | None:
    """An abstract as a record may hold it, or None: empty, or starting or ending with `…` (a snippet, not
    an abstract; spec 01), is missing. An ellipsis inside (`x₁, …, x_n`) is kept."""
    if not text or text.startswith(SNIPPET) or text.endswith(SNIPPET):
        return None
    return text


def missing_reason(page_ok: bool, title_matches: bool, abstract: str | None) -> str | None:
    """Why a record has no abstract (None when it has one): `page_missing` (404/410), `title_mismatch` (the
    page's citation_title isn't the listed title), or `no_abstract` (empty, or a snippet)."""
    if abstract is not None:
        return None
    return "page_missing" if not page_ok else "title_mismatch" if not title_matches else "no_abstract"


def record_from_claims(record_id: str, claims: list[Claim]) -> PaperRecord:
    """The record its claims resolve to (decision-005's precedence, the same code dedup runs), so the record
    and its provenance can never disagree."""
    record, conflicts = resolve(record_id, claims)
    if conflicts:  # one source, one claim per field: a conflict here is a miner bug
        raise ValueError(f"{record_id}: the miner's own claims conflict")
    return record


@dataclass
class ListingReport:
    """One listing's crawl, for the snapshot manifest's `sources` (and the ingest command's output)."""

    source: str  # neurips_proceedings | pmlr
    venue: str
    year: int
    listing: str  # the index URL
    role: str  # primary | confirm (OpenReview is primary for that venue-year)
    stated: int | None  # the page's own count (NeurIPS) or the volume table's verified count (PMLR)
    volume: int | None = None
    listed: int = 0  # entries on the index page
    records: int = 0
    skipped: Counter[str] = field(default_factory=Counter)  # reason → entries not made into records
    tracks: Counter[str] = field(default_factory=Counter)
    abstract_missing: int = 0
    abstract_title_mismatch: int = 0  # of abstract_missing: the page's citation_title isn't the listed title
    page_missing: int = 0  # of abstract_missing: the paper page answered 404/410
    unknown_track: int = 0
    fetched: list[datetime] = field(default_factory=list)
    to_fetch: int | None = None  # a dry run: paper pages not yet in the cache (never in a manifest)
    see_also: list[str] = field(default_factory=list)  # other volumes the page points to, not crawled

    def count(self, record: PaperRecord, missing: str | None) -> None:
        """Count one record made from this listing (after it validated)."""
        self.records += 1
        self.tracks[record.track] += 1
        self.unknown_track += record.track == "unknown"
        if missing is not None:
            self.abstract_missing += 1
            self.page_missing += missing == "page_missing"
            self.abstract_title_mismatch += missing == "title_mismatch"

    @property
    def count_ok(self) -> bool:
        """Did we parse every entry the listing says it has? (None stated: nothing to compare with.)"""
        return self.stated is None or self.stated == self.listed

    def to_manifest(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "source": self.source, "venue": self.venue, "year": self.year, "listing": self.listing,
            "role": self.role, "stated": self.stated, "listed": self.listed, "count_ok": self.count_ok,
            "records": self.records, "skipped": dict(sorted(self.skipped.items())),
            "tracks": dict(sorted(self.tracks.items())), "abstract_missing": self.abstract_missing,
            "abstract_title_mismatch": self.abstract_title_mismatch, "page_missing": self.page_missing,
            "unknown_track": self.unknown_track,
        }  # fmt: skip
        if self.volume is not None:
            out["volume"] = self.volume
        if self.see_also:
            out["see_also"] = list(self.see_also)
        if self.to_fetch is not None:
            out["to_fetch"] = self.to_fetch
        if self.fetched:
            out["crawl_window"] = {"from": min(self.fetched).isoformat(), "to": max(self.fetched).isoformat()}
        return dict(sorted(out.items()))


def source_manifest(reports: list[ListingReport]) -> dict[str, Any]:
    """A source's `sources` entry: its crawl window (`coverage.crawl_dates` reads it) and one report per
    listing."""
    fetched = [t for r in reports for t in r.fetched]
    out: dict[str, Any] = {"listings": [r.to_manifest() for r in reports]}
    if fetched:
        out["crawl_window"] = {"from": min(fetched).isoformat(), "to": max(fetched).isoformat()}
    return out


# --- crawl markers ---------------------------------------------------------------------------------------


def marker_dir(cache: Path, source_dir: str) -> Path:
    return cache / source_dir / "crawls"


def write_marker(cache: Path, source_dir: str, name: str, body: dict[str, Any]) -> None:
    """Record that a listing's crawl finished (atomically: a crash leaves no marker, and the next run
    resumes from the page cache)."""
    directory = marker_dir(cache, source_dir)
    directory.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(body, sort_keys=True, indent=1) + "\n").encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=storage.TMP, suffix=".json")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            storage.fsync(fh.fileno())
        os.replace(tmp, directory / f"{name}.json")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def markers(cache: Path, source_dir: str) -> list[dict[str, Any]]:
    """Every finished crawl's marker, in name order; hidden and `.tmp-` files are never markers."""
    out = []
    for path in sorted(marker_dir(cache, source_dir).glob("*.json")):
        if path.name.startswith("."):
            continue
        body = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(body, dict):
            raise ValueError(f"crawl marker {path.name} is not an object")
        out.append(body)
    return out
