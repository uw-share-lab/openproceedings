"""The official accepted counts `GET /coverage` serves are exactly `docs/results/coverage-sources.md`'s rows
(spec 07 §C; coverage-reporting skill): the report is the cited, human-edited table and
`official_counts.OFFICIAL_ACCEPTED` its machine-readable copy, so a row added to one and not the other fails
here. Until the counts are sourced there is no file and the table is empty."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from openproceedings.official_counts import (
    OFFICIAL_ACCEPTED,
    UNGATED_NOTES,
    OfficialCount,
    UngatedNote,
    check_notes,
    check_table,
)

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
NOTE_HEADER = ["venue", "year", "track", "why it is not gated", "source (URL or citation)", "accessed"]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table(text: str, header: list[str]) -> list[str]:
    """The data lines of the one Markdown table in `text` headed `header` (a table is a run of `|` lines)."""
    tables: list[list[str]] = []
    run: list[str] = []
    for line in [*text.splitlines(), ""]:
        if line.startswith("|"):
            run.append(line)
        elif run:
            tables.append(run)
            run = []
    found = [t for t in tables if _cells(t[0]) == header]
    assert len(found) == 1, f"expected one table headed {header}, found {len(found)}"
    return found[0][2:]


def rows_of(text: str) -> dict[tuple[str, int, str], OfficialCount]:
    """The skill's table: `| venue | year | track | official_accepted | what it counts | source | accessed |`."""
    rows: dict[tuple[str, int, str], OfficialCount] = {}
    for line in _table(text, HEADER):
        venue, year, track, accepted, counts, citation, accessed = _cells(line)
        key = (venue, int(year), track)
        assert key not in rows, f"{key} is in two rows"
        rows[key] = OfficialCount(
            int(accepted.replace(",", "")), counts, citation, date.fromisoformat(accessed)
        )
    return rows


def notes_of(text: str) -> dict[tuple[str, int, str], UngatedNote]:
    """§Ungated cells with a note: `| venue | year | track | why it is not gated | source | accessed |`."""
    notes: dict[tuple[str, int, str], UngatedNote] = {}
    for line in _table(text, NOTE_HEADER):
        venue, year, track, note, citation, accessed = _cells(line)
        key = (venue, int(year), track)
        assert key not in notes, f"{key} is in two rows"
        notes[key] = UngatedNote(note, citation, date.fromisoformat(accessed))
    return notes


def test_the_served_table_is_the_reports() -> None:
    if not SOURCES.exists():
        assert OFFICIAL_ACCEPTED == {}, "an official count needs its cited row in coverage-sources.md"
        return
    assert rows_of(SOURCES.read_text(encoding="utf-8")) == OFFICIAL_ACCEPTED


def test_the_served_notes_are_the_reports() -> None:
    """The ungated cells' notes are the report's §Ungated cells with a note, row for row (TASK-222)."""
    assert notes_of(SOURCES.read_text(encoding="utf-8")) == UNGATED_NOTES


def test_an_ungated_note_needs_an_ungated_cell_and_a_citation() -> None:
    assert ("IASEAI", 2026, "main") in UNGATED_NOTES
    gated = next(k for k in OFFICIAL_ACCEPTED if k[2] == "main")
    with pytest.raises(ValueError, match="gated"):
        check_notes({gated: UngatedNote("x", "https://example.org", date(2026, 10, 10))})
    with pytest.raises(ValueError, match="citation"):
        check_notes({("IASEAI", 2026, "main"): UngatedNote("x", " ", date(2026, 10, 10))})
    with pytest.raises(ValueError, match="citation"):
        check_notes({("IASEAI", 2026, "main"): UngatedNote(" ", "https://example.org", date(2026, 10, 10))})
    with pytest.raises(ValueError, match="unknown"):
        check_notes({("PMLR", 2026, "main"): UngatedNote("x", "https://example.org", date(2026, 10, 10))})


def test_aaai_main_is_gated_or_noted_from_2010_on() -> None:
    """Every AAAI main cell from 2010 has a gate row (an AAAI statement or a count of AAAI's own accepted-paper
    list) or a note saying why not (TASK-219's ruling, 2026-10-10)."""
    gated = {y for v, y, t in OFFICIAL_ACCEPTED if v == "AAAI" and t == "main"}
    noted = {y for v, y, t in UNGATED_NOTES if v == "AAAI" and t == "main"}
    assert gated == {2012, 2013, 2015, 2017, 2018, 2019, 2020, 2021}
    # 2010 and 2014: lists captured only after publication are not evidently independent (gate C round 1)
    assert noted == {2010, 2011, 2014, 2016, 2022, 2023, 2024, 2025, 2026}
    for year in (2010, 2014):
        assert "captured" in UNGATED_NOTES[("AAAI", year, "main")].note
    for year in (2012, 2017, 2020, 2021):  # list counts say so, and name AAAI's list
        assert "counted" in OFFICIAL_ACCEPTED[("AAAI", year, "main")].counts
        assert "AAAI's own" in OFFICIAL_ACCEPTED[("AAAI", year, "main")].counts


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
