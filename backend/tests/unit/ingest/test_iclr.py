"""ICLR 2014-2016 accepted-paper archive source (TASK-096), from recorded public pages."""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from types import ModuleType

import pytest
from openproceedings import cli
from openproceedings.ingest.dedup import dedup
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.sources.html import MAX_DEPTH, HTMLBudgetError
from openproceedings.ingest.sources.http import canonical

from tests.unit.ingest.proceedings_helpers import T0, fetcher, fixture_text, fixture_url, seed, seed_fixture

FIXTURES = {
    2014: "iclr/2014/conference-index.json",
    2015: "iclr/2015/conference-index.json",
    2016: "iclr/2016/conference-index.json",
}


def source() -> ModuleType:
    return importlib.import_module("openproceedings.ingest.sources.iclr")


def seed_year(cache: Path, year: int) -> None:
    seed_fixture(cache, "iclr", FIXTURES[year])


def mine(cache: Path, year: int):  # type: ignore[no-untyped-def]
    iclr = source()
    crawler, _ = fetcher(cache / "iclr", None, iclr.HOSTS)
    return iclr.mine_year(year, crawler)


def by_id(records: list[PaperRecord]) -> dict[str, PaperRecord]:
    return {record.id: record for record in records}


def test_the_three_recorded_pages_parse_only_conference_track_papers() -> None:
    iclr = source()
    parsed = {
        year: iclr.parse_index(year, fixture_text(rel), fixture_url(rel)) for year, rel in FIXTURES.items()
    }
    assert {year: len(entries) for year, entries in parsed.items()} == {2014: 2, 2015: 4, 2016: 4}
    assert [entry.title for entry in parsed[2015]] == [
        "Synthetic title 1",
        "Synthetic title 4",
        "Synthetic title 7",
        "Synthetic title 10",
    ]  # the two recorded Workshop Papers entries are excluded
    assert parsed[2014][0].authors == ("Synthetic Author 2", "Synthetic Author 3")
    assert "<p " in fixture_text(FIXTURES[2014]) and "<li " not in fixture_text(FIXTURES[2014])


def test_list_parser_is_attribute_order_independent_and_ignores_decoy_links_and_other_sections() -> None:
    page = """<h3 data-x='1' id='workshop_papers'>Workshop Papers</h3>
    <ol><li><a href='http://arxiv.org/abs/1412.7272'>Workshop Title</a><br/>Workshop Person</li></ol>
    <h3 class='sectionedit1' id='main_conference_-_oral_presentations'>Main Conference</h3>
    <ol><li data-x='1' class='level1'><div class='li'>Decoy Person <a rel='nofollow' href='decoy.html'>Decoy Link</a>
          <a title='t' class='urlextern' href='http://arxiv.org/abs/1412.6623'>Actual Title</a><br/>
          Actual One; Actual Two and Actual Three</div></li>
        <li class='level1'><a target='_blank' href='https://beta.openreview.net/forum?id=Forum00001'>Forum Title</a>,
          Forum Author</li></ol>"""
    iclr = source()
    assert iclr.parse_index(2015, page, iclr.LISTINGS[2015]) == [
        iclr.Entry("https://arxiv.org/abs/1412.6623", "iclr-77b79d4a8d13c419bf89c1bf9c2a109d", "Actual Title",
                   ("Actual One", "Actual Two", "Actual Three"), None),
        iclr.Entry("https://openreview.net/forum?id=Forum00001", "Forum00001", "Forum Title", ("Forum Author",),
                   "https://openreview.net/forum?id=Forum00001"),
    ]  # fmt: skip


