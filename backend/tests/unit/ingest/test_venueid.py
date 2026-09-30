"""Track and status from an OpenReview venueid or a proceedings claim (spec 01 §Track taxonomy; openreview-venueids
and track-taxonomy skills; task-020). Every row stays forever; add one per new form seen in a crawl log."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.ingest.classify import (
    _V1_VENUE,
    classify_proceedings,
    classify_v1_venue,
    classify_venueid,
    is_v1,
)

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

LIVE: list[tuple[str, str | None, int | None, str, str]] = [
    # forms checked against live notes on 2026-09-27 (TASK-002; docs/research/2026-09-27-openreview-and-
    # proceedings-facts.md §venueid forms confirmed); FIXTURE_ROWS below reads the recorded notes themselves
    (
        "NeurIPS.cc/2025/Position_Paper_Track",
        "NeurIPS",
        2025,
        "position",
        "accepted",
    ),  # 40 accepted (TASK-094)
    (
        "NeurIPS.cc/2025/Position_Paper_Track/Rejected_Submission",
        "NeurIPS",
        2025,
        "position",
        "rejected",
    ),  # 55
    ("NeurIPS.cc/2024/Competition_Track", "NeurIPS", 2024, "competition", "accepted"),  # 16 (TASK-094)
    ("NeurIPS.cc/2025/Competition_Track", "NeurIPS", 2025, "competition", "accepted"),
    # the 2026 rename of D&B: a live group with no public notes yet (TASK-094)
    ("NeurIPS.cc/2026/Evaluations_and_Datasets_Track", "NeurIPS", 2026, "datasets_benchmarks", "accepted"),
    (
        "NeurIPS.cc/2026/Evaluations_and_Datasets_Track/Rejected_Submission",
        "NeurIPS",
        2026,
        "datasets_benchmarks",
        "rejected",
    ),
    ("NeurIPS.cc/2025/Creative_AI_Track", "NeurIPS", 2025, "other", "unknown"),
    ("ICLR.cc/2025/Workshop/ICBINB/Rejected_Submission", "ICLR", 2025, "workshop", "rejected"),
    # API v1 venue-years: the bare path is on rejected papers too, so it never gives status (TASK-095)
    ("ICLR.cc/2017/conference", "ICLR", 2017, "other", "unknown"),  # lower case; 245 of 490 rejected
    ("ICLR.cc/2021/Conference", "ICLR", 2021, "main", "unknown"),
    ("ICLR.cc/2022/Conference", "ICLR", 2022, "main", "unknown"),  # 1,523 rejected carry it
    ("ICLR.cc/2023/Conference", "ICLR", 2023, "main", "unknown"),  # 2,219 rejected carry it
    ("ICLR.cc/2023/BlogPosts", "ICLR", 2023, "blogpost", "unknown"),
    ("NeurIPS.cc/2021/Conference", "NeurIPS", 2021, "main", "unknown"),  # 136 opt-in rejected carry it
    ("NeurIPS.cc/2022/Conference", "NeurIPS", 2022, "main", "unknown"),  # 153 opt-in rejected carry it
    ("NeurIPS.cc/2022/Track/Datasets_and_Benchmarks", "NeurIPS", 2022, "datasets_benchmarks", "unknown"),
    # the first v2 years keep venueid status
    ("NeurIPS.cc/2023/Conference/Rejected_Submission", "NeurIPS", 2023, "main", "rejected"),
    ("ICLR.cc/2024/Conference/Rejected_Submission", "ICLR", 2024, "main", "rejected"),
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
        "unknown",  # v1: status comes from `content.venue` (TASK-095)
    ),
    ("ICML.cc/2024/Workshop/X/Submission", "ICML", 2024, "workshop", "unknown"),
    ("ICML.cc/2024/Workshop/X/Rejected_Submission", "ICML", 2024, "workshop", "rejected"),
    ("ICLR.cc/2023/TinyPapers", "ICLR", 2023, "tiny_papers", "unknown"),  # v1: all 219 "Submitted to"
    ("ICLR.cc/2024/BlogPosts", "ICLR", 2024, "blogpost", "accepted"),
    ("NeurIPS.cc/2022/Track/Competition", "NeurIPS", 2022, "competition", "unknown"),  # a v1 year
    ("NeurIPS.cc/2023/Track/Creative_AI", "NeurIPS", 2023, "other", "unknown"),  # parses, not in the taxonomy
    (
        "NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round1",
        "NeurIPS",
        2021,
        "datasets_benchmarks",
        "unknown",  # v1: 78 of Round 1's 144 carry this bare path and are rejected (`iBLHqLgbRn`)
    ),
    ("ICLR.cc/2013/Conference", "ICLR", 2013, "main", "unknown"),  # the first year that parses (a v1 year)
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
    VALIDATED + LIVE + UNVERIFIED,
    ids=[r[0] for r in VALIDATED + LIVE + UNVERIFIED],
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
        "NeurIPS.cc/2024/Competition",  # competition is `Competition_Track` or `Track/Competition`
        "NeurIPS.cc/2024/Competition/LMC",  # a competition's own group (seen live), not the track
        "NeurIPS.cc/2026/Evaluations_and_Datasets",
        "NeurIPS.cc/2026/Track/Evaluations_and_Datasets_Track",
        "ICML.cc/2023/TinyPapers",  # TinyPapers is ICLR's
        "ICLR.cc/2024/Conference/Blind_Submission/Extra",
        "ICLR.cc/2024/Conference/Main",
        "ICLR.cc/2024/conference",  # track segments match exactly, case included
        "ICLR.cc/2024/CONFERENCE",
    ],
)
def test_forms_outside_the_table_are_other(venueid: str) -> None:
    c = classify_venueid(venueid)
    assert (c.track, c.status) == ("other", "unknown")  # never accepted without a known form


@pytest.mark.parametrize(
    "venueid",
    [
        "NeurIPS.cc/2024/Position_Paper_Track",  # first verified in 2025
        "NeurIPS.cc/2025/Evaluations_and_Datasets_Track",  # the D&B rename starts in 2026
        "ICML.cc/2024/Position_Paper_Track",  # 2024 position papers used Conference
    ],
)
def test_track_forms_do_not_leak_into_adjacent_years(venueid: str) -> None:
    c = classify_venueid(venueid)
    assert (c.track, c.status) == ("other", "unknown")


@pytest.mark.parametrize(
    "venueid",
    [
        "ICLR.cc/2025/Position_Paper_Track",  # each row belongs to one organisation
        "ICML.cc/2026/Evaluations_and_Datasets_Track",
        "ICML.cc/2024/Competition_Track",
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


# --- Recorded notes (backend/tests/fixtures/http/openreview; TASK-002's live run, TASK-094/095) ---

OPENREVIEW = Path(__file__).parents[2] / "fixtures" / "http" / "openreview"


def _submission(fixture: str) -> dict[str, Any]:
    """The fixture's submission note (`id == forum`; a forum listing isn't ordered), content unwrapped."""
    notes = json.loads((OPENREVIEW / fixture).read_text())["response"]["json"]["notes"]
    note = next(n for n in notes if n["id"] == n["forum"])
    return {k: v["value"] if isinstance(v, dict) and "value" in v else v for k, v in note["content"].items()}


V2_NOTES: list[tuple[str, str, str]] = [
    # fixture, track, status: the v2 venueid decides both (openreview-api skill §The authority rule)
    ("v2/iclr-2024/notes-accepted.json", "main", "accepted"),
    ("v2/iclr-2024/notes-rejected.json", "main", "rejected"),
    ("v2/iclr-2024/notes-withdrawn.json", "main", "withdrawn"),
    ("v2/iclr-2024/notes-desk-rejected.json", "main", "desk_rejected"),
    ("v2/iclr-2024/notes-tinypapers.json", "tiny_papers", "accepted"),
    ("v2/iclr-2025/notes-blogposts.json", "blogpost", "accepted"),
    ("v2/iclr-2025/notes-workshop-rejected.json", "workshop", "rejected"),
    ("v2/iclr-2026/notes-accepted.json", "main", "accepted"),
    ("v2/icml-2023/notes-accepted.json", "main", "accepted"),
    ("v2/icml-2024/notes-accepted.json", "main", "accepted"),
    ("v2/icml-2025/notes-position.json", "position", "accepted"),
    ("v2/icml-2026/notes-accepted.json", "main", "accepted"),
    ("v2/neurips-2023/notes-db-track-path.json", "datasets_benchmarks", "accepted"),
    ("v2/neurips-2024/notes-competition.json", "competition", "accepted"),  # TASK-094 (was `other`)
    ("v2/neurips-2024/notes-db.json", "datasets_benchmarks", "accepted"),
    ("v2/neurips-2024/notes-db-rejected.json", "datasets_benchmarks", "rejected"),
    ("v2/neurips-2025/notes-creative-ai.json", "other", "unknown"),
    ("v2/neurips-2025/notes-position.json", "position", "accepted"),  # TASK-094 (was `other`)
    ("v2/neurips-2025/notes-workshop-city.json", "workshop", "accepted"),
    ("v2/neurips-2026/notes-accepted.json", "other", "unknown"),
    # TASK-101: one note per presentation string, trimmed from the TASK-054 crawl cache
    ("v2/iclr-2024/notes-presentation-conference.json", "main", "accepted"),
    ("v2/iclr-2024/notes-presentation-blogposts.json", "blogpost", "accepted"),
    ("v2/iclr-2024/notes-presentation-tinypapers.json", "tiny_papers", "accepted"),
    ("v2/iclr-2025/notes-presentation-conference.json", "main", "accepted"),
    ("v2/iclr-2025/notes-presentation-blogposts.json", "blogpost", "accepted"),
    ("v2/icml-2023/notes-presentation-conference.json", "main", "accepted"),
    ("v2/icml-2024/notes-presentation-conference.json", "main", "accepted"),
    ("v2/icml-2025/notes-presentation-conference.json", "main", "accepted"),
    ("v2/icml-2025/notes-presentation-position-paper-track.json", "position", "accepted"),
    ("v2/neurips-2023/notes-presentation-conference.json", "main", "accepted"),
    (
        "v2/neurips-2023/notes-presentation-track-datasets-and-benchmarks.json",
        "datasets_benchmarks",
        "accepted",
    ),
    ("v2/neurips-2024/notes-presentation-conference.json", "main", "accepted"),
    (
        "v2/neurips-2024/notes-presentation-datasets-and-benchmarks-track.json",
        "datasets_benchmarks",
        "accepted",
    ),
    ("v2/neurips-2024/notes-presentation-competition-track.json", "competition", "accepted"),
    ("v2/neurips-2025/notes-presentation-conference.json", "main", "accepted"),
    (
        "v2/neurips-2025/notes-presentation-datasets-and-benchmarks-track.json",
        "datasets_benchmarks",
        "accepted",
    ),
    ("v2/neurips-2025/notes-presentation-position-paper-track.json", "position", "accepted"),
]

V2_VENUE_LABELS = [
    ("v2/iclr-2024/notes-tinypapers.json", "Tiny Papers @ ICLR 2024 Archive"),
    ("v2/neurips-2025/notes-workshop-city.json", "ResponsibleFM @ NeurIPS 2025"),
    # TASK-101: scrub.py once read this label as an email address
    ("v2/iclr-2024/notes-presentation-blogposts.json", "BT@ICLR2024"),
]

V1_NOTES: list[tuple[str, str, str, str]] = [
    # fixture, the venueid's track, then track and status from `content.venue` (TASK-095): the venueid's
    # status is always `unknown` in a v1 year, and the venue string decides
    ("v1/iclr-2017/note-rejected-bare-venueid.json", "other", "main", "rejected"),  # `Submitted to ICLR 2017`
    ("v1/iclr-2017/note-invite-to-workshop.json", "other", "workshop", "unknown"),
    ("v1/iclr-2017/note-authors-string-live.json", "other", "main", "rejected"),
    ("v1/iclr-2017/note-workshop-invitation-live.json", "other", "workshop", "unknown"),
    ("v1/iclr-2017/notes-conference-listing.json", "other", "main", "accepted"),
    ("v1/iclr-2021/note-accepted.json", "main", "main", "accepted"),
    ("v1/iclr-2021/forum-accepted.json", "main", "main", "accepted"),
    # the venue string alone says accepted; the withdrawn invitation disagrees: the v1 adapter makes it unknown + a conflict row
    ("v1/iclr-2021/note-withdrawn-with-accepted-venue.json", "main", "main", "accepted"),
    ("v1/iclr-2022/note-rejected-bare-venueid.json", "main", "main", "rejected"),  # `ICLR 2022 Submitted`
    ("v1/iclr-2022/notes-blind-listing.json", "main", "main", "accepted"),
    ("v1/iclr-2023/note-rejected-bare-venueid.json", "main", "main", "rejected"),  # `Submitted to ICLR 2023`
    ("v1/iclr-2023/notes-blind-count.json", "main", "main", "accepted"),  # `ICLR 2023 poster`
    ("v1/iclr-2023/note-tinypapers.json", "tiny_papers", "tiny_papers", "unknown"),
    ("v1/iclr-2023/notes-blogposts-blind-submission.json", "blogpost", "blogpost", "accepted"),
    ("v1/neurips-2021/note-rejected.json", "main", "main", "rejected"),  # `NeurIPS 2021 Submitted`
    ("v1/neurips-2021/notes-main-listing.json", "main", "main", "accepted"),
    (
        "v1/neurips-2021/note-db-round1-rejected.json",
        "datasets_benchmarks",
        "datasets_benchmarks",
        "rejected",
    ),
    (
        "v1/neurips-2021/note-db-round2-accepted.json",
        "datasets_benchmarks",
        "datasets_benchmarks",
        "accepted",
    ),
    ("v1/neurips-2022/note-accepted.json", "main", "main", "accepted"),  # `NeurIPS 2022 Accept`
    ("v1/neurips-2022/notes-main-listing.json", "main", "main", "accepted"),
    (
        "v1/neurips-2022/notes-db-listing.json",
        "datasets_benchmarks",
        "datasets_benchmarks",
        "accepted",
    ),
]

V1_NO_VENUE_EVIDENCE = {
    # submission notes with neither a venueid nor a venue string: status is from `content.decision`, a
    # decision note or an invitation (the v1 adapters, TASK-051), never from classify.py
    "v1/iclr-2013/notes-submission-decision-field.json",
    "v1/iclr-2014/notes-submission-no-decision.json",
    "v1/iclr-2016/notes-workshop.json",
    "v1/iclr-2017/note-workshop-null-nonreaders-live.json",  # nonreaders null (TASK-119); no venue string
    "v1/iclr-2018/forum-rejected.json",
    "v1/iclr-2018/notes-blind-listing.json",
    "v1/iclr-2018/notes-withdrawn-listing.json",
    "v1/iclr-2019/forum-rejected-meta-review.json",
    "v1/iclr-2019/notes-blind-listing.json",
    "v1/iclr-2019/notes-withdrawn-listing.json",
    "v1/iclr-2020/forum-accepted.json",
    "v1/iclr-2020/forum-accepted-spotlight.json",  # Accept (Spotlight), TASK-123
    "v1/iclr-2020/forum-accepted-talk.json",  # Accept (Talk), TASK-123
    "v1/iclr-2020/forum-rejected.json",
    "v1/iclr-2020/notes-blind-listing.json",
    "v1/iclr-2020/notes-desk-rejected-listing.json",
    "v1/iclr-2020/notes-withdrawn-listing.json",
    "v1/iclr-2021/forum-rejected-no-venueid.json",
    "v1/iclr-2021/notes-blind-listing.json",
    "v1/iclr-2021/notes-desk-rejected-listing.json",
    "v1/iclr-2022/note-withdrawn-empty-venueid.json",  # `venue = venueid = ""`
    "v1/iclr-2022/notes-desk-rejected-listing.json",
    "v1/iclr-2023/note-desk-rejected.json",
}


def test_every_recorded_note_has_a_row() -> None:
    """A newly recorded note fixture fails here until it gets a row (openreview-venueids skill: every form
    seen gets a table-test row)."""
    recorded = set()
    for f in OPENREVIEW.rglob("*.json"):
        body = json.loads(f.read_text())["response"].get("json")
        if isinstance(body, dict) and body.get("notes") and "content" in body["notes"][0]:
            recorded.add(f.relative_to(OPENREVIEW).as_posix())
    rows = {r[0] for r in V2_NOTES} | {r[0] for r in V1_NOTES} | V1_NO_VENUE_EVIDENCE
    assert recorded == rows


@pytest.mark.parametrize(("fixture", "track", "status"), V2_NOTES, ids=[r[0] for r in V2_NOTES])
def test_recorded_v2_notes(fixture: str, track: str, status: str) -> None:
    c = classify_venueid(_submission(fixture)["venueid"])
    assert (c.track, c.status, c.parsed) == (track, status, True)
    assert c.year is not None and c.venue is not None and not is_v1(c.venue, c.year)


@pytest.mark.parametrize(("fixture", "expected"), V2_VENUE_LABELS, ids=[r[0] for r in V2_VENUE_LABELS])
def test_recorded_v2_venue_labels_survive_scrubbing(fixture: str, expected: str) -> None:
    assert _submission(fixture)["venue"] == expected


@pytest.mark.parametrize(
    ("fixture", "venueid_track", "track", "status"), V1_NOTES, ids=[r[0] for r in V1_NOTES]
)
def test_recorded_v1_notes_take_status_from_the_venue_string(
    fixture: str, venueid_track: str, track: str, status: str
) -> None:
    content = _submission(fixture)
    by_id = classify_venueid(content["venueid"])
    assert (by_id.track, by_id.status) == (venueid_track, "unknown")  # never status evidence in v1
    assert by_id.venue is not None and by_id.year is not None and is_v1(by_id.venue, by_id.year)
    by_venue = classify_v1_venue(content["venue"])
    assert (by_venue.track, by_venue.status, by_venue.parsed) == (track, status, True)
    assert (by_venue.venue, by_venue.year) == (by_id.venue, by_id.year)  # the two agree on venue and year


@pytest.mark.parametrize("fixture", sorted(V1_NO_VENUE_EVIDENCE))
def test_recorded_v1_notes_without_venue_evidence(fixture: str) -> None:
    content = _submission(fixture)
    assert not content.get("venueid") and not content.get("venue")


V1_VENUE_UNKNOWN = [
    "",
    "ICLR 2022 submitted",  # exact, case included
    "ICLR 2022 Submitted ",
    "Submitted to ICLR 2024",  # a v2 string: v2 status comes from the venueid
    "NeurIPS 2022 Datasets and Benchmarks",  # the live string has a trailing space
    "ICLR 2018 Accept (Poster)",  # a decision, not a venue string
    "conferencePoster-iclr2013-conference",  # ICLR 2013's `content.decision` (TASK-051)
]


@pytest.mark.parametrize("venue", V1_VENUE_UNKNOWN)
def test_an_unlisted_v1_venue_string_is_unknown(venue: str) -> None:
    c = classify_v1_venue(venue)
    assert (c.track, c.status, c.venue, c.year, c.parsed) == ("unknown", "unknown", None, None, False)


def test_no_v1_venue_string_puts_a_rejected_paper_in_a_default_track_as_accepted() -> None:
    """`Submitted` wording is never accepted, and nothing outside main / D&B is accepted by default."""
    for venue, (_org, _year, track, status) in _V1_VENUE.items():
        if "Submitted" in venue:
            assert status == "rejected" or track == "tiny_papers", venue
        if status == "accepted":
            assert "Submitted" not in venue, venue


V1_VENUE_YEARS = [("ICLR", y) for y in range(2013, 2024)] + [("NeurIPS", 2021), ("NeurIPS", 2022)]
_TRACK_PATHS = [
    "Conference",
    "conference",
    "Track/Datasets_and_Benchmarks",
    "Track/Datasets_and_Benchmarks/Round1",
    "TinyPapers",
    "BlogPosts",
    "Workshop/X",
    "Position_Paper_Track",
    "Competition_Track",
]
_SUFFIXES = ["", "/Submission", "/Rejected_Submission", "/Withdrawn_Submission", "/Desk_Rejected_Submission"]


@given(st.sampled_from(V1_VENUE_YEARS), st.sampled_from(_TRACK_PATHS), st.sampled_from(_SUFFIXES))
def test_a_v1_venueid_never_gives_status(venue_year: tuple[str, int], path: str, suffix: str) -> None:
    venue, year = venue_year
    assert classify_venueid(f"{venue}.cc/{year}/{path}{suffix}").status == "unknown"


@pytest.mark.parametrize(
    ("venue", "year", "v1"),
    [("ICLR", 2012, False), ("ICLR", 2013, True), ("ICLR", 2023, True), ("ICLR", 2024, False),
     ("NeurIPS", 2020, False), ("NeurIPS", 2021, True), ("NeurIPS", 2022, True), ("NeurIPS", 2023, False),
     ("ICML", 2020, False), ("ICML", 2022, False), ("ICML", 2023, False)],
)  # fmt: skip
def test_v1_venue_years(venue: str, year: int, v1: bool) -> None:
    """The boundary years (research doc §Hosts and API versions): ICLR 2024 and NeurIPS 2023 are v2."""
    assert is_v1(venue, year) is v1
