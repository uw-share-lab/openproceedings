"""Abstracts for ICML 1988-2012 from the official ICML pages (TASK-206, decision-047): each page's parser, the
table, reading a year through the page cache, and attaching abstracts to dblp's records by exact title key only.

Each page below is a synthetic excerpt in that page's real markup, as the survey recorded it
(`docs/research/2026-10-06-icml-pre-2013-abstract-sources.md`; decision-004: structure and paper numbers real,
titles and abstracts synthetic). No network: pages are seeded into a page cache.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings.ingest.sources import dblp, icml_sites
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.sources.dblp_xml import DblpEntry
from openproceedings.ingest.sources.html import HTMLBudgetError
from openproceedings.ingest.sources.http import Fetcher, Response
from openproceedings.ingest.sources.icml_sites import Entry, SitePage

from tests.unit.ingest.proceedings_helpers import FakeTransport, fetcher, seed
from tests.unit.ingest.test_dblp import TABLE, prepared

ABSTRACT = "Synthetic abstract sentence one about learning. Sentence two about data."
P2012 = """<p>intro</p>
<div class="paper" id="paper-943">
  <h2>Synthetic Title  One</h2>
  <p class="authors">Synthetic Author 1
  <p class="type">&ndash; Invited applications paper
  <p class="abstract"><strong>Abstract: </strong>Synthetic abstract one.
<p><a href="943.pdf.html">ICML version (pdf)</a>
</div>
<div class="paper" id="paper-12">
  <h2>Synthetic Title Two</h2>
  <p class="authors">Synthetic Author 2
  <p class="type">&ndash; Not for proceedings
  <p class="abstract"><strong>Abstract: </strong>Synthetic abstract two.
</div>
"""
P2011 = """<a name='6'><h3 style='margin-top:6ex;'>Synthetic Title One </h3>
<span class='name'>Synthetic Author 1</span>
<p style='width:66em;'><span style='font-weight:bold;'>Abstract:</span>Synthetic abstract one. </p>
<p>[<a href='papers/6_icmlpaper.pdf'>download</a>]</p>
<a name="cross"></a>
<h2>Invited Cross-Conference Track</h2>
<a name='X1'><h3 style='margin-top:6ex;'>Another venue's paper</h3>
"""
P2010 = """<a name="901"></a>
<p>Paper ID: 901</p>
<h3>Synthetic Title One</h3>
<p><em>Synthetic Author 1 (Somewhere)</em></p>
<p class="abstracts">Synthetic abstract<br /> one, Na&iuml;ve.</p>
<p class="discussion">[<a href="papers/901.pdf">Full Paper</a>]</p>
"""
P2009 = """<h3><a name="10"></a>For Participants</h3><ul><li>Registration</li></ul>
<h3><a name="10"></a>Synthetic Title One</h3>
   <p><i>Synthetic Author 1</i></p>
  <p>paper ID: 10 </p>
    <p>Synthetic abstract with $L_2$ one.</p>
         [<a href="papers/10.pdf">Full paper</a>]
<hr/>
"""
P2008 = """<a name="113"></a>
<p>paper ID: 113</p>
<h3>Synthetic Title One</h3>
<p><i> Synthetic Author 1</i><br></p>
<p>Synthetic abstract
one.</p>
<p>[<a href="papers/113.pdf">Full paper</a>]</p><hr>
"""
CYBERCHAIR = """<a name="88">
<table border cellspacing=1 cellpadding=5><tr><th>Synthetic Title One</th></tr><tr><td>Synthetic Author 1 - <i>Somewhere</i><br></td></tr><tr><td><pre>Synthetic abstract
one.
</pre></td></tr></table>
<table border cellspacing=1 cellpadding=5><tr><th>Synthetic Title Two</th></tr><tr><td>Synthetic Author 2<br></td></tr><tr><td>Synthetic abstract two.</td></tr></table>
"""
LIST2007 = """<tr class="header"><td colspan="2">
 <a name="105"> Synthetic Title One</a>
 </td></tr><td><td colspan="2"><a href="abstracts/105.htm">[Abstract]</a></td></tr>
<tr class="header"><td colspan="2">
 <a name="242"> Synthetic Title Two</a>
 </td></tr>
