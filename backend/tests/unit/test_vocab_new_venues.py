"""The four venues added by decision-049 (docs/plans/2026-10-09-new-venues-design.md §Data model)."""

import pytest
from openproceedings.ingest.record import is_paper_id
from openproceedings.vocab import TRACKS, VENUES, venue_name


@pytest.mark.parametrize(
    ("venue", "year", "expected"),
    [
        ("AAAI", 1980, "AAAI Conference on Artificial Intelligence (AAAI 1980)"),
        ("AAAI", 2026, "AAAI Conference on Artificial Intelligence (AAAI 2026)"),
        ("AIES", 2018, "AAAI/ACM Conference on AI, Ethics, and Society (AIES 2018)"),
        ("FAccT", 2018, "ACM Conference on Fairness, Accountability, and Transparency (FAT* 2018)"),
        ("FAccT", 2020, "ACM Conference on Fairness, Accountability, and Transparency (FAT* 2020)"),
        ("FAccT", 2021, "ACM Conference on Fairness, Accountability, and Transparency (FAccT 2021)"),
        ("IASEAI", 2026, "International Association for Safe and Ethical AI Conference (IASEAI 2026)"),
    ],
)
def test_venue_name_per_era(venue: str, year: int, expected: str) -> None:
    assert venue_name(venue, year) == expected


@pytest.mark.parametrize(
    ("venue", "year"), [("AAAI", 1979), ("AIES", 2017), ("FAccT", 2017), ("IASEAI", 2024)]
)
def test_year_before_the_venue_is_refused(venue: str, year: int) -> None:
    with pytest.raises(ValueError, match="not held under that name"):
        venue_name(venue, year)


def test_venue_query_spellings_are_case_insensitive() -> None:
    assert VENUES["facct"] == "FAccT"
    assert VENUES["aaai"] == "AAAI"
    assert VENUES["iaseai"] == "IASEAI"
    assert list(VENUES.values())[-4:] == ["AAAI", "AIES", "FAccT", "IASEAI"]


def test_new_tracks_sit_before_other() -> None:
    assert TRACKS[TRACKS.index("blogpost") + 1 : TRACKS.index("other")] == (
        "student_abstract", "consortium", "demo", "iaai", "eaai",
    )  # fmt: skip


@pytest.mark.parametrize("prefix", ["aaai", "aies", "facct", "iaseai"])
def test_record_ids_of_new_venues_have_the_id_shape(prefix: str) -> None:
    assert is_paper_id(f"op:{prefix}:2024:ojs-28000")
