"""Track and status from an OpenReview venueid or a proceedings claim (spec 01 §Track taxonomy; openreview-venueids
and track-taxonomy skills; task-020). Every row stays forever; add one per new form seen in a crawl log."""

from __future__ import annotations

import logging

import pytest
from openproceedings.ingest.classify import classify_proceedings, classify_venueid

VALIDATED: list[tuple[str, str | None, int | None, str, str]] = [
    # venueid, venue, year, track, status. Forms seen in the Trust-Evals 90 hand-verified venueids
    # (Trust-Evals-LitReview verification/openreview-venues.json; forms only) and scholarmend's 90/90 cases.
    ("ICLR.cc/2024/Conference", "ICLR", 2024, "main", "accepted"),
    ("ICML.cc/2025/Conference", "ICML", 2025, "main", "accepted"),
    ("NeurIPS.cc/2023/Conference", "NeurIPS", 2023, "main", "accepted"),
    ("ICLR.cc/2024/Conference/Rejected_Submission", "ICLR", 2024, "main", "rejected"),
    ("ICLR.cc/2024/Conference/Withdrawn_Submission", "ICLR", 2024, "main", "withdrawn"),
    ("NeurIPS.cc/2023/Track/Datasets_and_Benchmarks", "NeurIPS", 2023, "datasets_benchmarks", "accepted"),
    (
        "NeurIPS.cc/2024/Track/Datasets_and_Benchmarks_Track",
        "NeurIPS",
        2024,
        "datasets_benchmarks",
        "accepted",
    ),
    ("ICML.cc/2026/Workshop/AI4GOOD", "ICML", 2026, "workshop", "accepted"),
    ("NeurIPS.cc/2024/Workshop/SafeGenAi", "NeurIPS", 2024, "workshop", "accepted"),
    ("ICLR.cc/2024/Workshop/SeT_LLM", "ICLR", 2024, "workshop", "accepted"),
    ("NeurIPS.cc/2025/Workshop_Mexico_City/ResponsibleFM", "NeurIPS", 2025, "workshop", "accepted"),
    ("ICML.cc/2025/Position_Paper_Track", "ICML", 2025, "position", "accepted"),  # seen in the gold file
]

UNVERIFIED: list[tuple[str, str | None, int | None, str, str]] = [
    # the skill's forms still marked "verify" (task-002 checks them against live notes)
    ("ICLR.cc/2024/Conference/Desk_Rejected_Submission", "ICLR", 2024, "main", "desk_rejected"),
    ("ICLR.cc/2024/Conference/Submission", "ICLR", 2024, "main", "unknown"),
    ("NeurIPS.cc/2024/Datasets_and_Benchmarks_Track", "NeurIPS", 2024, "datasets_benchmarks", "accepted"),
    (
        "NeurIPS.cc/2024/Track/Datasets_and_Benchmarks/Rejected_Submission",
        "NeurIPS",
        2024,
        "datasets_benchmarks",
        "rejected",
    ),
    (
        "NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round2",
        "NeurIPS",
        2021,
        "datasets_benchmarks",
        "accepted",
    ),
    ("ICML.cc/2024/Workshop/X/Submission", "ICML", 2024, "workshop", "unknown"),
    ("ICML.cc/2024/Workshop/X/Rejected_Submission", "ICML", 2024, "workshop", "rejected"),
    ("ICLR.cc/2023/TinyPapers", "ICLR", 2023, "tiny_papers", "accepted"),
    ("ICLR.cc/2024/BlogPosts", "ICLR", 2024, "blogpost", "accepted"),
    ("NeurIPS.cc/2022/Track/Competition", "NeurIPS", 2022, "competition", "accepted"),
    (
        "NeurIPS.cc/2023/Track/Creative_AI",
        "NeurIPS",
        2023,
        "other",
        "accepted",
    ),  # parses, not in the taxonomy
]

NEVER_PARSE: list[str] = [
    "AAAI.org/2026/Workshop/X",  # another organisation: out of scope
    "AAAI.org/2026/Workshop/X/Submission",
    "ICLR.cc/24/Conference",  # the year must be four digits
    "ICLR.cc/2024",  # nothing after the year
    "ICLR.cc/2024/",
    "iclr.cc/2024/Conference",  # the org is case-sensitive
    "ICLR/2024/Conference",
    "",
]


@pytest.mark.parametrize(
    ("venueid", "venue", "year", "track", "status"),
    VALIDATED + UNVERIFIED,
    ids=[r[0] for r in VALIDATED + UNVERIFIED],
)
def test_table(venueid: str, venue: str, year: int, track: str, status: str) -> None:
    c = classify_venueid(venueid)
    assert (c.venue, c.year, c.track, c.status) == (venue, year, track, status)
    assert c.venue_id_raw == venueid


@pytest.mark.parametrize("venueid", NEVER_PARSE, ids=[v or "<empty>" for v in NEVER_PARSE])
def test_unparseable_is_unknown_never_main(venueid: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="openproceedings"):
        c = classify_venueid(venueid)
    assert (c.track, c.status, c.parsed) == ("unknown", "unknown", False)
    assert any("venueid_unparsed" in r.getMessage() for r in caplog.records)  # logged (DEBUG: per record)


@pytest.mark.parametrize(
    "venueid",
    [
        "NeurIPS.cc/2024/Workshop/Conference",  # a workshop named like a track
        "ICML.cc/2024/Workshop/Datasets_and_Benchmarks",
        "NeurIPS.cc/2024/Track/Datasets_and_Benchmarks/Workshop/X",
        "ICLR.cc/2024/Workshop_Kigali/Conference",
    ],
)
def test_workshop_wins_over_every_other_segment(venueid: str) -> None:
    assert classify_venueid(venueid).track == "workshop"


def test_segments_match_whole_never_as_substrings() -> None:
    assert classify_venueid("ICLR.cc/2024/Conferences").track == "other"
    assert classify_venueid("ICLR.cc/2024/WorkshopX/y").track == "other"  # `Workshop_` needs the underscore
    assert (
        classify_venueid("ICLR.cc/2024/Conference/Rejected_Submissions").status == "accepted"
    )  # not a suffix


PROCEEDINGS = [
    ("Conference", "main"),
    ("Datasets_and_Benchmarks_Track", "datasets_benchmarks"),
    ("Datasets_and_Benchmarks", "datasets_benchmarks"),
    ("Position_Paper_Track", "position"),
    ("Creative_AI_Track", "other"),
    ("", "unknown"),
    ("Workshop", "workshop"),
]


@pytest.mark.parametrize(("token", "track"), PROCEEDINGS, ids=[t or "<empty>" for t, _ in PROCEEDINGS])
def test_proceedings_claims(token: str, track: str) -> None:
    c = classify_proceedings(token)
    assert c.track == track
    assert c.status == "accepted"  # a proceedings listing means accepted (spec 01; decision-005)
