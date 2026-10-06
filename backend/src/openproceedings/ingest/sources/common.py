"""What every crawler shares above the HTTP layer (spec 01 §Pipeline; snapshots skill §manifest.json `sources`):
the crawl report and the manifest entry it feeds, the crawl markers that tell `op snapshot build` a crawl
finished and how it is replayed, the crawl error, and the proceedings miners' helpers (the title check before
an abstract is taken, records built from their own claims).

A crawler runs twice: online under `op ingest` (fetching into its cache), and offline under `op snapshot build`
(the cache only), so a snapshot is a function of the cache. A crawl counts only once it finished and wrote its
marker (`<source dir>/crawls/<name>.json`, written atomically); a crawl that stopped half-way resumes from the
cache. `Crawls` is the one ingest loop and the one replay: `ingest` crawls under the source's lock and writes
each finished crawl's marker where `replay` reads them; `replay` re-runs every marker of a source, in key order,
offline; a marked crawl whose responses are no longer cached is an error, never a silently smaller snapshot.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Protocol

from openproceedings import storage
from openproceedings.ingest.dedup import resolve, title_key
from openproceedings.ingest.record import Claim, PaperRecord, abstract_text
from openproceedings.ingest.sources.http import FetchError, SourceError

_LEADING_MATH = re.compile(r"^\s*\$[^$]+\$[\s:,.-]*")
SNIPPET = "…"


class CrawlError(SourceError):
    """A listing can't be mined or replayed as it stands (not published, a heading the table doesn't name, a
    volume outside the table, a listing that changed under a resumed crawl, an unreadable crawl marker): the
    message says why and what to do."""

    reason = "crawl_inconsistent"


MinerError = CrawlError  # the proceedings miners' name for it


# --- the report ------------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class Report:
    """One crawl's report (a proceedings listing, an OpenReview venue-year): `to_manifest()` goes into the
    snapshot manifest's `sources[<source>][<manifest_key>]`, and every response's fetch time into the source's
    `crawl_window` (`coverage.crawl_dates` reads it)."""

    source: str
    fetched: list[datetime] = field(default_factory=list)  # every response's fetched_at, from the cache

    manifest_key: ClassVar[str] = "crawls"

    def crawl_window(self) -> dict[str, str] | None:
        return window(self.fetched)

    def to_manifest(self) -> dict[str, Any]:
        raise NotImplementedError


def window(fetched: Iterable[datetime]) -> dict[str, str] | None:
    times = list(fetched)
    return {"from": min(times).isoformat(), "to": max(times).isoformat()} if times else None


def sources_manifest(reports: Iterable[Report]) -> dict[str, Any]:
    """manifest.json's `sources` entries for the crawlers: per source, its reports under the report type's
    `manifest_key` (`crawls`, `listings`) and, when any crawl fetched something, its `crawl_window`."""
    grouped: dict[str, list[Report]] = {}
    for r in reports:
        grouped.setdefault(r.source, []).append(r)
    out: dict[str, Any] = {}
    for source, mine in grouped.items():
        entry: dict[str, Any] = {mine[0].manifest_key: [r.to_manifest() for r in mine]}
        if span := window(t for r in mine for t in r.fetched):
            entry["crawl_window"] = span
        out[source] = entry
    return out


# --- progress ---------------------------------------------------------------------------------------------

PROGRESS_SECONDS = 30.0  # logging-standards: a long crawl's periodic summary, at most this often


class Heartbeat:
    """When a long crawl's next progress line is due: at most one every `every` seconds on a monotonic clock
    (the HTTP client's, so a test's fake clock drives it), never per item (TASK-116)."""

    def __init__(self, monotonic: Callable[[], float], every: float = PROGRESS_SECONDS) -> None:
        self._monotonic, self._every = monotonic, every
        self._last = monotonic()

    def due(self) -> bool:
        now = self._monotonic()
        if now - self._last < self._every:
            return False
        self._last = now
        return True


# --- crawl markers and the one replay ----------------------------------------------------------------------


def write_marker(directory: Path, name: str, body: Mapping[str, Any]) -> None:
    """Record that a crawl finished (atomically: a crash leaves no marker, and the next run resumes from the
    cache)."""
    storage.write_json(directory / f"{name}.json", dict(body))


def read_markers(directory: Path) -> list[tuple[str, dict[str, Any]]]:
    """Every finished crawl's marker (file name, body), in name order; hidden and `.tmp-` files are never
    markers."""
    out = []
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("."):
            continue
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            body = None
        if not isinstance(body, dict):
            raise CrawlError(
                f"crawl marker {path.name} is unreadable; crawl it again", reason="crawl_file_invalid"
            )
        out.append((path.name, body))
    return out


class Mined(Protocol):
    """What replaying one marked crawl gives."""

    @property
    def records(self) -> Sequence[PaperRecord]: ...
    @property
    def reports(self) -> Sequence[Report]: ...


@dataclass(frozen=True)
class Crawls[M: Mined]:
    """One source's finished crawls: where its markers are, what identifies one (`key`: the replay order, and
    a marker that says less is unreadable), and how one is re-run from the cache with no network. The source's
    directory (the lock `op ingest` holds) is the marker directory's parent."""

    directory: Callable[[Path], Path]  # the cache → this source's marker directory
    key: Callable[[Mapping[str, Any]], tuple[Any, ...]]
    label: Callable[[tuple[Any, ...]], str]  # a key → "NeurIPS 2013", for an error
    command: str  # what re-crawls it
    run: Callable[[Path, tuple[Any, ...]], M]  # (the cache, a key) → the replayed crawl

    def ingest[K](
        self, cache: Path, keys: Iterable[K], crawl: Callable[[K], M],
        marker: Callable[[K, M], tuple[str, Mapping[str, Any]] | None],
    ) -> list[M]:  # fmt: skip
        """The one `op ingest` loop: one run at a time per source (an exclusive lock on the source's
        directory), each key crawled in order, and each finished crawl's marker (`marker` → its file name and
        body, or None for a dry run or an incomplete crawl) written where `replay` reads it."""
        directory = self.directory(cache)
        out = []
        with storage.exclusive(directory.parent):
            for key in keys:
                mined = crawl(key)
                out.append(mined)
                if (m := marker(key, mined)) is not None:
                    write_marker(directory, *m)
        return out

    def replay(self, cache: Path) -> list[M]:
        keys = set()
        for name, marker in read_markers(self.directory(cache)):
            try:
                keys.add(self.key(marker))
            except (KeyError, TypeError, ValueError):
                raise CrawlError(f"crawl marker {name} is unreadable; crawl it again",
                                 reason="crawl_file_invalid") from None  # fmt: skip
        out = []
        for key in sorted(keys):
            try:
                out.append(self.run(cache, key))
            except FetchError as e:
                raise CrawlError(f"{self.label(key)} is marked crawled but {e}; re-run {self.command}",
                                 reason=e.reason) from e  # fmt: skip
        return out