"""
PAPER2007 = """<html><head><title>Synthetic Ti tle One</title></head><body><table border cellspacing=1 cellpadding=5><tr><th>
Synthetic Ti tle One
</th></tr><tr><td>
Synthetic Author 1 - Somewhere <br>
</td></tr><tr><td>
Synthetic abstract one.
</td></tr></table></body></html>"""
CAPTURE = "https://web.archive.org/web/20071116064757id_/http://oregonstate.edu:80/conferences/icml2007/abstracts/105.htm"


@pytest.mark.parametrize(
    ("parser", "page", "expected"),
    [
        ("icml2012", P2012, [Entry("943", "Synthetic Title One", "Synthetic abstract one.")]),  # not-for-proceedings out
        ("icml2011", P2011, [Entry("6", "Synthetic Title One", "Synthetic abstract one.")]),  # cross-conference out
        ("icml2010", P2010, [Entry("901", "Synthetic Title One", "Synthetic abstract one, Naïve.")]),
        ("icml2009", P2009, [Entry("10", "Synthetic Title One", "Synthetic abstract with $L_2$ one.")]),  # sidebar out
        ("icml2008", P2008, [Entry("113", "Synthetic Title One", "Synthetic abstract one.")]),
        ("cyberchair", CYBERCHAIR, [Entry(None, "Synthetic Title One", "Synthetic abstract one."),
                                    Entry(None, "Synthetic Title Two", "Synthetic abstract two.")]),
        ("icml2007_list", LIST2007, [Entry("105", "Synthetic Title One", None), Entry("242", "Synthetic Title Two", None)]),
    ],
)  # fmt: skip
def test_each_parser_reads_its_pages_markup(parser: str, page: str, expected: list[Entry]) -> None:
    assert icml_sites.PARSERS[parser](page, "https://icml.cc/x") == expected


def test_a_2007_paper_page_gives_its_number_and_abstract_never_its_broken_title() -> None:
    assert icml_sites.icml2007_paper(PAPER2007, CAPTURE) == [Entry("105", None, "Synthetic abstract one.")]


# --- the table ------------------------------------------------------------------------------------------------------


def test_the_shipped_table_names_official_pages_only() -> None:
    assert set(icml_sites.PAGES) == {2001, 2003, 2004, 2007, 2008, 2009, 2010, 2011, 2012}
    assert {"icml.cc", "web.archive.org"} == icml_sites.HOSTS
    for pages in icml_sites.PAGES.values():
        for p in pages:
            assert p.capture is not None or p.url.startswith("https://icml.cc/")
    assert len(icml_sites.PAGES[2007]) == 151  # the list and its 150 per-paper captures


def row(**over: object) -> str:
    fields = {"year": 2009, "url": '"https://icml.cc/Conferences/2009/abstracts.html"',
              "official": '"https://icml.cc/Conferences/2009/abstracts.html"', "parser": '"icml2009"',
              "charset": '"utf-8"', "entries": 1, "verified": "2026-10-06", "note": '"x"'} | over  # fmt: skip
    return "[[page]]\n" + "".join(f"{k} = {v}\n" for k, v in fields.items())


@pytest.mark.parametrize(
    ("over", "why"),
    [
        ({"url": '"https://dl.acm.org/doi/x"', "official": '"https://dl.acm.org/doi/x"'}, "icml.cc page"),
        ({"url": '"https://web.archive.org/web/2009/https://icml.cc/x"'}, "pins one capture"),
        ({"url": '"https://web.archive.org/web/20090101000000id_/https://icml.cc/y"'}, "of the official URL"),
        ({"parser": '"guess"'}, "no parser"),
        ({"year": 2013}, "1988 to 2012"),
        ({"charset": '"latin-1"'}, "charset"),
        # a capture of a site that isn't an official ICML one, however well pinned
        ({"url": '"https://web.archive.org/web/20090101000000id_/https://dl.acm.org/doi/x"',
          "official": '"https://dl.acm.org/doi/x"'}, "not an official ICML site"),
        ({"url": '"https://web.archive.org/web/20090101000000id_/https://arxiv.org/abs/x"',
          "official": '"https://arxiv.org/abs/x"'}, "not an official ICML site"),
        ({"url": '"https://web.archive.org/web/20091399000000id_/https://icml.cc/x"',
          "official": '"https://icml.cc/x"'}, "not a date"),
        ({"url": '"https://web.archive.org/web/20270101000000id_/https://icml.cc/x"',
          "official": '"https://icml.cc/x"'}, "after the row was verified"),
        ({"verified": "2026-10-06T00:00:00"}, "verified a date"),
    ],
)  # fmt: skip
def test_a_row_off_the_rules_is_refused(over: dict[str, object], why: str) -> None:
    with pytest.raises(ValueError, match=why):
        icml_sites.load(row(**over))


# --- a year, and attaching its abstracts ------------------------------------------------------------------------------

T = datetime(2026, 10, 6, 12, tzinfo=UTC)


def pages_1990(*parts: tuple[str, str, str, int]) -> dict[int, tuple[SitePage, ...]]:
    return {
        1990: tuple(
            SitePage(1990, url, url, parser, "utf-8", n, T.date(), "test") for url, parser, _, n in parts
        )
    }


def test_a_year_is_read_through_the_cache_and_a_changed_page_stops_it(tmp_path: Path) -> None:
    url = "https://icml.cc/Conferences/1990/abstracts.html"
    seed(tmp_path, "icml_sites", url, CYBERCHAIR, at=T)
    f, _ = fetcher(tmp_path / "icml_sites", None, frozenset({"icml.cc"}))
    site = icml_sites.read_year(1990, f, pages=pages_1990((url, "cyberchair", "", 2)))
    assert site is not None and site.pages == [url] and site.fetched == [T]
    assert [(e.title, e.abstract, e.url) for e in site.entries] == [
        ("Synthetic Title One", "Synthetic abstract one.", url), ("Synthetic Title Two", "Synthetic abstract two.", url),
    ]  # fmt: skip
    assert site.entries[0].evidence == f"official ICML 1990 page {url}"
    assert icml_sites.read_year(1991, f, pages=pages_1990((url, "cyberchair", "", 2))) is None
    with pytest.raises(CrawlError, match="gives 2 entries, the table verified 3") as e:
        icml_sites.read_year(1990, f, pages=pages_1990((url, "cyberchair", "", 3)))
    assert e.value.reason == "site_count_mismatch"


def test_a_years_pages_log_a_start_progress_and_end_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """2007's 151 pages take over 7 minutes at 3 s apart: a start line, a progress line whenever the heartbeat on
    the fetcher's clock is due, and the end line with the counts (never page text)."""
    import logging

    class Ticking:  # every read of the monotonic clock is 31 s on: each progress check is due
        t = 0.0

        def monotonic(self) -> float:
            self.t += 31
            return self.t

        def sleep(self, seconds: float) -> None:
            pass

        def now(self) -> datetime:
            return T

    listing = "https://icml.cc/Conferences/2007/paperlist.html"
    seed(tmp_path, "icml_sites", listing, LIST2007, at=T)
    seed(tmp_path, "icml_sites", CAPTURE, PAPER2007, at=T)
    f, _ = fetcher(tmp_path / "icml_sites", None, frozenset({"icml.cc", "web.archive.org"}))
    f.clock = Ticking()
    pages = {2007: (SitePage(2007, listing, listing, "icml2007_list", "utf-8", 2, T.date(), "t"),
                    SitePage(2007, CAPTURE, CAPTURE.split("id_/", 1)[1], "icml2007_paper", "utf-8", 1, T.date(), "t"))}  # fmt: skip
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.sources.icml_sites"):
        icml_sites.read_year(2007, f, pages=pages)
    lines = {r.getMessage(): r for r in caplog.records}
    assert list(lines) == ["icml_site_year_started", "icml_site_year_progress", "icml_site_year_read"]
    read = lines["icml_site_year_read"]
    assert (read.pages, read.entries, read.unjoined, read.dropped) == (2, 1, 1, 0)  # type: ignore[attr-defined]
    assert "Synthetic" not in caplog.text


