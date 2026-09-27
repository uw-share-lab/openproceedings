"""Official accepted counts per venue × year × track, each with its citation (spec 07 §C; coverage-reporting
skill), and the M4 gate on them: every main-track and D&B cell with an official count is within ±1%.

This is the machine-readable copy of `docs/results/coverage-sources.md` (the cited, human-edited table); a
row goes into both in one change, and `tests/unit/test_official_counts.py` fails when they differ.
`GET /coverage` joins it to the indexed counts (`coverage.breakdown`). A row is added only with a citation a
reader can check (the conference's statistics page, the proceedings index or the OpenReview accepted
group), what it counts, and the date it was read; never a number from memory. Until a row exists, a cell is
reported with no official count and is not gated. The table is empty until the counts are sourced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from openproceedings.vocab import TRACKS, VENUES

GATED_TRACKS: tuple[str, ...] = ("main", "datasets_benchmarks")  # spec 07 §C: main-track and D&B cells
GATE_PERCENT = 1  # |delta| ≤ 1% of the official count


@dataclass(frozen=True, slots=True)
class OfficialCount:
    accepted: int  # > 0
    counts: str  # what the number counts (orals + spotlights + posters? before withdrawals?)
    citation: str  # a URL or a citation a reader can check
    accessed: date


# (venue, year, track) → its official accepted count
type OfficialTable = dict[tuple[str, int, str], OfficialCount]
OFFICIAL_ACCEPTED: OfficialTable = {}


def check_table(table: OfficialTable) -> None:
    """Every row names a known venue and track, a positive count and a citation (ValueError otherwise)."""
    for (venue, _year, track), row in table.items():
        if venue not in VENUES.values() or track not in TRACKS or track == "unknown":
            raise ValueError(f"an official count names an unknown venue or track: {venue} {track}")
        if row.accepted <= 0 or not row.citation.strip() or not row.counts.strip():
            raise ValueError(f"the official count for {venue} {track} needs a positive count and a citation")


check_table(OFFICIAL_ACCEPTED)


def within_gate(indexed: int, official: int) -> bool:
    """|indexed − official| ≤ 1% of official, in exact integer arithmetic."""
    return 100 * abs(indexed - official) <= GATE_PERCENT * official
