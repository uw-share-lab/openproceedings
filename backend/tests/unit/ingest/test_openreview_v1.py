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
from openproceedings.ingest.record import PaperRecord
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
    # early 2017 notes give `authors` as one string: never split by guess, counted
    assert got[rejected["id"]].authors == () and crawl.report.authors_unsplit == 1


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
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        crawl = run(FakeOpenReviewV1({NEURIPS_2021_MAIN: notes}), tmp_path, "NeurIPS", 2021)
    [record] = crawl.records
    assert record.native == note["id"]  # the lower number, whatever the listing order
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
        {"venue": None},  # W6e384Lkjbw: same pdf, but no venue, so another status (unknown)
    ],
    ids=["pdf", "title", "authors", "abstract", "keywords", "presentation", "status"],
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


def test_a_same_paper_note_in_another_track_or_status_listing_is_not_collapsed(tmp_path: Path) -> None:
    """ICLR 2018 lists 24 pdfs twice, a blind note and a withdrawn one (status, often authors, differ): two
    submissions to reconcile downstream, never merged here."""
    note, twin = neurips_2021_twins()
    server = FakeOpenReviewV1({NEURIPS_2021_MAIN: [note],
                               "NeurIPS.cc/2021/Conference/-/Withdrawn_Submission": [twin]})  # fmt: skip
    crawl = run(server, tmp_path, "NeurIPS", 2021)
    assert {outcome(r) for r in crawl.records} == {("main", "accepted", "poster"), ("main", "unknown", None)}
    assert crawl.report.skipped["duplicate_submission"] == 0


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