def test_2007s_halves_are_joined_by_paper_number_and_the_rest_counted(tmp_path: Path) -> None:
    listing = "https://icml.cc/Conferences/2007/paperlist.html"
    seed(tmp_path, "icml_sites", listing, LIST2007, at=T)
    seed(tmp_path, "icml_sites", CAPTURE, PAPER2007, at=T)
    f, _ = fetcher(tmp_path / "icml_sites", None, frozenset({"icml.cc", "web.archive.org"}))
    pages = {2007: (SitePage(2007, listing, listing, "icml2007_list", "utf-8", 2, T.date(), "t"),
                    SitePage(2007, CAPTURE, CAPTURE.split("id_/", 1)[1], "icml2007_paper", "utf-8", 1, T.date(), "t"))}  # fmt: skip
    site = icml_sites.read_year(2007, f, pages=pages)
    assert site is not None
    [entry] = site.entries
    assert (entry.title, entry.abstract, entry.url) == (
        "Synthetic Title One",
        "Synthetic abstract one.",
        CAPTURE,
    )
    assert "Internet Archive capture 20071116064757" in entry.evidence
    assert site.unjoined == 1  # paper 242 has a title and no abstract page
    # an abstract page whose number the list doesn't hold is the other kind of half
    orphan = CAPTURE.replace("/105.htm", "/999.htm")
    seed(tmp_path, "icml_sites", orphan, PAPER2007, at=T)
    more = {2007: (*pages[2007],
                   SitePage(2007, orphan, orphan.split("id_/", 1)[1], "icml2007_paper", "utf-8", 1, T.date(), "t"))}  # fmt: skip
    again = icml_sites.read_year(2007, f, pages=more)
    assert again is not None and (len(again.entries), again.unjoined) == (1, 2)


