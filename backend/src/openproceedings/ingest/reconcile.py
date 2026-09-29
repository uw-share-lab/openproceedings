"""Reconcile OpenReview acceptance against the crawled proceedings (decision-005; spec 01 §Pipeline 4;
dedup-rules skill §Reconcile; TASK-072).

Where a venue-year's official proceedings (the ICLR archive, NeurIPS proceedings, a PMLR volume) are
published and crawled, they decide acceptance: an OpenReview-accepted paper they don't list gets
`status=unknown` and a `conflicts.csv` row, never silently accepted or rejected. Dedup can't decide that
alone: it needs to know which listings were crawled, and whether completely. So this step runs after dedup.

- **Crawled** (`crawled`): a (proceedings source, venue, year) whose every listing report says its stated
  count matched and every entry became a record (duplicates of an entry aside). One incomplete listing and
  the venue-year is left alone: an entry the crawl skipped may be the paper.
- **Covered tracks**: only the tracks the crawled listings hold (`main`, `datasets_benchmarks`, `position`;
  the proceedings host no others). A listing's own track claim says which; a listing that can't say (a PMLR
  volume mixing main and position papers: `unknown`) covers the track of the record it merged into. A
  track no listing holds (a track published later, or never) is never judged.
- **Unlisted**: a record whose status is OpenReview's `accepted` (it won `PRECEDENCE`), in a covered
  venue-year and track, that is no listing (no proceedings claim or proceedings id) and shares no title key
  and no forum id with one. A record that shares one but stayed apart (an ambiguous title) may be the
  listed paper: it keeps its status, and dedup's not-merged row already names it.

An unlisted record gains one claim per crawled source: `status=unknown` from that source, its evidence starting
`not listed:` (`dedup.is_absence`), its listing as the URL, the crawl's last fetch as `fetched_at`, and the evidence. `resolve` then gives the
record `unknown` (the proceedings outrank OpenReview for status) and the `precedence:<source>` conflicts.csv
row; the OpenReview claim is kept. The record still equals what its claims resolve to, and an absence claim
gives it no proceedings source, so dedup run again changes nothing; this step strips absence claims before
it judges, so it is idempotent too.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import cast

from openproceedings.ingest.dedup import (
    ABSENT,
    ABSENT_EVIDENCE,
    PRECEDENCE,
    Conflict,
    DedupResult,
    forum_ids,
    is_absence,
    proceedings_ids,
    resolve,
    title_key,
)
from openproceedings.ingest.record import Claim, PaperRecord, Source
from openproceedings.ingest.sources.common import ListingReport, Report

log = logging.getLogger(__name__)

PROCEEDINGS_SOURCES: frozenset[str] = frozenset({"iclr_archive", "neurips_proceedings", "pmlr"})
PROCEEDINGS_TRACKS: frozenset[str] = frozenset({"main", "datasets_benchmarks", "position"})
OPENREVIEW_SOURCES: frozenset[str] = frozenset({"openreview_v2", "openreview_v1"})

type Key = tuple[str, str, int]  # (proceedings source, venue, year)


@dataclass(frozen=True)
class Crawl:
    """A proceedings source's crawl of one venue-year: its listings (index URLs, in order) and the tracks each
    claims, the last fetch, and whether every listing is complete."""

    source: str
    venue: str
    year: int
    listings: tuple[tuple[str, frozenset[str]], ...]  # (index URL, the tracks its records claim)
    fetched_at: datetime
    complete: bool


def complete(report: ListingReport) -> bool:
    """Every entry the listing states became a record, one per paper (a repeated entry is no missing paper)."""
    return report.count_ok and report.records + report.skipped.get("duplicate", 0) == report.listed


def crawled(reports: Iterable[Report]) -> dict[Key, Crawl]:
    """The proceedings listings' reports, per (source, venue, year)."""
    grouped: dict[Key, list[ListingReport]] = defaultdict(list)
    for r in reports:
        if isinstance(r, ListingReport) and r.source in PROCEEDINGS_SOURCES:
            grouped[(r.source, r.venue, r.year)].append(r)
    out = {}
    for key, group in sorted(grouped.items()):
        fetched = [t for r in group for t in r.fetched]
        if not fetched:
            continue  # nothing read, nothing to say
        out[key] = Crawl(
            group[0].source, group[0].venue, group[0].year,
            tuple((r.listing, frozenset(r.tracks)) for r in group), max(fetched), all(complete(r) for r in group),
        )  # fmt: skip
    return out


def _without_absence(record: PaperRecord) -> PaperRecord:
    if not any(is_absence(c) for c in record.provenance):
        return record
    bare, _ = resolve(record.id, [c for c in record.provenance if not is_absence(c)])
    return bare


def _listing_sources(record: PaperRecord) -> frozenset[str]:
    return frozenset(
        c.source for c in record.provenance if c.source in PROCEEDINGS_SOURCES and not is_absence(c)
    )