def test_paragraph_parser_ignores_a_decoy_link_paragraph_and_reads_single_quoted_attributes() -> None:
    page = """<p dir='ltr'><a href='https://example.org/decoy.pdf'>Decoy Link</a></p><p>Decoy Person</p>
    <p dir='ltr'><span style='font-weight:bold'><a rel='nofollow' href='http://arxiv.org/abs/1312.6173'>Actual Title</a></span></p>
    <p dir='ltr'><span style='font-style:italic'>Actual One; Actual Two</span></p>"""
    iclr = source()
    assert iclr.parse_index(2014, page, iclr.LISTINGS[2014]) == [
        iclr.Entry("https://arxiv.org/abs/1312.6173", "iclr-beb53fd8b4fa307df929907eb35e1a7b", "Actual Title",
                   ("Actual One", "Actual Two"), None),
    ]  # fmt: skip


def test_an_entry_outside_any_paragraph_is_read_with_the_next_blocks_authors() -> None:
    """The live 2014 page (2026-09-29) sets one of its 35 papers, arXiv 1312.6055, in a bare <span><b><a> with
    its authors in the next <div><i>, not in <p> paragraphs; it was dropped and the listing counted 34 (TASK-124).
    Compact case in that markup (the <div> goes on to hold later entries, as on the page), names synthetic."""
    page = """<p dir="ltr"><span style="font-weight:bold"><a href="http://arxiv.org/abs/1301.3584" rel="nofollow">Paragraph Title</a></span></p>
    <p dir="ltr"><span style="font-style:italic">Para One; Para Two</span></p>
    <span style="color:rgb(34,34,34)"><div><br /></div></span>
    <span style="font-size:12.7px"><b><a href="http://arxiv.org/abs/1312.6055" rel="nofollow">Bare Title</a></b></span>
    <div><i style="font-size:1em"><span>Bare One; Bare Two</span></i>
      <p dir="ltr"><span style="font-weight:bold"><a href="http://arxiv.org/abs/1312.6086">Next Title</a></span></p>
      <p dir="ltr"><span style="font-style:italic">Next One</span></p></div>"""
    iclr = source()
    parsed = iclr.parse_index(2014, page, iclr.LISTINGS[2014])
    assert [(e.title, e.authors) for e in parsed] == [
        ("Paragraph Title", ("Para One", "Para Two")),
        ("Bare Title", ("Bare One", "Bare Two")),
        ("Next Title", ("Next One",)),
    ]


def test_bare_entries_side_by_side_and_a_block_opening_with_text() -> None:
    """Two identical bare wrappers must not be confused (elements compare by value), and a block that opens
    with loose text holds no author element: the entry gets no authors rather than a later title (TASK-124)."""
    twin = '<span><b><a href="http://arxiv.org/abs/1312.6055">Twin Title</a></b></span>'
    page = f"""<div>{twin}<div><i>Twin One</i></div>{twin}<div><i>Twin Two</i></div></div>
    <span><b><a href="http://arxiv.org/abs/1312.6086">Loose Title</a></b></span>
    <div>Plain One, Plain Two<i>Later Title</i></div>"""
    iclr = source()
    parsed = iclr.parse_index(2014, page, iclr.LISTINGS[2014])
    assert [(e.title, e.authors) for e in parsed] == [("Twin Title", ("Twin One",)), ("Loose Title", ())]


