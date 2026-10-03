"""Statuses indexed (spec 07 §C, TASK-082): which statuses a venue-year's sources can contain, from the source
table (`ingest/statuses.py`), pinned to spec 01's source table and to what the classifiers can produce."""

from __future__ import annotations

from typing import get_args

import pytest
from openproceedings.ingest.classify import classify_proceedings, classify_venueid
from openproceedings.ingest.record import Source
from openproceedings.ingest.sources.openreview_v1 import ADAPTERS
from openproceedings.ingest.sources.openreview_v2 import FIRST_V2_YEAR
from openproceedings.ingest.statuses import (
    ACCEPTED_ONLY,
    EVERY_STATUS,
    SOURCE_STATUSES,
    on_openreview,
    statuses_indexed,
)
from openproceedings.vocab import STATUSES


def test_openreview_years_come_from_the_crawler_adapters() -> None:
    """TASK-115: the irregular ICLR v1 years cannot be represented by a single lower bound."""
    assert {year: on_openreview("ICLR", year) for year in range(2013, 2018)} == {
        2013: True,
        2014: True,
        2015: False,
        2016: True,
        2017: True,
    }
    assert all(on_openreview(venue, year) for (venue, year), adapter in ADAPTERS.items() if adapter.listings)
    assert all(on_openreview(venue, year) for venue, year in FIRST_V2_YEAR.items())


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
        (["ris"], "ICLR", 2013, list(STATUSES)),
        (["ris"], "ICLR", 2014, list(STATUSES)),
        (["ris"], "ICLR", 2015, ["accepted"]),
        (["ris"], "ICLR", 2016, list(STATUSES)),
        (["ris"], "ICLR", 2017, list(STATUSES)),
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