def _names(record: PaperRecord) -> set[tuple[str, str]]:
    """What could make the record a listing's paper: its kept title claims' keys and its forum ids."""
    keys = {("title", k) for c in record.provenance if c.field == "title" and (k := title_key(str(c.value)))}
    return keys | {("forum", f) for f in forum_ids(record)}


def _is_listing(record: PaperRecord) -> bool:
    """A listing, as dedup judges one: a proceedings claim, or a proceedings id in a URL claim."""
    return bool(_listing_sources(record) or proceedings_ids(record.provenance))


def _openreview_accepted(record: PaperRecord) -> bool:
    """The record's status is OpenReview's `accepted`: the best-ranked status claim is an OpenReview one."""
    order = PRECEDENCE["status"]
    ranked = sorted(
        (c for c in record.provenance if c.field == "status"), key=lambda c: order.index(c.source)
    )
    return bool(ranked) and ranked[0].source in OPENREVIEW_SOURCES and record.status == "accepted"


def _covered(records: Iterable[PaperRecord], crawls: Mapping[Key, Crawl]) -> dict[Key, set[str]]:
    """The tracks each complete crawl's listings hold: a listing's own track claim, or, where the listing
    can't say (`unknown`), the track of the record it merged into."""
    out: dict[Key, set[str]] = defaultdict(set)
    for r in records:
        for c in r.provenance:
            key = (c.source, r.venue, r.year)
            if c.field != "track" or key not in crawls or not crawls[key].complete:
                continue
            track = r.track if c.value == "unknown" else c.value
            if track in PROCEEDINGS_TRACKS:
                out[key].add(str(track))
    return out


def _absence(crawl: Crawl, track: str) -> Claim:
    holding = [url for url, tracks in crawl.listings if track in tracks or "unknown" in tracks]
    names = ", ".join(url for url, _ in crawl.listings)
    return Claim(
        field="status", value=ABSENT, source=cast(Source, crawl.source), url=(holding or [crawl.listings[0][0]])[0],
        fetched_at=crawl.fetched_at,
        evidence=f"{ABSENT_EVIDENCE} OpenReview says accepted, but the crawled {crawl.venue} {crawl.year} {track} "
        f"listings ({names}) hold no record with its title or forum id (decision-005)",
    )  # fmt: skip


@dataclass(frozen=True)
class Reconciled:
    result: DedupResult
    unlisted: dict[tuple[str, int, str], int]  # (venue, year, track) → records made unknown
    # OpenReview-accepted and covered, but sharing a title key or forum id with a listing it didn't merge with
    shares_listing: int
    incomplete: tuple[Key, ...]  # crawls left alone: a listing skipped an entry or miscounted


def reconcile(result: DedupResult, crawls: Mapping[Key, Crawl]) -> Reconciled:
    """`result` with every unlisted OpenReview-accepted record set to `unknown` by an absence claim (module
    doc). Merges are unchanged; conflicts gain each such record's `precedence:<source>` status row."""
    bare = [_without_absence(r) for r in result.records]
    covered = _covered(bare, crawls)
    listed: dict[tuple[str, int], set[tuple[str, str]]] = defaultdict(set)  # (venue, year) → listings' names
    for r in bare:
        if _is_listing(r):
            listed[(r.venue, r.year)] |= _names(r)
    out: list[PaperRecord] = []
    changed: dict[str, list[Conflict]] = {}  # id → its status rows, for every record this step changed
    unlisted: Counter[tuple[str, int, str]] = Counter()
    shares = 0
    for before, r in zip(result.records, bare, strict=True):
        sources = sorted(k for k in crawls if k[1:] == (r.venue, r.year) and r.track in covered.get(k, ()))
        if sources and _openreview_accepted(r) and not _is_listing(r):
            if _names(r) & listed[(r.venue, r.year)]:
                shares += 1
            else:
                r, _ = resolve(r.id, [*r.provenance, *(_absence(crawls[k], r.track) for k in sources)])
                unlisted[(r.venue, r.year, r.track)] += 1
        if r != before:  # made unknown, or an earlier absence claim no longer holds
            changed[r.id] = [c for c in resolve(r.id, r.provenance)[1] if c.field == "status"]
        out.append(r)
    kept = {
        c for c in result.conflicts
        if not (c.id in changed and c.field == "status" and c.resolution.startswith("precedence:"))
    }  # fmt: skip
    fresh = {c for rows in changed.values() for c in rows}
    incomplete = tuple(k for k, c in crawls.items() if not c.complete)
    log.info(
        "proceedings_reconciled",
        extra={"crawls": len(crawls), "unlisted": sum(unlisted.values()), "shares_listing": shares,
               "incomplete": len(incomplete)},
    )  # fmt: skip
    if incomplete:
        log.warning(
            "proceedings_reconcile_skipped",
            extra={"crawls": [f"{s}:{v}:{y}" for s, v, y in incomplete]},
        )
    return Reconciled(
        replace(result, records=tuple(out), conflicts=tuple(sorted(kept | fresh))),
        dict(sorted(unlisted.items())), shares, incomplete,
    )  # fmt: skip
