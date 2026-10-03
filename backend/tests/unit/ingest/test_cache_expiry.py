"""Cache expiry (TASK-102; spec 01 §Pipeline, Cache expiry): the TTL per listing type, a live client
re-fetching (and logging) an expired entry, an offline client never expiring anything, and a listing
re-fetched as a whole. Fake clocks and scripted transports only; no network."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from openproceedings.ingest.sources import neurips
from openproceedings.ingest.sources import openreview_v2 as orv
from openproceedings.ingest.sources.http import PROCEEDINGS, Response
from openproceedings.ingest.sources.openreview_client import (
    DAY,
    POLICY,
    TTL,
    Credentials,
    OpenReviewClient,
    listing_kind,
    ttl,
)

from tests.unit.ingest.openreview_fakes import EPOCH, PASSWORD, USERNAME, FakeClock, FakeOpenReview
from tests.unit.ingest.proceedings_helpers import FakeTransport, fetcher

V2 = "https://api2.openreview.net"
NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)
OPEN_SUBMISSIONS = "ICLR.cc/2026/Conference/Submission"


# --- the table ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "kind", "year"),
    [
        (f"{V2}/notes?content.venueid=ICLR.cc/2024/Conference&limit=1000&offset=0&sort=number:asc", "accepted", 2024),
        (f"{V2}/notes?content.venueid=ICLR.cc/2024/Conference/Submission&offset=0", "status", 2024),
        (f"{V2}/notes?content.venueid=ICLR.cc/2024/Conference/Rejected_Submission", "status", 2024),
        (f"{V2}/notes?content.venueid=ICLR.cc/2024/Conference/Withdrawn_Submission", "status", 2024),
        (f"{V2}/notes?content.venueid=ICLR.cc/2024/Conference/Desk_Rejected_Submission", "status", 2024),
        (f"{V2}/notes?content.venueid=NeurIPS.cc/2025/Datasets_and_Benchmarks_Track", "accepted", 2025),
        (f"{V2}/notes?content.venueid=ICLR.cc/2024/Workshop/ICBINB/Rejected_Submission", "status", 2024),
        (f"{V2}/groups?parent=ICML.cc/2026&limit=1000&offset=0", "groups", 2026),
        (f"{V2}/groups?id=ICML.cc/2026/Conference", "groups", 2026),
        (f"{V2}/groups?parent=ICML.cc/2026/Workshop_Mexico_City", "groups", 2026),
        (f"{V2}/notes?id=abc", "other", None),
        (f"{V2}/notes?content.venueid=NoYear/Conference", "other", None),
    ],
)  # fmt: skip
def test_each_listing_has_a_kind_and_a_venue_year(url: str, kind: str, year: int | None) -> None:
    assert listing_kind(url) == (kind, year)


def test_ttl_by_kind_and_whether_the_venue_year_is_open() -> None:
    accepted = f"{V2}/notes?content.venueid=ICLR.cc/{{}}/Conference"
    submissions = f"{V2}/notes?content.venueid=ICLR.cc/{{}}/Conference/Submission"
    groups = f"{V2}/groups?parent=ICLR.cc/{{}}"
    # open: this calendar year or later; over: earlier
    assert [ttl(u.format(2026), NOW) for u in (accepted, submissions, groups)] == [7 * DAY, DAY, DAY]
    assert [ttl(u.format(2027), NOW) for u in (accepted, submissions, groups)] == [7 * DAY, DAY, DAY]
    assert [ttl(u.format(2025), NOW) for u in (accepted, submissions, groups)] == [
        365 * DAY,
        90 * DAY,
        90 * DAY,
    ]
    assert ttl(f"{V2}/notes?id=abc", NOW) == DAY
    # a settled list never expires sooner than one that can still change
    assert all(open_ <= over for open_, over in TTL.values())


def test_api_v1_and_the_proceedings_never_expire() -> None:
    assert (
        ttl("https://api.openreview.net/notes?invitation=ICLR.cc/2021/Conference/-/Blind_Submission", NOW)
        is None
    )
    assert POLICY.ttl is ttl
    assert PROCEEDINGS.ttl("https://proceedings.neurips.cc/paper_files/paper/2013", NOW) is None


# --- the client --------------------------------------------------------------------------------------------


def or_client(
    cache: Path, server: FakeOpenReview, clock: FakeClock, *, offline: bool = False
) -> OpenReviewClient:
    return OpenReviewClient(cache, credentials=Credentials(USERNAME, PASSWORD), transport=server, clock=clock,
                            min_interval=0.0, jitter=lambda: 0.0, offline=offline)  # fmt: skip


def listing(n: int) -> list[dict[str, object]]:
    return [{"id": f"note{i}", "readers": ["everyone"], "content": {}} for i in range(n)]


def test_an_expired_entry_is_refetched_overwritten_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    server = FakeOpenReview(notes={OPEN_SUBMISSIONS: listing(1)})
    clock = FakeClock()
    c = or_client(tmp_path, server, clock)
    params = {"content.venueid": OPEN_SUBMISSIONS}
    assert c.get("/notes", params)["fetched_at"] == EPOCH.isoformat()
    clock.t = DAY  # exactly the TTL: still fresh
    c.get("/notes", params)
    assert (len(server.gets()), c.stats.expired, c.cached) == (1, 0, 1)

    server.notes[OPEN_SUBMISSIONS] = listing(2)  # a paper submitted since
    clock.t = DAY + 1
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.sources.http"):
        entry = c.get("/notes", params)
    assert len(entry["json"]["notes"]) == 2
    assert entry["fetched_at"] == (EPOCH + timedelta(seconds=DAY + 1)).isoformat()
    assert (len(server.gets()), c.stats.expired) == (2, 1)
    [line] = [r for r in caplog.records if r.getMessage() == "openreview_cache_expired"]
    assert (line.age_s, line.ttl_s) == (DAY + 1, DAY)  # type: ignore[attr-defined]
    assert "venueid" in line.url  # type: ignore[attr-defined]
    # overwritten: fresh again from the new fetch time
    c.get("/notes", params)
    assert (len(server.gets()), c.stats.expired) == (2, 1)


def test_a_settled_accepted_list_lasts_a_year(tmp_path: Path) -> None:
    vid = "ICLR.cc/2024/Conference"
    server = FakeOpenReview(notes={vid: listing(1)})
    clock = FakeClock()
    c = or_client(tmp_path, server, clock)
    c.get("/notes", {"content.venueid": vid})
    clock.t = 364 * DAY
    c.get("/notes", {"content.venueid": vid})
    assert len(server.gets()) == 1
    clock.t = 366 * DAY
    c.get("/notes", {"content.venueid": vid})
    assert len(server.gets()) == 2


def test_offline_never_expires(tmp_path: Path) -> None:
    """Replay must stay reproducible: an offline client reads an entry of any age, and never fetches."""
    server = FakeOpenReview(notes={OPEN_SUBMISSIONS: listing(1)})
    clock = FakeClock()
    or_client(tmp_path, server, clock).get("/notes", {"content.venueid": OPEN_SUBMISSIONS})
    clock.t = 10 * 365 * DAY
    offline = or_client(tmp_path, server, clock, offline=True)
    entry = offline.get("/notes", {"content.venueid": OPEN_SUBMISSIONS})
    assert entry["fetched_at"] == EPOCH.isoformat()
    assert (len(server.gets()), offline.stats.expired, offline.requests) == (1, 0, 0)


def test_refresh_still_refetches_a_fresh_entry(tmp_path: Path) -> None:
    server = FakeOpenReview(notes={OPEN_SUBMISSIONS: listing(1)})
    clock = FakeClock()
    or_client(tmp_path, server, clock).get("/notes", {"content.venueid": OPEN_SUBMISSIONS})
    c = or_client(tmp_path, server, clock)
    c.get("/notes", {"content.venueid": OPEN_SUBMISSIONS}, refresh=True)
    assert (len(server.gets()), c.stats.expired) == (2, 0)


def test_a_listing_is_refetched_as_a_whole(tmp_path: Path) -> None:
    """Page 0 fetched at t=0, page 1 twelve hours later: at 25 h only page 0 is past its TTL, but page 1 is
    fetched again too, so the listing's pages (and its `count`) come from one moment."""
    server = FakeOpenReview(notes={OPEN_SUBMISSIONS: listing(3)})
    clock = FakeClock()
    c = or_client(tmp_path, server, clock)
    params = {"content.venueid": OPEN_SUBMISSIONS, "sort": "number:asc"}
    c.get("/notes", {**params, "limit": 2, "offset": 0})
    clock.t = 12 * 3600
    c.get("/notes", {**params, "limit": 2, "offset": 2})
    assert len(server.gets()) == 2

    server.notes[OPEN_SUBMISSIONS] = listing(4)
    clock.t = 25 * 3600
    pages = list(orv._pages(c, "/notes", params, "notes", 2))
    assert [len(items) for _, items in pages] == [2, 2, 0]  # the new paper, and a third (short) page
    assert (len(server.gets()), c.stats.expired) == (5, 1)
    assert {e["json"]["count"] for e, _ in pages} == {4}


def test_a_fresh_listing_is_not_refetched(tmp_path: Path) -> None:
    server = FakeOpenReview(notes={OPEN_SUBMISSIONS: listing(3)})
    clock = FakeClock()
    c = or_client(tmp_path, server, clock)
    params = {"content.venueid": OPEN_SUBMISSIONS, "sort": "number:asc"}
    list(orv._pages(c, "/notes", params, "notes", 2))
    clock.t = DAY - 1
    list(orv._pages(c, "/notes", params, "notes", 2))
    assert (len(server.gets()), c.stats.expired) == (2, 0)


def test_the_proceedings_never_expire_even_live(tmp_path: Path) -> None:
    url = "https://proceedings.neurips.cc/paper_files/paper/2013"
    transport = FakeTransport({url: Response(200, {"content-type": "text/html"}, b"<html>x</html>")})
    f, clock = fetcher(tmp_path, transport, neurips.HOSTS, min_interval=0)
    f.get(url)
    clock.now = lambda: datetime(2036, 1, 1, tzinfo=UTC)  # type: ignore[method-assign]
    f.get(url)
    assert (len(transport.calls), f.stats.expired) == (1, 0)
