from datetime import UTC, datetime

import pytest
from openproceedings.ingest import ojs_table
from openproceedings.ingest.sources import ojs
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.sources.http import Fetcher, PageCache, canonical

from tests.unit.ingest.ojs import oai
from tests.unit.ingest.proceedings_helpers import T0, FakeTransport, response, seed

TABLE_TEXT = """
[[journal]]
code = "AAAI"
venue = "AAAI"
year_offset = 1986
verified = 2026-10-09
source = "test"

[[section]]
journal = "AAAI"
volume = 34
set_spec = "AAAI:AISI"
kind = "papers"
track = "main"
label = "Special Track on AI for Social Impact"
papers = 2
verified = 2026-10-09
source = "test"

[[section]]
journal = "AAAI"
volume = 34
set_spec = "AAAI:IAAI"
kind = "papers"
track = "iaai"
label = "IAAI Technical Track on Emerging Applications of AI"
papers = 1
verified = 2026-10-09
source = "test"

[[section]]
journal = "AAAI"
volume = 34
set_spec = "AAAI:FMT"
kind = "front_matter"
label = "Front Matter"
papers = 1
verified = 2026-10-09
source = "test"
"""
TABLE = ojs_table.load(TABLE_TEXT)


def _offline(tmp_path) -> Fetcher:
    return Fetcher(PageCache(tmp_path / "ojs"), None, hosts=ojs.HOSTS, expect="xml", keep_query=True)


SET = "AAAI:AISI"


def _seed(tmp_path, *pages: str, times: tuple[datetime, ...] = ()) -> None:
    """Seed a ListSets page naming one set and that set's token chain: page i links to page i+1 by token
    `t<i+1>`. The miner takes each record's section from its own header, not from the set it was listed under,
    so these chains may mix sections (the per-set tests below keep them apart)."""
    seed(tmp_path, "ojs", ojs.sets_url("AAAI"), oai.sets_page(SET), at=T0, keep_query=True)
    for i, text in enumerate(pages):
        at = times[i] if times else T0
        url = ojs.oai_url("AAAI", set_spec=SET) if i == 0 else ojs.oai_url("AAAI", f"t{i}")
        seed(tmp_path, "ojs", url, text, at=at, keep_query=True)


def test_two_pages_become_records_with_claims(tmp_path) -> None:
    _seed(
        tmp_path,
        oai.page(oai.record(28000, title="First"), oai.deleted(27999), token="t1"),
        oai.page(
            oai.record(28001, title="Second"),
            oai.record(28002, "AAAI:IAAI", title="Third"),
            oai.record(28003, "AAAI:FMT", title="Preface"),
        ),
    )
    result = ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    ids = sorted(r.id for r in result.records)
    assert ids == ["op:aaai:2020:ojs-28000", "op:aaai:2020:ojs-28001", "op:aaai:2020:ojs-28002"]
    first = next(r for r in result.records if r.native == "ojs-28000")
    assert (first.track, first.status, first.authors, first.abstract) == (
        "main",
        "accepted",
        ("Jane Doe",),
        "An abstract.",
    )
    assert first.urls.doi == "10.1609/aaai.v34i01.28000"
    assert first.urls.proceedings == "https://ojs.aaai.org/index.php/AAAI/article/view/28000"
    assert {c.source for c in first.provenance} == {"ojs"}
    track = next(c for c in first.provenance if c.field == "track")
    assert "Special Track on AI for Social Impact" in (track.evidence or "") and "AAAI:AISI" in (
        track.evidence or ""
    )
    third = next(r for r in result.records if r.native == "ojs-28002")
    assert third.track == "iaai"
    assert (result.deleted, result.front_matter, result.pages) == (1, 1, 2)
    (report,) = result.reports
    assert (report.venue, report.year, report.volume, report.stated, report.listed, report.records) == (
        "AAAI",
        2020,
        34,
        3,
        3,
        3,
    )
    assert report.count_ok and report.tracks == {"main": 2, "iaai": 1}


def test_unlisted_section_stops(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1, "AAAI:NEW")))
    with pytest.raises(CrawlError, match=r"AAAI v34 section AAAI:NEW") as e:
        ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    assert e.value.reason == "unlisted_section"


def test_unlisted_volume_stops(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1, volume="Vol. 41 No. 1: AAAI-27")))
    with pytest.raises(CrawlError, match=r"AAAI v41.*set AAAI:AISI") as e:
        ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    assert e.value.reason == "unlisted_volume"


def test_record_without_a_volume_stops(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1, volume="no volume here")))
    with pytest.raises(CrawlError, match="no volume") as e:
        ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    assert e.value.reason == "oai_unreadable"


def test_count_mismatch_is_reported_not_hidden(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1), oai.record(2, "AAAI:IAAI")))  # AISI has 1 of its 2
    (report,) = ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE).reports
    assert not report.count_ok and (report.stated, report.listed) == (3, 2)


def test_a_record_without_title_is_skipped_and_counted(tmp_path) -> None:
    rec = oai.record(1).replace('<dc:title xml:lang="en-US">A Paper</dc:title>', "")
    _seed(tmp_path, oai.page(rec, oai.record(2), oai.record(3, "AAAI:IAAI")))
    result = ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    assert result.reports[0].skipped == {"no_title": 1}
    assert len(result.records) == 2


