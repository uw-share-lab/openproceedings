"""Abstracts for ICML 1988-2012 from the official ICML pages (TASK-206, decision-047): each page's parser, the
table, reading a year through the page cache, and attaching abstracts to dblp's records by exact title key only.

Each page below is a synthetic excerpt in that page's real markup, as the survey recorded it
(`docs/research/2026-10-06-icml-pre-2013-abstract-sources.md`; decision-004: structure and paper numbers real,
titles and abstracts synthetic). No network: pages are seeded into a page cache.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings.ingest.sources import dblp, icml_sites
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.sources.icml_sites import Entry, SitePage

from tests.unit.ingest.proceedings_helpers import fetcher, seed
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
