"""Statuses a venue-year's sources cannot supply (TASK-109; spec 01 §Pipeline 5): the snapshot build reports
each (venue, year, status) its records hold that none of their claim sources can carry there, with the
records behind it, instead of letting the statuses a venue-year shows widen silently.

A source's statuses are a property of the source, not of the records (spec 01 §Status handling):

- An OpenReview note (API v2 or v1) can carry every status.
- A proceedings listing (NeurIPS proceedings, a PMLR volume) holds accepted papers only.
- The RIS bootstrap resolves each record through a venueid or a listing, so it can carry every status in a
  venue-year OpenReview holds (API v1: ICLR 2013, 2014 and 2016–2023, NeurIPS 2021–2022; API v2 from ICLR
  2024, NeurIPS 2023, ICML 2023), and only `accepted` in any other.

An unexpected cell points at an error in a source's classification or in this table (synthetic data showed an
ICML 2019 withdrawn record, which a proceedings-only venue-year can't hold). The check is a report, never a
refusal and never a change to the snapshot: its bytes and hash are the same with or without it.

`SOURCE_STATUSES` and `expected` are this branch's copy of the per-source table; `unexpected_statuses` takes
the table as a function so the coverage table (`statuses_indexed`, TASK-082) can supersede it unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import get_args

from openproceedings.ingest.record import PaperRecord, Source
from openproceedings.ingest.sources.openreview_v1 import ADAPTERS
from openproceedings.ingest.sources.openreview_v2 import FIRST_V2_YEAR
from openproceedings.vocab import STATUSES

log = logging.getLogger(__name__)

EVERY_STATUS: tuple[str, ...] = STATUSES
ACCEPTED_ONLY: tuple[str, ...] = ("accepted",)
# per claim source: the statuses it can carry in a venue-year OpenReview holds, and in any other
SOURCE_STATUSES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "openreview_v2": (EVERY_STATUS, EVERY_STATUS),
    "openreview_v1": (EVERY_STATUS, EVERY_STATUS),
    "neurips_proceedings": (ACCEPTED_ONLY, ACCEPTED_ONLY),
    "pmlr": (ACCEPTED_ONLY, ACCEPTED_ONLY),
    "ris": (EVERY_STATUS, ACCEPTED_ONLY),
}
if set(SOURCE_STATUSES) != set(get_args(Source)):  # a new claim source needs a row before it can build
    raise RuntimeError("SOURCE_STATUSES must name exactly the claim sources of `record.Source`")
LOGGED_IDS = 20  # the ids a log line names; the build's report carries them all

Expected = Callable[[Iterable[str], str, int], Iterable[str]]  # (claim sources, venue, year) → statuses


def on_openreview(venue: str, year: int) -> bool:
    """Whether OpenReview holds `venue`'s `year` (spec 01 §Sources): a v1 adapter with something to list (not
    ICLR 2015), or a year API v2 holds."""
    first_v2 = FIRST_V2_YEAR.get(venue)
    adapter = ADAPTERS.get((venue, year))
    return (adapter is not None and bool(adapter.listings)) or (first_v2 is not None and year >= first_v2)


def expected(sources: Iterable[str], venue: str, year: int) -> list[str]:
    """The statuses a venue-year whose records came from `sources` (claim sources) can hold, in vocabulary
    order. KeyError for a source without a row."""
    held = on_openreview(venue, year)
    can: set[str] = set()
    for source in sources:
        on, off = SOURCE_STATUSES[source]
        can.update(on if held else off)
    return [s for s in STATUSES if s in can]


@dataclass(frozen=True, slots=True)
class UnexpectedStatus:
    """A (venue, year, status) the venue-year's records hold but its claim sources can't supply."""

    venue: str
    year: int
    status: str
    sources: tuple[str, ...]  # the venue-year's claim sources, sorted
    expected: tuple[str, ...]  # what they can supply, in vocabulary order
    records: tuple[str, ...]  # the ids holding `status`, sorted

    def to_json(self) -> dict[str, object]:
        return {"venue": self.venue, "year": self.year, "status": self.status, "sources": list(self.sources),
                "expected": list(self.expected), "records": list(self.records)}  # fmt: skip


def unexpected_statuses(records: Iterable[PaperRecord], table: Expected = expected) -> list[UnexpectedStatus]:
    """Each (venue, year, status) whose records hold a status `table` says the venue-year's claim sources
    (every record's, together) can't supply; in venue, year, status order. Each is logged
    (`snapshot_unexpected_status`, with up to `LOGGED_IDS` record ids; never record text)."""
    sources: dict[tuple[str, int], set[str]] = {}
    ids: dict[tuple[str, int, str], list[str]] = {}
    for r in records:
        sources.setdefault((r.venue, r.year), set()).update(c.source for c in r.provenance)
        ids.setdefault((r.venue, r.year, r.status), []).append(r.id)
    found = []
    for venue, year, status in sorted(ids, key=lambda k: (k[0], k[1], STATUSES.index(k[2]))):
        can = tuple(s for s in STATUSES if s in set(table(sources[(venue, year)], venue, year)))
        if status in can:
            continue
        cell = UnexpectedStatus(venue, year, status, tuple(sorted(sources[(venue, year)])), can,
                                tuple(sorted(ids[(venue, year, status)])))  # fmt: skip
        log.warning("snapshot_unexpected_status", extra={
            "venue": venue, "year": year, "status": status, "sources": list(cell.sources),
            "expected": list(can), "records": len(cell.records), "ids": list(cell.records[:LOGGED_IDS])})  # fmt: skip
        found.append(cell)
    return found