def test_a_nonempty_trimmed_archive_page_reports_the_verified_count_mismatch(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seed_year(tmp_path, 2014)
    with caplog.at_level(logging.WARNING, logger="openproceedings.ingest.sources.iclr"):
        [report] = mine(tmp_path, 2014).reports
    assert (report.stated, report.listed, report.count_ok) == (35, 2, False)
    assert [record.getMessage() for record in caplog.records] == ["listing_count_mismatch"]


def test_archive_entries_are_accepted_main_records_with_stable_target_ids(tmp_path: Path) -> None:
    expected = {
        2014: "op:iclr:2014:iclr-beb53fd8b4fa307df929907eb35e1a7b",
        2015: "op:iclr:2015:iclr-77b79d4a8d13c419bf89c1bf9c2a109d",
        2016: "op:iclr:2016:iclr-960e1350bda0ad8be2b614ed7faf6ac4",
    }
    for year, wanted in expected.items():
        seed_year(tmp_path, year)
        result = mine(tmp_path, year)
        records = by_id(result.records)
        assert wanted in records
        record = records[wanted]
        assert (record.venue, record.year, record.track, record.status, record.abstract) == (
            "ICLR",
            year,
            "main",
            "accepted",
            None,
        )
        assert record.urls.proceedings == record.claims("urls.proceedings")[0].value
        assert {claim.source for claim in record.provenance} == {"iclr_archive"}
        assert dedup([record]).records == (record,)  # the target URL is identity evidence for its native id
        [report] = result.reports
        assert (report.role, report.records, report.abstract_missing) == (
            "primary",
            len(result.records),
            len(result.records),
        )


def test_the_archive_crawl_marks_each_year_and_replays_offline(tmp_path: Path) -> None:
    crawl = importlib.import_module("openproceedings.ingest.sources.crawl")
    for year in FIXTURES:
        seed_year(tmp_path, year)
    out = crawl.ingest_iclr(FIXTURES, tmp_path, offline=True)
    assert out["requests"] == 0
    assert [listing["year"] for listing in out["listings"]] == [2014, 2015, 2016]
    assert sorted(path.name for path in (tmp_path / "iclr" / "crawls").glob("*.json")) == [
        "2014.json",
        "2015.json",
        "2016.json",
    ]
    records, sources = crawl.load_crawls(tmp_path)
    assert len(records) == 10
    assert len(sources["iclr_archive"]["listings"]) == 3


def test_an_index_page_past_the_html_budget_names_its_url_and_how_to_recover(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """TASK-116: the listing's URL, `--refresh` and its cache entry; the CLI refuses with that line."""
    iclr = source()
    data = tmp_path / "data"
    listing = canonical(iclr.LISTINGS[2016])
    seed(data / "cache", "iclr", listing, "<html>" + "<div>" * (MAX_DEPTH + 1) + "</html>")
    crawler, _ = fetcher(data / "cache" / "iclr", None, iclr.HOSTS)
    with pytest.raises(HTMLBudgetError) as refused:
        iclr.mine_year(2016, crawler)
    entry = crawler.cache.path(listing).relative_to(crawler.cache.root)
    message = str(refused.value)
    assert message.startswith(f"{listing}: HTML nesting exceeds {MAX_DEPTH} elements")
    assert "--refresh" in message and f"({entry} under the source's cache directory)" in message
    assert (refused.value.url, refused.value.reason) == (listing, "html_budget")

    code = cli.main(["--data-dir", str(data), "ingest", "iclr", "--year", "2016", "--offline"])
    err = capsys.readouterr().err
    assert code == 1 and f"op ingest iclr: {listing}: HTML nesting exceeds" in err
    [line] = [e for e in map(json.loads, (x for x in err.splitlines() if x.startswith("{")))
              if e.get("event") == "cli_refused"]  # fmt: skip
    assert (line["level"], line["reason"], line["error"]) == ("WARNING", "html_budget", "HTMLBudgetError")


def test_the_reports_first_fetch_is_the_index_page(tmp_path: Path) -> None:
    """`ListingReport.fetched[0]` is the archive page's read (reconcile dates its absence claims by it); the
    archive has no paper pages, so it is the only fetch."""
    seed_year(tmp_path, 2014)
    [report] = mine(tmp_path, 2014).reports
    assert report.fetched == [T0]


def test_a_listed_title_with_a_control_character_keeps_its_paper() -> None:
    """decision-036 (TASK-180 review): the control character becomes a space and the claim says so; before, the
    record was refused and the listing lost a paper."""
    iclr = source()
    entry = iclr.Entry("https://arxiv.org/abs/1412.6623", "iclr-77b79d4a8d13c419bf89c1bf9c2a109d",
                       "Induc\x02tive Trust", ("Actual One",), None)  # fmt: skip
    record = iclr._record(2015, iclr.LISTINGS[2015], T0, entry)
    assert record.title == "Induc tive Trust"
    [title] = record.claims("title")
    assert title.evidence is not None and title.evidence.endswith("(1 control character replaced by a space)")
