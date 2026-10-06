"""The OpenReview v2 crawler (TASK-050) against the recorded, scrubbed fixtures: every recorded venueid form,
the authority rule, group and venueid enumeration, pagination, resume, offline replay, dry run, the
snapshot build and the CLI. No network (conftest); the transport is `FakeOpenReview`."""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from openproceedings import cli
from openproceedings.ingest import snapshot as snap
from openproceedings.ingest.classify import V2_PRESENTATION, classify_venueid
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.sources import openreview_v2 as orv
from openproceedings.ingest.sources.common import PROGRESS_SECONDS, Heartbeat
from openproceedings.ingest.sources.http import CacheMiss as OpenReviewCacheMiss
from openproceedings.ingest.sources.http import Request, Response
from openproceedings.ingest.sources.http import RetriesExhausted as OpenReviewRetriesExhausted
from openproceedings.ingest.sources.openreview_client import Credentials, OpenReviewClient

from tests.unit.ingest.openreview_fakes import (
    PASSWORD,
    USERNAME,
    FakeClock,
    FakeOpenReview,
    TickingClock,
    clone,
    group_doc,
    json_response,
    recorded,
    recorded_note,
    response,
)

PAGE_URL = "https://api2.openreview.net/notes?content.venueid=X&limit=1000&offset=0&sort=number:asc"
FETCHED = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
CONF = "ICLR.cc/2024/Conference"

# fixture → (venue, year, track, status), per the openreview-venueids skill's table
FORMS = [
    ("iclr-2024/notes-accepted.json", "ICLR", 2024, "main", "accepted"),
    ("iclr-2024/notes-rejected.json", "ICLR", 2024, "main", "rejected"),
    ("iclr-2024/notes-withdrawn.json", "ICLR", 2024, "main", "withdrawn"),
    ("iclr-2024/notes-desk-rejected.json", "ICLR", 2024, "main", "desk_rejected"),
    ("iclr-2024/notes-tinypapers.json", "ICLR", 2024, "tiny_papers", "accepted"),
    ("iclr-2025/notes-blogposts.json", "ICLR", 2025, "blogpost", "accepted"),
    ("iclr-2025/notes-workshop-rejected.json", "ICLR", 2025, "workshop", "rejected"),
    ("iclr-2026/notes-accepted.json", "ICLR", 2026, "main", "accepted"),
    ("neurips-2023/notes-db-track-path.json", "NeurIPS", 2023, "datasets_benchmarks", "accepted"),
    ("neurips-2024/notes-db.json", "NeurIPS", 2024, "datasets_benchmarks", "accepted"),
    ("neurips-2024/notes-db-rejected.json", "NeurIPS", 2024, "datasets_benchmarks", "rejected"),
    ("neurips-2025/notes-workshop-city.json", "NeurIPS", 2025, "workshop", "accepted"),
    ("neurips-2025/notes-creative-ai.json", "NeurIPS", 2025, "other", "unknown"),
    ("neurips-2026/notes-accepted.json", "NeurIPS", 2026, "other", "unknown"),
    ("icml-2023/notes-accepted.json", "ICML", 2023, "main", "accepted"),
    ("icml-2024/notes-accepted.json", "ICML", 2024, "main", "accepted"),
    ("icml-2025/notes-position.json", "ICML", 2025, "position", "accepted"),
    ("icml-2026/notes-accepted.json", "ICML", 2026, "main", "accepted"),
    # TASK-178, from the 2026 crawl cache: an opt-in public rejection and an undecided workshop submission
    ("icml-2026/notes-rejected.json", "ICML", 2026, "main", "rejected"),
    ("icml-2026/notes-workshop-submission.json", "ICML", 2026, "workshop", "unknown"),
]
# classify.py's mapping of these is TASK-094's (position / competition); the crawler must just follow it
DELEGATED = [
    ("neurips-2025/notes-position.json", "NeurIPS", 2025),
    ("neurips-2024/notes-competition.json", "NeurIPS", 2024),
]

RECORDED_V2_YEARS = {
    "iclr": range(2024, 2027),
    "neurips": range(2023, 2027),
    "icml": range(2023, 2027),
}
LIVE_COVERAGE_FIXTURES = {
    "icml-2023/groups-parent.json": "ICML.cc/2023",
    "icml-2023/notes-accepted.json": None,
    "iclr-2026/groups-parent.json": "ICLR.cc/2026",
    "iclr-2026/notes-accepted.json": None,
    "neurips-2026/groups-parent.json": "NeurIPS.cc/2026",
    "neurips-2026/notes-accepted.json": None,
    "icml-2026/groups-parent.json": "ICML.cc/2026",
    "icml-2026/notes-accepted.json": None,
}


def build(note: dict[str, Any], venue: str = "ICLR", year: int = 2024) -> PaperRecord | str:
    return orv.note_record(note, venue=venue, year=year, page_url=PAGE_URL, fetched_at=FETCHED)


def test_recorded_fixture_inventory_covers_every_v2_venue_year() -> None:
    actual = {
        (venue, int(year))
        for path in (Path(__file__).parents[2] / "fixtures" / "http" / "openreview" / "v2").glob(
            "*-????/notes-*.json"
        )
        for venue, year in [path.parent.name.rsplit("-", 1)]
    }
    expected = {(venue, year) for venue, years in RECORDED_V2_YEARS.items() for year in years}
    assert expected <= actual


@pytest.mark.parametrize(("fixture", "parent"), LIVE_COVERAGE_FIXTURES.items())
def test_new_live_fixture_is_authenticated_and_replays_from_the_cache_offline(
    fixture: str, parent: str | None, tmp_path: Path
) -> None:
    exchange = recorded(fixture)
    request_url = exchange["request"]["url"]
    parts = urlsplit(request_url)
    params = {key: values[0] for key, values in parse_qs(parts.query).items()}
    assert exchange["request"] == {"method": "GET", "url": request_url, "authenticated": True}
    assert exchange["response"]["status"] == 200
    if parent is not None:
        assert parts.path == "/groups" and params["parent"] == parent
        assert exchange["response"]["json"]["groups"]
    else:
        assert parts.path == "/notes"
        assert exchange["response"]["json"]["notes"]

    def recorded_exchange(request: Request) -> Response | None:
        return response(fixture) if request.method == "GET" and request.url == request_url else None

    server = FakeOpenReview(override=recorded_exchange)
    fetched = client(tmp_path, server).get(parts.path, params)
    silent = FakeOpenReview()
    replayed = client(tmp_path, silent, credentials=None, offline=True).get(parts.path, params)
    assert silent.calls == [] and replayed == fetched


