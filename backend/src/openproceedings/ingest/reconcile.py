"""Reconcile OpenReview acceptance against the crawled proceedings (decision-005; spec 01 §Pipeline 4;
dedup-rules skill §Reconcile; TASK-072).

Where a venue-year's official proceedings (the ICLR archive, NeurIPS proceedings, a PMLR volume) are
published and crawled, they decide acceptance: an OpenReview-accepted paper they don't list gets
`status=unknown` and a `conflicts.csv` row, never silently accepted or rejected. Dedup can't decide that
alone: it needs to know which listings were crawled, and whether completely. So this step runs after dedup.

- **Crawled** (`crawled`): a (proceedings source, venue, year) whose every listing report states a count, the
  count matched, every entry became a record (duplicates of an entry aside) and the page names no other volume
  left uncrawled (`see_also`). One incomplete listing and the venue-year is left alone: an entry the crawl
  skipped, or a volume it didn't follow, may hold the paper; and with no stated count nothing says the page
  showed every entry.
- **Covered tracks**: only the tracks the crawled listings hold (`main`, `datasets_benchmarks`, `position`;
  the proceedings host no others). A listing's own track claim says which; a listing that can't say (a PMLR
  volume mixing main and position papers: `unknown`) covers the track of the record it merged into. A
  track no listing holds (a track published later, or never) is never judged.
- **Unlisted**: a record whose status is OpenReview's `accepted` (it won `PRECEDENCE`), in a covered
  venue-year and track, that is no listing (no proceedings claim or proceedings id) and shares no title key
  and no forum id with one. A record that shares one but stayed apart (an ambiguous title) may be the
  listed paper: it keeps its status, and dedup's not-merged row already names it.

An unlisted record gains one claim per crawled source: `status=unknown` from that source, its evidence starting
`not listed:` (`dedup.is_absence`; the prefix is reserved for it), its listing as the URL, that listing's
index-page fetch as `fetched_at`, and the evidence. `resolve` then gives the
record `unknown` (the proceedings outrank OpenReview for status) and its `precedence:<source>` conflicts.csv
rows, one per OpenReview status value it outranks; they replace the record's earlier `precedence:` status rows
(a v2-over-v1 row, say), as dedup run again would write them. The OpenReview claims are kept. The record still equals what its claims resolve to, and an absence claim
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
    PROCEEDINGS_SOURCES,
    PROCEEDINGS_TRACKS,
    Conflict,
    DedupResult,
    forum_ids,
    is_absence,
    is_listing,
    resolve,
    title_key,
)
from openproceedings.ingest.record import Claim, PaperRecord, Source
from openproceedings.ingest.sources.common import ListingReport, Report

log = logging.getLogger(__name__)

OPENREVIEW_SOURCES: frozenset[str] = frozenset({"openreview_v2", "openreview_v1"})

type Key = tuple[str, str, int]  # (proceedings source, venue, year)


@dataclass(frozen=True)
class Listing:
    """One crawled listing: its index URL, the tracks its records claim, and when its index page was fetched."""

    url: str
    tracks: frozenset[str]
    fetched_at: datetime


@dataclass(frozen=True)
class Crawl:
    """A proceedings source's crawl of one venue-year: its listings, in order, and whether every one is
    complete."""

    source: str
    venue: str
    year: int
    listings: tuple[Listing, ...]
    complete: bool


def complete(report: ListingReport) -> bool:
    """The listing states its count and it matched, every entry became a record, one per paper (a repeated
    entry is no missing paper), and it points to no volume left uncrawled."""
    return (
        report.stated is not None and report.count_ok and not report.see_also
        and report.records + report.skipped.get("duplicate", 0) == report.listed
    )  # fmt: skip


def crawled(reports: Iterable[Report]) -> dict[Key, Crawl]:
    """The proceedings listings' reports, per (source, venue, year)."""
    grouped: dict[Key, list[ListingReport]] = defaultdict(list)
    for r in reports:
        if isinstance(r, ListingReport) and r.source in PROCEEDINGS_SOURCES:
            grouped[(r.source, r.venue, r.year)].append(r)
    out = {}
    for key, group in sorted(grouped.items()):
        read = [r for r in group if r.fetched]  # a crawler's first fetch is always the listing's index page
        if not read:
            continue  # nothing read, nothing to say
        out[key] = Crawl(
            group[0].source, group[0].venue, group[0].year,
            tuple(Listing(r.listing, frozenset(r.tracks), r.fetched[0]) for r in read),
            len(read) == len(group) and all(complete(r) for r in group),
        )  # fmt: skip
    return out


def _without_absence(record: PaperRecord) -> PaperRecord:
    if not any(is_absence(c) for c in record.provenance):
        return record
    bare, _ = resolve(record.id, [c for c in record.provenance if not is_absence(c)])
    return bare


def _names(record: PaperRecord) -> set[tuple[str, str]]:
    """What could make the record a listing's paper: its kept title claims' keys and its forum ids."""
    keys = {("title", k) for c in record.provenance if c.field == "title" and (k := title_key(str(c.value)))}
    return keys | {("forum", f) for f in forum_ids(record)}


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
    holding = [x for x in crawl.listings if track in x.tracks or "unknown" in x.tracks]
    listing = (holding or [crawl.listings[0]])[0]
    names = ", ".join(x.url for x in crawl.listings)
    return Claim(
        field="status", value=ABSENT, source=cast(Source, crawl.source), url=listing.url,
        fetched_at=listing.fetched_at,
        evidence=f"{ABSENT_EVIDENCE} OpenReview says accepted, but the crawled {crawl.venue} {crawl.year} {track} "
        f"listings ({names}) hold no record with its title or forum id (decision-005)",
    )  # fmt: skip


@dataclass(frozen=True)
class Reconciled:
    result: DedupResult
    unlisted: dict[tuple[str, int, str], int]  # (venue, year, track) → records made unknown
    # OpenReview-accepted and covered, but sharing a title key or forum id with a listing it didn't merge with
    shares_listing: int
    # crawls left alone: a listing skipped an entry, miscounted, states no count, or names a volume not crawled
    incomplete: tuple[Key, ...]


def reconcile(result: DedupResult, crawls: Mapping[Key, Crawl]) -> Reconciled:
    """`result` with every unlisted OpenReview-accepted record set to `unknown` by an absence claim (module
    doc). Merges are unchanged. A record this step changes has its `precedence:` status rows replaced by the ones
    its claims now resolve to; every other row is kept."""
    bare = [_without_absence(r) for r in result.records]
    covered = _covered(bare, crawls)
    listed: dict[tuple[str, int], set[tuple[str, str]]] = defaultdict(set)  # (venue, year) → listings' names
    for r in bare:
        if is_listing(r):
            listed[(r.venue, r.year)] |= _names(r)
    out: list[PaperRecord] = []
    changed: dict[str, list[Conflict]] = {}  # id → its status rows, for every record this step changed
    unlisted: Counter[tuple[str, int, str]] = Counter()
    shares = 0
    for before, r in zip(result.records, bare, strict=True):
        sources = sorted(k for k in crawls if k[1:] == (r.venue, r.year) and r.track in covered.get(k, ()))
        if sources and _openreview_accepted(r) and not is_listing(r):
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
