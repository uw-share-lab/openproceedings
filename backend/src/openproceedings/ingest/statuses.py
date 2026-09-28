"""Statuses indexed (spec 07 §C; spec 01 §Sources, TASK-082): which review statuses the sources of a
venue-year can contain at all, so the coverage report can say, for example, that a proceedings-only
venue-year holds no rejected papers to exclude.

It is a property of the sources, not of the records: a venue-year whose sources can carry `rejected` lists
it even when no rejected record was indexed. The snapshot build records it per venue-year in the manifest
(`statuses_indexed`), from the claim sources of that venue-year's records, so a later change to this
table never rewrites what an existing snapshot says.

- An OpenReview note's `content.venueid` can carry every status (`classify.classify_venueid`: the bare
  path is `accepted`, the `…Submission` suffixes `rejected`, `withdrawn`, `desk_rejected` or `unknown`).
- A proceedings listing (NeurIPS or ICLR proceedings, a PMLR volume) holds accepted papers only
  (`classify.classify_proceedings`).
- The RIS bootstrap resolves each record through a venueid or a listing (spec 01 §Sources, RIS row), so a
  venue-year it covers can carry every status where OpenReview holds that venue-year, and only `accepted`
  before it: pre-2021 NeurIPS, ICML before 2023 and ICLR before 2018 come from proceedings only.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import get_args

from openproceedings.ingest.record import Source
from openproceedings.vocab import STATUSES

EVERY_STATUS: tuple[str, ...] = STATUSES
ACCEPTED_ONLY: tuple[str, ...] = ("accepted",)
# The first year OpenReview holds each venue (spec 01 §Sources: API v1 from ICLR 2018 and NeurIPS 2021, API v2
# from ICML 2023); a pinned test reads the same years from spec 01's table
OPENREVIEW_FROM: dict[str, int] = {"ICLR": 2018, "NeurIPS": 2021, "ICML": 2023}
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


def on_openreview(venue: str, year: int) -> bool:
    """Whether OpenReview holds `venue`'s `year` (spec 01 §Sources)."""
    first = OPENREVIEW_FROM.get(venue)
    return first is not None and year >= first


def statuses_indexed(sources: Iterable[str], venue: str, year: int, present: Iterable[str] = ()) -> list[str]:
    """The statuses a venue-year whose records came from `sources` (claim sources) can contain, in vocabulary
    order: the table's, plus any status the venue-year's records actually hold (`present`), since a status a
    record holds is one its sources carried, whatever the table expected. KeyError for a source without a
    row (a build refuses it rather than guess)."""
    held = on_openreview(venue, year)
    can = set(present)
    for source in sources:
        on, off = SOURCE_STATUSES[source]
        can.update(on if held else off)
    return [s for s in STATUSES if s in can]