def test_an_empty_creator_is_skipped(tmp_path) -> None:
    _seed(
        tmp_path,
        oai.page(oai.record(1, creators=("Doe, Jane", " ")), oai.record(2), oai.record(3, "AAAI:IAAI")),
    )
    rec = next(
        r for r in ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE).records if r.native == "ojs-1"
    )
    assert rec.authors == ("Jane Doe",)


def test_a_snippet_abstract_is_dropped(tmp_path) -> None:
    _seed(
        tmp_path, oai.page(oai.record(1, description="…a snippet"), oai.record(2), oai.record(3, "AAAI:IAAI"))
    )
    rec = next(
        r for r in ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE).records if r.native == "ojs-1"
    )
    assert rec.abstract is None


def test_the_same_article_twice_is_counted_once(tmp_path) -> None:
    _seed(
        tmp_path,
        oai.page(oai.record(1), token="t1"),
        oai.page(oai.record(1), oai.record(2), oai.record(3, "AAAI:IAAI")),
    )
    result = ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    assert len(result.records) == 3 and result.reports[0].skipped == {"duplicate": 1}


def test_a_journal_without_a_row_is_refused(tmp_path) -> None:
    with pytest.raises(CrawlError, match=r"not in ojs_sections\.toml"):
        ojs.mine_journal("XYZ", _offline(tmp_path), table=TABLE)


def test_an_expired_token_stops_with_what_to_do(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1), token="t1"), oai.error("badResumptionToken"))
    with pytest.raises(CrawlError, match="--refresh") as e:
        ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    assert e.value.reason == "oai_error"


T2 = datetime(2026, 10, 1, 8, 30, tzinfo=UTC)


def test_claims_carry_their_own_page_url_and_time(tmp_path) -> None:
    _seed(
        tmp_path,
        oai.page(oai.record(1), oai.record(2, "AAAI:IAAI"), token="t1"),
        oai.page(oai.record(3)),
        times=(T0, T2),
    )
    result = ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    one = next(r for r in result.records if r.native == "ojs-1")
    three = next(r for r in result.records if r.native == "ojs-3")
    assert {(c.url, c.fetched_at) for c in one.provenance} == {(ojs.oai_url("AAAI", set_spec=SET), T0)}
    assert {(c.url, c.fetched_at) for c in three.provenance} == {(ojs.oai_url("AAAI", "t1"), T2)}
    assert three.urls.pdf == "https://ojs.aaai.org/index.php/AAAI/article/view/3/7003"
    assert result.reports[0].fetched == [T0, T2]  # one volume over two pages: both times


def test_refresh_fetches_only_the_first_page_again(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1), token="t1"), oai.page(oai.record(2), oai.record(3, "AAAI:IAAI")))
    sets, first = ojs.sets_url("AAAI"), ojs.oai_url("AAAI", set_spec=SET)
    transport = FakeTransport({})
    headers = {"content-type": "text/xml; charset=utf-8"}
    transport.script = {
        canonical(sets, keep_query=True): [response(oai.sets_page(SET), headers=headers)],
        canonical(first, keep_query=True): [response(oai.page(oai.record(1), token="t1"), headers=headers)],
    }
    fetcher = Fetcher(
        PageCache(tmp_path / "ojs"), transport, hosts=ojs.HOSTS, min_interval=0, expect="xml", keep_query=True
    )
    result = ojs.mine_journal("AAAI", fetcher, refresh=True, table=TABLE)
    assert transport.calls == [canonical(sets, keep_query=True), canonical(first, keep_query=True)]
    assert len(result.records) == 3


def test_a_listed_volume_the_harvest_never_showed_is_reported(tmp_path) -> None:
    two = ojs_table.load(
        str(TABLE_TEXT)
        + """
[[section]]
journal = "AAAI"
volume = 35
set_spec = "AAAI:AISI"
kind = "papers"
track = "main"
label = "Special Track on AI for Social Impact"
papers = 4
verified = 2026-10-09
source = "test"
"""
    )
    _seed(tmp_path, oai.page(oai.record(1), oai.record(2), oai.record(3, "AAAI:IAAI")))
    reports = ojs.mine_journal("AAAI", _offline(tmp_path), table=two).reports
    assert [r.volume for r in reports] == [34, 35]
    assert reports[0].count_ok
    assert (reports[1].year, reports[1].listed, reports[1].stated, reports[1].count_ok) == (2021, 0, 4, False)


def test_authors_evidence_says_what_was_done(tmp_path) -> None:
    _seed(
        tmp_path, oai.page(oai.record(1), oai.record(2, creators=("Aristotle",)), oai.record(3, "AAAI:IAAI"))
    )
    records = {r.native: r for r in ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE).records}

    def evidence(native: str) -> str:
        return next(c.evidence or "" for c in records[native].provenance if c.field == "authors")

    assert "shown First Last" in evidence("ojs-1")
    assert "as published" in evidence("ojs-2") and "shown First Last" not in evidence("ojs-2")
