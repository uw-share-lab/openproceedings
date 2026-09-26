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
    ("NeurIPS.cc/2023/Track/Creative_AI", "NeurIPS", 2023, "other", "unknown"),  # parses, not in the taxonomy
    (
        "NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round1",
        "NeurIPS",
        2021,
        "datasets_benchmarks",
        "accepted",
    ),
    ("ICLR.cc/2013/Conference", "ICLR", 2013, "main", "accepted"),  # the first year that parses
    (
        "ICML.cc/2024/Workshop/Rejected",
        "ICML",
        2024,
        "workshop",
        "accepted",
    ),  # a workshop's name, not a status
    ("ICML.cc/2024/Workshop/Data_Submission", "ICML", 2024, "workshop", "accepted"),
    ("ICML.cc/2024/Workshop/Post_Decision_Theory", "ICML", 2024, "workshop", "accepted"),
    ("ICLR.cc/2024/Conference/rejected_submission", "ICLR", 2024, "main", "unknown"),  # status words any case
    ("ICLR.cc/2024/Conference/_Submission", "ICLR", 2024, "main", "unknown"),
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
    "ICLR.cc/2024/Conference/",  # an empty segment
    "ICLR.cc/2024//Conference",
    "ICLR.cc/2024/Submission",  # a status with no track in front of it
    "ICLR.cc/2024/Rejected_Submission",
    "ICLR.cc/2024/Conference/-/Blind_Submission",  # an invitation path, never a venueid (rule 6)
    "ICLR.cc/2024/Conference/-/Withdrawn_Submission",
    "ICML.cc/0000/Conference",  # a year outside 2013–2099
    "ICML.cc/2100/Conference",
    "ICLR.cc/2012/Conference",
    "ICLR.cc/2024/Blind_Submission",  # a status with no track in front of it
]


@pytest.mark.parametrize(
    ("venueid", "venue", "year", "track", "status"),
    VALIDATED + UNVERIFIED,
    ids=[r[0] for r in VALIDATED + UNVERIFIED],
)
def test_table(venueid: str, venue: str, year: int, track: str, status: str) -> None:
    c = classify_venueid(venueid)
    assert (c.venue, c.year, c.track, c.status) == (venue, year, track, status)
    assert c.venue_id_raw == venueid and c.parsed


@pytest.mark.parametrize("venueid", NEVER_PARSE, ids=[v or "<empty>" for v in NEVER_PARSE])
def test_unparseable_is_unknown_never_main(venueid: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="openproceedings"):
        c = classify_venueid(venueid)
    assert (c.track, c.status, c.parsed) == ("unknown", "unknown", False)
    [r] = [r for r in caplog.records if r.getMessage() == "venueid_unparsed"]
    assert r.levelno == logging.DEBUG and r.venue_id_raw == venueid  # type: ignore[attr-defined]  # per record


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
        classify_venueid("ICML.cc/2024/Workshop/SafeSubmission").status == "accepted"
    )  # a name, not a status
    assert classify_venueid("ICML.cc/2024/Workshop/AlignDecision").status == "accepted"


@pytest.mark.parametrize(
    "suffix",
    ["Rejected_Submissions", "Blind_Submission", "Withdrawn", "Desk_Rejected", "Post_Decision", "Rejected"],
)
def test_an_unmapped_status_is_unknown_never_accepted(suffix: str) -> None:
    c = classify_venueid(f"ICLR.cc/2024/Conference/{suffix}")
    assert (c.track, c.status) == ("main", "unknown")  # the track path is still exact


@pytest.mark.parametrize(
    "venueid",
    [
        "ICLR.cc/2024/Datasets_and_Benchmarks",  # D&B is NeurIPS's track
        "ICML.cc/2024/Track/Datasets_and_Benchmarks",
        "NeurIPS.cc/2024/Round1/Datasets_and_Benchmarks",  # order matters
        "NeurIPS.cc/2024/Track/Track/Datasets_and_Benchmarks_Track",
        "NeurIPS.cc/2024/Track/Datasets_and_Benchmarks/Creative_AI",
        "NeurIPS.cc/2024/Track/Datasets_and_Benchmarks_Track/Round1",
        "NeurIPS.cc/2024/Position",  # position is ICML's Position_Paper_Track only
        "ICLR.cc/2024/Track/Position",
        "ICML.cc/2025/Position_Paper_Track/Track",
        "ICML.cc/2025/Position_Paper_Track/X",
        "ICML.cc/2025/Position",
        "ICLR.cc/2024/Tiny_Papers",  # unseen spellings
        "ICLR.cc/2024/BlogPost",
        "NeurIPS.cc/2022/Competition_Track",
        "ICML.cc/2023/TinyPapers",  # TinyPapers is ICLR's
        "ICLR.cc/2024/Conference/Blind_Submission/Extra",
        "ICLR.cc/2024/Conference/Main",
    ],
)
def test_forms_outside_the_table_are_other(venueid: str) -> None:
    c = classify_venueid(venueid)
    assert (c.track, c.status) == ("other", "unknown")  # never accepted without a known form


@pytest.mark.parametrize(
    "venueid",
    [
        "NeurIPS.cc/2025/Position_Paper_Track",  # each row belongs to one organisation
        "ICLR.cc/2024/Datasets_and_Benchmarks_Track",
        "ICML.cc/2024/Track/Datasets_and_Benchmarks_Track",
        "ICML.cc/2021/Track/Datasets_and_Benchmarks/Round2",
        "ICLR.cc/2024/Track/Competition",
        "ICML.cc/2024/BlogPosts",
        "ICLR.cc/2024/Conference/Rejected_Submission_2",
        "ICLR.cc/2024/Conference/Under_Review",
        "ICLR.cc/2024/Conference/Rejected_Submission/Conference",
    ],
)
def test_rows_belong_to_their_organisation(venueid: str) -> None:
    assert classify_venueid(venueid).track == "other"


def test_workshop_is_recognised_in_any_case() -> None:
    assert classify_venueid("ICLR.cc/2024/workshop/X").track == "workshop"
    assert classify_proceedings("Workshop/X").track == "workshop"


PROCEEDINGS = [
    ("Conference", "main"),
    ("Datasets_and_Benchmarks_Track", "datasets_benchmarks"),
    ("Datasets_and_Benchmarks", "datasets_benchmarks"),
    ("Position_Paper_Track", "position"),
    ("Creative_AI_Track", "other"),
    ("", "unknown"),
    ("conference", "unknown"),  # an unseen token is never guessed
    ("Main", "unknown"),
    ("Workshop", "workshop"),
]


@pytest.mark.parametrize(("token", "track"), PROCEEDINGS, ids=[t or "<empty>" for t, _ in PROCEEDINGS])
def test_proceedings_claims(token: str, track: str) -> None:
    c = classify_proceedings(token)
    assert c.track == track
    assert c.parsed is (track != "unknown")
    assert c.status == "accepted"  # a proceedings listing means accepted (spec 01; decision-005)