def site_year(*entries: tuple[str, str]) -> icml_sites.SiteYear:
    url = "https://icml.cc/Conferences/1990/abstracts.html"
    return icml_sites.SiteYear([url], [icml_sites.SiteAbstract(t, a, 0, url, T, f"official ICML 1990 page {url}")
                                       for t, a in entries], [T])  # fmt: skip


def test_an_abstract_attaches_only_by_an_exact_title_key_one_to_one(tmp_path: Path) -> None:
    extract = prepared(tmp_path)  # 1990's one paper: "Synthetic title with markup 1"
    hit = dblp.mine_year(1990, extract, table=TABLE,
                         site=site_year(("SYNTHETIC title with Markup 1", ABSTRACT), ("Unrelated", "Other.")))  # fmt: skip
    [r] = hit.records
    assert r.abstract == ABSTRACT
    [claim] = r.claims("abstract")
    assert (claim.source, claim.url, claim.fetched_at) == (
        "icml_site",
        "https://icml.cc/Conferences/1990/abstracts.html",
        T,
    )
    assert "dblp record conf/icml/Synthetic90" in (claim.evidence or "")
    [report] = hit.reports
    assert (
        report.abstract_attached,
        report.abstract_missing,
        report.site_entries,
        report.site_unmatched,
    ) == (1, 0, 2, 1)
    manifest = report.to_manifest()
    assert (
        manifest["sites"] == ["https://icml.cc/Conferences/1990/abstracts.html"]
        and manifest["abstract_attached"] == 1
    )
    # a near title (one word off, or a prefix) is no match: never fuzzy
    near = dblp.mine_year(
        1990, extract, table=TABLE, site=site_year(("Synthetic title with markup", ABSTRACT))
    )
    assert near.records[0].abstract is None and near.reports[0].site_unmatched == 1
    # two page entries with the paper's key: neither is used
    two = dblp.mine_year(1990, extract, table=TABLE, site=site_year(("Synthetic title with markup 1", ABSTRACT),
                                                                     ("Synthetic Title With Markup 1", "Other text.")))  # fmt: skip
    assert two.records[0].abstract is None and two.reports[0].site_ambiguous == 2
    assert two.reports[0].abstract_missing == 1
    # no pages for the year: the report says nothing about sites
    assert "sites" not in dblp.mine_year(1990, extract, table=TABLE).reports[0].to_manifest()


def one_page(
    tmp_path: Path, text: str, *, charset: str = "utf-8", status: int = 200
) -> tuple[Fetcher, dict[int, tuple[SitePage, ...]]]:
    url = "https://icml.cc/Conferences/1990/abstracts.html"
    seed(tmp_path, "icml_sites", url, text, status=status, at=T)
    f, _ = fetcher(tmp_path / "icml_sites", None, frozenset({"icml.cc"}))
    return f, {1990: (SitePage(1990, url, url, "cyberchair", charset, 2, T.date(), "t"),)}


def test_a_page_gone_or_misread_stops_the_crawl(tmp_path: Path) -> None:
    f, pages = one_page(tmp_path, "", status=404)
    with pytest.raises(CrawlError, match="answered HTTP 404") as e:
        icml_sites.read_year(1990, f, pages=pages)
    assert e.value.reason == "no_listing"
    # UTF-8 bytes decoded as cp1252 (`â€™` for `’`): the row's charset is wrong, never a garbled abstract
    f, pages = one_page(tmp_path, CYBERCHAIR.replace("one.", "Shannonâ€™s one."), charset="cp1252")
    with pytest.raises(CrawlError, match="charset is wrong") as e:
        icml_sites.read_year(1990, f, pages=pages)
    assert e.value.reason == "wrong_charset"
    f, pages = one_page(tmp_path, CYBERCHAIR.replace("one.", "Renée’s one."), charset="cp1252")
    assert icml_sites.read_year(1990, f, pages=pages) is not None  # real cp1252 text is not UTF-8


