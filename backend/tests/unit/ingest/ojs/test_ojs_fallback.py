"""The journal harvest (`ojs.harvest_journal`): the inventory (journal-wide ListIdentifiers) says which articles exist
and counts the deleted ones; each set's ListRecords chain supplies metadata, with its fallback (a page that answers
HTTP 5xx on every retry sends the set to ListIdentifiers + GetRecord); an inventory article no set returned is read
by GetRecord; an article returned twice is kept once (two different copies stop the crawl); an article no route
serves is `unavailable` (named in the table, or the crawl stops); the cached failure makes the offline replay take
the same path."""

import pytest
from openproceedings.ingest import ojs_table
from openproceedings.ingest.sources import ojs
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.sources.http import CacheMiss, Fetcher, PageCache, RetriesExhausted, canonical

from tests.unit.ingest.ojs import oai
from tests.unit.ingest.ojs.test_ojs_mine import TABLE_TEXT
from tests.unit.ingest.proceedings_helpers import FakeTransport, fetcher, response

XML = {"content-type": "text/xml; charset=utf-8"}
APP = """
[[section]]
journal = "AAAI"
volume = 34
set_spec = "AAAI:APP"
kind = "papers"
track = "main"
label = "AAAI Technical Track: Applications"
papers = 4

verified = 2026-10-09
source = "test"
"""
NAMED = """
[[unavailable]]
journal = "AAAI"
article = 39173
set_spec = "AAAI:APP"
volume = 34
reason = "every OAI form and the article page answer HTTP 500"
verified = 2026-10-09
source = "test"
"""
IAAI_TEXT = TABLE_TEXT.replace("papers = 1\n", "papers = 2\n", 1)  # IAAI: 3, and 5 (which no set returns)
assert IAAI_TEXT != TABLE_TEXT
FULL = ojs_table.load(IAAI_TEXT + APP + NAMED)  # v34: AISI 2 + IAAI 2 + APP 4 (one of them unavailable) = 8
UNNAMED = ojs_table.load(IAAI_TEXT + APP)
INVENTORY = (
    (1, False, "AAAI:AISI"), (2, False, "AAAI:AISI"), (9, True, "AAAI:AISI"), (3, False, "AAAI:IAAI"),
    (5, False, "AAAI:IAAI"), (4, False, "AAAI:FMT"), (101, False, "AAAI:APP"), (90, True, "AAAI:APP"),
    (90, True, "AAAI:APP"), (102, False, "AAAI:APP"), (103, False, "AAAI:APP"), (39173, False, "AAAI:APP"),
    (77, True, "AAAI:OLD"),  # a deleted header no set chain shows: counted from the inventory
)  # fmt: skip


def _key(url: str) -> str:
    return canonical(url, keep_query=True)


