"""Statuses indexed (spec 07 §C; spec 01 §Sources, TASK-082): which review statuses the sources of a
venue-year can contain at all, so the coverage report can say, for example, that a proceedings-only
venue-year holds no rejected papers to exclude.

It is a property of the sources, not of the records: a venue-year whose sources can carry `rejected` lists
it even when no rejected record was indexed. The snapshot build records it per venue-year in the manifest
(`statuses_indexed`), from the claim sources of that venue-year's records, so a later change to this
table never rewrites what an existing snapshot says.

- An OpenReview note's `content.venueid` can carry every status (`classify.classify_venueid`: the bare
  path is `accepted`, the `…Submission` suffixes `rejected`, `withdrawn`, `desk_rejected` or `unknown`).
- A proceedings listing (the ICLR archive, NeurIPS proceedings, or a PMLR volume) holds accepted papers only
  (`classify.classify_proceedings`), and so does the pinned dblp release's ICML 1988-2012 (published papers)
  with the official ICML pages that give some of them abstracts (decision-047).
- The RIS bootstrap resolves each record through a venueid or a listing (spec 01 §Sources, RIS row), so a
  venue-year it covers can carry every status where OpenReview holds that venue-year, and only `accepted`
  outside it: pre-2021 NeurIPS, ICML before 2023 and ICLR 2015 come from proceedings only.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import get_args

from openproceedings.ingest.record import Source
from openproceedings.ingest.sources.openreview_v1 import ADAPTERS
from openproceedings.ingest.sources.openreview_v2 import FIRST_V2_YEAR
from openproceedings.vocab import STATUSES

EVERY_STATUS: tuple[str, ...] = STATUSES
ACCEPTED_ONLY: tuple[str, ...] = ("accepted",)
# per claim source: the statuses it can carry in a venue-year OpenReview holds, and in any other
SOURCE_STATUSES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "openreview_v2": (EVERY_STATUS, EVERY_STATUS),
    "openreview_v1": (EVERY_STATUS, EVERY_STATUS),
    "iclr_archive": (ACCEPTED_ONLY, ACCEPTED_ONLY),
    "neurips_proceedings": (ACCEPTED_ONLY, ACCEPTED_ONLY),
    "pmlr": (ACCEPTED_ONLY, ACCEPTED_ONLY),
    # ICML 1988-2012: published papers only (decision-047), and an official ICML page's abstract of one (TASK-206)
    "dblp": (ACCEPTED_ONLY, ACCEPTED_ONLY),
    "icml_site": (ACCEPTED_ONLY, ACCEPTED_ONLY),
    # AAAI 2010+, AIES 2024+, IASEAI 2026+ from ojs.aaai.org: published papers only (decision-049)
    "ojs": (ACCEPTED_ONLY, ACCEPTED_ONLY),
    "ris": (EVERY_STATUS, ACCEPTED_ONLY),
}
if set(SOURCE_STATUSES) != set(get_args(Source)):  # a new claim source needs a row before it can build
    raise RuntimeError("SOURCE_STATUSES must name exactly the claim sources of `record.Source`")


def on_openreview(venue: str, year: int) -> bool:
    """Whether OpenReview holds `venue`'s `year` (spec 01 §Sources): a non-empty API v1 adapter or a year
    at or after the venue's first API v2 year. ICLR 2015 deliberately has an empty adapter."""
    adapter = ADAPTERS.get((venue, year))
    first_v2 = FIRST_V2_YEAR.get(venue)
    return (adapter is not None and bool(adapter.listings)) or (first_v2 is not None and year >= first_v2)


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