def test_an_entry_left_without_an_abstract_is_counted_as_dropped(tmp_path: Path) -> None:
    f, pages = one_page(tmp_path, CYBERCHAIR.replace("Synthetic abstract two.", " "))
    site = icml_sites.read_year(1990, f, pages=pages)
    assert site is not None and (len(site.entries), site.dropped) == (1, 1)
    hit = dblp.mine_year(1990, prepared(tmp_path / "x"), table=TABLE, site=site)
    assert hit.reports[0].to_manifest()["site_dropped"] == 1


def test_a_paper_number_listed_twice_stops_the_crawl(tmp_path: Path) -> None:
    listing = "https://icml.cc/Conferences/2007/paperlist.html"
    seed(tmp_path, "icml_sites", listing, LIST2007.replace('name="242"', 'name="105"'), at=T)
    f, _ = fetcher(tmp_path / "icml_sites", None, frozenset({"icml.cc"}))
    pages = {2007: (SitePage(2007, listing, listing, "icml2007_list", "utf-8", 2, T.date(), "t"),)}
    with pytest.raises(CrawlError, match="listed twice") as e:
        icml_sites.read_year(2007, f, pages=pages)
    assert e.value.reason == "duplicate_paper"


def test_a_title_key_two_dblp_papers_share_attaches_nothing(tmp_path: Path) -> None:
    extract = prepared(tmp_path)
    [paper] = [e for e in extract.entries if e.key == "conf/icml/Synthetic90"]
    twin = DblpEntry(
        paper.type, "conf/icml/Synthetic90b", paper.mdate, None, dict(paper.fields), dict(paper.lists)
    )
    doubled = dblp.Extract(extract.doi, extract.sha256, extract.fetched_at, (*extract.entries, twin))
    result = dblp.mine_year(
        1990, doubled, table=TABLE, site=site_year(("Synthetic title with markup 1", ABSTRACT))
    )
    assert [r.abstract for r in result.records] == [None, None]
    assert result.reports[0].site_ambiguous == 1


def test_an_ascii_page_is_never_taken_for_utf8_and_the_rows_charset_reaches_the_decoder(
    tmp_path: Path,
) -> None:
    f, pages = one_page(tmp_path, CYBERCHAIR, charset="cp1252")  # ASCII is valid UTF-8 too: no refusal
    site = icml_sites.read_year(1990, f, pages=pages)
    assert site is not None and len(site.entries) == 2
    # through a transport: bare `text/html` cp1252 bytes decode with the row's charset
    url = "https://icml.cc/Conferences/1990/abstracts.html"
    body = (CYBERCHAIR.replace("one.", "Naïve “one”.") + "</html>").encode("cp1252")
    live, _ = fetcher(tmp_path / "live", FakeTransport({url: Response(200, {"content-type": "text/html"}, body)}),
                      frozenset({"icml.cc"}), min_interval=0)  # fmt: skip
    read = icml_sites.read_year(1990, live, pages=pages)
    assert read is not None and read.entries[0].abstract == "Synthetic abstract Naïve “one”."
    # UTF-8 bytes a cp1252 row can't decode at all (`Á` is C3 81): the row's charset is named as the cause
    bad = (CYBERCHAIR.replace("one.", "Á one.") + "</html>").encode("utf-8")
    worse, _ = fetcher(tmp_path / "bad", FakeTransport({url: Response(200, {"content-type": "text/html"}, bad)}),
                       frozenset({"icml.cc"}), min_interval=0)  # fmt: skip
    with pytest.raises(CrawlError, match="charset is wrong") as e:
        icml_sites.read_year(1990, worse, pages=pages)
    assert e.value.reason == "wrong_charset"


def test_a_page_listed_twice_or_a_capture_off_the_official_sites_path_is_refused() -> None:
    with pytest.raises(ValueError, match="listed twice"):
        icml_sites.load(row() + row())
    assert not icml_sites.is_official("http://www.ecn.purdue.edu:80/ICML2001/../admissions/x.html")
    off_path = '"https://web.archive.org/web/20070101000000id_/http://oregonstate.edu:80/admissions/x.html"'
    with pytest.raises(ValueError, match="not an official ICML site"):
        icml_sites.load(row(url=off_path, official='"http://oregonstate.edu:80/admissions/x.html"'))
    on_path = '"https://web.archive.org/web/20070101000000id_/http://oregonstate.edu:80/conferences/icml2007/a/1.htm"'
    assert icml_sites.load(
        row(url=on_path, official='"http://oregonstate.edu:80/conferences/icml2007/a/1.htm"')
    )


