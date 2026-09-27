"""The OpenReview v2 crawler (TASK-050) against the recorded, scrubbed fixtures: every recorded venueid form,
the authority rule, group and venueid enumeration, pagination, resume, offline replay, dry run, the
snapshot build and the CLI. No network (conftest); the transport is `FakeOpenReview`."""

from __future__ import annotations

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
from openproceedings.ingest.classify import classify_venueid
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.sources import openreview_v2 as orv
from openproceedings.ingest.sources.openreview_client import (
    Credentials,
    OpenReviewCacheMiss,
    OpenReviewClient,
    OpenReviewRetriesExhausted,
    Request,
    Response,
)

from tests.unit.ingest.openreview_fakes import (
    PASSWORD,
    USERNAME,
    FakeClock,
    FakeOpenReview,
    clone,
    group_doc,
    json_response,
    recorded_note,
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
    ("neurips-2023/notes-db-track-path.json", "NeurIPS", 2023, "datasets_benchmarks", "accepted"),
    ("neurips-2024/notes-db.json", "NeurIPS", 2024, "datasets_benchmarks", "accepted"),
    ("neurips-2024/notes-db-rejected.json", "NeurIPS", 2024, "datasets_benchmarks", "rejected"),
    ("neurips-2025/notes-workshop-city.json", "NeurIPS", 2025, "workshop", "accepted"),
    ("neurips-2025/notes-creative-ai.json", "NeurIPS", 2025, "other", "unknown"),
    ("icml-2024/notes-accepted.json", "ICML", 2024, "main", "accepted"),
    ("icml-2025/notes-position.json", "ICML", 2025, "position", "accepted"),
]
# classify.py's mapping of these is TASK-094's (position / competition); the crawler must just follow it
DELEGATED = [
    ("neurips-2025/notes-position.json", "NeurIPS", 2025),
    ("neurips-2024/notes-competition.json", "NeurIPS", 2024),
]


def build(note: dict[str, Any], venue: str = "ICLR", year: int = 2024) -> PaperRecord | str:
    return orv.note_record(note, venue=venue, year=year, page_url=PAGE_URL, fetched_at=FETCHED)


# --- notes → records -------------------------------------------------------------------------------------


@pytest.mark.parametrize(("fixture", "venue", "year", "track", "status"), FORMS)
def test_each_recorded_venueid_form(fixture: str, venue: str, year: int, track: str, status: str) -> None:
    note = recorded_note(fixture)
    record = build(note, venue, year)
    assert isinstance(record, PaperRecord)
    assert (record.venue, record.year, record.track, record.status) == (venue, year, track, status)
    assert record.id == f"op:{venue.lower()}:{year}:{note['id']}"
    assert record.venue_id_raw == note["content"]["venueid"]["value"]


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


def test_a_note_without_a_venueid_is_unknown_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    note = recorded_note("iclr-2024/notes-accepted.json")
    del note["content"]["venueid"]
    with caplog.at_level(logging.WARNING):
        record = build(note)
    assert isinstance(record, PaperRecord) and (record.track, record.status) == ("unknown", "unknown")
    [line] = [r for r in caplog.records if r.getMessage() == "openreview_unknown_track"]
    assert line.__dict__["forum"] == note["id"]


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
                           "venue_id_raw", "urls.forum", "urls.pdf"}  # fmt: skip
    assert record.urls.forum == f"https://openreview.net/forum?id={note['id']}"
    assert record.urls.pdf == f"https://openreview.net{note['content']['pdf']['value']}"
    assert record.abstract == "Synthetic abstract text 20." and record.title == "Synthetic title text 1."


def test_a_pdf_value_that_is_not_an_openreview_pdf_path_is_dropped() -> None:
    note = recorded_note("iclr-2024/notes-accepted.json")
    note["content"]["pdf"]["value"] = "https://evil.example/x.pdf"
    record = build(note)
    assert isinstance(record, PaperRecord) and record.urls.pdf is None


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
        "https://api2.openreview.net/groups?limit=1000&offset=0&parent=NeurIPS.cc/2023&select=id"
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