# --- notes → records -------------------------------------------------------------------------------------


@pytest.mark.parametrize(("fixture", "venue", "year", "track", "status"), FORMS)
def test_each_recorded_venueid_form(fixture: str, venue: str, year: int, track: str, status: str) -> None:
    note = recorded_note(fixture)
    record = build(note, venue, year)
    assert isinstance(record, PaperRecord)
    assert (record.venue, record.year, record.track, record.status) == (venue, year, track, status)
    assert record.id == f"op:{venue.lower()}:{year}:{note['id']}"
    assert record.venue_id_raw == note["content"]["venueid"]["value"]


# --- control characters in a title (TASK-180) -----------------------------------------------------------------


def test_a_title_with_control_characters_is_imported_with_spaces_and_says_so(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ICLR 2026 `xHMNX3l8rx` (two U+0002 in its title) was skipped as `invalid`: a real paper lost to invisible
    characters. The title keeps everything else; the abstract gets the same rule (decision-044, TASK-188)."""
    note = recorded_note("iclr-2026/notes-accepted.json")
    note["content"]["title"]["value"] = "A SPEC\x02TRUM FROM STATISTICAL TO CAUSAL\x02"
    note["content"]["abstract"]["value"] = "the LiDAR modal\x02ity"
    with caplog.at_level(logging.DEBUG):
        record = build(note, "ICLR", 2026)
    assert isinstance(record, PaperRecord)
    assert (
        record.title == "A SPEC TRUM FROM STATISTICAL TO CAUSAL" and record.abstract == "the LiDAR modal ity"
    )
    [title] = record.claims("title")
    assert title.evidence == "content.title (2 control characters replaced by a space)"
    [abstract] = record.claims("abstract")
    assert (abstract.value, abstract.evidence) == (
        "the LiDAR modal ity",
        "content.abstract (1 control character replaced by a space)",
    )
    [line] = [r for r in caplog.records if r.getMessage() == "openreview_title_control_characters"]
    assert (line.levelno, line.__dict__["forum"], line.__dict__["replaced"]) == (logging.DEBUG, note["id"], 2)
    assert "title" not in line.__dict__  # a title is never logged


@pytest.mark.parametrize(
    ("title", "evidence"),
    [
        ("Trust\x00AI", "content.title (1 control character replaced by a space)"),
        (
            "Details  through\x0b Chain",
            "content.title",
        ),  # whitespace controls always collapsed: evidence unchanged
        ("Trust in AI", "content.title"),
    ],
)
def test_the_title_claims_evidence_counts_only_what_was_replaced(title: str, evidence: str) -> None:
    note = recorded_note("iclr-2024/notes-accepted.json")
    note["content"]["title"]["value"] = title
    record = build(note)
    assert isinstance(record, PaperRecord) and [c.evidence for c in record.claims("title")] == [evidence]
    assert record.title == " ".join(title.replace("\x00", " ").split())


@pytest.mark.parametrize(
    ("abstract", "stored", "evidence"),
    [
        (
            "quanti\x02fying 500x\x02 longer",
            "quanti fying 500x longer",
            "content.abstract (2 control characters replaced by a space)",
        ),
        (
            "We  study\x0b trust.",
            "We study trust.",
            "content.abstract",
        ),  # whitespace controls: evidence unchanged
        ("\x00\x02 ", None, None),  # nothing left: no abstract, the paper is kept
        ("\x02\u2026 a snippet", None, None),  # a snippet once the control is a space
    ],
)
def test_an_abstract_with_control_characters_is_imported_with_spaces_and_says_so(
    abstract: str, stored: str | None, evidence: str | None
) -> None:
    """decision-044 (TASK-188): the title rule, for abstracts."""
    note = recorded_note("iclr-2024/notes-accepted.json")
    note["content"]["abstract"]["value"] = abstract
    record = build(note)
    assert isinstance(record, PaperRecord) and record.abstract == stored
    assert [c.evidence for c in record.claims("abstract")] == ([] if evidence is None else [evidence])


@pytest.mark.parametrize("title", ["\x00\x02", " \x02 ", "", None, 7])
def test_a_title_of_only_control_characters_is_no_title(title: object) -> None:
    note = recorded_note("iclr-2024/notes-accepted.json")
    note["content"]["title"] = {"value": title}
    assert build(note) == "no_title"


@pytest.mark.parametrize(("fixture", "venue", "year"), DELEGATED)
def test_forms_classify_py_owns_follow_it(fixture: str, venue: str, year: int) -> None:
    note = recorded_note(fixture)
    record = build(note, venue, year)
    expected = classify_venueid(note["content"]["venueid"]["value"])
    assert isinstance(record, PaperRecord) and (record.track, record.status) == (
        expected.track,
        expected.status,
    )


def test_the_notes_own_venueid_decides_never_its_invitations() -> None:
    note = recorded_note("iclr-2024/notes-accepted.json")  # invitations name ICLR.cc/2024/Conference/-/…
    note["content"]["venueid"]["value"] = f"{CONF}/Rejected_Submission"
    record = build(note)
    assert isinstance(record, PaperRecord) and (record.track, record.status) == ("main", "rejected")
    assert all(i.startswith(f"{CONF}/") for i in note["invitations"])


def test_only_the_submission_note_becomes_a_record() -> None:
    reply = recorded_note("iclr-2024/notes-accepted.json")
    reply["id"] = "DecisionNote1"  # e.g. a Decision reply in the forum (zkNCWtw2fd)
    assert build(reply) == "not_submission"


def test_a_note_without_a_venueid_is_unknown_and_logged_at_debug(caplog: pytest.LogCaptureFixture) -> None:
    note = recorded_note("iclr-2024/notes-accepted.json")
    del note["content"]["venueid"]
    with caplog.at_level(logging.DEBUG):
        record = build(note)
    assert isinstance(record, PaperRecord) and (record.track, record.status) == ("unknown", "unknown")
    [line] = [r for r in caplog.records if r.getMessage() == "openreview_unknown_track"]
    # a per-note line is DEBUG; the crawl counts them in its one attention WARNING (TASK-116)
    assert line.__dict__["forum"] == note["id"] and line.levelno == logging.DEBUG


def test_an_unparseable_venueid_is_unknown_never_guessed() -> None:
    note = recorded_note("iclr-2024/notes-accepted.json")
    note["content"]["venueid"]["value"] = "ICLR.cc/2024/Conference/-/Submission"
    record = build(note)
    assert isinstance(record, PaperRecord) and (record.track, record.status) == ("unknown", "unknown")


def test_a_venueid_naming_another_venue_year_is_skipped_never_re_yeared() -> None:
    assert build(recorded_note("iclr-2025/notes-blogposts.json"), "ICLR", 2024) == "out_of_scope"


def test_claims_carry_the_source_the_page_and_its_fetch_time() -> None:
    note = recorded_note("iclr-2024/notes-accepted.json")
    record = build(note)
    assert isinstance(record, PaperRecord)
    assert {c.source for c in record.provenance} == {"openreview_v2"}
    assert {c.url for c in record.provenance} == {PAGE_URL} and {c.fetched_at for c in record.provenance} == {
        FETCHED
    }
    fields = {c.field: c for c in record.provenance}
    assert fields["status"].evidence == fields["track"].evidence == f"venueid={CONF}"
    assert set(fields) == {"venue", "year", "track", "status", "title", "authors", "abstract", "keywords",
                           "presentation", "venue_id_raw", "urls.forum", "urls.pdf"}  # fmt: skip
    assert (record.presentation, fields["presentation"].evidence) == (
        "poster",
        "content.venue=ICLR 2024 poster",
    )
    assert record.urls.forum == f"https://openreview.net/forum?id={note['id']}"
    assert record.urls.pdf == f"https://openreview.net{note['content']['pdf']['value']}"
    assert record.abstract == "Synthetic abstract text 20." and record.title == "Synthetic title text 1."


def test_a_pdf_value_that_is_not_an_openreview_pdf_path_is_dropped() -> None:
    note = recorded_note("iclr-2024/notes-accepted.json")
    note["content"]["pdf"]["value"] = "https://evil.example/x.pdf"
    record = build(note)
    assert isinstance(record, PaperRecord) and record.urls.pdf is None


# --- presentation (TASK-101) -------------------------------------------------------------------------------------

# (fixture, content.venue, presentation): every row of classify.V2_PRESENTATION, each on a recorded note
# (the notes-presentation-* fixtures are one note per string, trimmed from the TASK-054 crawl cache; the 2026
# ones from the TASK-178 cache)
PRESENTATIONS = [
    ("iclr-2024/notes-presentation-conference.json", "ICLR 2024 oral", "oral"),
    ("iclr-2024/notes-presentation-conference.json", "ICLR 2024 spotlight", "spotlight"),
    ("iclr-2024/notes-presentation-conference.json", "ICLR 2024 poster", "poster"),
    ("iclr-2024/notes-presentation-blogposts.json", "BT@ICLR2024", None),
    ("iclr-2024/notes-presentation-tinypapers.json", "Tiny Papers @ ICLR 2024 Archive", None),
    ("iclr-2024/notes-presentation-tinypapers.json", "Tiny Papers @ ICLR 2024 Present", None),
    ("iclr-2024/notes-presentation-tinypapers.json", "Tiny Papers @ ICLR 2024 Notable", None),
    ("iclr-2025/notes-presentation-conference.json", "ICLR 2025 Oral", "oral"),
    ("iclr-2025/notes-presentation-conference.json", "ICLR 2025 Spotlight", "spotlight"),
    ("iclr-2025/notes-presentation-conference.json", "ICLR 2025 Poster", "poster"),
    ("iclr-2025/notes-presentation-blogposts.json", "ICLR 2025 Blogpost Track", None),
    ("iclr-2026/notes-accepted.json", "ICLR 2026 Poster", "poster"),
    ("iclr-2026/notes-presentation-conference.json", "ICLR 2026 Oral", "oral"),
    ("iclr-2026/notes-presentation-conference.json", "ICLR 2026 Poster", "poster"),
    ("icml-2023/notes-presentation-conference.json", "ICML 2023 OralPoster", "oral"),
    ("icml-2023/notes-presentation-conference.json", "ICML 2023 Poster", "poster"),
    ("icml-2024/notes-presentation-conference.json", "ICML 2024 Oral", "oral"),
    ("icml-2024/notes-presentation-conference.json", "ICML 2024 Spotlight", "spotlight"),
    ("icml-2024/notes-presentation-conference.json", "ICML 2024 Poster", "poster"),
    ("icml-2025/notes-presentation-conference.json", "ICML 2025 oral", "oral"),
    ("icml-2025/notes-presentation-conference.json", "ICML 2025 spotlightposter", "spotlight"),
    ("icml-2025/notes-presentation-conference.json", "ICML 2025 poster", "poster"),
    ("icml-2025/notes-presentation-position-paper-track.json", "ICML 2025 Position Paper Track oral", "oral"),
    ("icml-2025/notes-presentation-position-paper-track.json", "ICML 2025 Position Paper Track spotlightposter",
     "spotlight"),
    ("icml-2025/notes-presentation-position-paper-track.json", "ICML 2025 Position Paper Track poster", "poster"),
    ("icml-2026/notes-presentation-conference.json", "ICML 2026 spotlight", "spotlight"),
    ("icml-2026/notes-presentation-conference.json", "ICML 2026 regular", None),  # decision-042
    ("icml-2026/notes-presentation-position-paper-track.json", "ICML 2026 Position Paper Track spotlight",
     "spotlight"),
    ("icml-2026/notes-presentation-position-paper-track.json", "ICML 2026 Position Paper Track regular", None),
    ("neurips-2023/notes-presentation-conference.json", "NeurIPS 2023 oral", "oral"),
    ("neurips-2023/notes-presentation-conference.json", "NeurIPS 2023 spotlight", "spotlight"),
    ("neurips-2023/notes-presentation-conference.json", "NeurIPS 2023 poster", "poster"),
    ("neurips-2023/notes-presentation-track-datasets-and-benchmarks.json",
     "NeurIPS 2023 Datasets and Benchmarks Oral", "oral"),
    ("neurips-2023/notes-presentation-track-datasets-and-benchmarks.json",
     "NeurIPS 2023 Datasets and Benchmarks Spotlight", "spotlight"),
    ("neurips-2023/notes-presentation-track-datasets-and-benchmarks.json",
     "NeurIPS 2023 Datasets and Benchmarks Poster", "poster"),
    ("neurips-2024/notes-presentation-conference.json", "NeurIPS 2024 oral", "oral"),
    ("neurips-2024/notes-presentation-conference.json", "NeurIPS 2024 spotlight", "spotlight"),
    ("neurips-2024/notes-presentation-conference.json", "NeurIPS 2024 poster", "poster"),
    ("neurips-2024/notes-presentation-datasets-and-benchmarks-track.json",
     "NeurIPS 2024 Track Datasets and Benchmarks Oral", "oral"),
    ("neurips-2024/notes-presentation-datasets-and-benchmarks-track.json",
     "NeurIPS 2024 Track Datasets and Benchmarks Spotlight", "spotlight"),
    ("neurips-2024/notes-presentation-datasets-and-benchmarks-track.json",
     "NeurIPS 2024 Track Datasets and Benchmarks Poster", "poster"),
    ("neurips-2024/notes-presentation-competition-track.json", "NeurIPS 2024 Competition Track", None),
    ("neurips-2025/notes-presentation-conference.json", "NeurIPS 2025 oral", "oral"),
    ("neurips-2025/notes-presentation-conference.json", "NeurIPS 2025 spotlight", "spotlight"),
    ("neurips-2025/notes-presentation-conference.json", "NeurIPS 2025 poster", "poster"),
    ("neurips-2025/notes-presentation-datasets-and-benchmarks-track.json",
     "NeurIPS 2025 Datasets and Benchmarks Track oral", "oral"),
    ("neurips-2025/notes-presentation-datasets-and-benchmarks-track.json",
     "NeurIPS 2025 Datasets and Benchmarks Track spotlight", "spotlight"),
    ("neurips-2025/notes-presentation-datasets-and-benchmarks-track.json",
     "NeurIPS 2025 Datasets and Benchmarks Track poster", "poster"),
    ("neurips-2025/notes-presentation-position-paper-track.json", "NeurIPS 2025 Position Paper Track Oral", "oral"),
    ("neurips-2025/notes-presentation-position-paper-track.json", "NeurIPS 2025 Position Paper Track", None),
]  # fmt: skip


def note_with_venue(fixture: str, venue_string: str) -> dict[str, Any]:
    [note] = [
        n
        for n in recorded(fixture)["response"]["json"]["notes"]
        if n["content"]["venue"]["value"] == venue_string
    ]
    return copy.deepcopy(note)  # type: ignore[no-any-return]


def venue_year(fixture: str) -> tuple[str, int]:
    slug, year = fixture.split("/")[0].rsplit("-", 1)
    return {"iclr": "ICLR", "icml": "ICML", "neurips": "NeurIPS"}[slug], int(year)


@pytest.mark.parametrize(("fixture", "venue_string", "presentation"), PRESENTATIONS)
def test_each_verified_venue_string_gives_its_presentation(
    fixture: str, venue_string: str, presentation: str | None
) -> None:
    venue, year = venue_year(fixture)
    note, unmapped = note_with_venue(fixture, venue_string), set[str]()
    record = orv.note_record(
        note, venue=venue, year=year, page_url=PAGE_URL, fetched_at=FETCHED, unmapped=unmapped
    )
    assert isinstance(record, PaperRecord) and record.status == "accepted" and not unmapped
    assert record.presentation == presentation
    claims = [c for c in record.provenance if c.field == "presentation"]
    expected = [("presentation", presentation, f"content.venue={venue_string}")] if presentation else []
    assert [(c.field, c.value, c.evidence) for c in claims] == expected


def test_the_table_holds_exactly_the_fixture_backed_strings() -> None:
    table = {(v, y, s, p) for (v, y), rows in V2_PRESENTATION.items() for s, (_, p) in rows.items()}
    assert table == {(*venue_year(f), s, p) for f, s, p in PRESENTATIONS}


def unmapped_after(note: dict[str, Any], venue: str, year: int) -> tuple[PaperRecord | str, set[str]]:
    unmapped = set[str]()
    record = orv.note_record(
        note, venue=venue, year=year, page_url=PAGE_URL, fetched_at=FETCHED, unmapped=unmapped
    )
    return record, unmapped


def test_an_unrecognised_string_is_null_counted_and_logged_at_debug(caplog: pytest.LogCaptureFixture) -> None:
    note = recorded_note("icml-2026/notes-accepted.json")
    note["content"]["venue"]["value"] = "ICML 2026 keynote"  # a string nobody has seen
    with caplog.at_level(logging.DEBUG):
        record, unmapped = unmapped_after(note, "ICML", 2026)
    assert isinstance(record, PaperRecord) and (record.status, record.presentation) == ("accepted", None)
    assert unmapped == {note["id"]} and "presentation" not in {c.field for c in record.provenance}
    [line] = [r for r in caplog.records if r.getMessage() == "openreview_presentation_unmapped"]
    assert line.levelno == logging.DEBUG and line.__dict__["forum"] == note["id"]
    assert "venue_string" not in line.__dict__  # the string can be free text: never logged


# decision-042: ICML 2026's other tier names no presentation. Its two strings are known (null, never counted;
# TASK-178: 5,805 main and 175 position notes in the crawl cache), so the count names only unseen strings.
@pytest.mark.parametrize(
    ("fixture", "venue_string", "track"),
    [
        ("icml-2026/notes-presentation-conference.json", "ICML 2026 regular", "main"),
        ("icml-2026/notes-presentation-position-paper-track.json", "ICML 2026 Position Paper Track regular",
         "position"),
    ],
)  # fmt: skip
def test_icml_2026_regular_is_known_and_states_no_presentation(
    fixture: str, venue_string: str, track: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        record, unmapped = unmapped_after(note_with_venue(fixture, venue_string), "ICML", 2026)
    assert isinstance(record, PaperRecord) and (record.track, record.status) == (track, "accepted")
    assert record.presentation is None and not unmapped
    assert "presentation" not in {c.field for c in record.provenance}
    assert not lines(caplog, "openreview_presentation_unmapped")


@pytest.mark.parametrize(
    "venue_string",
    [
        "ICML 2026 Regular",  # exact match only: another case is unseen
        "ICML 2026 regular ",
        "ICML 2026 Position Paper Track regular",  # known, but under the position track, not main
        "ICML 2026 oral",
    ],
)
def test_an_unseen_icml_2026_string_is_still_unmapped(venue_string: str) -> None:
    note = note_with_venue("icml-2026/notes-presentation-conference.json", "ICML 2026 regular")
    note["content"]["venue"]["value"] = venue_string
    record, unmapped = unmapped_after(note, "ICML", 2026)
    assert isinstance(record, PaperRecord) and record.track == "main"
    assert record.presentation is None and unmapped == {note["id"]}


@pytest.mark.parametrize(
    "edit",
    [
        {"venue": {"value": "ICLR 2024 Oral"}},  # another year's case: exact match only
        {"venue": {"value": "ICLR 2025 oral"}},  # another venue-year's string
        {"venue": {"value": ["ICLR 2024 oral"]}},  # not a string
        {"venue": None},  # no content.venue
    ],
)
def test_a_string_off_the_venue_years_table_is_unmapped(edit: dict[str, Any]) -> None:
    note = recorded_note("iclr-2024/notes-accepted.json")
    note["content"].update(edit)
    note["content"] = {k: v for k, v in note["content"].items() if v is not None}
    record, unmapped = unmapped_after(note, "ICLR", 2024)
    assert isinstance(record, PaperRecord) and record.presentation is None and unmapped == {note["id"]}


def test_a_string_listed_under_another_track_is_unmapped() -> None:
    note = note_with_venue("neurips-2024/notes-presentation-datasets-and-benchmarks-track.json",
                           "NeurIPS 2024 Track Datasets and Benchmarks Oral")  # fmt: skip
    note["content"]["venueid"]["value"] = "NeurIPS.cc/2024/Conference"  # the venueid says main
    record, unmapped = unmapped_after(note, "NeurIPS", 2024)
    assert isinstance(record, PaperRecord) and record.track == "main"
    assert record.presentation is None and unmapped == {note["id"]}


def test_an_icml_2026_main_spotlight_on_a_position_venueid_is_unmapped() -> None:
    note = note_with_venue("icml-2026/notes-presentation-conference.json", "ICML 2026 spotlight")
    note["content"]["venueid"]["value"] = "ICML.cc/2026/Position_Paper_Track"  # the venueid says position
    record, unmapped = unmapped_after(note, "ICML", 2026)
    assert isinstance(record, PaperRecord) and record.track == "position"
    assert record.presentation is None and unmapped == {note["id"]}


@pytest.mark.parametrize(
    ("fixture", "venue", "year"),
    [
        ("iclr-2024/notes-rejected.json", "ICLR", 2024),  # `Submitted to ICLR 2024`
        ("iclr-2024/notes-withdrawn.json", "ICLR", 2024),
        ("neurips-2025/notes-creative-ai.json", "NeurIPS", 2025),  # status unknown
        ("neurips-2025/notes-workshop-city.json", "NeurIPS", 2025),  # accepted workshop: not the conference's
        ("icml-2026/notes-rejected.json", "ICML", 2026),  # `Submitted to ICML 2026`, an opt-in rejection
        ("icml-2026/notes-workshop-submission.json", "ICML", 2026),  # an undecided workshop submission
    ],
)
def test_only_accepted_non_workshop_notes_are_looked_up(fixture: str, venue: str, year: int) -> None:
    record, unmapped = unmapped_after(recorded_note(fixture), venue, year)
    assert isinstance(record, PaperRecord) and record.presentation is None and not unmapped


def test_a_rejected_note_never_takes_a_presentation_from_its_string() -> None:
    note = recorded_note("iclr-2024/notes-rejected.json")
    note["content"]["venue"]["value"] = "ICLR 2024 oral"  # the venueid decides status; venue can't promote
    record, unmapped = unmapped_after(note, "ICLR", 2024)
    assert isinstance(record, PaperRecord) and (record.status, record.presentation) == ("rejected", None)
    assert not unmapped


# --- the crawl ----------------------------------------------------------------------------------------------------


def world(accepted: int = 3) -> FakeOpenReview:
    """ICLR 2024: the Conference venue (every status), Tiny Papers, one workshop, a proposal venue, a
    workshop container, and a group that isn't a v2 venue."""
    acc = recorded_note("iclr-2024/notes-accepted.json")
    ws = json.loads(
        json.dumps(recorded_note("iclr-2025/notes-workshop-rejected.json")).replace("2025", "2024")
    )
    return FakeOpenReview(
        children={
            "ICLR.cc/2024": [CONF, "ICLR.cc/2024/TinyPapers", "ICLR.cc/2024/Workshop", "ICLR.cc/2024/Workshop_Proposals",
                             "ICLR.cc/2024/Program_Chairs"],
            "ICLR.cc/2024/Workshop": ["ICLR.cc/2024/Workshop/ICBINB"],
        },
        groups={
            CONF: group_doc(CONF),
            "ICLR.cc/2024/TinyPapers": group_doc("ICLR.cc/2024/TinyPapers"),
            "ICLR.cc/2024/Workshop/ICBINB": group_doc("ICLR.cc/2024/Workshop/ICBINB"),
            "ICLR.cc/2024/Program_Chairs": group_doc("ICLR.cc/2024/Program_Chairs", domain=CONF),
        },
        notes={
            CONF: [clone(acc, f"Accepted{i:04d}", i) for i in range(accepted)],
            f"{CONF}/Rejected_Submission": [recorded_note("iclr-2024/notes-rejected.json")],
            f"{CONF}/Withdrawn_Submission": [recorded_note("iclr-2024/notes-withdrawn.json")],
            f"{CONF}/Desk_Rejected_Submission": [recorded_note("iclr-2024/notes-desk-rejected.json")],
            "ICLR.cc/2024/TinyPapers": [recorded_note("iclr-2024/notes-tinypapers.json")],
            "ICLR.cc/2024/Workshop/ICBINB/Rejected_Submission": [ws],
        },
    )  # fmt: skip


def client(
    cache: Path, server: FakeOpenReview | Callable[[Request], Response], **kw: Any
) -> OpenReviewClient:
    return OpenReviewClient(orv.http_dir(cache), credentials=kw.pop("credentials", Credentials(USERNAME, PASSWORD)),
                            transport=server, clock=FakeClock(), jitter=lambda: 0.0, **kw)  # fmt: skip


def venueids_listed(server: FakeOpenReview) -> set[str]:
    return {parse_qs(urlsplit(u).query)["content.venueid"][0] for u in server.gets() if "/notes?" in u}


def test_a_crawl_finds_every_venue_group_and_lists_every_status_venueid(tmp_path: Path) -> None:
    server = world()
    result = orv.crawl(client(tmp_path, server), "ICLR", 2024)
    report = result.report
    assert report.groups == [CONF, "ICLR.cc/2024/TinyPapers", "ICLR.cc/2024/Workshop/ICBINB"]
    assert report.skipped_groups == {"ICLR.cc/2024/Workshop_Proposals": "proposal",
                                     "ICLR.cc/2024/Program_Chairs": "not_a_v2_venue"}  # fmt: skip
    statuses = (
        "",
        "/Submission",
        "/Rejected_Submission",
        "/Withdrawn_Submission",
        "/Desk_Rejected_Submission",
    )
    # decision-012: every status venueid is listed explicitly
    assert {f"{CONF}{s}" for s in statuses} <= venueids_listed(server)
    assert report.track_status == {"main": {"accepted": 3, "rejected": 1, "withdrawn": 1, "desk_rejected": 1},
                                   "tiny_papers": {"accepted": 1}, "workshop": {"rejected": 1}}  # fmt: skip
    assert report.imported == len(result.records) == 8 and report.notes_read == 8
    assert report.public[CONF] == {"public_submissions": True, "public_withdrawn_submissions": True,
                                   "public_desk_rejected_submissions": True}  # fmt: skip
    assert [r.id for r in result.records] == sorted(r.id for r in result.records)
    assert report.to_manifest()["crawl_window"]["from"] <= report.to_manifest()["crawl_window"]["to"]


def test_per_note_anomalies_are_debug_and_the_crawl_has_one_attention_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    server = world()
    for note in server.notes[CONF]:
        del note["content"]["venueid"]  # three accepted notes without their own venueid: unknown track
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        orv.crawl(client(tmp_path, server), "ICLR", 2024)
    unknown = [r for r in caplog.records if r.getMessage() == "openreview_unknown_track"]
    assert len(unknown) == 3 and {r.levelno for r in unknown} == {logging.DEBUG}
    [attention] = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert attention.getMessage() == "openreview_crawl_attention"
    assert {k: attention.__dict__[k] for k in ("api", "venue", "year", "unknown_track")} == {
        "api": "v2", "venue": "ICLR", "year": 2024, "unknown_track": 3,
    }  # fmt: skip


def test_unmapped_presentations_are_counted_per_venue_year_in_one_attention_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    server = world(accepted=4)
    for note in server.notes[CONF][:3]:
        note["content"]["venue"]["value"] = "ICLR 2024 keynote"  # three notes the table doesn't know
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        result = orv.crawl(client(tmp_path, server), "ICLR", 2024)
    assert [r.presentation for r in result.records if r.track == "main" and r.status == "accepted"].count(
        None
    ) == 3
    assert {r.presentation for r in result.records if r.track == "tiny_papers"} == {
        None
    }  # a known `none` string
    assert result.report.presentation_unmapped == 3 == result.report.to_manifest()["presentation_unmapped"]
    assert len(lines(caplog, "openreview_presentation_unmapped")) == 3  # per record: DEBUG only
    [attention] = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert attention.getMessage() == "openreview_crawl_attention"
    assert (attention.__dict__["presentation_unmapped"], attention.__dict__["unknown_track"]) == (3, 0)
    [finished] = lines(caplog, "openreview_crawl_finished")
    assert finished.__dict__["presentation_unmapped"] == 3


def test_titles_that_lost_a_control_character_are_counted_in_the_report_and_the_finished_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """decision-036: each title says so in its evidence and a DEBUG line; the crawl counts the titles (never an
    attention WARNING: the papers are kept). A crawl with none keeps its manifest shape."""
    server = world(accepted=4)
    server.notes[CONF][0]["content"]["title"]["value"] = "A SPEC\x02TRUM\x02"
    server.notes[CONF][1]["content"]["title"]["value"] = "Trust\x00AI"
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        result = orv.crawl(client(tmp_path, server), "ICLR", 2024)
    assert (
        result.report.title_control_characters == 2 == result.report.to_manifest()["title_control_characters"]
    )
    [finished] = lines(caplog, "openreview_crawl_finished")
    assert finished.__dict__["title_control_characters"] == 2
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    plain = orv.crawl(client(tmp_path / "plain", world()), "ICLR", 2024).report
    assert plain.title_control_characters == 0 and "title_control_characters" not in plain.to_manifest()


def test_a_crawl_whose_strings_are_all_mapped_has_no_attention_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        result = orv.crawl(client(tmp_path, world()), "ICLR", 2024)
    assert result.report.presentation_unmapped == 0
    assert {r.presentation for r in result.records if r.status == "accepted" and r.track == "main"} == {
        "poster"
    }
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def lines(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == event]


def test_the_heartbeat_is_due_at_most_every_30_seconds_of_monotonic_time() -> None:
    times = iter([100.0, 110.0, 129.9, 130.0, 145.0, 159.9, 160.1, 500.0])
    beat = Heartbeat(lambda: next(times))  # read once at the start (100.0)
    assert [beat.due() for _ in range(7)] == [False, False, True, False, False, True, True]
    assert PROGRESS_SECONDS == 30.0


def test_a_crawl_logs_a_start_line_and_bounded_progress_heartbeats(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    server = world()
    live = OpenReviewClient(orv.http_dir(tmp_path), credentials=Credentials(USERNAME, PASSWORD), transport=server,
                            clock=TickingClock(31.0), jitter=lambda: 0.0)  # fmt: skip
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.sources"):
        orv.crawl(live, "ICLR", 2024)
    [started] = lines(caplog, "openreview_crawl_started")
    assert {k: started.__dict__[k] for k in ("api", "venue", "year", "offline", "page_size")} == {
        "api": "v2", "venue": "ICLR", "year": 2024, "offline": False, "page_size": orv.PAGE_SIZE,
    }  # fmt: skip
    # every read of this clock is 31 s on, so each note's tick is due: one line per note, counts so far
    beats = lines(caplog, "openreview_crawl_progress")
    assert [b.__dict__["notes_read"] for b in beats] == list(range(8))
    assert {(b.__dict__["api"], b.__dict__["venue"], b.__dict__["year"]) for b in beats} == {
        ("v2", "ICLR", 2024)
    }
    last = beats[-1].__dict__
    assert (last["imported"], last["skipped"]) == (7, 0) and 0 < last["requests"] <= live.requests
    assert last["cached"] == 0 and all(b.levelno == logging.INFO for b in [started, *beats])
    [finished] = lines(caplog, "openreview_crawl_finished")
    assert finished.__dict__["api"] == "v2"

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.sources"):  # a stopped clock: none due
        replayed = OpenReviewClient(orv.http_dir(tmp_path), credentials=None, offline=True, clock=FakeClock())
        orv.crawl(replayed, "ICLR", 2024)
    assert lines(caplog, "openreview_crawl_progress") == []
    assert lines(caplog, "openreview_crawl_started")[0].__dict__["offline"] is True


def test_purged_pre_projection_cache_entries_are_debug_and_counted_by_the_crawl(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A one-time migration can meet thousands of old entries: one DEBUG line each, counted in the crawl's
    finished line and its one attention WARNING (TASK-116 review)."""
    server = world()
    live = client(tmp_path, server)
    orv.crawl(live, "ICLR", 2024)
    old = [p for p in orv.http_dir(tmp_path).rglob("*.json")][:2]
    for path in old:  # back to the raw, pre-projection layout
        document = json.loads(path.read_text())
        del document["payload"]["public_projection"]
        path.write_text(json.dumps(document))
    caplog.clear()
    again = client(tmp_path, server)
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        orv.crawl(again, "ICLR", 2024)
    purged = [r for r in caplog.records if r.getMessage() == "openreview_cache_incompatible"]
    assert len(purged) == 2 and {r.levelno for r in purged} == {logging.DEBUG} and again.incompatible == 2
    [finished] = lines(caplog, "openreview_crawl_finished")
    assert finished.__dict__["cache_incompatible"] == 2
    [attention] = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert (
        attention.getMessage() == "openreview_crawl_attention"
        and attention.__dict__["cache_incompatible"] == 2
    )


def test_pagination_stops_on_a_short_page(tmp_path: Path) -> None:
    server = world(accepted=5)
    result = orv.crawl(client(tmp_path, server), "ICLR", 2024, page_size=2)
    offsets = [parse_qs(urlsplit(u).query)["offset"][0] for u in server.gets()
               if parse_qs(urlsplit(u).query).get("content.venueid") == [CONF]]  # fmt: skip
    assert offsets == ["0", "2", "4"] and result.report.venueids[CONF] == 5
    assert all(parse_qs(urlsplit(u).query)["limit"] == ["2"] for u in server.gets() if "/notes?" in u)


def test_a_full_last_page_is_followed_by_an_empty_one(tmp_path: Path) -> None:
    server = world(accepted=4)
    orv.crawl(client(tmp_path, server), "ICLR", 2024, page_size=2)
    offsets = [parse_qs(urlsplit(u).query)["offset"][0] for u in server.gets()
               if parse_qs(urlsplit(u).query).get("content.venueid") == [CONF]]  # fmt: skip
    assert offsets == ["0", "2", "4"]


def test_a_listing_whose_count_disagrees_is_refused(tmp_path: Path) -> None:
    server = world()
    server.count_bias = 1  # the venue gained a paper between cached pages
    with pytest.raises(orv.CrawlError, match="--refresh"):
        orv.crawl(client(tmp_path, server), "ICLR", 2024)


def test_a_multi_page_listing_whose_count_changes_between_pages_is_refused(tmp_path: Path) -> None:
    server = world(accepted=3)

    def grown_first_page(request: Request) -> Response | None:
        q = parse_qs(urlsplit(request.url).query)
        if q.get("content.venueid") != [CONF] or q.get("offset") != ["0"]:
            return None
        # 4 on page 1, 3 on page 2: {3, 4} pops 3, which the 3 rows match, so only the count-change guard refuses
        # (a first-page count below the rows would be caught by the row check instead, testing nothing here)
        return json_response({"notes": server.notes[CONF][:2], "count": 4})  # page 2 says 3, as the rows do

    server.override = grown_first_page
    with pytest.raises(orv.CrawlError, match=r"changed between its cached pages.*--refresh"):
        orv.crawl(client(tmp_path, server), "ICLR", 2024, page_size=2)


@pytest.mark.parametrize("conflicting", [False, True])
def test_a_note_in_two_listings_is_a_counted_duplicate_only_when_its_record_is_identical(
    tmp_path: Path, conflicting: bool, caplog: pytest.LogCaptureFixture
) -> None:
    server = world()
    again = clone(server.notes[CONF][0], server.notes[CONF][0]["id"], server.notes[CONF][0]["number"])
    if conflicting:
        again["content"]["title"]["value"] = "Changed Title"
    server.notes[f"{CONF}/Rejected_Submission"].append(again)  # its own venueid still says accepted
    if conflicting:
        with pytest.raises(orv.CrawlError, match=r"conflicting data in two status listings.*--refresh"):
            orv.crawl(client(tmp_path, server), "ICLR", 2024)
        return
    with caplog.at_level(logging.WARNING, logger="openproceedings.ingest.sources"):
        result = orv.crawl(client(tmp_path, server), "ICLR", 2024)
    assert result.report.skipped["duplicate"] == 1 and result.report.notes_read == 9
    [attention] = [r for r in caplog.records if r.levelno >= logging.WARNING]  # counted, TASK-116 review
    assert attention.getMessage() == "openreview_crawl_attention" and attention.__dict__["duplicate"] == 1
    assert result.report.imported == len(result.records) == 8
    assert result.report.venueids[f"{CONF}/Rejected_Submission"] == 2
    [kept] = [r for r in result.records if r.native == again["id"]]
    assert {c.url for c in kept.provenance} == {  # the first listing's claims are kept
        next(u for u in server.gets() if parse_qs(urlsplit(u).query).get("content.venueid") == [CONF])
    }


@pytest.mark.parametrize("count", [None, "1", True, -1])
def test_a_listing_with_a_missing_or_invalid_count_is_refused(tmp_path: Path, count: object) -> None:
    server = world()

    def malformed(request: Request) -> Response | None:
        if parse_qs(urlsplit(request.url).query).get("content.venueid") != [CONF]:
            return None
        body: dict[str, object] = {"notes": server.notes[CONF]}
        if count is not None:
            body["count"] = count
        return json_response(body)

    server.override = malformed
    with pytest.raises(orv.CrawlError, match=r"missing or invalid count.*--refresh"):
        orv.crawl(client(tmp_path, server), "ICLR", 2024)


def test_a_note_in_two_status_listings_is_refused_as_a_stale_transition(tmp_path: Path) -> None:
    server = world()
    stale = clone(recorded_note("iclr-2024/notes-accepted.json"), "StatusChanged1", 42)
    current = clone(stale, "StatusChanged1", 42)
    current["content"]["venueid"]["value"] = f"{CONF}/Withdrawn_Submission"
    server.notes[CONF].append(stale)
    server.notes[f"{CONF}/Withdrawn_Submission"].append(current)
    with pytest.raises(orv.CrawlError, match=r"two status listings.*--refresh"):
        orv.crawl(client(tmp_path, server), "ICLR", 2024)


def test_an_ignored_offset_is_refused_not_looped(tmp_path: Path) -> None:
    server = world(accepted=5)
    server.ignore_offset = True
    with pytest.raises(orv.CrawlError, match="ignored the offset"):
        orv.crawl(client(tmp_path, server), "ICLR", 2024, page_size=2)


def test_a_v1_year_or_unknown_venue_is_refused(tmp_path: Path) -> None:
    for venue, year, message in (
        ("ICLR", 2023, "API v1"),
        ("NeurIPS", 2022, "openreview_v1"),
        ("AAAI", 2024, "unknown"),
    ):
        with pytest.raises(ValueError, match=message):
            orv.crawl(client(tmp_path, world()), venue, year)


# --- resume, replay, dry run ---------------------------------------------------------------------------------


def test_an_interrupted_crawl_resumes_without_refetching(tmp_path: Path) -> None:
    healthy = world(accepted=5)
    failing_url = f"content.venueid={CONF}&limit=2&offset=4"

    def outage(request: Request) -> Response | None:
        return json_response({"name": "ServiceUnavailable"}, 503) if failing_url in request.url else None

    broken = world(accepted=5)
    broken.override = outage
    with pytest.raises(OpenReviewRetriesExhausted):
        orv.ingest(client(tmp_path, broken, max_attempts=2), tmp_path, "ICLR", [2024], page_size=2)
    assert not orv.crawl_file(tmp_path, "ICLR", 2024).exists()  # unfinished: not a source yet
    fetched_before = {u for u in broken.gets() if failing_url not in u}
    [report] = orv.ingest(client(tmp_path, healthy), tmp_path, "ICLR", [2024], page_size=2)
    assert report.complete and orv.crawl_file(tmp_path, "ICLR", 2024).exists()
    assert not fetched_before & set(healthy.gets())  # every cached response was reused
    assert any(failing_url in u for u in healthy.gets())


def test_a_finished_crawl_replays_offline_with_no_credentials_and_no_request(tmp_path: Path) -> None:
    [report] = orv.ingest(client(tmp_path, world()), tmp_path, "ICLR", [2024])
    silent = FakeOpenReview()
    again = orv.crawl(client(tmp_path, silent, credentials=None, offline=True), "ICLR", 2024)
    assert silent.calls == [] and again.report.to_manifest() == report.to_manifest()
    [replayed] = orv.replay(tmp_path)
    assert replayed.records == again.records


def test_offline_refuses_an_uncached_crawl(tmp_path: Path) -> None:
    with pytest.raises(OpenReviewCacheMiss):
        orv.ingest(client(tmp_path, FakeOpenReview(), offline=True), tmp_path, "ICLR", [2024])


def test_a_dry_run_lists_what_it_would_fetch_and_writes_nothing(tmp_path: Path) -> None:
    orv.crawl(client(tmp_path, world()), "ICLR", 2024)  # warm everything …
    for p in orv.http_dir(tmp_path).rglob("*.json"):  # … then forget the rejected listings
        if "Rejected_Submission" in json.loads(p.read_text())["key"] and "Desk" not in p.read_text()[:400]:
            p.unlink()
    silent = FakeOpenReview()
    [report] = orv.ingest(client(tmp_path, silent, credentials=None, offline=True), tmp_path, "ICLR", [2024],
                          dry_run=True)  # fmt: skip
    assert silent.calls == [] and not report.complete and not orv.crawl_file(tmp_path, "ICLR", 2024).exists()
    assert report.to_manifest()["would_fetch"] == [
        "https://api2.openreview.net/notes?content.venueid=ICLR.cc/2024/Conference/Rejected_Submission"
        "&limit=1000&offset=0&sort=number%3Aasc",
        "https://api2.openreview.net/notes?content.venueid=ICLR.cc/2024/TinyPapers/Rejected_Submission"
        "&limit=1000&offset=0&sort=number%3Aasc",
        "https://api2.openreview.net/notes?content.venueid=ICLR.cc/2024/Workshop/ICBINB/Rejected_Submission"
        "&limit=1000&offset=0&sort=number%3Aasc",
    ]
    assert report.track_status["main"] == {"accepted": 3, "withdrawn": 1, "desk_rejected": 1}


def test_a_dry_run_needs_an_offline_client(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="offline"):
        orv.crawl(client(tmp_path, world()), "ICLR", 2024, dry_run=True)


# --- the snapshot build and the CLI ------------------------------------------------------------------------


def test_the_snapshot_build_replays_finished_crawls(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    orv.ingest(client(cache, world()), cache, "ICLR", [2024])
    result = snap.build(cache, tmp_path / "snapshots", FETCHED)
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_count"] == 8 and manifest["counts"]["ICLR"]["2024"]["main"]["accepted"] == 3
    assert set(manifest["sources"]) == {"openreview_v2"}
    entry = manifest["sources"]["openreview_v2"]
    assert set(entry["crawl_window"]) == {"from", "to"} and entry["crawls"][0]["venue"] == "ICLR"
    records = snap.load_records(result.path)
    rejected = recorded_note("iclr-2024/notes-rejected.json")["id"]
    assert records[f"op:iclr:2024:{rejected}"].status == "rejected" and "op:iclr:2024:Accepted0000" in records


def test_an_empty_cache_names_both_ingest_commands(tmp_path: Path) -> None:
    with pytest.raises(snap.SnapshotError, match="op ingest openreview"):
        snap.build(tmp_path / "cache", tmp_path / "snapshots", FETCHED)


def test_cli_offline_replays_and_dry_run_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cache = tmp_path / "cache"
    orv.ingest(client(cache, world()), cache, "ICLR", [2024])
    capsys.readouterr()
    argv = ["--data-dir", str(tmp_path), "ingest", "openreview", "--venue", "ICLR", "--years", "2024"]
    assert cli.main([*argv, "--offline"]) == 0
    [report] = json.loads(capsys.readouterr().out)
    assert (report["imported"], report["complete"]) == (8, True)
    assert cli.main(["--data-dir", str(tmp_path / "empty"), "ingest", "openreview", "--venue", "NeurIPS",
                     "--year", "2023", "--dry-run"]) == 0  # fmt: skip
    [dry] = json.loads(capsys.readouterr().out)
    assert dry["complete"] is False and dry["would_fetch"] == [
        "https://api2.openreview.net/groups?limit=1000&offset=0&parent=NeurIPS.cc/2023"
    ]


def test_cli_refusals(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = ["--data-dir", str(tmp_path), "ingest", "openreview", "--venue", "ICLR"]
    assert cli.main([*base, "--years", "2022-2024", "--offline"]) == 1  # 2022-2023 go to v1: uncached
    assert "not cached" in capsys.readouterr().err
    assert cli.main([*base, "--years", "2024", "--offline"]) == 1
    assert "not cached" in capsys.readouterr().err
    for bad in ("24", "2026-2024", "2024-x"):
        with pytest.raises(SystemExit) as e:
            cli.main([*base, "--years", bad])
        assert e.value.code == 2
    with pytest.raises(SystemExit):
        cli.main([*base, "--years", "2024", "--offline", "--dry-run"])