def _script() -> dict[str, list]:
    """AAAI with three sets. AISI's chain is two pages; IAAI's one; APP's second page answers HTTP 500 every time
    (it holds 39173), so APP falls back: ListIdentifiers (two pages, one deleted header) then GetRecord for 102
    and 39173 (101 was on APP's first page; 39173's GetRecord answers 500 too)."""
    ok = lambda text: [response(text, headers=XML)]  # noqa: E731
    fail = [response("", status=500, headers=XML)]
    return {
        _key(ojs.ids_url("AAAI")): ok(oai.identifiers_page(*INVENTORY[:6], token="v1")),
        _key(ojs.ids_url("AAAI", "v1")): ok(oai.identifiers_page(*INVENTORY[6:])),
        # IAAI is named twice (as a case-blind clash would): both requests answer with article 3, never 5
        _key(ojs.sets_url("AAAI")): ok(oai.sets_page("AAAI:AISI", "AAAI:IAAI", "AAAI:Iaai", token="s1")),
        _key(ojs.oai_url("AAAI", set_spec="AAAI:Iaai")): ok(oai.page(oai.record(3, "AAAI:IAAI"))),
        _key(ojs.record_url("AAAI", 5)): ok(oai.get_record(oai.record(5, "AAAI:IAAI", title="Shadowed"))),
        _key(ojs.sets_url("AAAI", "s1")): ok(oai.sets_page("AAAI:APP", "AAAI:FMT", "OTHER:X")),
        _key(ojs.oai_url("AAAI", set_spec="AAAI:AISI")): ok(oai.page(oai.record(1), token="a1")),
        _key(ojs.oai_url("AAAI", "a1")): ok(oai.page(oai.record(2), oai.deleted(9))),
        _key(ojs.oai_url("AAAI", set_spec="AAAI:IAAI")): ok(oai.page(oai.record(3, "AAAI:IAAI"))),
        _key(ojs.oai_url("AAAI", set_spec="AAAI:FMT")): ok(oai.page(oai.record(4, "AAAI:FMT"))),
        _key(ojs.oai_url("AAAI", set_spec="AAAI:APP")): ok(
            oai.page(oai.record(101, "AAAI:APP"), oai.deleted(90, "AAAI:APP"), token="p1")
        ),
        _key(ojs.oai_url("AAAI", "p1")): fail,
        _key(ojs.ids_url("AAAI", set_spec="AAAI:APP")): ok(
            oai.identifiers_page((90, True, "AAAI:APP"), (101, False, "AAAI:APP"), token="i1")
        ),
        _key(ojs.ids_url("AAAI", "i1")): ok(
            oai.identifiers_page(
                (90, True, "AAAI:APP"),
                (102, False, "AAAI:APP"),
                (103, False, "AAAI:APP"),
                (39173, False, "AAAI:APP"),
            )
        ),
        _key(ojs.record_url("AAAI", 102)): ok(oai.get_record(oai.record(102, "AAAI:APP", title="Recovered"))),
        _key(ojs.record_url("AAAI", 103)): ok(oai.get_record(oai.record(103, "AAAI:APP"))),
        _key(ojs.record_url("AAAI", 39173)): fail,
    }


def _live(tmp_path, script: dict[str, list] | None = None) -> tuple[Fetcher, FakeTransport]:
    transport = FakeTransport({})
    transport.script = script or _script()
    f, _clock = fetcher(tmp_path / "ojs", transport, ojs.HOSTS, min_interval=0, expect="xml", keep_query=True)
    return f, transport


def _offline(tmp_path) -> Fetcher:
    return Fetcher(PageCache(tmp_path / "ojs"), None, hosts=ojs.HOSTS, expect="xml", keep_query=True)


def test_each_set_chain_is_followed_and_only_the_journals_own_sets(tmp_path) -> None:
    f, transport = _live(tmp_path)
    assert ojs.journal_sets("AAAI", f) == ["AAAI:AISI", "AAAI:APP", "AAAI:FMT", "AAAI:IAAI", "AAAI:Iaai"]
    h = ojs.harvest_set("AAAI", "AAAI:AISI", f)
    assert [e.article for _p, e in h.live] == [1, 2] and (h.deleted, h.pages, h.fallback) == (1, 2, False)
    assert _key(ojs.oai_url("AAAI", "a1")) in transport.calls


def test_a_5xx_page_falls_back_to_identifiers_and_getrecord(tmp_path) -> None:
    f, transport = _live(tmp_path)
    h = ojs.harvest_set("AAAI", "AAAI:APP", f)
    assert h.fallback
    assert [e.article for _p, e in h.live] == [101, 102, 103]  # 101 from ListRecords, not fetched again
    assert _key(ojs.record_url("AAAI", 101)) not in transport.calls
    assert [a for a, _p in h.unavailable] == [39173] and h.unavailable[0][1].status == 500
    assert h.deleted == 2  # every deleted header ListIdentifiers lists (90 twice), not ListRecords' subset
    recovered = next(p for p, e in h.live if e.article == 102)
    assert recovered.url == _key(ojs.record_url("AAAI", 102))


def test_a_named_unavailable_article_is_listed_and_reported(tmp_path) -> None:
    f, _t = _live(tmp_path)
    result = ojs.mine_journal("AAAI", f, table=FULL)
    assert sorted(r.native for r in result.records) == [f"ojs-{n}" for n in (1, 101, 102, 103, 2, 3, 5)]
    (report,) = result.reports
    assert (report.stated, report.listed, report.records) == (8, 8, 7)
    assert report.count_ok and report.skipped == {"unavailable": 1}
    assert (result.unavailable, result.front_matter) == (1, 1)
    title = next(r for r in result.records if r.native == "ojs-102").title
    assert title == "Recovered"


