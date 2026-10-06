"""The OpenReview API v1 adapters (TASK-051) against the recorded, scrubbed v1 fixtures: one adapter per
venue-year schema, each replayed from its recorded notes through `FakeOpenReviewV1`; the v1 authority rules
(a venueid never gives status, a withdrawn-invitation note with an accepted venue is a conflict); the
coverage gaps (ICLR 2014, 2015, 2016); resume, offline replay, dry run, the snapshot build and the CLI's
v1/v2 dispatch. No network (conftest)."""

from __future__ import annotations

import csv
import io
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
from openproceedings.ingest.dedup import dedup
from openproceedings.ingest.record import PaperRecord, Urls
from openproceedings.ingest.ris import import_ris
from openproceedings.ingest.sources import openreview_v1 as v1
from openproceedings.ingest.sources import openreview_v2 as orv2
from openproceedings.ingest.sources.http import CacheMiss as OpenReviewCacheMiss
from openproceedings.ingest.sources.http import Request, Response
from openproceedings.ingest.sources.http import RetriesExhausted as OpenReviewRetriesExhausted
from openproceedings.ingest.sources.openreview_client import Credentials, OpenReviewClient

from tests.unit.ingest.openreview_fakes import (
    PASSWORD,
    TOKEN,
    USERNAME,
    FakeClock,
    FakeOpenReviewV1,
    TickingClock,
    json_response,
    v1_clone,
    v1_note,
    v1_notes,
)

FETCHED = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
BLIND = "ICLR.cc/{y}/Conference/-/Blind_Submission"
WITHDRAWN = "ICLR.cc/{y}/Conference/-/Withdrawn_Submission"
DESK = "ICLR.cc/{y}/Conference/-/Desk_Rejected_Submission"


def client(
    cache: Path, server: FakeOpenReviewV1 | Callable[[Request], Response], **kw: Any
) -> OpenReviewClient:
    return v1.make_client(cache, credentials=kw.pop("credentials", Credentials(USERNAME, PASSWORD)),
                          transport=server, clock=FakeClock(), jitter=lambda: 0.0, **kw)  # fmt: skip


def run(server: FakeOpenReviewV1, tmp_path: Path, venue: str, year: int, **kw: Any) -> v1.Crawl:
    return v1.crawl(client(tmp_path, server), venue, year, **kw)


def by_forum(crawl: v1.Crawl) -> dict[str, PaperRecord]:
    return {r.native: r for r in crawl.records}


def outcome(r: PaperRecord) -> tuple[str, str, str | None]:
    return r.track, r.status, r.presentation


def claim(r: PaperRecord, field: str) -> Any:
    [c] = r.claims(field)  # type: ignore[arg-type]
    return c


def forum_gets(server: FakeOpenReviewV1) -> list[str]:
    return [parse_qs(urlsplit(u).query)["forum"][0] for u in server.gets() if "forum=" in u]


# --- the adapter table ----------------------------------------------------------------------------------------


def test_every_v1_venue_year_has_an_adapter_and_every_year_one_api() -> None:
    iclr = {y for (v, y) in v1.ADAPTERS if v == "ICLR"}
    assert iclr == set(range(2013, 2024)) and {y for (v, y) in v1.ADAPTERS if v == "NeurIPS"} == {2021, 2022}
    assert [v1.api_for("ICLR", y) for y in (2013, 2015, 2023, 2024)] == ["v1", "v1", "v1", "v2"]
    assert (v1.api_for("NeurIPS", 2021), v1.api_for("NeurIPS", 2023), v1.api_for("ICML", 2023)) == (
        "v1",
        "v2",
        "v2",
    )
    for venue, year in (("NeurIPS", 2020), ("ICML", 2022), ("ICLR", 2012)):
        with pytest.raises(ValueError, match="not on OpenReview"):
            v1.api_for(venue, year)
    with pytest.raises(ValueError, match="unknown venue"):
        v1.api_for("AAAI", 2020)
    with pytest.raises(ValueError, match="API v2"):
        v1.adapter("ICLR", 2024)


def test_listing_invitations_are_exact_prefix_safe_strings() -> None:
    """v1 invitation filters are prefix regexes: a listed invitation must hold no regex metacharacter other
    than the literal dots of `<Org>.cc`, or it would match other invitations."""
    for ad in v1.ADAPTERS.values():
        for listing in ad.listings:
            assert not set(listing.invitation) & set("*+?[](){}|^$\\"), listing.invitation
            assert listing.invitation.startswith(f"{ad.venue}.cc/{ad.year}/")


# --- one test per adapter, replaying its recorded fixtures --------------------------------------------------------


def test_iclr_2013_status_and_track_from_content_decision(tmp_path: Path) -> None:
    ws = v1_note("iclr-2013/notes-submission-decision-field.json")  # conferencePoster-iclr2013-workshop
    rejected = v1_clone(ws, "RejectedNote2013", 1, decision="reject")
    oral = v1_clone(ws, "OralNote2013x", 2, decision="conferenceOral-iclr2013-conference")
    odd = v1_clone(ws, "OddNote2013xx", 3, decision="conferenceSomething-new")
    server = FakeOpenReviewV1({"ICLR.cc/2013/conference/-/submission": [ws, rejected, oral, odd]})
    crawl = run(server, tmp_path, "ICLR", 2013)
    got = by_forum(crawl)
    assert outcome(got[ws["id"]]) == ("workshop", "accepted", "poster")
    assert claim(got[ws["id"]], "status").evidence == "content.decision=conferencePoster-iclr2013-workshop"
    assert outcome(got["RejectedNote2013"]) == (
        "main",
        "rejected",
        None,
    )  # `reject` names no track: its listing's
    assert (
        claim(got["RejectedNote2013"], "track").evidence == "invitation=ICLR.cc/2013/conference/-/submission"
    )
    assert outcome(got["OralNote2013x"]) == ("main", "accepted", "oral")
    assert outcome(got["OddNote2013xx"]) == ("main", "unknown", None)  # never guessed from its wording
    assert crawl.report.unmapped == {"content.decision": 1} and forum_gets(server) == []
    assert got[ws["id"]].urls.pdf is None  # an arXiv abstract page is not this note's PDF


def test_iclr_2014_has_no_decisions_status_unknown_and_a_coverage_gap(tmp_path: Path) -> None:
    conf = v1_note("iclr-2014/notes-submission-no-decision.json")
    ws = v1_clone(conf, "Workshop2014x", 3)
    server = FakeOpenReviewV1({"ICLR.cc/2014/conference/-/submission": [conf],
                               "ICLR.cc/2014/workshop/-/submission": [ws]})  # fmt: skip
    crawl = run(server, tmp_path, "ICLR", 2014)
    got = by_forum(crawl)
    assert outcome(got[conf["id"]]) == ("main", "unknown", None)
    assert outcome(got["Workshop2014x"]) == ("workshop", "unknown", None)
    manifest = crawl.report.to_manifest()
    assert manifest["track_status"] == {"main": {"unknown": 1}, "workshop": {"unknown": 1}}
    assert manifest["unknown_status"] == 2 and manifest["unmapped"] == {} and manifest["complete"]
    assert any("no decisions" in g for g in manifest["coverage_gaps"])


def test_iclr_2015_is_a_coverage_gap_not_an_error_and_makes_no_request(tmp_path: Path) -> None:
    server = FakeOpenReviewV1()
    [report] = v1.ingest(client(tmp_path, server), tmp_path, "ICLR", [2015])
    assert server.calls == [] and report.complete and report.imported == 0
    manifest = json.loads(v1.crawl_file(tmp_path, "ICLR", 2015).read_text())
    assert manifest["crawl_window"] is None and "no OpenReview group" in manifest["coverage_gaps"][0]
    assert v1.replay(tmp_path)[0].records == ()


def test_iclr_2016_workshop_only_status_unknown(tmp_path: Path) -> None:
    ws = v1_note("iclr-2016/notes-workshop.json")
    crawl = run(FakeOpenReviewV1({"ICLR.cc/2016/workshop/-/submission": [ws]}), tmp_path, "ICLR", 2016)
    [record] = crawl.records
    assert outcome(record) == ("workshop", "unknown", None) and record.id == f"op:iclr:2016:{ws['id']}"
    assert record.urls.pdf == f"https://openreview.net/pdf/{ws['id']}.pdf"  # 2016's PDF path is the forum id
    gaps = crawl.report.to_manifest()["coverage_gaps"]
    assert len(gaps) == 2 and "conference track is not on OpenReview" in gaps[0]


def test_iclr_2017_status_and_track_from_content_venue_never_the_venueid(tmp_path: Path) -> None:
    rejected = v1_note("iclr-2017/note-rejected-bare-venueid.json")  # venueid ICLR.cc/2017/conference
    invited = v1_note("iclr-2017/note-invite-to-workshop.json")
    server = FakeOpenReviewV1({"ICLR.cc/2017/conference/-/submission": [rejected, invited]})
    crawl = run(server, tmp_path, "ICLR", 2017)
    got = by_forum(crawl)
    assert outcome(got[rejected["id"]]) == ("main", "rejected", None)
    assert claim(got[rejected["id"]], "status").evidence == "content.venue=Submitted to ICLR 2017"
    assert outcome(got[invited["id"]]) == ("workshop", "unknown", None)
    assert got[rejected["id"]].venue_id_raw == "ICLR.cc/2017/conference"
    # early 2017 notes give `authors` as one string: split only as far as the email count allows (decision-019)
    assert got[rejected["id"]].authors == ("Synthetic Author 4",)
    assert (crawl.report.authors_split, crawl.report.authors_unsplit) == (1, 0)


WORKSHOP_COPY = "iclr-2017/note-workshop-submitted-to-iclr-live.json"


