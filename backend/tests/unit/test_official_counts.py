"""The official accepted counts `GET /coverage` serves are exactly `docs/results/coverage-sources.md`'s rows
(spec 07 §C; coverage-reporting skill): the report is the cited, human-edited table and
`official_counts.OFFICIAL_ACCEPTED` its machine-readable copy, so a row added to one and not the other fails
here. Until the counts are sourced there is no file and the table is empty."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from openproceedings.official_counts import OFFICIAL_ACCEPTED, OfficialCount, check_table

SOURCES = Path(__file__).resolve().parents[3] / "docs" / "results" / "coverage-sources.md"
HEADER = [
    "venue",
    "year",
    "track",
    "official_accepted",
    "what it counts",
    "source (URL or citation)",
    "accessed",
]


def rows_of(text: str) -> dict[tuple[str, int, str], OfficialCount]:
    """The skill's one table: `| venue | year | track | official_accepted | what it counts | source | accessed |`."""
    rows: dict[tuple[str, int, str], OfficialCount] = {}
    lines = [line for line in text.splitlines() if line.startswith("|")]
    assert lines and [c.strip() for c in lines[0].strip("|").split("|")] == HEADER
    for line in lines[2:]:
        venue, year, track, accepted, counts, citation, accessed = (
            c.strip() for c in line.strip("|").split("|")
        )
        key = (venue, int(year), track)
        assert key not in rows, f"{key} is in two rows"
        rows[key] = OfficialCount(
            int(accepted.replace(",", "")), counts, citation, date.fromisoformat(accessed)
        )
    return rows


def test_the_served_table_is_the_reports() -> None:
    if not SOURCES.exists():
        assert OFFICIAL_ACCEPTED == {}, "an official count needs its cited row in coverage-sources.md"
        return
    assert rows_of(SOURCES.read_text(encoding="utf-8")) == OFFICIAL_ACCEPTED


def test_the_report_parser_reads_the_skills_shape() -> None:
    text = "\n".join(
        [
            "| " + " | ".join(HEADER) + " |",
            "|---|---|---|---|---|---|---|",
            "| NeurIPS | 2023 | main | 3,218 | posters + orals | https://example.org/a | 2026-09-01 |",
        ]
    )
    assert rows_of(text) == {
        ("NeurIPS", 2023, "main"): OfficialCount(
            3218, "posters + orals", "https://example.org/a", date(2026, 9, 1)
        )
    }


@pytest.mark.parametrize(
    "table",
    [
        {("PMLR", 2023, "main"): OfficialCount(1, "x", "https://example.org", date(2026, 9, 1))},
        {("ICML", 2023, "unknown"): OfficialCount(1, "x", "https://example.org", date(2026, 9, 1))},
        {("ICML", 2023, "main"): OfficialCount(0, "x", "https://example.org", date(2026, 9, 1))},
        {("ICML", 2023, "main"): OfficialCount(1, "x", " ", date(2026, 9, 1))},
        {("ICML", 2023, "main"): OfficialCount(1, "", "https://example.org", date(2026, 9, 1))},
    ],
)
def test_a_row_without_a_cell_a_count_or_a_citation_is_refused(
    table: dict[tuple[str, int, str], OfficialCount],
) -> None:
    with pytest.raises(ValueError):
        check_table(table)