def test_deleted_headers_are_counted_from_the_inventory(tmp_path) -> None:
    f, _t = _live(tmp_path)
    assert ojs.mine_journal("AAAI", f, table=FULL).deleted == 4  # 9, 90 twice, and 77 that no set shows


def test_an_inventory_article_no_set_returns_is_read_by_getrecord(tmp_path) -> None:
    f, transport = _live(tmp_path)
    result = ojs.mine_journal("AAAI", f, table=FULL)
    five = next(r for r in result.records if r.native == "ojs-5")
    assert (five.title, five.track) == ("Shadowed", "iaai")
    assert {c.url for c in five.provenance} == {_key(ojs.record_url("AAAI", 5))}
    assert result.recovered == 1 and _key(ojs.record_url("AAAI", 5)) in transport.calls


def test_an_article_two_set_requests_return_is_counted_once(tmp_path) -> None:
    f, _t = _live(tmp_path)
    result = ojs.mine_journal("AAAI", f, table=FULL)
    assert [r.native for r in result.records].count("ojs-3") == 1
    assert result.duplicates == 1 and result.reports[0].listed == 8  # listed counts distinct articles


def test_two_different_copies_of_an_article_stop_the_crawl(tmp_path) -> None:
    script = _script()
    script[_key(ojs.oai_url("AAAI", set_spec="AAAI:Iaai"))] = [
        response(oai.page(oai.record(3, "AAAI:IAAI", title="Another title")), headers=XML)
    ]
    f, _t = _live(tmp_path, script)
    with pytest.raises(CrawlError, match=r"article 3 came back from two set requests with different") as e:
        ojs.mine_journal("AAAI", f, table=FULL)
    assert e.value.reason == "conflicting_duplicate"


def test_a_set_record_the_inventory_lacks_stops_the_crawl(tmp_path) -> None:
    script = _script()
    script[_key(ojs.oai_url("AAAI", set_spec="AAAI:Iaai"))] = [
        response(oai.page(oai.record(6, "AAAI:IAAI")), headers=XML)
    ]
    f, _t = _live(tmp_path, script)
    with pytest.raises(CrawlError, match=r"article 6 .*not a live article of the inventory") as e:
        ojs.mine_journal("AAAI", f, table=FULL)
    assert e.value.reason == "not_in_inventory"


def test_an_unnamed_unavailable_article_stops_the_crawl(tmp_path) -> None:
    f, _t = _live(tmp_path)
    with pytest.raises(CrawlError, match=r"article 39173 \(set AAAI:APP\).*\[\[unavailable\]\]") as e:
        ojs.mine_journal("AAAI", f, table=UNNAMED)
    assert e.value.reason == "unavailable_record"


def test_the_offline_replay_takes_the_same_fallback_and_gives_the_same_result(tmp_path) -> None:
    f, _t = _live(tmp_path)
    live = ojs.mine_journal("AAAI", f, table=FULL)
    replayed = ojs.mine_journal("AAAI", _offline(tmp_path), table=FULL)  # no transport: a miss would raise
    assert [r.model_dump() for r in replayed.records] == [r.model_dump() for r in live.records]
    assert [r.to_manifest() for r in replayed.reports] == [r.to_manifest() for r in live.reports]
    fields = ("deleted", "unavailable", "pages", "duplicates", "recovered", "front_matter")
    assert [getattr(replayed, k) for k in fields] == [getattr(live, k) for k in fields]


def test_a_failure_that_is_not_a_5xx_is_not_cached(tmp_path) -> None:
    script = _script()
    script[_key(ojs.oai_url("AAAI", "p1"))] = [response("", status=429, headers=XML)]
    f, _t = _live(tmp_path, script)
    with pytest.raises(RetriesExhausted) as e:
        ojs.harvest_set("AAAI", "AAAI:APP", f)
    assert e.value.status == 429
    assert not _offline(tmp_path).is_cached(ojs.oai_url("AAAI", "p1"))


def test_offline_a_missing_page_is_a_miss_not_a_fallback(tmp_path) -> None:
    with pytest.raises(CacheMiss):
        ojs.harvest_set("AAAI", "AAAI:APP", _offline(tmp_path))