def test_a_main_track_outcome_on_a_workshop_listing_note_is_its_twins_not_its_own(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """TASK-152: ICLR 2017's workshop listing holds 18 copies of rejected conference papers (the recorded one's
    real `_bibtex` names its conference twin, `ryh_8f9lg`) that say `Submitted to ICLR 2017`, the twin's outcome. The
    note keeps its listing's track, and nothing states the workshop submission's status. The same string on the
    conference listing is still a main-track rejection, and a workshop invitation there still moves the track."""
    copy = v1_note(WORKSHOP_COPY)
    rejected = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    invited = v1_note("iclr-2017/note-invite-to-workshop.json")
    assert (copy["content"]["venue"], copy["content"]["venueid"]) == (
        "Submitted to ICLR 2017",
        "ICLR.cc/2017/conference",
    )
    server = FakeOpenReviewV1(
        {
            "ICLR.cc/2017/conference/-/submission": [rejected, invited],
            "ICLR.cc/2017/workshop/-/submission": [copy],
        }
    )
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        crawl = run(server, tmp_path, "ICLR", 2017)
    got = by_forum(crawl)
    [line] = [r for r in caplog.records if r.getMessage() == "openreview_v1_twin_outcome"]
    assert (line.levelno, line.__dict__["forum"]) == (logging.DEBUG, copy["id"])
    assert outcome(got[copy["id"]]) == ("workshop", "unknown", None)
    assert claim(got[copy["id"]], "track").evidence == "invitation=ICLR.cc/2017/workshop/-/submission"
    assert claim(got[copy["id"]], "status").evidence == (
        "content.venue=Submitted to ICLR 2017 (the main track's outcome, not this workshop submission's)"
    )
    assert outcome(got[rejected["id"]]) == ("main", "rejected", None)
    assert outcome(got[invited["id"]]) == ("workshop", "unknown", None)
    report = crawl.report.to_manifest()
    assert report["track_status"] == {"main": {"rejected": 1}, "workshop": {"unknown": 2}}
    assert (report["unmapped"], report["conflicts"], report["twin_outcome"]) == ({}, 0, 1)


@pytest.mark.parametrize(
    "venueid",
    # no venueid, ICLR 2017's lower-case `conference` (`other`), an in-scope path that doesn't parse (`unknown`)
    [None, "ICLR.cc/2017/conference", "ICLR.cc/2017/workshop/-/submission"],
)
def test_a_main_track_outcome_is_the_twins_wherever_the_venueid_names_no_track(
    tmp_path: Path, venueid: str | None
) -> None:
    note = v1_clone(v1_note(WORKSHOP_COPY), "WsNoTrack1", venueid=venueid)
    crawl = run(FakeOpenReviewV1({"ICLR.cc/2017/workshop/-/submission": [note]}), tmp_path, "ICLR", 2017)
    assert outcome(by_forum(crawl)["WsNoTrack1"]) == ("workshop", "unknown", None)
    report = crawl.report.to_manifest()
    assert (report["twin_outcome"], report["conflicts"]) == (1, 0)


def test_a_main_track_outcome_on_another_tracks_listing_is_the_twins_for_any_track(tmp_path: Path) -> None:
    """The rule is the listing's track, not ICLR 2017's workshop: a Tiny Papers note saying `Submitted to ICLR
    2023` (unseen live) would be a copy too, so it keeps `tiny_papers` with an unknown status."""
    note = v1_clone(v1_note(WORKSHOP_COPY), "TinyCopy01", venue="Submitted to ICLR 2023", venueid=None)
    crawl = run(
        FakeOpenReviewV1({"ICLR.cc/2023/TinyPapers/-/Blind_Submission": [note]}), tmp_path, "ICLR", 2023
    )
    assert outcome(by_forum(crawl)["TinyCopy01"]) == ("tiny_papers", "unknown", None)
    assert crawl.report.to_manifest()["twin_outcome"] == 1


@pytest.mark.parametrize(
    ("year", "invitation", "venue", "expected"),
    [
        (
            2023,
            "ICLR.cc/2023/BlogPosts/-/Blind_Submission",
            "Blogposts @ ICLR 2023",
            ("blogpost", "accepted", None),
        ),
        (
            2017,
            "ICLR.cc/2017/workshop/-/submission",
            "ICLR 2017 Invite to Workshop",
            ("workshop", "unknown", None),
        ),
    ],
)
def test_a_non_main_outcome_on_a_non_main_listing_is_the_notes_own(
    tmp_path: Path, year: int, invitation: str, venue: str, expected: tuple[str, str, None]
) -> None:
    """Only a `main` outcome is read as the twin's: a string naming the listing's own track keeps its status."""
    note = v1_clone(v1_note(WORKSHOP_COPY), "OwnTrack01", venue=venue, venueid=None)
    crawl = run(FakeOpenReviewV1({invitation: [note]}), tmp_path, "ICLR", year)
    assert outcome(by_forum(crawl)["OwnTrack01"]) == expected
    assert "twin_outcome" not in crawl.report.to_manifest()


def test_a_main_track_outcome_against_a_venueid_naming_the_listings_track_stays_a_conflict(
    tmp_path: Path,
) -> None:
    """The twin reading is only for a venueid that names no track (ICLR 2017's `conference`). A venueid naming a
    track is checked against the string's as before (rule 2): the track is `unknown`, with a conflict row."""
    note = v1_clone(v1_note(WORKSHOP_COPY), "WsVenueId1", venueid="ICLR.cc/2017/workshop")
    crawl = run(FakeOpenReviewV1({"ICLR.cc/2017/workshop/-/submission": [note]}), tmp_path, "ICLR", 2017)
    assert outcome(by_forum(crawl)["WsVenueId1"]) == ("unknown", "rejected", None)
    report = crawl.report.to_manifest()
    assert report["conflicts"] == 1 and "twin_outcome" not in report


def bibtex(forum: str) -> str:
    """A `_bibtex` as OpenReview v1 writes it (the recorded fixtures' are scrubbed): its url names a forum."""
    return f"@misc{{\nsynthetic2017,\ntitle={{Synthetic}},\nyear={{2017}},\nurl={{https://openreview.net/forum?id={forum}}}\n}}"


def twins(r: PaperRecord) -> tuple[tuple[str, ...], str | None]:
    [c] = r.claims("twin")
    assert c.source == "openreview_v1"
    return c.value, c.evidence


def iclr_2017(tmp_path: Path, conference: list[dict[str, Any]], workshop: list[dict[str, Any]]) -> v1.Crawl:
    listings = {
        "ICLR.cc/2017/conference/-/submission": conference,
        "ICLR.cc/2017/workshop/-/submission": workshop,
    }
    return run(FakeOpenReviewV1(listings), tmp_path, "ICLR", 2017)


def test_a_workshop_copy_and_its_conference_twin_are_linked_both_ways(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """TASK-159 (decision-029): a copy on ICLR 2017's workshop listing whose `_bibtex` names its conference twin,
    the one main-track submission with its title, stays its own record (different submissions, different
    outcomes); each record gets a `twin` claim naming the other's id. Track, status and content_hash don't change."""
    rejected = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    copy = v1_clone(v1_note(WORKSHOP_COPY), "WsCopy0001", title=rejected["content"]["title"],
                    _bibtex=bibtex(rejected["id"]))  # fmt: skip
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        crawl = iclr_2017(tmp_path, [rejected], [copy])
    got = by_forum(crawl)
    ws, conf = got["WsCopy0001"], got[rejected["id"]]
    assert twins(ws) == (
        (conf.id,),
        f"workshop copy of {rejected['id']}: its _bibtex names that forum, the main-track submission with this title",
    )
    assert twins(conf) == (
        (ws.id,),
        "workshop copy WsCopy0001: its _bibtex names this forum, the main-track submission with its title",
    )
    assert outcome(ws) == ("workshop", "unknown", None) and outcome(conf) == ("main", "rejected", None)
    assert [c.url for c in ws.claims("twin")] == [
        c.url for c in ws.claims("title")
    ]  # the copy's listing page
    report = crawl.report.to_manifest()
    assert report["twins_linked"] == 1 and "twins_ambiguous" not in report
    [line] = [r for r in caplog.records if r.getMessage() == "openreview_v1_twin_linked"]
    assert (line.levelno, line.__dict__["forum"], line.__dict__["twin"]) == (
        logging.DEBUG,
        "WsCopy0001",
        rejected["id"],
    )


def test_a_v1_title_with_a_control_character_is_imported_with_a_space(tmp_path: Path) -> None:
    """TASK-180: the v1 crawler reads a title through the v2 crawler's rule, so a note is no longer `invalid`
    over an invisible character."""
    note = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    note["content"]["title"] = "Deep\x02Learn\x02ing with Trust"
    crawl = iclr_2017(tmp_path, [note], [])
    record = by_forum(crawl)[note["id"]]
    assert record.title == "Deep Learn ing with Trust" and crawl.report.skipped["invalid"] == 0
    assert [c.evidence for c in record.claims("title")] == [
        "content.title (2 control characters replaced by a space)"
    ]
    assert (
        crawl.report.title_control_characters == 1 == crawl.report.to_manifest()["title_control_characters"]
    )


def test_a_v1_abstract_with_a_control_character_is_imported_with_a_space(tmp_path: Path) -> None:
    """decision-044 (TASK-188): the v1 crawler reads an abstract through the v2 crawler's rule."""
    note = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    note["content"]["abstract"] = "the LiDAR modal\x02ity"
    record = by_forum(iclr_2017(tmp_path, [note], []))[note["id"]]
    assert record.abstract == "the LiDAR modal ity"
    assert [c.evidence for c in record.claims("abstract")] == [
        "content.abstract (1 control character replaced by a space)"
    ]


def test_a_title_match_links_a_copy_whose_bibtex_names_another_forum(tmp_path: Path) -> None:
    """ICLR 2017's 35 `Invite to Workshop` notes all carry a `_bibtex` naming one unrelated conference forum
    (B1akgy9xx), so a `_bibtex` counts only when it names a submission with the copy's title; otherwise the one
    main-track submission with that title is the twin, by title alone."""
    rejected = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    other = v1_clone(rejected, "Unrelated01", title="An unrelated synthetic title")
    invited = v1_clone(v1_note(WORKSHOP_COPY), "WsInvite01", title=rejected["content"]["title"],
                       venue="ICLR 2017 Invite to Workshop", _bibtex=bibtex("Unrelated01"))  # fmt: skip
    got = by_forum(iclr_2017(tmp_path, [rejected, other], [invited]))
    assert twins(got["WsInvite01"]) == (
        (got[rejected["id"]].id,),
        f"workshop copy of {rejected['id']}: the only main-track submission with this title",
    )
    assert (
        twins(got[rejected["id"]])[1]
        == "workshop copy WsInvite01: the only main-track submission with its title"
    )
    assert got["Unrelated01"].claims("twin") == ()


def test_no_title_match_or_two_leaves_a_workshop_note_unlinked(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rejected = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    same = v1_clone(rejected, "SameTitle1", number=999, abstract="Another synthetic abstract.")  # a 2nd one
    alone = v1_clone(v1_note(WORKSHOP_COPY), "WsAlone001", title="A title no conference note has")
    ambiguous = v1_clone(v1_note(WORKSHOP_COPY), "WsTwoMatch", title=rejected["content"]["title"])
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        crawl = iclr_2017(tmp_path, [rejected, same], [alone, ambiguous])
    assert all(r.claims("twin") == () for r in crawl.records)
    report = crawl.report.to_manifest()
    assert "twins_linked" not in report and report["twins_ambiguous"] == 1  # auditable without the DEBUG line
    [line] = [r for r in caplog.records if r.getMessage() == "openreview_v1_twin_ambiguous"]
    assert (line.__dict__["forum"], line.__dict__["candidates"]) == ("WsTwoMatch", 2)


def test_a_title_of_punctuation_only_is_never_matched(tmp_path: Path) -> None:
    """Review round 1: dedup never matches an empty title key, and neither does the twin rule."""
    rejected = v1_clone(v1_note("iclr-2017/note-rejected-bare-venueid.json"), "Punct00001", title="???")
    copy = v1_clone(v1_note(WORKSHOP_COPY), "WsPunct001", title="\u2014!")
    crawl = iclr_2017(tmp_path, [rejected], [copy])
    assert len(crawl.records) == 2 and all(r.claims("twin") == () for r in crawl.records)


def test_a_twin_the_collapse_dropped_is_never_named(tmp_path: Path) -> None:
    """Rule 6 runs after rule 5: the copy's `_bibtex` names the higher-numbered of two identical conference notes,
    which the collapse drops, so the copy links to the survivor, the one record with its title."""
    rejected = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    dropped = v1_clone(rejected, "Dropped001", number=9_999)
    copy = v1_clone(
        v1_note(WORKSHOP_COPY), "WsCopy0001", title=rejected["content"]["title"], _bibtex=bibtex("Dropped001")
    )
    crawl = iclr_2017(tmp_path, [rejected, dropped], [copy])
    got = by_forum(crawl)
    assert "Dropped001" not in got and crawl.report.skipped["duplicate_submission"] == 1
    assert twins(got["WsCopy0001"]) == (
        (got[rejected["id"]].id,),
        f"workshop copy of {rejected['id']}: the only main-track submission with this title",
    )


def test_a_copy_the_collapse_dropped_is_never_named(tmp_path: Path) -> None:
    """Two identical workshop copies collapse to the lower-numbered one before linking: the twin names only it."""
    rejected = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    kept, dropped = (v1_clone(v1_note(WORKSHOP_COPY), nid, number=n, title=rejected["content"]["title"])
                     for nid, n in (("WsCopyKept", 100), ("WsCopyGone", 200)))  # fmt: skip
    crawl = iclr_2017(tmp_path, [rejected], [kept, dropped])
    got = by_forum(crawl)
    assert "WsCopyGone" not in got and crawl.report.skipped["duplicate_submission"] == 1
    assert twins(got[rejected["id"]])[0] == ("op:iclr:2017:WsCopyKept",)
    assert crawl.report.to_manifest()["twins_linked"] == 1


def test_a_bibtex_naming_one_of_two_title_matches_picks_it(tmp_path: Path) -> None:
    rejected = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    same = v1_clone(rejected, "SameTitle1", number=999, abstract="Another synthetic abstract.")
    copy = v1_clone(
        v1_note(WORKSHOP_COPY), "WsCopy0001", title=rejected["content"]["title"], _bibtex=bibtex("SameTitle1")
    )
    got = by_forum(iclr_2017(tmp_path, [rejected, same], [copy]))
    assert twins(got["WsCopy0001"])[0] == (got["SameTitle1"].id,)
    assert got[rejected["id"]].claims("twin") == ()


def test_a_conference_note_with_two_copies_names_both(tmp_path: Path) -> None:
    rejected = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    copies = [v1_clone(v1_note(WORKSHOP_COPY), f"WsCopy000{i}", number=100 + i, title=rejected["content"]["title"],
                       abstract=f"Synthetic abstract {i}.")
              for i in (1, 2)]  # fmt: skip
    got = by_forum(iclr_2017(tmp_path, [rejected], copies))
    value, evidence = twins(got[rejected["id"]])
    assert value == ("op:iclr:2017:WsCopy0001", "op:iclr:2017:WsCopy0002")
    assert evidence == (
        "workshop copy WsCopy0001: the only main-track submission with its title; "
        "workshop copy WsCopy0002: the only main-track submission with its title"
    )


def test_twin_claims_survive_dedup_a_ris_merge_and_a_takedown(tmp_path: Path) -> None:
    """The links are provenance: dedup never merges the pair (two forum ids), a RIS record of the twin merges into
    it by forum id with the claim kept, a takedown of the copy keeps the claims, and the snapshot renders."""
    rejected = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    copy = v1_clone(v1_note(WORKSHOP_COPY), "WsCopy0001", title=rejected["content"]["title"])
    crawl = iclr_2017(tmp_path / "crawl", [rejected], [copy])
    claims = {r.id: r.claims("twin") for r in crawl.records}
    alone = dedup(crawl.records)
    assert not alone.merges  # two forum ids: never merged (dedup-rules §Never merge)
    assert {r.id: r.claims("twin") for r in alone.records} == claims
    assert dedup(alone.records).records == alone.records
    ris = ris_record_of(tmp_path / "ris", 12, rejected["id"])  # the twin's RIS record, merged by forum id
    result = dedup([*crawl.records, ris])
    assert [(m.rule, m.key) for m in result.merges] == [("forum_id", rejected["id"])]
    assert {r.id: tuple(c for c in r.claims("twin")) for r in result.records} == claims
    withheld = snap.withhold(result, frozenset({"op:iclr:2017:WsCopy0001"}))
    assert {r.id: r.claims("twin") for r in withheld.result.records} == claims
    files = snap.render(withheld.result, [], datetime(2026, 10, 2, tzinfo=UTC), withheld=withheld.withheld)
    assert files["records.jsonl"].count(b'"field":"twin"') == 2


def test_a_snapshot_refuses_a_twin_it_doesnt_hold(tmp_path: Path) -> None:
    rejected = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    copy = v1_clone(v1_note(WORKSHOP_COPY), "WsCopy0001", title=rejected["content"]["title"])
    crawl = iclr_2017(tmp_path, [rejected], [copy])
    built = datetime(2026, 10, 2, tzinfo=UTC)
    assert snap.render(dedup(crawl.records), [], built)["records.jsonl"].count(b'"field":"twin"') == 2
    alone = [r for r in crawl.records if r.native == "WsCopy0001"]
    rejected_id = f"op:iclr:2017:{rejected['id']}"
    with pytest.raises(
        snap.SnapshotError, match=f"record op:iclr:2017:WsCopy0001's twin claim names {rejected_id}, "
    ):
        snap.render(dedup(alone), [], built)


def ris_record_of(tmp_path: Path, row: int, forum: str) -> PaperRecord:
    """The RIS v1 fixture's `row`, as scholarmend would resolve it for `forum`: the same claims, that forum id."""
    fixture = Path(__file__).parents[2] / "fixtures" / "ris" / "v1"
    entries = json.loads((fixture / "resolved.json").read_text(encoding="utf-8"))
    [fid] = [c for c in entries[row]["claims"] if c["field"] == "forum_id"]
    fid["value"], fid["evidence"] = forum, f"https://openreview.net/pdf?id={forum}"
    tmp_path.mkdir()
    (tmp_path / "mended.ris").write_bytes((fixture / "mended.ris").read_bytes())
    (tmp_path / "resolved.json").write_text(json.dumps(entries), encoding="utf-8")
    records, _ = import_ris(tmp_path / "mended.ris")
    [record] = [
        r for r in records if r.native == forum and r.title == " ".join(entries[row]["title"].split())
    ]
    return record  # the row itself: row 15 already holds the recorded copy's forum (TASK-157)


def test_a_workshop_copy_the_ris_importer_reads_as_main_is_workshop_once_merged_with_the_crawl(
    tmp_path: Path,
) -> None:
    """TASK-152 (the lead's decision, 2026-10-01): scholarmend gives the RIS importer a note's venueid and
    `content.venue`, never its listing, so a workshop copy's claims equal a main-track rejection's and the importer
    reads it as `main`/`rejected` (row 12, `Submitted to ICLR 2017`). In a snapshot it merges with the crawl's
    record by forum id, and the crawl's track and status win (decision-005), each with a conflicts row."""
    copy = v1_note(WORKSHOP_COPY)
    crawl = run(FakeOpenReviewV1({"ICLR.cc/2017/workshop/-/submission": [copy]}), tmp_path, "ICLR", 2017)
    ris = ris_record_of(tmp_path / "ris", 12, copy["id"])
    assert (ris.id, ris.track, ris.status) == (crawl.records[0].id, "main", "rejected")
    result = dedup([*crawl.records, ris])
    [merged] = result.records
    assert [(m.rule, m.key) for m in result.merges] == [("forum_id", copy["id"])]  # not a title merge
    assert dedup(result.records).records == result.records  # a second run changes nothing
    assert (merged.track, merged.status) == ("workshop", "unknown")
    # (the synthetic fixtures' titles differ too: a title row, not this task's)
    assert {
        (c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts if c.field != "title"
    } == {
        ("track", "workshop", "main", "precedence:openreview_v1"),
        ("status", "unknown", "rejected", "precedence:openreview_v1"),
    }


def test_the_crawler_and_the_ris_importer_read_a_workshop_copy_alike(tmp_path: Path) -> None:
    """TASK-157 AC #4: the recorded copy through the v1 crawler, and the claims scholarmend 0.1.5 builds from it
    (row 15 of the RIS v1 fixture: its venueid, `content.venue` and invitation) through the RIS importer, give the
    same track and status, without a merge to settle it (TASK-152's was at the snapshot level only)."""
    copy = v1_note(WORKSHOP_COPY)
    crawl = run(FakeOpenReviewV1({copy["invitation"]: [copy]}), tmp_path, "ICLR", 2017)
    ris = ris_record_of(tmp_path / "ris", 15, copy["id"])
    [crawled] = crawl.records
    assert [c.value for c in ris.claims("invitation")] == [copy["invitation"]]
    assert (ris.id, ris.track, ris.status) == (crawled.id, crawled.track, crawled.status) == (
        crawled.id, "workshop", "unknown"
    )  # fmt: skip


def test_iclr_2017_notes_with_a_null_nonreaders_are_public_and_imported(tmp_path: Path) -> None:
    """A recorded live 2017 workshop note whose `nonreaders` is null, as on 59 of that listing's 161 notes
    (2026-09-29). The public-data guard refused it and stopped the ICLR crawl (TASK-119)."""
    note = v1_note("iclr-2017/note-workshop-null-nonreaders-live.json")
    assert note["readers"] == ["everyone"] and note["nonreaders"] is None
    crawl = run(FakeOpenReviewV1({"ICLR.cc/2017/workshop/-/submission": [note]}), tmp_path, "ICLR", 2017)
    assert list(by_forum(crawl)) == [note["id"]]
    assert outcome(by_forum(crawl)[note["id"]]) == (
        "workshop",
        "unknown",
        None,
    )  # as the other 2017 workshop note


def test_iclr_2018_status_from_the_acceptance_decision_note(tmp_path: Path) -> None:
    forum = v1_notes("iclr-2018/forum-rejected.json")  # not ordered: the submission is last
    sub = v1_note("iclr-2018/forum-rejected.json")
    server = FakeOpenReviewV1({BLIND.format(y=2018): [sub]}, {sub["id"]: forum})
    crawl = run(server, tmp_path, "ICLR", 2018)
    [record] = crawl.records
    assert outcome(record) == ("main", "rejected", None) and forum_gets(server) == [sub["id"]]
    status = claim(record, "status")
    assert status.evidence == "decision note BJ2zBJ6Hf (decision=Reject)"
    assert status.url == f"https://api.openreview.net/notes?forum={sub['id']}&limit=1000&offset=0"
    assert claim(record, "track").evidence == f"invitation={BLIND.format(y=2018)}"
    assert crawl.report.forums == 1


def test_iclr_2018_accept_and_invite_to_workshop_decisions(tmp_path: Path) -> None:
    forum = v1_notes("iclr-2018/forum-rejected.json")
    sub = v1_note("iclr-2018/forum-rejected.json")
    notes, forums = [], {}
    for i, decision in enumerate(("Accept (Oral)", "Invite to Workshop Track"), start=1):
        nid = f"Decided2018n{i}"
        notes.append(v1_clone(sub, nid))
        forums[nid] = [dict(n, forum=nid, replyto=nid if n.get("replyto") == sub["id"] else n.get("replyto"),
                            content={**n["content"], "decision": decision} if "decision" in n["content"] else n["content"])
                       if n["id"] != sub["id"] else v1_clone(sub, nid) for n in forum]  # fmt: skip
    crawl = run(FakeOpenReviewV1({BLIND.format(y=2018): notes}, forums), tmp_path, "ICLR", 2018)
    got = by_forum(crawl)
    assert outcome(got["Decided2018n1"]) == ("main", "accepted", "oral")
    assert outcome(got["Decided2018n2"]) == ("workshop", "unknown", None)
    assert claim(got["Decided2018n2"], "track").evidence.startswith("decision note ")


def test_iclr_2019_status_from_the_meta_review_of_this_paper_only(tmp_path: Path) -> None:
    forum = v1_notes("iclr-2019/forum-rejected-meta-review.json")
    sub = v1_note("iclr-2019/forum-rejected-meta-review.json")  # number 1027, meta-review Paper1027
    other = v1_clone(
        sub, "OtherPaper19", 1028
    )  # its forum holds only a meta-review from Paper1027's invitation
    stray = [dict(n, forum="OtherPaper19", replyto="OtherPaper19") for n in forum if n["id"] != sub["id"]]
    server = FakeOpenReviewV1({BLIND.format(y=2019): [sub, other]},
                              {sub["id"]: forum, "OtherPaper19": [other, *stray]})  # fmt: skip
    crawl = run(server, tmp_path, "ICLR", 2019)
    got = by_forum(crawl)
    assert outcome(got[sub["id"]]) == ("main", "rejected", None)
    assert claim(got[sub["id"]], "status").evidence == "decision note BJxW71mgxE (recommendation=Reject)"
    assert outcome(got["OtherPaper19"]) == (
        "main",
        "unknown",
        None,
    )  # another paper's decision is never taken
    assert crawl.report.unmapped == {"decision_note": 1}


def test_iclr_2020_decision_notes_map_reject_and_accept_poster(tmp_path: Path) -> None:
    forum = v1_notes("iclr-2020/forum-rejected.json")
    sub = v1_note("iclr-2020/forum-rejected.json")
    accepted = v1_clone(sub, "Accepted2020x", 2000)
    accepted_forum = [v1_clone(sub, "Accepted2020x", 2000)] + [
        dict(n, forum="Accepted2020x", replyto="Accepted2020x", invitation="ICLR.cc/2020/Conference/Paper2000/-/Decision",
             content={**n["content"], "decision": "Accept (Poster)"})
        for n in forum if n["invitation"].endswith("/-/Decision")
    ]  # fmt: skip
    server = FakeOpenReviewV1(
        {BLIND.format(y=2020): [sub, accepted]}, {sub["id"]: forum, "Accepted2020x": accepted_forum}
    )
    crawl = run(server, tmp_path, "ICLR", 2020)
    got = by_forum(crawl)
    assert outcome(got[sub["id"]]) == ("main", "rejected", None)
    assert outcome(got["Accepted2020x"]) == ("main", "accepted", "poster")
    assert crawl.report.unmapped == {} and crawl.report.gaps == ()


def test_iclr_2020_recorded_accept_decision_is_accepted_poster(tmp_path: Path) -> None:
    forum = v1_notes("iclr-2020/forum-accepted.json")
    sub = v1_note("iclr-2020/forum-accepted.json")
    crawl = run(FakeOpenReviewV1({BLIND.format(y=2020): [sub]}, {sub["id"]: forum}), tmp_path, "ICLR", 2020)
    [record] = crawl.records
    assert outcome(record) == ("main", "accepted", "poster")
    assert claim(record, "status").evidence == "decision note EE4Ml5hZtI (decision=Accept (Poster))"
    assert crawl.report.unmapped == {} and crawl.report.gaps == ()


@pytest.mark.parametrize(
    ("fixture", "presentation"), [("forum-accepted-spotlight", "spotlight"), ("forum-accepted-talk", "oral")]
)
def test_iclr_2020_spotlight_and_talk_decisions_are_accepted(
    tmp_path: Path, fixture: str, presentation: str
) -> None:
    """Recorded ICLR 2020 forums (TASK-123): the decision table mapped only Accept (Poster), so the 108 Spotlight
    and 48 Talk papers (156, exactly the coverage shortfall) were status unknown. A talk is an oral."""
    forum = v1_notes(f"iclr-2020/{fixture}.json")
    sub = v1_note(f"iclr-2020/{fixture}.json")
    crawl = run(FakeOpenReviewV1({BLIND.format(y=2020): [sub]}, {sub["id"]: forum}), tmp_path, "ICLR", 2020)
    [record] = crawl.records
    assert outcome(record) == ("main", "accepted", presentation)
    assert crawl.report.unmapped == {}


def test_iclr_2021_venue_first_then_the_decision_note_and_the_withdrawn_conflict(tmp_path: Path) -> None:
    accepted = v1_note("iclr-2021/note-accepted.json")  # venue ICLR 2021 Poster
    forum = v1_notes("iclr-2021/forum-rejected-no-venueid.json")
    rejected = v1_note("iclr-2021/forum-rejected-no-venueid.json")  # no venue: the decision note decides
    withdrawn = v1_note("iclr-2021/note-withdrawn-with-accepted-venue.json")  # xGZG2kS5bFk
    server = FakeOpenReviewV1(
        {BLIND.format(y=2021): [accepted, rejected], WITHDRAWN.format(y=2021): [withdrawn]},
        {rejected["id"]: forum},
    )
    crawl = run(server, tmp_path, "ICLR", 2021)
    got = by_forum(crawl)
    assert outcome(got[accepted["id"]]) == ("main", "accepted", "poster")
    assert outcome(got[rejected["id"]]) == ("main", "rejected", None)
    assert forum_gets(server) == [rejected["id"]]  # a venue string that decides needs no forum
    # the withdrawn invitation and the accepted venue string disagree: unknown and a conflict, never accepted
    assert withdrawn["id"] == "xGZG2kS5bFk" and outcome(got[withdrawn["id"]]) == ("main", "unknown", None)
    [conflict] = crawl.report.conflicts
    assert (conflict.id, conflict.field, conflict.resolution) == (
        "op:iclr:2021:xGZG2kS5bFk",
        "status",
        v1.CONFLICT,
    )
    assert conflict.value_a.startswith("withdrawn (invitation=ICLR.cc/2021/Conference/-/Withdrawn_Submission")
    assert conflict.value_b == "accepted (content.venue=ICLR 2021 Poster)"
    assert (conflict.source_a, conflict.source_b) == ("openreview_v1", "openreview_v1")
    assert crawl.report.to_manifest()["conflicts"] == 1


def test_iclr_2021_recorded_accept_decision_is_the_fallback_when_venue_is_absent(tmp_path: Path) -> None:
    forum = v1_notes("iclr-2021/forum-accepted.json")
    recorded = v1_note("iclr-2021/forum-accepted.json")
    sub = v1_clone(recorded, recorded["id"], venue=None)
    server = FakeOpenReviewV1({BLIND.format(y=2021): [sub]}, {sub["id"]: forum})
    crawl = run(server, tmp_path, "ICLR", 2021)
    [record] = crawl.records
    assert outcome(record) == ("main", "accepted", "poster")
    assert claim(record, "status").evidence == "decision note MWujQIPYpqt (decision=Accept (Poster))"
    assert forum_gets(server) == [sub["id"]]


def test_iclr_2022_submitted_is_rejected_and_the_withdrawn_invitation_decides(tmp_path: Path) -> None:
    rejected = v1_note("iclr-2022/note-rejected-bare-venueid.json")  # venueid ICLR.cc/2022/Conference
    withdrawn = v1_note("iclr-2022/note-withdrawn-empty-venueid.json")  # venue = venueid = ""
    server = FakeOpenReviewV1({BLIND.format(y=2022): [rejected], WITHDRAWN.format(y=2022): [withdrawn]})
    crawl = run(server, tmp_path, "ICLR", 2022)
    got = by_forum(crawl)
    assert outcome(got[rejected["id"]]) == ("main", "rejected", None)
    assert outcome(got[withdrawn["id"]]) == ("main", "withdrawn", None)
    assert claim(got[withdrawn["id"]], "status").evidence == f"invitation={WITHDRAWN.format(y=2022)}"
    assert got[withdrawn["id"]].venue_id_raw is None and crawl.report.conflicts == []
    listed = {parse_qs(urlsplit(u).query)["invitation"][0] for u in server.gets()}
    assert listed == {BLIND.format(y=2022), WITHDRAWN.format(y=2022), DESK.format(y=2022)}  # decision-012


def test_iclr_2023_every_listing_and_tiny_papers(tmp_path: Path) -> None:
    accepted = v1_note("iclr-2023/notes-blind-count.json")  # ICLR 2023 poster
    rejected = v1_note("iclr-2023/note-rejected-bare-venueid.json")
    desk = v1_note("iclr-2023/note-desk-rejected.json")
    tiny = v1_note("iclr-2023/note-tinypapers.json")
    server = FakeOpenReviewV1({BLIND.format(y=2023): [accepted, rejected], DESK.format(y=2023): [desk],
                               "ICLR.cc/2023/TinyPapers/-/Blind_Submission": [tiny]})  # fmt: skip
    crawl = run(server, tmp_path, "ICLR", 2023)
    got = by_forum(crawl)
    assert outcome(got[accepted["id"]]) == ("main", "accepted", "poster")
    assert outcome(got[rejected["id"]]) == ("main", "rejected", None)
    assert outcome(got[desk["id"]]) == ("main", "desk_rejected", None)
    assert outcome(got[tiny["id"]]) == ("tiny_papers", "unknown", None)
    assert crawl.report.to_manifest()["track_status"] == {
        "main": {"accepted": 1, "rejected": 1, "desk_rejected": 1}, "tiny_papers": {"unknown": 1}}  # fmt: skip
    assert crawl.report.listings == {BLIND.format(y=2023): 2, WITHDRAWN.format(y=2023): 0, DESK.format(y=2023): 1,
                                     "ICLR.cc/2023/TinyPapers/-/Blind_Submission": 1,
                                     "ICLR.cc/2023/BlogPosts/-/Blind_Submission": 0}  # fmt: skip


def test_iclr_2023_recorded_blogpost_listing_is_crawled(tmp_path: Path) -> None:
    note = v1_note("iclr-2023/notes-blogposts-blind-submission.json")
    invitation = "ICLR.cc/2023/BlogPosts/-/Blind_Submission"
    crawl = run(FakeOpenReviewV1({invitation: [note]}), tmp_path, "ICLR", 2023)
    [record] = crawl.records
    assert outcome(record) == ("blogpost", "accepted", None)
    assert crawl.report.listings[invitation] == 1
    assert not any("Blogposts" in gap for gap in crawl.report.gaps)


def test_neurips_2021_main_and_both_dnb_rounds(tmp_path: Path) -> None:
    main = v1_note("neurips-2021/note-rejected.json")
    r1 = v1_note("neurips-2021/note-db-round1-rejected.json")  # bare Round1 venueid, rejected
    r2 = v1_note("neurips-2021/note-db-round2-accepted.json")
    server = FakeOpenReviewV1({
        "NeurIPS.cc/2021/Conference/-/Blind_Submission": [main],
        "NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round1/-/Submission": [r1],
        "NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round2/-/Submission": [r2],
    })  # fmt: skip
    got = by_forum(run(server, tmp_path, "NeurIPS", 2021))
    assert outcome(got[main["id"]]) == ("main", "rejected", None)
    assert outcome(got[r1["id"]]) == ("datasets_benchmarks", "rejected", None)
    assert outcome(got[r2["id"]]) == ("datasets_benchmarks", "accepted", None)
    assert got[r1["id"]].id == f"op:neurips:2021:{r1['id']}"


def test_neurips_2022_accept(tmp_path: Path) -> None:
    note = v1_note("neurips-2022/note-accepted.json")
    server = FakeOpenReviewV1({"NeurIPS.cc/2022/Conference/-/Blind_Submission": [note]})
    crawl = run(server, tmp_path, "NeurIPS", 2022)
    [record] = crawl.records
    assert outcome(record) == ("main", "accepted", None)
    assert any("only accepted papers" in g for g in crawl.report.gaps)


@pytest.mark.parametrize("year", [2021, 2022])
def test_neurips_verified_empty_status_listings_are_still_crawled(tmp_path: Path, year: int) -> None:
    server = FakeOpenReviewV1()
    crawl = run(server, tmp_path, "NeurIPS", year)
    invitations = {parse_qs(urlsplit(url).query)["invitation"][0] for url in server.gets()}
    withdrawn = f"NeurIPS.cc/{year}/Conference/-/Withdrawn_Submission"
    desk = f"NeurIPS.cc/{year}/Conference/-/Desk_Rejected_Submission"
    assert {withdrawn, desk} <= invitations
    assert crawl.report.listings[withdrawn] == crawl.report.listings[desk] == 0
    assert not any("not crawled until" in gap for gap in crawl.report.gaps)


# --- the v1 authority rules ---------------------------------------------------------------------------------------


def test_a_bare_v1_venueid_alone_never_gives_status(tmp_path: Path) -> None:
    note = v1_clone(v1_note("iclr-2022/note-rejected-bare-venueid.json"), "NoVenue2022x", venue=None)
    crawl = run(FakeOpenReviewV1({BLIND.format(y=2022): [note]}), tmp_path, "ICLR", 2022)
    [record] = crawl.records
    assert outcome(record) == ("main", "unknown", None) and record.venue_id_raw == "ICLR.cc/2022/Conference"
    assert crawl.report.unmapped == {"content.venue": 1}


def test_a_note_naming_another_venue_year_is_skipped_never_re_yeared(tmp_path: Path) -> None:
    base = v1_note("iclr-2022/note-rejected-bare-venueid.json")
    by_venue = v1_clone(base, "OtherYear01", venue="Submitted to ICLR 2023")
    by_venueid = v1_clone(base, "OtherYear02", venue="ICLR 2022 Poster", venueid="ICLR.cc/2023/Conference")
    crawl = run(FakeOpenReviewV1({BLIND.format(y=2022): [by_venue, by_venueid]}), tmp_path, "ICLR", 2022)
    assert crawl.records == () and crawl.report.skipped["out_of_scope"] == 2


def test_a_venueid_track_that_disagrees_makes_the_track_unknown_and_a_conflict(tmp_path: Path) -> None:
    note = v1_clone(
        v1_note("iclr-2023/notes-blind-count.json"), "TrackClash01", venueid="ICLR.cc/2023/TinyPapers"
    )
    crawl = run(FakeOpenReviewV1({BLIND.format(y=2023): [note]}), tmp_path, "ICLR", 2023)
    [record] = crawl.records
    assert outcome(record) == ("unknown", "accepted", None)
    [conflict] = crawl.report.conflicts
    assert conflict.field == "track" and conflict.value_b == "tiny_papers (venueid=ICLR.cc/2023/TinyPapers)"


def test_decision_notes_that_disagree_are_a_conflict_and_unknown(tmp_path: Path) -> None:
    forum = v1_notes("iclr-2020/forum-rejected.json")
    sub = v1_note("iclr-2020/forum-rejected.json")
    [decision] = [n for n in forum if n["invitation"].endswith("/-/Decision")]
    second = dict(decision, id="SecondDecision", content={**decision["content"], "decision": "Reject"})
    # two decision notes that agree are fine; two that disagree (2018's table maps both strings) are not
    ok = run(
        FakeOpenReviewV1({BLIND.format(y=2020): [sub]}, {sub["id"]: [*forum, second]}), tmp_path, "ICLR", 2020
    )
    assert outcome(ok.records[0]) == ("main", "rejected", None) and ok.report.conflicts == []
    forum18 = v1_notes("iclr-2018/forum-rejected.json")
    sub18 = v1_note("iclr-2018/forum-rejected.json")
    [d18] = [n for n in forum18 if n["invitation"].endswith("Acceptance_Decision")]
    accept = dict(d18, id="AcceptDecisionX", content={**d18["content"], "decision": "Accept (Poster)"})
    clash = run(FakeOpenReviewV1({BLIND.format(y=2018): [sub18]}, {sub18["id"]: [*forum18, accept]}),
                tmp_path / "b", "ICLR", 2018)  # fmt: skip
    assert outcome(clash.records[0]) == ("main", "unknown", None)
    [conflict] = clash.report.conflicts
    assert (conflict.field, conflict.resolution) == ("status", v1.CONFLICT)
    assert {conflict.value_a, conflict.value_b} == {"accepted (decision note AcceptDecisionX)",
                                                    "rejected (decision note BJ2zBJ6Hf)"}  # fmt: skip


def test_a_decision_note_must_reply_to_the_submission_in_its_forum(tmp_path: Path) -> None:
    forum = v1_notes("iclr-2020/forum-rejected.json")
    sub = v1_note("iclr-2020/forum-rejected.json")
    moved = [
        dict(n, replyto="SomeReviewNote") if n["invitation"].endswith("/-/Decision") else n for n in forum
    ]
    crawl = run(FakeOpenReviewV1({BLIND.format(y=2020): [sub]}, {sub["id"]: moved}), tmp_path, "ICLR", 2020)
    assert outcome(crawl.records[0]) == ("main", "unknown", None) and crawl.report.unmapped == {
        "decision_note": 1
    }


def test_only_the_submission_note_becomes_a_record(tmp_path: Path) -> None:
    [reply] = [
        n for n in v1_notes("iclr-2020/forum-rejected.json") if n["invitation"].endswith("/-/Decision")
    ]
    crawl = run(FakeOpenReviewV1({BLIND.format(y=2020): [reply]}), tmp_path, "ICLR", 2020)
    assert crawl.records == () and crawl.report.skipped["not_submission"] == 1 and crawl.report.forums == 0


def test_claims_carry_the_v1_source_and_the_page_they_came_from(tmp_path: Path) -> None:
    note = v1_note("iclr-2021/note-accepted.json")
    crawl = run(FakeOpenReviewV1({BLIND.format(y=2021): [note]}), tmp_path, "ICLR", 2021)
    [record] = crawl.records
    assert {c.source for c in record.provenance} == {"openreview_v1"}
    page = f"https://api.openreview.net/notes?invitation={BLIND.format(y=2021)}&limit=1000&offset=0"
    assert {c.url for c in record.provenance} == {page}
    assert claim(record, "presentation").value == "poster" and claim(record, "status").evidence == (
        "content.venue=ICLR 2021 Poster"
    )
    assert record.urls.pdf == f"https://openreview.net{note['content']['pdf']}"


# --- the client, pagination, resume, replay, dry run ------------------------------------------------------------


def test_the_client_logs_in_on_api2_and_reads_api1_and_caches_no_token(tmp_path: Path) -> None:
    server = FakeOpenReviewV1({BLIND.format(y=2022): [v1_note("iclr-2022/note-rejected-bare-venueid.json")]})
    run(server, tmp_path, "ICLR", 2022)
    assert server.logins() == 1 and all(urlsplit(u).hostname == "api.openreview.net" for u in server.gets())
    for path in v1.http_dir(tmp_path).rglob("*.json"):
        assert TOKEN not in path.read_text() and PASSWORD not in path.read_text()


def test_pagination_and_a_listing_whose_count_disagrees(tmp_path: Path) -> None:
    base = v1_note("iclr-2022/note-rejected-bare-venueid.json")
    notes = [v1_clone(base, f"Paged2022n{i}", i) for i in range(5)]
    server = FakeOpenReviewV1({BLIND.format(y=2022): notes})
    crawl = run(server, tmp_path, "ICLR", 2022, page_size=2)
    offsets = [parse_qs(urlsplit(u).query)["offset"][0] for u in server.gets() if "Blind" in u]
    assert offsets == ["0", "2", "4"] and crawl.report.listings[BLIND.format(y=2022)] == 5
    bad = FakeOpenReviewV1({BLIND.format(y=2022): notes})
    bad.count_bias = 1
    with pytest.raises(orv2.CrawlError, match="--refresh"):
        run(bad, tmp_path / "b", "ICLR", 2022)


def test_a_multi_page_listing_whose_count_changes_between_pages_is_refused(tmp_path: Path) -> None:
    base = v1_note("iclr-2022/note-rejected-bare-venueid.json")
    notes = [v1_clone(base, f"Paged2022n{i}", i) for i in range(3)]

    def grown_first_page(request: Request) -> Response | None:
        q = parse_qs(urlsplit(request.url).query)
        if q.get("invitation") != [BLIND.format(y=2022)] or q.get("offset") != ["0"]:
            return None
        # 4 on page 1, 3 on page 2: {3, 4} pops 3, which the 3 rows match, so only the count-change guard refuses
        # (a first-page count below the rows would be caught by the row check instead, testing nothing here)
        return json_response({"notes": notes[:2], "count": 4}, headers={"content-type": "application/json"})

    server = FakeOpenReviewV1({BLIND.format(y=2022): notes}, override=grown_first_page)  # page 2 says 3
    with pytest.raises(orv2.CrawlError, match=r"changed between its cached pages.*--refresh"):
        run(server, tmp_path, "ICLR", 2022, page_size=2)


@pytest.mark.parametrize("conflicting", [False, True])
def test_a_note_in_two_listings_is_a_counted_duplicate_only_when_its_record_is_identical(
    tmp_path: Path, conflicting: bool
) -> None:
    note = v1_note("neurips-2021/note-db-round2-accepted.json")
    again = v1_clone(note, note["id"], title="Changed Title") if conflicting else note
    round1, round2 = (f"NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round{n}/-/Submission" for n in (1, 2))
    server = FakeOpenReviewV1({round1: [note], round2: [again]})  # the same track and status evidence
    if conflicting:
        with pytest.raises(orv2.CrawlError, match=r"conflicting data in two status listings.*--refresh"):
            run(server, tmp_path, "NeurIPS", 2021)
        return
    crawl = run(server, tmp_path, "NeurIPS", 2021)
    assert crawl.report.skipped["duplicate"] == 1 and crawl.report.notes_read == 2
    assert crawl.report.imported == 1 and crawl.report.listings[round1] == crawl.report.listings[round2] == 1
    [record] = crawl.records
    assert outcome(record) == ("datasets_benchmarks", "accepted", None)
    assert {parse_qs(urlsplit(c.url).query)["invitation"][0] for c in record.provenance} == {round1}


def test_per_note_anomalies_are_debug_and_the_crawl_has_one_attention_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ws = v1_note("iclr-2013/notes-submission-decision-field.json")
    odd = [v1_clone(ws, f"OddNote2013x{n}", n, decision="conferenceSomething-new") for n in range(1, 3)]
    server = FakeOpenReviewV1({"ICLR.cc/2013/conference/-/submission": [ws, *odd]})
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        run(server, tmp_path, "ICLR", 2013)
    unmapped = [r for r in caplog.records if r.getMessage() == "openreview_v1_unmapped"]
    assert len(unmapped) == 2 and {r.levelno for r in unmapped} == {logging.DEBUG}
    [attention] = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert attention.getMessage() == "openreview_crawl_attention"
    assert {k: attention.__dict__[k] for k in ("api", "venue", "year", "unmapped", "duplicate")} == {
        "api": "v1", "venue": "ICLR", "year": 2013, "unmapped": 2, "duplicate": 0,
    }  # fmt: skip

    # a note whose own evidence disagrees (xGZG2kS5bFk: withdrawn invitation, accepted venue): a DEBUG
    # conflict line, counted in the crawl's one WARNING
    caplog.clear()
    withdrawn = v1_note("iclr-2021/note-withdrawn-with-accepted-venue.json")
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        run(FakeOpenReviewV1({WITHDRAWN.format(y=2021): [withdrawn]}), tmp_path / "2021", "ICLR", 2021)
    [conflict] = [r for r in caplog.records if r.getMessage() == "openreview_v1_conflict"]
    assert (conflict.levelno, conflict.__dict__["forum"]) == (logging.DEBUG, "xGZG2kS5bFk")
    [attention] = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert attention.getMessage() == "openreview_crawl_attention" and attention.__dict__["conflicts"] == 1


def test_purged_pre_projection_cache_entries_are_debug_and_counted_by_the_v1_crawl(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The v1 counterpart of v2's test: each purged entry is one DEBUG line; the crawl reports the count in its
    finished line and its one attention WARNING (TASK-116 review)."""
    ws = v1_note("iclr-2013/notes-submission-decision-field.json")
    server = FakeOpenReviewV1(
        {"ICLR.cc/2013/conference/-/submission": [ws, v1_clone(ws, "MoreNote2013x1", 1)]}
    )
    run(server, tmp_path, "ICLR", 2013, page_size=1)  # three pages: two full, one empty
    for path in sorted(v1.http_dir(tmp_path).rglob("*.json"))[:2]:  # back to the raw, pre-projection layout
        document = json.loads(path.read_text())
        del document["payload"]["public_projection"]
        path.write_text(json.dumps(document))
    again = client(tmp_path, server)
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        v1.crawl(again, "ICLR", 2013, page_size=1)
    purged = [r for r in caplog.records if r.getMessage() == "openreview_cache_incompatible"]
    assert len(purged) == 2 and {r.levelno for r in purged} == {logging.DEBUG} and again.incompatible == 2
    [finished] = [r for r in caplog.records if r.getMessage() == "openreview_crawl_finished"]
    assert finished.__dict__["cache_incompatible"] == 2
    [attention] = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert attention.getMessage() == "openreview_crawl_attention"
    assert (attention.__dict__["api"], attention.__dict__["cache_incompatible"]) == ("v1", 2)


def test_a_duplicate_note_is_a_debug_line_counted_in_the_attention_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    note = v1_note("neurips-2021/note-db-round2-accepted.json")
    round1, round2 = (f"NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round{n}/-/Submission" for n in (1, 2))
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        run(FakeOpenReviewV1({round1: [note], round2: [note]}), tmp_path, "NeurIPS", 2021)
    [duplicate] = [r for r in caplog.records if r.getMessage() == "openreview_v1_duplicate"]
    assert duplicate.levelno == logging.DEBUG
    [attention] = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert attention.getMessage() == "openreview_crawl_attention" and attention.__dict__["duplicate"] == 1


def test_a_v1_crawl_logs_a_start_line_and_bounded_progress_heartbeats(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ws = v1_note("iclr-2013/notes-submission-decision-field.json")
    notes = [ws, *(v1_clone(ws, f"MoreNote2013x{n}", n) for n in range(1, 4))]
    server = FakeOpenReviewV1({"ICLR.cc/2013/conference/-/submission": notes})
    live = v1.make_client(tmp_path, credentials=Credentials(USERNAME, PASSWORD), transport=server,
                          clock=TickingClock(31.0), jitter=lambda: 0.0)  # fmt: skip
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.sources"):
        v1.crawl(live, "ICLR", 2013)
    [started] = [r for r in caplog.records if r.getMessage() == "openreview_crawl_started"]
    assert {k: started.__dict__[k] for k in ("api", "venue", "year", "offline")} == {
        "api": "v1", "venue": "ICLR", "year": 2013, "offline": False,
    }  # fmt: skip
    beats = [r for r in caplog.records if r.getMessage() == "openreview_crawl_progress"]
    assert [b.__dict__["notes_read"] for b in beats] == [0, 1, 2, 3]
    assert set(beats[-1].__dict__) >= {
        "api",
        "venue",
        "year",
        "forums",
        "imported",
        "skipped",
        "requests",
        "cached",
    }
    assert beats[-1].__dict__["api"] == "v1" and beats[-1].__dict__["imported"] == 3

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.sources"):  # a stopped clock: none due
        v1.crawl(v1.make_client(tmp_path, credentials=None, offline=True, clock=FakeClock()), "ICLR", 2013)
    assert not [r for r in caplog.records if r.getMessage() == "openreview_crawl_progress"]


@pytest.mark.parametrize("count", [None, "1", True, -1])
def test_a_listing_with_a_missing_or_invalid_count_is_refused(tmp_path: Path, count: object) -> None:
    note = v1_note("iclr-2022/note-rejected-bare-venueid.json")

    def malformed(request: Request) -> Response | None:
        if "Blind_Submission" not in request.url:
            return None
        body: dict[str, object] = {"notes": [note]}
        if count is not None:
            body["count"] = count
        return json_response(body, headers={"content-type": "application/json"})

    server = FakeOpenReviewV1({BLIND.format(y=2022): [note]}, override=malformed)
    with pytest.raises(orv2.CrawlError, match=r"missing or invalid count.*--refresh"):
        run(server, tmp_path, "ICLR", 2022)


def test_a_note_in_two_status_listings_is_refused_as_a_stale_transition(tmp_path: Path) -> None:
    note = v1_note("iclr-2022/note-withdrawn-empty-venueid.json")
    server = FakeOpenReviewV1({BLIND.format(y=2022): [note], WITHDRAWN.format(y=2022): [note]})
    with pytest.raises(orv2.CrawlError, match=r"two status listings.*--refresh"):
        run(server, tmp_path, "ICLR", 2022)


NEURIPS_2021_MAIN = "NeurIPS.cc/2021/Conference/-/Blind_Submission"


def neurips_2021_twins(**second: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """TASK-125: the recorded NeurIPS 2021 accepted note and a second note of it as the live API holds 300 pairs
    (e.g. -K4tIyQLaY #292 and BW2Z6B7S9KZ #8244): another id and number, and a `_bibtex` that embeds the id,
    with everything else identical. `second` changes content values of the second note (`None` deletes)."""
    note = v1_note("neurips-2021/notes-main-listing.json")
    twin = v1_clone(
        note, "BW2Z6B7S9KZ", note["number"] + 604, _bibtex="@inproceedings{BW2Z6B7S9KZ}", **second
    )
    return note, twin


@pytest.mark.parametrize("listed_first", ["lower", "higher"])
def test_two_notes_of_one_paper_collapse_to_the_lowest_number_and_are_counted(
    tmp_path: Path, listed_first: str, caplog: pytest.LogCaptureFixture
) -> None:
    note, twin = neurips_2021_twins()
    notes = [note, twin] if listed_first == "lower" else [twin, note]
    server = FakeOpenReviewV1({NEURIPS_2021_MAIN: notes})
    # one note a page, as live (BW2Z6B7S9KZ is on offset 0): the twins' claims cite different pages, so the
    # comparison must leave provenance out
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        crawl = run(server, tmp_path, "NeurIPS", 2021, page_size=1)
    [record] = crawl.records
    assert record.native == note["id"]  # the lower number, whatever the listing order
    kept_page = [u for u in server.gets() if "invitation=" in u][notes.index(note)]
    assert {c.url for c in record.provenance} == {kept_page}  # its own page, not its twin's
    assert crawl.report.skipped["duplicate_submission"] == 1 and crawl.report.skipped["duplicate"] == 0
    assert (crawl.report.notes_read, crawl.report.imported) == (2, 1)
    assert crawl.report.to_manifest()["skipped"]["duplicate_submission"] == 1
    assert crawl.report.track_status == {"main": {"accepted": 1}}
    [line] = [r for r in caplog.records if r.getMessage() == "openreview_duplicate_submission"]
    assert (line.levelno, line.__dict__["forum"], line.__dict__["kept"]) == (
        logging.DEBUG,
        twin["id"],
        note["id"],
    )
    [attention] = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert attention.getMessage() == "openreview_crawl_attention"
    assert attention.__dict__["duplicate_submission"] == 1


@pytest.mark.parametrize(
    "second",
    [
        {"pdf": "/pdf/0123456789abcdef0123456789abcdef01234567.pdf"},  # another pdf: another submission
        {"title": "Synthetic title text 1, revised."},  # same pdf, another title: never guessed to be one
        {"authors": ["Synthetic Author 6", "Synthetic Author 7"]},
        {"abstract": "Another synthetic abstract."},
        {"keywords": ["Another keyword."]},
        {"venue": "NeurIPS 2021 Spotlight"},  # another presentation
        {"venue": None},  # no venue but a venueid: not silent (TASK-132 needs both absent), so another status
        {"venue": ""},  # an empty venue string is not an absent one: never a silent twin
        {"venueid": None},  # the same status and track, but another (here no) venueid
    ],
    ids=[
        "pdf",
        "title",
        "authors",
        "abstract",
        "keywords",
        "presentation",
        "status",
        "empty-venue",
        "venueid",
    ],
)
def test_notes_that_differ_in_any_compared_field_stay_two_records(
    tmp_path: Path, second: dict[str, Any]
) -> None:
    note, twin = neurips_2021_twins(**second)
    crawl = run(FakeOpenReviewV1({NEURIPS_2021_MAIN: [note, twin]}), tmp_path, "NeurIPS", 2021)
    assert {r.native for r in crawl.records} == {note["id"], twin["id"]}
    assert crawl.report.skipped["duplicate_submission"] == 0 and crawl.report.imported == 2


def test_notes_without_a_pdf_or_a_number_are_never_collapsed(tmp_path: Path) -> None:
    note, twin = neurips_2021_twins(pdf=None)
    del note["content"]["pdf"]
    crawl = run(FakeOpenReviewV1({NEURIPS_2021_MAIN: [note, twin]}), tmp_path / "pdf", "NeurIPS", 2021)
    assert len(crawl.records) == 2 and crawl.report.skipped["duplicate_submission"] == 0

    note, twin = neurips_2021_twins()
    del twin["number"]  # no number: no deterministic choice of which note speaks for the paper
    crawl = run(FakeOpenReviewV1({NEURIPS_2021_MAIN: [note, twin]}), tmp_path / "number", "NeurIPS", 2021)
    assert len(crawl.records) == 2 and crawl.report.skipped["duplicate_submission"] == 0


def test_identical_notes_with_a_crawl_conflict_are_never_collapsed(tmp_path: Path) -> None:
    """Both twins listed as withdrawn while `content.venue` says accepted (as ICLR 2021 xGZG2kS5bFk): each has
    status `unknown` and a conflicts.csv row naming its own id, and a record with a conflict is not collapsed
    (its row would otherwise point at a record the crawl dropped)."""
    note, twin = neurips_2021_twins()
    withdrawn = "NeurIPS.cc/2021/Conference/-/Withdrawn_Submission"
    crawl = run(FakeOpenReviewV1({withdrawn: [note, twin]}), tmp_path, "NeurIPS", 2021)
    assert {r.native for r in crawl.records} == {note["id"], twin["id"]}
    assert {outcome(r) for r in crawl.records} == {("main", "unknown", None)}
    assert {c.id for c in crawl.report.conflicts} == {r.id for r in crawl.records}
    assert crawl.report.skipped["duplicate_submission"] == 0


def test_a_same_paper_note_in_another_track_or_status_listing_is_not_collapsed(tmp_path: Path) -> None:
    """ICLR 2018 lists 24 pdfs twice, a blind note and a withdrawn one (status, often authors, differ): two
    submissions to reconcile downstream, never merged here."""
    note, twin = neurips_2021_twins()
    server = FakeOpenReviewV1({NEURIPS_2021_MAIN: [note],
                               "NeurIPS.cc/2021/Conference/-/Withdrawn_Submission": [twin]})  # fmt: skip
    crawl = run(server, tmp_path, "NeurIPS", 2021)
    assert {outcome(r) for r in crawl.records} == {("main", "accepted", "poster"), ("main", "unknown", None)}
    assert crawl.report.skipped["duplicate_submission"] == 0


# --- a silent twin (rule 5, TASK-132) ----------------------------------------------------------------------------

SILENT, SPEAKING = "W6e384Lkjbw", "rDdb26AQ0SO"


def silent_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    """NeurIPS 2021 `W6e384Lkjbw` #5999 (no `venue`, no `venueid`: status unknown) and `rDdb26AQ0SO` #11021
    (`NeurIPS 2021 Poster`), as recorded from the 2026-09-29 crawl (offsets 1000 and 0 of the main listing): the
    same pdf and supplementary material, and the free text the real notes share scrubbed to the same text."""
    silent = v1_note("neurips-2021/notes-main-listing-silent-twin.json")
    speaking = v1_note("neurips-2021/notes-main-listing-accepted-silent-twin.json")
    assert (silent["id"], silent["number"], speaking["id"], speaking["number"]) == (
        SILENT,
        5999,
        SPEAKING,
        11021,
    )
    assert "venue" not in silent["content"] and "venueid" not in silent["content"]
    assert speaking["content"]["venue"] == "NeurIPS 2021 Poster"
    shared = ("title", "authors", "abstract", "keywords", "pdf", "supplementary_material")
    assert all(silent["content"][k] == speaking["content"][k] for k in shared)
    return silent, speaking


@pytest.mark.parametrize("listed_first", ["silent", "speaking"])
def test_a_silent_twin_collapses_into_its_accepted_note_whatever_the_numbers(
    tmp_path: Path, listed_first: str, caplog: pytest.LogCaptureFixture
) -> None:
    """The real pair: the silent note has the lower number, but the accepted note is kept (it is the one with
    evidence), with only its own claims; the silent note is a counted `duplicate_submission`."""
    silent, speaking = silent_pair()
    notes = [silent, speaking] if listed_first == "silent" else [speaking, silent]
    server = FakeOpenReviewV1({NEURIPS_2021_MAIN: notes})
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        crawl = run(server, tmp_path, "NeurIPS", 2021, page_size=1)
    [record] = crawl.records
    assert record.native == SPEAKING and outcome(record) == ("main", "accepted", "poster")
    assert record.venue_id_raw == "NeurIPS.cc/2021/Conference"
    kept_page = [u for u in server.gets() if "invitation=" in u][notes.index(speaking)]
    assert {c.url for c in record.provenance} == {kept_page}
    assert crawl.report.skipped["duplicate_submission"] == 1 and (
        crawl.report.notes_read,
        crawl.report.imported,
    ) == (2, 1)
    assert crawl.report.track_status == {"main": {"accepted": 1}} and crawl.report.unknown_status == 0
    [line] = [r for r in caplog.records if r.getMessage() == "openreview_duplicate_submission"]
    assert (line.__dict__["forum"], line.__dict__["kept"]) == (SILENT, SPEAKING)


def test_without_its_twin_a_silent_note_is_an_unknown_record(tmp_path: Path) -> None:
    silent, _ = silent_pair()
    crawl = run(FakeOpenReviewV1({NEURIPS_2021_MAIN: [silent]}), tmp_path, "NeurIPS", 2021)
    [record] = crawl.records
    assert (record.native, outcome(record)) == (SILENT, ("main", "unknown", None))
    assert crawl.report.skipped["duplicate_submission"] == 0 and crawl.report.unmapped["content.venue"] == 1


@pytest.mark.parametrize(
    "speaking_changes",
    [
        {"pdf": "/pdf/0123456789abcdef0123456789abcdef01234567.pdf"},  # another pdf: another submission
        {"title": "Another synthetic title."},
        {"authors": ["Synthetic Author 7", "Synthetic Author 9", "Synthetic Author 8"]},  # order counts
        {"abstract": "Another synthetic abstract."},
        {"keywords": ["Another keyword."]},
        {"venue": "NeurIPS 2021 Submitted"},  # rejected: only an acceptance absorbs a silent twin
    ],
    ids=["pdf", "title", "authors", "abstract", "keywords", "rejected"],
)
def test_a_silent_note_that_differs_or_whose_twin_is_not_accepted_stays_a_record(
    tmp_path: Path, speaking_changes: dict[str, Any]
) -> None:
    silent, speaking = silent_pair()
    speaking["content"].update(speaking_changes)
    crawl = run(FakeOpenReviewV1({NEURIPS_2021_MAIN: [silent, speaking]}), tmp_path, "NeurIPS", 2021)
    assert {r.native for r in crawl.records} == {SILENT, SPEAKING}
    assert crawl.report.skipped["duplicate_submission"] == 0


def test_a_silent_note_with_two_differing_accepted_twins_is_never_given_one(tmp_path: Path) -> None:
    """Poster and spotlight twins: two notes with evidence that disagree on presentation, so which one the silent
    note would join is a choice. Nothing is collapsed."""
    silent, speaking = silent_pair()
    spotlight = v1_clone(speaking, "Zz9Spotlight", 12000, venue="NeurIPS 2021 Spotlight")
    crawl = run(
        FakeOpenReviewV1({NEURIPS_2021_MAIN: [silent, speaking, spotlight]}), tmp_path, "NeurIPS", 2021
    )
    assert {r.native for r in crawl.records} == {SILENT, SPEAKING, "Zz9Spotlight"}
    assert crawl.report.skipped["duplicate_submission"] == 0


def test_a_silent_note_joins_an_accepted_pair_after_the_pair_collapses(tmp_path: Path) -> None:
    """Two identical accepted notes (rule 5) and a silent third: the pair collapses to its lower number first,
    then the silent note joins that record."""
    silent, speaking = silent_pair()
    copy = v1_clone(speaking, "Zz9Identical", 12000)
    crawl = run(FakeOpenReviewV1({NEURIPS_2021_MAIN: [copy, silent, speaking]}), tmp_path, "NeurIPS", 2021)
    [record] = crawl.records
    assert record.native == SPEAKING and outcome(record) == ("main", "accepted", "poster")
    assert crawl.report.skipped["duplicate_submission"] == 2


def test_a_note_is_silent_only_on_the_submission_listing_of_a_venue_year(tmp_path: Path) -> None:
    """On the withdrawn listing the invitation speaks (`withdrawn`), so the note is no silent twin; in a year whose
    status also comes from a decision note (ICLR 2021), a note without a venue isn't silent either: its forum may
    hold the decision."""
    silent, speaking = silent_pair()
    withdrawn = "NeurIPS.cc/2021/Conference/-/Withdrawn_Submission"
    crawl = run(
        FakeOpenReviewV1({NEURIPS_2021_MAIN: [speaking], withdrawn: [silent]}),
        tmp_path / "w",
        "NeurIPS",
        2021,
    )
    # rule 4 instead: an accepted note whose pdf a withdrawn note shares is `unknown` with a conflict row
    assert {(r.native, r.status) for r in crawl.records} == {(SILENT, "withdrawn"), (SPEAKING, "unknown")}

    accepted = v1_note("iclr-2021/note-accepted.json")
    quiet = v1_clone(accepted, "Zz9NoVenue", accepted["number"] + 1, venue=None, venueid=None)
    server = FakeOpenReviewV1({BLIND.format(y=2021): [accepted, quiet]}, {"Zz9NoVenue": []})
    crawl = run(server, tmp_path / "iclr", "ICLR", 2021)
    assert {(r.native, r.status) for r in crawl.records} == {
        (accepted["id"], "accepted"),
        ("Zz9NoVenue", "unknown"),
    }
    assert crawl.report.skipped["duplicate_submission"] == 0


def test_a_record_with_a_crawl_conflict_is_a_rival_for_a_silent_note(tmp_path: Path) -> None:
    """A third note of the paper on the withdrawn listing whose venue says accepted (a crawl conflict: `unknown`,
    exempt from rule 5) is still a second candidate: the silent note stays a record (found by the property test)."""
    silent, speaking = silent_pair()
    conflicted = v1_clone(speaking, "Zz9Conflict", 12000)
    withdrawn = "NeurIPS.cc/2021/Conference/-/Withdrawn_Submission"
    server = FakeOpenReviewV1({NEURIPS_2021_MAIN: [silent, speaking], withdrawn: [conflicted]})
    crawl = run(server, tmp_path, "NeurIPS", 2021)
    assert {(r.native, r.status) for r in crawl.records} == {
        (SILENT, "unknown"),
        (SPEAKING, "accepted"),
        ("Zz9Conflict", "unknown"),
    }
    assert {c.id for c in crawl.report.conflicts} == {"op:neurips:2021:Zz9Conflict"}
    assert crawl.report.skipped["duplicate_submission"] == 0


def test_two_silent_notes_of_one_accepted_paper_are_never_collapsed(tmp_path: Path) -> None:
    """Rule 5 needs exactly two records, the silent note and the accepted one. A second silent note without a
    number (so the identical-note collapse leaves it alone) makes three: nothing collapses."""
    silent, speaking = silent_pair()
    numberless = v1_clone(silent, "Zz9Numberless")
    del numberless["number"]
    server = FakeOpenReviewV1({NEURIPS_2021_MAIN: [silent, speaking, numberless]})
    crawl = run(server, tmp_path, "NeurIPS", 2021)
    assert {(r.native, r.status) for r in crawl.records} == {
        (SILENT, "unknown"),
        (SPEAKING, "accepted"),
        ("Zz9Numberless", "unknown"),
    }
    assert crawl.report.skipped["duplicate_submission"] == 0


def test_a_silent_note_in_another_track_stays_a_record(tmp_path: Path) -> None:
    """Silent on the D&B Round 2 listing (its track is the listing's), its twin accepted in main: two tracks."""
    silent, speaking = silent_pair()
    round2 = "NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round2/-/Submission"
    crawl = run(
        FakeOpenReviewV1({NEURIPS_2021_MAIN: [speaking], round2: [silent]}), tmp_path, "NeurIPS", 2021
    )
    assert {(r.native, r.track) for r in crawl.records} == {
        (SILENT, "datasets_benchmarks"),
        (SPEAKING, "main"),
    }
    assert crawl.report.skipped["duplicate_submission"] == 0


def test_a_silent_note_without_a_pdf_is_never_collapsed(tmp_path: Path) -> None:
    silent, speaking = silent_pair()
    del silent["content"]["pdf"], speaking["content"]["pdf"]
    crawl = run(FakeOpenReviewV1({NEURIPS_2021_MAIN: [silent, speaking]}), tmp_path, "NeurIPS", 2021)
    assert {r.native for r in crawl.records} == {SILENT, SPEAKING}


# --- an accepted note with a withdrawn twin (rule 4 across two notes, decision-020) ------------------------------

ELMO, ELMO_TWIN, ELMO_DECISION = "S1p31z-Ab", "SJTCsqMUf", "S1HRmJaHM"


def elmo_world(
    decision: str | None = "Accept (Poster)", twin_pdf: str | None = None, twin_listing: str = WITHDRAWN
) -> FakeOpenReviewV1:
    """ICLR 2018 `S1p31z-Ab` (its decision note `Accept (Poster)`) and `SJTCsqMUf`, listed as withdrawn with the
    same pdf, as recorded; `decision` (None: the forum without its decision note, as the 12 undecided ICLR 2018
    blind notes with a withdrawn twin), `twin_pdf` and `twin_listing` vary one of them."""
    blind = v1_note("iclr-2018/notes-blind-accepted-with-withdrawn-twin.json")
    twin = v1_note("iclr-2018/notes-withdrawn-twin-of-accepted.json")
    assert blind["id"] == ELMO and twin["id"] == ELMO_TWIN
    assert blind["content"]["pdf"] == twin["content"]["pdf"]
    if twin_pdf is not None:
        twin["content"]["pdf"] = twin_pdf
    forum = [
        dict(n, content={**n["content"], "decision": decision}) if n["id"] == ELMO_DECISION else n
        for n in v1_notes("iclr-2018/forum-accepted-with-withdrawn-twin.json")
        if decision is not None or n["id"] != ELMO_DECISION
    ]
    return FakeOpenReviewV1(
        {BLIND.format(y=2018): [blind], twin_listing.format(y=2018): [twin]}, {ELMO: forum}
    )


def test_an_accepted_note_with_a_withdrawn_twin_is_unknown_and_an_unresolved_conflict(tmp_path: Path) -> None:
    """ELMo, ICLR 2018: accepted by its decision note, withdrawn as `SJTCsqMUf` (same pdf), not presented at ICLR
    2018. No signal outranks the other (decision-020): the accepted record is `unknown`, the twin stays withdrawn."""
    crawl = run(elmo_world(), tmp_path, "ICLR", 2018)
    got = by_forum(crawl)
    assert outcome(got[ELMO]) == ("main", "unknown", None)
    assert outcome(got[ELMO_TWIN]) == ("main", "withdrawn", None)
    decided = f"decision note {ELMO_DECISION} (decision=Accept (Poster))"
    twin = f"withdrawn (twin {ELMO_TWIN}, same pdf: invitation={WITHDRAWN.format(y=2018)})"
    status = claim(got[ELMO], "status")
    assert (status.value, status.evidence) == ("unknown", f"conflict: {decided} vs {twin}")
    assert status.url.endswith(f"forum={ELMO}&limit=1000&offset=0")  # still the forum page the decision is on
    assert got[ELMO].claims("presentation") == ()
    assert [(c.id, c.field, c.value_a, c.value_b, c.resolution) for c in crawl.report.conflicts] == [
        (f"op:iclr:2018:{ELMO}", "status", f"accepted ({decided})", twin, v1.CONFLICT)
    ]
    manifest = crawl.report.to_manifest()
    assert manifest["conflicts"] == 1 and manifest["track_status"] == {"main": {"unknown": 1, "withdrawn": 1}}
    assert manifest["unknown_status"] == 1 and manifest["skipped"]["duplicate_submission"] == 0


OTHER_PDF = "/pdf/" + "0" * 40 + ".pdf"


@pytest.mark.parametrize(
    ("decision", "twin_pdf", "expected", "rows"),
    [
        ("Accept (Poster)", None, ("main", "unknown", None), 1),  # as recorded: the conflict
        ("Accept (Oral)", None, ("main", "unknown", None), 1),  # any accepting decision
        ("Accept (Poster)", OTHER_PDF, ("main", "accepted", "poster"), 0),  # another pdf: two papers
        # no decision at all: the twin's withdrawal is the one signal (the owner, 2026-09-29, TASK-139)
        (None, None, ("main", "withdrawn", None), 0),
        (None, OTHER_PDF, ("main", "unknown", None), 0),  # no decision, another pdf: still undecided
        ("Reject", None, ("main", "rejected", None), 0),  # the owner: a rejected note stays rejected
        ("Invite to Workshop Track", None, ("workshop", "unknown", None), 0),  # a decision, and another track
    ],
    ids=[
        "poster",
        "oral",
        "accepted-other-pdf",
        "no-decision",
        "no-decision-other-pdf",
        "reject",
        "workshop",
    ],
)
def test_the_withdrawn_twin_rule_by_the_blind_notes_decision(
    tmp_path: Path,
    decision: str | None,
    twin_pdf: str | None,
    expected: tuple[str, str, str | None],
    rows: int,
) -> None:
    crawl = run(elmo_world(decision, twin_pdf), tmp_path, "ICLR", 2018)
    got = by_forum(crawl)
    assert outcome(got[ELMO]) == expected and outcome(got[ELMO_TWIN]) == ("main", "withdrawn", None)
    assert len(crawl.report.conflicts) == rows and len(crawl.records) == 2  # never collapsed


def test_an_undecided_note_made_withdrawn_is_never_collapsed_into_its_twin(tmp_path: Path) -> None:
    """The twin rule changes a status, never which records exist: even when the withdrawn twin's content is the
    blind note's to the letter (live, the authors differ), the two stay two records after both are withdrawn."""
    server = elmo_world(None)
    [blind] = server.listings[BLIND.format(y=2018)]
    [twin] = server.listings[WITHDRAWN.format(y=2018)]
    twin["content"] = dict(blind["content"])
    assert type(blind["number"]) is int and type(twin["number"]) is int
    crawl = run(server, tmp_path, "ICLR", 2018)
    assert {r.native: r.status for r in crawl.records} == {ELMO: "withdrawn", ELMO_TWIN: "withdrawn"}
    assert crawl.report.skipped["duplicate_submission"] == 0


def test_an_undecided_note_in_a_content_venue_year_keeps_unknown_beside_a_withdrawn_twin(
    tmp_path: Path,
) -> None:
    """Only the found absence of a decision note (`NO_DECISION_NOTE`, ICLR 2018–2021's decision-note years)
    counts as "no decision at all". A NeurIPS 2021 blind note with no `content.venue` (a content.venue year,
    where a note's silence is another rule's business) stays `unknown` beside a withdrawn twin of its pdf."""
    note, twin = neurips_2021_twins(venue=None)
    del note["content"]["venue"]
    server = FakeOpenReviewV1({NEURIPS_2021_MAIN: [note],
                               "NeurIPS.cc/2021/Conference/-/Withdrawn_Submission": [twin]})  # fmt: skip
    crawl = run(server, tmp_path, "NeurIPS", 2021)
    got = by_forum(crawl)
    assert outcome(got[note["id"]]) == ("main", "unknown", None)
    assert claim(got[note["id"]], "status").evidence != v1.NO_DECISION_NOTE
    assert outcome(got[twin["id"]]) == ("main", "withdrawn", None)
    assert crawl.report.conflicts == [] and len(crawl.records) == 2
    decision_note_years = {k for k, ad in v1.ADAPTERS.items() if ad.decision_notes is not None}
    assert decision_note_years == {("ICLR", y) for y in (2018, 2019, 2020, 2021)}


def test_an_undecided_note_with_a_withdrawn_twin_is_withdrawn_with_the_twin_as_evidence(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The 12 ICLR 2018 blind notes with no decision note and a withdrawn twin (the owner's answer, TASK-139):
    `withdrawn`, the claim citing the twin's listing page and naming it, and no conflict row, since nothing
    disagrees. The report moves it out of `unmapped` (where its missing decision note was counted) into
    `withdrawn_by_twin`, so the crawl's attention warning no longer reports it."""
    server = elmo_world(None)
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        crawl = run(server, tmp_path, "ICLR", 2018)
    got = by_forum(crawl)
    status, twin_status = claim(got[ELMO], "status"), claim(got[ELMO_TWIN], "status")
    assert (status.value, status.source) == ("withdrawn", "openreview_v1")
    assert status.evidence == (
        f"{v1.NO_DECISION_NOTE}; withdrawn twin {ELMO_TWIN} shares the pdf (invitation={WITHDRAWN.format(y=2018)})"
    )
    assert (status.url, status.fetched_at) == (twin_status.url, twin_status.fetched_at)
    assert "invitation=" in status.url and WITHDRAWN.format(y=2018).split("/")[-1] in status.url
    assert got[ELMO].claims("presentation") == () and got[ELMO].presentation is None
    assert crawl.report.conflicts == []
    manifest = crawl.report.to_manifest()
    assert manifest["track_status"] == {"main": {"withdrawn": 2}} and manifest["unknown_status"] == 0
    assert manifest["unmapped"] == {} and manifest["withdrawn_by_twin"] == 1
    assert crawl.report.withdrawn_by_twin == 1 and not crawl.report.unmapped
    [line] = [r for r in caplog.records if r.getMessage() == "openreview_v1_withdrawn_twin"]
    assert (line.levelno, line.__dict__["forum"]) == (logging.DEBUG, ELMO)
    assert "openreview_crawl_attention" not in [r.getMessage() for r in caplog.records]


def test_an_undecided_note_without_a_twin_stays_unmapped_and_the_manifest_keeps_its_shape(
    tmp_path: Path,
) -> None:
    """Another pdf: no twin, so the missing decision note stays in `unmapped` (and the attention warning), and a
    crawl with no note made withdrawn has no `withdrawn_by_twin` key (every other crawl file is unchanged)."""
    crawl = run(elmo_world(None, OTHER_PDF), tmp_path, "ICLR", 2018)
    manifest = crawl.report.to_manifest()
    assert manifest["unmapped"] == {"decision_note": 1} and "withdrawn_by_twin" not in manifest
    assert crawl.report.withdrawn_by_twin == 0


NOTHING = v1.Twins([], [])


def _forum(nid: str) -> str:
    return f"https://openreview.net/forum?id={nid}"


def pre_rule_pair(tmp_path: Path) -> tuple[PaperRecord, PaperRecord]:
    """ELMo's two records as the listings gave them, before the twin rule: accepted, and withdrawn."""
    records = {r.id: r for r in run(elmo_world(), tmp_path, "ICLR", 2018).records}
    elmo, twin = records[f"op:iclr:2018:{ELMO}"], records[f"op:iclr:2018:{ELMO_TWIN}"]
    [status] = elmo.claims("status")
    kept = tuple(c for c in elmo.provenance if c.field != "status")
    accepted = elmo.model_copy(
        update={"status": "accepted", "provenance": (*kept, status.model_copy(update={"value": "accepted"}))}
    )
    return accepted, twin


def test_the_twin_rule_is_order_free_and_idempotent(tmp_path: Path) -> None:
    accepted, twin = pre_rule_pair(tmp_path)
    for order in ((accepted, twin), (twin, accepted)):
        world = {r.id: r for r in order}
        [row] = v1.withdrawn_twins(world).conflicts
        assert row.id == accepted.id and row.value_b.startswith(f"withdrawn (twin {ELMO_TWIN}, same pdf:")
        assert world[accepted.id].status == "unknown" and world[twin.id].status == "withdrawn"
        assert v1.withdrawn_twins(world) == NOTHING  # an unknown record has no conflict left to find


def test_the_row_names_every_withdrawn_twin(tmp_path: Path) -> None:
    accepted, twin = pre_rule_pair(tmp_path)
    second = twin.model_copy(update={"id": "op:iclr:2018:SecondTwin18"})
    world = {r.id: r for r in (accepted, twin, second)}
    [row] = v1.withdrawn_twins(world).conflicts
    assert row.value_b.count("twin ") == 2
    assert row.value_b.index(f"twin {ELMO_TWIN},") < row.value_b.index("twin SecondTwin18,")


@pytest.mark.parametrize(
    ("change_accepted", "change_twin"),
    [
        # a desk rejection (e.g. for a duplicate submission) can leave the same pdf beside the presented copy
        ({}, {"status": "desk_rejected"}),
        # an accepted workshop note beside a withdrawn conference note of the same pdf: two submissions
        ({"track": "workshop"}, {}),
        # no OpenReview pdf on either side (`_pdf` drops an arXiv link, as for ICLR 2013–2014): nothing to join on
        ({"urls": Urls(forum=_forum(ELMO))}, {"urls": Urls(forum=_forum(ELMO_TWIN))}),
    ],
    ids=["desk-rejected twin", "another track", "no pdf"],
)
def test_no_conflict_without_a_withdrawn_same_track_twin_of_the_pdf(
    tmp_path: Path, change_accepted: dict[str, Any], change_twin: dict[str, Any]
) -> None:
    accepted, twin = pre_rule_pair(tmp_path)
    world = {
        accepted.id: accepted.model_copy(update=change_accepted),
        twin.id: twin.model_copy(update=change_twin),
    }
    before = dict(world)
    assert v1.withdrawn_twins(world) == NOTHING and world == before  # both statuses kept


def as_status(r: PaperRecord, status: str, evidence: str) -> PaperRecord:
    """`r` with its status (and its status claim's value and evidence) replaced, as the listings could give it."""
    [was] = r.claims("status")
    kept = tuple(c for c in r.provenance if c.field not in ("status", "presentation"))
    now = was.model_copy(update={"value": status, "evidence": evidence})
    return r.model_copy(update={"status": status, "presentation": None, "provenance": (*kept, now)})


DECIDED = f"decision note {ELMO_DECISION} (decision=Reject)"
UNDECIDED = v1.NO_DECISION_NOTE


@pytest.mark.parametrize(
    ("blind", "twin", "change_twin", "expected"),
    [
        (("unknown", UNDECIDED), ("withdrawn", None), {}, "withdrawn"),  # the owner's answer (1)
        (("rejected", DECIDED), ("withdrawn", None), {}, "rejected"),  # answer (2): stays rejected
        (("unknown", UNDECIDED), ("desk_rejected", "invitation=x"), {}, "unknown"),  # answer (3): no effect
        (("accepted", DECIDED), ("desk_rejected", "invitation=x"), {}, "accepted"),  # answer (3), accepted side
        (("accepted", DECIDED), ("withdrawn", None), {}, "unknown"),  # decision-020: unknown and a row
        (("unknown", UNDECIDED), ("withdrawn", None), {"track": "workshop"}, "unknown"),  # another track
        # unknown for another reason than no decision: a conflict, an unmapped string, a dry run
        (("unknown", "decision notes disagree"), ("withdrawn", None), {}, "unknown"),
        (("unknown", "decision note string not in the table"), ("withdrawn", None), {}, "unknown"),
        (("unknown", "decision note not fetched (dry run)"), ("withdrawn", None), {}, "unknown"),
        (("withdrawn", "invitation=y"), ("withdrawn", None), {}, "withdrawn"),  # both withdrawn: untouched
    ],
    ids=["undecided", "rejected", "undecided-desk", "accepted-desk", "accepted", "undecided-other-track",
         "conflict", "unmapped", "dry-run", "withdrawn"],
)  # fmt: skip
def test_the_twin_rule_table(
    tmp_path: Path,
    blind: tuple[str, str],
    twin: tuple[str, str | None],
    change_twin: dict[str, Any],
    expected: str,
) -> None:
    accepted, withdrawn = pre_rule_pair(tmp_path)
    b = as_status(accepted, *blind)
    t = withdrawn if twin[1] is None else as_status(withdrawn, twin[0], twin[1])
    t = t.model_copy(update=change_twin)
    world = {b.id: b, t.id: t}
    got = v1.withdrawn_twins(world)
    assert world[b.id].status == expected and world[t.id] == t  # the twin never changes
    assert got.withdrawn == ([b.id] if expected != blind[0] == "unknown" else [])
    assert [c.id for c in got.conflicts] == ([b.id] if blind[0] == "accepted" != expected else [])
    if expected == blind[0]:
        assert world[b.id] == b  # untouched, claims and all


def test_the_undecided_rule_is_order_free_and_idempotent(tmp_path: Path) -> None:
    """An accepted note, an undecided note and a withdrawn note of one pdf (not seen live): the accepted one is
    `unknown` with a row naming the listed twin only, the undecided one `withdrawn`, whatever the order; a second
    run changes nothing (its newly withdrawn record makes nothing else withdrawn or unknown)."""
    accepted, twin = pre_rule_pair(tmp_path)
    undecided = as_status(accepted, "unknown", UNDECIDED).model_copy(
        update={"id": "op:iclr:2018:Undecided18"}
    )
    results = []
    for order in ((accepted, undecided, twin), (twin, undecided, accepted), (undecided, twin, accepted)):
        world = {r.id: r for r in order}
        got = v1.withdrawn_twins(world)
        assert got.withdrawn == [undecided.id] and [c.id for c in got.conflicts] == [accepted.id]
        assert "Undecided18" not in got.conflicts[0].value_b
        assert {r.id: r.status for r in world.values()} == {
            accepted.id: "unknown", undecided.id: "withdrawn", twin.id: "withdrawn"}  # fmt: skip
        after = dict(world)
        assert v1.withdrawn_twins(world) == NOTHING and world == after
        results.append(sorted(world.items()))
    assert results[0] == results[1] == results[2]


def test_an_undecided_note_names_every_withdrawn_twin_in_id_order(tmp_path: Path) -> None:
    accepted, twin = pre_rule_pair(tmp_path)
    undecided = as_status(accepted, "unknown", UNDECIDED)
    second = twin.model_copy(update={"id": "op:iclr:2018:ASecondTwin"})
    world = {r.id: r for r in (undecided, twin, second)}
    assert v1.withdrawn_twins(world).withdrawn == [undecided.id]
    [status] = world[undecided.id].claims("status")
    assert status.evidence.count("withdrawn twin ") == 2
    assert status.evidence.index("twin ASecondTwin ") < status.evidence.index(f"twin {ELMO_TWIN} ")
    [first] = second.claims("status")
    assert status.url == first.url  # the first twin's listing page


def test_an_arxiv_pdf_link_is_no_pdf_so_no_twin(tmp_path: Path) -> None:
    arxiv = "http://arxiv.org/abs/1301.3781"
    world = elmo_world()
    for notes in world.listings.values():
        for n in notes:
            n["content"]["pdf"] = arxiv
    crawl = run(world, tmp_path, "ICLR", 2018)
    assert {r.native: r.status for r in crawl.records} == {ELMO: "accepted", ELMO_TWIN: "withdrawn"}
    assert crawl.report.conflicts == [] and all(r.urls.pdf is None for r in crawl.records)


def world_2021() -> FakeOpenReviewV1:
    forum = v1_notes("iclr-2021/forum-rejected-no-venueid.json")
    rejected = v1_note("iclr-2021/forum-rejected-no-venueid.json")
    return FakeOpenReviewV1(
        {BLIND.format(y=2021): [v1_note("iclr-2021/note-accepted.json"), rejected],
         WITHDRAWN.format(y=2021): [v1_note("iclr-2021/note-withdrawn-with-accepted-venue.json")]},
        {rejected["id"]: forum},
    )  # fmt: skip


def test_an_interrupted_crawl_resumes_without_refetching(tmp_path: Path) -> None:
    def outage(request: Request) -> Response | None:
        return json_response({"name": "ServiceUnavailable"}, 503) if "forum=" in request.url else None

    broken = world_2021()
    broken.override = outage
    with pytest.raises(OpenReviewRetriesExhausted):
        v1.ingest(client(tmp_path, broken, max_attempts=2), tmp_path, "ICLR", [2021])
    assert not v1.crawl_file(tmp_path, "ICLR", 2021).exists()
    before = {u for u in broken.gets() if "forum=" not in u}
    healthy = world_2021()
    [report] = v1.ingest(client(tmp_path, healthy), tmp_path, "ICLR", [2021])
    assert report.complete and v1.crawl_file(tmp_path, "ICLR", 2021).exists()
    assert not before & set(healthy.gets()) and forum_gets(healthy) == ["pAj7zLJK05U"]


def test_a_finished_crawl_replays_offline_with_no_credentials_and_no_request(tmp_path: Path) -> None:
    [report] = v1.ingest(client(tmp_path, world_2021()), tmp_path, "ICLR", [2021])
    silent = FakeOpenReviewV1()
    again = v1.crawl(client(tmp_path, silent, credentials=None, offline=True), "ICLR", 2021)
    assert silent.calls == [] and again.report.to_manifest() == report.to_manifest()
    [replayed] = v1.replay(tmp_path)
    assert replayed.records == again.records and replayed.report.conflicts == again.report.conflicts


def test_offline_refuses_an_uncached_crawl(tmp_path: Path) -> None:
    with pytest.raises(OpenReviewCacheMiss):
        v1.ingest(client(tmp_path, FakeOpenReviewV1(), offline=True), tmp_path, "ICLR", [2022])


def test_a_dry_run_counts_uncached_forums_and_writes_nothing(tmp_path: Path) -> None:
    server = world_2021()
    v1.crawl(client(tmp_path, server), "ICLR", 2021)
    for p in v1.http_dir(tmp_path).rglob("*.json"):  # forget the forum listing
        if "forum=" in json.loads(p.read_text())["key"]:
            p.unlink()
    silent = FakeOpenReviewV1()
    [report] = v1.ingest(client(tmp_path, silent, credentials=None, offline=True), tmp_path, "ICLR", [2021],
                         dry_run=True)  # fmt: skip
    manifest = report.to_manifest()
    assert (
        silent.calls == [] and not manifest["complete"] and not v1.crawl_file(tmp_path, "ICLR", 2021).exists()
    )
    assert manifest["forums_uncached"] == 1
    assert manifest["would_fetch"] == [
        "https://api.openreview.net/notes?forum=pAj7zLJK05U&limit=1000&offset=0"
    ]
    with pytest.raises(ValueError, match="offline"):
        v1.crawl(client(tmp_path, server), "ICLR", 2021, dry_run=True)


# --- the snapshot build and the CLI --------------------------------------------------------------------------


def test_the_snapshot_build_replays_v1_crawls_and_writes_their_conflicts(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    v1.ingest(client(cache, world_2021()), cache, "ICLR", [2021])
    v1.ingest(client(cache, FakeOpenReviewV1()), cache, "ICLR", [2015])  # a coverage gap: nothing fetched
    result = snap.build(cache, tmp_path / "snapshots", FETCHED)
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_count"] == 3 and set(manifest["sources"]) == {"openreview_v1"}
    entry = manifest["sources"]["openreview_v1"]
    assert set(entry["crawl_window"]) == {"from", "to"}
    assert [(c["year"], c["api"]) for c in entry["crawls"]] == [(2015, "v1"), (2021, "v1")]
    assert manifest["counts"]["ICLR"]["2021"]["main"] == {"accepted": 1, "rejected": 1, "unknown": 1}
    # the scrubbed fixtures share synthetic titles, so dedup also reports them (ambiguous_not_merged)
    assert manifest["conflicts"]["unresolved"] == 1
    rows = list(csv.DictReader(io.StringIO((result.path / "conflicts.csv").read_text(encoding="utf-8"))))
    assert [
        (r["id"], r["field"], r["resolution"]) for r in rows if r["resolution"].startswith("unresolved")
    ] == [("op:iclr:2021:xGZG2kS5bFk", "status", "unresolved:openreview_v1")]
    assert snap.load_records(result.path)["op:iclr:2021:xGZG2kS5bFk"].status == "unknown"


def test_crawl_conflicts_follow_a_merge_to_the_surviving_record() -> None:
    from openproceedings.ingest.dedup import Conflict, DedupResult, Merge

    report = v1.CrawlReport("ICLR", 2021)
    report.conflicts.append(Conflict("op:iclr:2021:Merged", "status", "a", "openreview_v1", "b", "openreview_v1",
                                     v1.CONFLICT))  # fmt: skip
    merge = Merge("op:iclr:2021:Survivor", "op:iclr:2021:Merged", "title_venue_year", "k", "ICLR", 2021, "x")
    out = snap.with_crawl_conflicts(DedupResult((), (merge,), ()), [report])
    assert [c.id for c in out.conflicts] == ["op:iclr:2021:Survivor"]
    assert snap.with_crawl_conflicts(DedupResult((), (), ()), [v1.CrawlReport("ICLR", 2022)]).conflicts == ()


def test_cli_picks_v1_or_v2_by_year(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cache = tmp_path / "cache"
    v1.ingest(client(cache, world_2021()), cache, "ICLR", [2021])
    capsys.readouterr()
    base = ["--data-dir", str(tmp_path), "ingest", "openreview", "--venue", "ICLR"]
    assert cli.main([*base, "--years", "2021", "--offline"]) == 0
    [report] = json.loads(capsys.readouterr().out)
    assert (report["api"], report["imported"], report["conflicts"]) == ("v1", 3, 1)
    # 2015 needs no request; 2024 (v2) is uncached: a dry run reports both, in year order
    assert cli.main([*base, "--years", "2015", "--offline"]) == 0
    [gap] = json.loads(capsys.readouterr().out)
    assert gap["year"] == 2015 and gap["complete"] and gap["coverage_gaps"]
    assert cli.main(["--data-dir", str(tmp_path / "empty"), "ingest", "openreview", "--venue", "ICLR",
                     "--years", "2023-2024", "--dry-run"]) == 0  # fmt: skip
    dry = json.loads(capsys.readouterr().out)
    assert [(d["year"], d["api"], d["complete"]) for d in dry] == [(2023, "v1", False), (2024, "v2", False)]
    assert dry[0]["would_fetch"][0].startswith("https://api.openreview.net/notes?invitation=ICLR.cc/2023/")


def test_cli_refuses_a_year_on_neither_api_before_fetching(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--data-dir", str(tmp_path), "ingest", "openreview", "--venue", "NeurIPS", "--years", "2020-2021"]
    assert cli.main(argv) == 1
    assert "not on OpenReview" in capsys.readouterr().err and not (tmp_path / "cache").exists()


def test_a_twin_rule_miscount_raises_instead_of_hiding_a_negative_unmapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the twin rule ever reported a record made withdrawn whose missing decision note wasn't counted in
    `unmapped`, the crawl refuses rather than letting `+report.unmapped` drop the negative count."""
    real = v1.withdrawn_twins

    def overcounting(records: dict[str, PaperRecord]) -> v1.Twins:
        got = real(records)
        return v1.Twins(got.conflicts, [*got.withdrawn, *sorted(records)])

    monkeypatch.setattr(v1, "withdrawn_twins", overcounting)
    with pytest.raises(RuntimeError, match="more undecided notes than were counted"):
        run(elmo_world(None), tmp_path, "ICLR", 2018)
