"""Statuses indexed (spec 07 §C, TASK-082): which statuses a venue-year's sources can contain, from the source
table (`ingest/sources.py`), pinned to spec 01's source table and to what the classifiers can produce."""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest
from openproceedings.ingest.classify import classify_proceedings, classify_venueid
from openproceedings.ingest.record import Source
from openproceedings.ingest.sources import (
    ACCEPTED_ONLY,
    EVERY_STATUS,
    OPENREVIEW_FROM,
    SOURCE_STATUSES,
    on_openreview,
    statuses_indexed,
)
from openproceedings.vocab import STATUSES

SPEC_01 = Path(__file__).resolve().parents[4] / "docs" / "specs" / "01-ingestion.md"


def test_openreview_first_years_are_spec_01s() -> None:
    """The first year of each venue on OpenReview, read from spec 01 §Sources' two OpenReview rows (a hand
    copy here could drift from both)."""
    rows = [
        line
        for line in SPEC_01.read_text(encoding="utf-8").splitlines()
        if line.startswith("| OpenReview API")
    ]
    assert len(rows) == 2
    covers = " ".join(row.split("|")[2] for row in rows)
    first: dict[str, int] = {}
    for venue, year in re.findall(r"(ICLR|NeurIPS|ICML) (\d{4})", covers):
        first[venue] = min(first.get(venue, 9999), int(year))
    assert first == OPENREVIEW_FROM


def test_every_claim_source_has_a_row() -> None:
    assert set(SOURCE_STATUSES) == set(get_args(Source))


def test_a_venueid_can_carry_every_status_and_a_listing_only_accepted() -> None:
    """The table's two capabilities are exactly what the classifiers produce."""
    forms = ["", "/Rejected_Submission", "/Withdrawn_Submission", "/Desk_Rejected_Submission", "/Submission"]
    assert {classify_venueid(f"ICLR.cc/2024/Conference{f}").status for f in forms} == set(EVERY_STATUS)
    assert EVERY_STATUS == STATUSES
    tokens = ["Conference", "Datasets_and_Benchmarks_Track", "Position_Paper_Track", "Workshop", "", "Unseen"]
    assert {classify_proceedings(t).status for t in tokens} == set(ACCEPTED_ONLY)


@pytest.mark.parametrize(
    ("sources", "venue", "year", "held"),
    [
        # spec 07 §C's examples: pre-2021 NeurIPS and ICML 2020–22 come from proceedings only
        (["ris"], "NeurIPS", 2020, ["accepted"]),
        (["ris"], "ICML", 2022, ["accepted"]),
        (["neurips_proceedings"], "NeurIPS", 2019, ["accepted"]),
        (["pmlr"], "ICML", 2021, ["accepted"]),
        # where OpenReview holds the venue-year, a venueid can carry any status
        (["ris"], "NeurIPS", 2021, list(STATUSES)),
        (["ris"], "ICML", 2023, list(STATUSES)),
        (["ris"], "ICLR", 2018, list(STATUSES)),
        (["ris"], "ICLR", 2017, ["accepted"]),
        (["openreview_v2"], "ICML", 2025, list(STATUSES)),
        (["pmlr", "openreview_v2"], "ICML", 2024, list(STATUSES)),  # a union, in vocabulary order
        (["pmlr"], "ICML", 2024, ["accepted"]),  # a listing alone, even where OpenReview has the year
    ],
)
def test_statuses_indexed(sources: list[str], venue: str, year: int, held: list[str]) -> None:
    assert statuses_indexed(sources, venue, year) == held


def test_an_unknown_source_is_refused_not_guessed() -> None:
    with pytest.raises(KeyError):
        statuses_indexed(["scholar"], "ICLR", 2024)
    assert not on_openreview("PMLR", 2024)