# --- the proceedings miners -------------------------------------------------------------------------------


def titles_match(listed: str, page: str | None) -> bool:
    """Is the abstract page about the listed paper? The same title key (the token contract), tolerating a
    leading `$…$` formula that one side drops."""
    if not page:
        return False

    def keys(t: str) -> set[str]:
        return {k for k in (title_key(t), title_key(_LEADING_MATH.sub("", t))) if k}

    return bool(keys(listed) & keys(page))


def clean_abstract(text: str | None) -> tuple[str | None, int]:
    """An abstract as a record may hold it, or None, and how many control characters became a space
    (`record.abstract_text`, decision-044; the claim's evidence says so). Empty, or starting or ending with `…`
    (a snippet, not an abstract; spec 01), is missing. An ellipsis inside (`x₁, …, x_n`) is kept."""
    text, replaced = abstract_text(text or "")
    if not text or text.startswith(SNIPPET) or text.endswith(SNIPPET):
        return None, 0
    return text, replaced


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


@dataclass(kw_only=False)
class ListingReport(Report):
    """One proceedings listing's crawl, for the snapshot manifest's `sources` (and the ingest command's output).
    Every miner appends the index page's fetch first, so `fetched[0]` is when the listing was read (reconcile's
    absence claims carry it)."""

    source: str  # iclr_archive | neurips_proceedings | pmlr
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
    abstract_control_characters: int = (
        0  # records whose abstract had a control character replaced (decision-044)
    )
    to_fetch: int | None = None  # a dry run: paper pages not yet in the cache (never in a manifest)
    see_also: list[str] = field(default_factory=list)  # other volumes the page points to, not crawled

    manifest_key: ClassVar[str] = "listings"

    def count(self, record: PaperRecord, missing: str | None, spaced: int = 0) -> None:
        """Count one record made from this listing (after it validated); `spaced` is how many control characters
        its abstract lost (`clean_abstract`'s own count, never read back from the evidence; TASK-199)."""
        self.records += 1
        self.abstract_control_characters += spaced > 0
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
        if self.abstract_control_characters:  # listed only when there are any, so a listing's shape is kept
            out["abstract_control_characters"] = self.abstract_control_characters
        if self.volume is not None:
            out["volume"] = self.volume
        if self.see_also:
            out["see_also"] = list(self.see_also)
        if self.to_fetch is not None:
            out["to_fetch"] = self.to_fetch
        if span := self.crawl_window():
            out["crawl_window"] = span
        return dict(sorted(out.items()))