HOSTILE = {  # the review gate's probes: openings whose closing tag never comes, about 0.3 MB each
    "cyberchair": "<table>" + "<th>x</th><td>" * 20_000,
    "icml2007_paper": "<table>" * 1_000 + "<th>x</th><td>y</td>" * 20_000,  # deep nesting, then many cells
    "icml2007_list": '<a name="1">' * 20_000 + "</a>",  # one far closing tag after every opening
    "icml2008": '<a name="1"></a>' + "<h3>" * 20_000 + "<p><i>a</p>" * 10_000,
    # the old 2009 patterns were bounded already; the row keeps a future rewrite honest
    "icml2009": '<h3><a name="1"></a>paper ID: 1</p>' + "x" * 300_000,
    "icml2010": '<a name="1"></a>' + "<h3>" * 20_000 + '<p class="abstracts">' * 20_000,
    "icml2011": "<a name='1'><h3>t</h3>" + "Abstract: </span>" * 20_000,
    "icml2012": '<div class="paper" id="paper-1">' + "<h2>" * 20_000 + "<strong>Abstract: </strong>" * 5_000,
}


@pytest.mark.parametrize("parser", sorted(HOSTILE))
def test_a_hostile_page_is_parsed_in_linear_time(parser: str) -> None:
    """Unclosed tags made a backtracking pattern take 87 s at 5.6 KB, and lazy `(.*?)` openings tens of seconds
    at 0.4 MB. Every parser reads such a page at once."""
    import time

    assert sorted(HOSTILE) == sorted(icml_sites.PARSERS)
    hostile = HOSTILE[parser]
    started = time.monotonic()
    with contextlib.suppress(HTMLBudgetError):  # the shared tree's nesting bound: a refusal, fine, and fast
        icml_sites.PARSERS[parser](hostile, CAPTURE)
    assert time.monotonic() - started < 2.0


@pytest.mark.parametrize("parser", ["icml2008", "icml2009", "icml2010", "icml2011", "icml2012"])
def test_a_page_that_lost_its_papers_gives_none_and_stops_the_crawl(tmp_path: Path, parser: str) -> None:
    moved = "<html><body>This page has moved.</body></html>"
    assert icml_sites.PARSERS[parser](moved, "https://icml.cc/x") == []
    url = "https://icml.cc/Conferences/1990/abstracts.html"
    seed(tmp_path, "icml_sites", url, moved, at=T)
    f, _ = fetcher(tmp_path / "icml_sites", None, frozenset({"icml.cc"}))
    pages = {1990: (SitePage(1990, url, url, parser, "utf-8", 1, T.date(), "t"),)}
    with pytest.raises(CrawlError, match="gives 0 entries") as e:
        icml_sites.read_year(1990, f, pages=pages)
    assert e.value.reason == "site_count_mismatch"


def test_a_span_cuts_at_the_right_place_whatever_the_text_and_never_at_pre() -> None:
    """`str.lower()` can lengthen a string (U+0130 lowers to two code points), so ends are searched in the text
    itself; `<p\\b` ends a paragraph, `<pre>` doesn't."""
    assert icml_sites._span("\u0130\u0130\u0130<h3>Title</h3>rest", r"<h3>", r"</h3>") == "Title"
    assert icml_sites._span("<h3>\u0130\u0130 Title</h3>", r"<h3>", r"</h3>") == "\u0130\u0130 Title"
    page = '<div class="paper" id="paper-1"><h2>T</h2><p class="type">Accepted<p class="abstract">' \
           "<strong>Abstract: </strong>a <pre>b</pre> c<p>links</div>"  # fmt: skip
    assert icml_sites.icml2012(page, "https://icml.cc/2012/papers/") == [Entry("1", "T", "a b c")]


def test_a_table_inside_a_paper_table_is_nobodys_and_its_cells_stay_out() -> None:
    page = ("<table><tr><th>Title</th></tr><tr><td>Authors</td></tr><tr><td>Abstract "
            "<table><tr><th>inner</th><td>a</td><td>b</td></tr></table> text.</td></tr></table>")  # fmt: skip
    assert icml_sites.cyberchair(page, "https://icml.cc/x") == [
        Entry(None, "Title", "Abstract inner a b text.")
    ]
