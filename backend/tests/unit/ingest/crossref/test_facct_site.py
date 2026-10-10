# backend/tests/unit/ingest/crossref/test_facct_site.py
from pathlib import Path

import pytest
from openproceedings.ingest import acm_table
from openproceedings.ingest.dedup import attribution
from openproceedings.ingest.sources import crawl, crossref, facct_site
from openproceedings.ingest.sources.common import CrawlError

from tests.unit.ingest.crossref import api
from tests.unit.ingest.crossref.test_crossref_mine import D1, D2, NP, TABLE, _offline, _whole
from tests.unit.ingest.crossref.test_crossref_parse import T
from tests.unit.ingest.proceedings_helpers import FakeTransport, fetcher, response, seed

URL26 = "https://facctconference.org/static/docs/facct2026-final.csv"
URL25 = "https://facctconference.org/static/docs/facct2025-final.csv"
URL22 = "https://facctconference.org/2022/acceptedpapers.html"
SITE_TABLE = f"""
[[page]]
year = 2023
url = "{URL26}"
parser = "facct2026_csv"
join = "title"
rows = 3
verified = 2026-10-10
note = "test"
"""


def csv26(*rows: tuple[str, str, str], bom: bool = False, eol: str = "\n") -> str:
    """The 2026 CSV's shape. The real file has no byte-order mark and `\\n` line ends (the defaults); `bom` and
    `eol` give the other forms a CSV export may take."""
    lines = ["Paper ID,Title,Authors,Abstract"] + [f'{i},"{t}","Synthetic Author","{a}"' for i, t, a in rows]
    return ("\ufeff" if bom else "") + eol.join(lines) + eol


def site(tmp_path: Path, text: str, table: str = SITE_TABLE) -> facct_site.SiteYear:
    seed(tmp_path, "facct_site", URL26, text)
    f, _ = fetcher(tmp_path / "facct_site", None, facct_site.HOSTS, expect="text")
    got = facct_site.read_year(2023, f, table=facct_site.load(table))
    assert got is not None
    return got


@pytest.fixture(autouse=True)
def _acm(monkeypatch):
    monkeypatch.setattr(acm_table, "TABLE", TABLE)


def test_a_title_join_attaches_the_official_abstract_credited_to_the_doi_link(tmp_path: Path) -> None:
    _whole(
        tmp_path,
        api.work(D1, title="Fair Ranking, Revisited"),
        api.work(D2, title="Other"),
        api.work(NP),
        total=3,
    )
    s = site(tmp_path, csv26(("1", "fair ranking revisited", "Official abstract one."),
                             ("2", "A non-archival talk", "Abstract two."), ("3", "", "No title here.")))  # fmt: skip
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE, site=s)
    r = next(x for x in result.records if x.urls.doi == D1)
    assert r.abstract == "Official abstract one."
    (claim,) = r.claims("abstract")
    assert (claim.source, claim.url) == ("facct_site", URL26) and "title key" in (claim.evidence or "")
    assert "row 1" in (claim.evidence or "")
    att = attribution(r.abstract, r.provenance, forum=None, proceedings=r.urls.proceedings, native=r.native)
    assert att is not None and att.url == f"https://doi.org/{D1}"  # never the CSV
    report = result.reports[0]
    assert (report.site_entries, report.abstract_attached, report.site_unmatched, report.site_ambiguous,
            report.site_dropped) == (2, 1, 1, 0, 1)  # fmt: skip
    assert next(x for x in result.records if x.urls.doi == D2).abstract is None
    manifest = report.to_manifest()
    assert manifest["sites"] == [URL26] and manifest["abstract_attached"] == 1
    assert manifest["abstract_missing"] == 1


def test_a_report_with_no_site_lists_no_site_fields(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1), api.work(D2), api.work(NP), total=3)
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert (
        "sites" not in result.reports[0].to_manifest()
        and "site_entries" not in result.reports[0].to_manifest()
    )


def test_two_rows_sharing_a_title_key_attach_nothing(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1, title="Fair Ranking"), api.work(D2, title="Other"), api.work(NP), total=3)
    s = site(tmp_path, csv26(("1", "Fair Ranking", "A."), ("2", "FAIR ranking!", "B."), ("3", "Other", "C.")))
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE, site=s)
    assert next(x for x in result.records if x.urls.doi == D1).abstract is None
    assert next(x for x in result.records if x.urls.doi == D2).abstract == "C."
    assert (result.reports[0].site_ambiguous, result.reports[0].abstract_attached) == (2, 1)


def test_two_records_sharing_a_title_key_attach_nothing(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1, title="Same"), api.work(D2, title="same."), api.work(NP), total=3)
    s = site(tmp_path, csv26(("1", "Same", "A."), ("2", "x", "B."), ("3", "y", "C.")))
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE, site=s)
    assert all(r.abstract is None for r in result.records) and result.reports[0].site_ambiguous == 1


def test_a_row_dropped_for_no_abstract_still_makes_a_shared_title_key_ambiguous(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1, title="Fair Ranking"), api.work(D2, title="Other"), api.work(NP), total=3)
    s = site(tmp_path, csv26(("1", "Fair Ranking", "A."), ("2", "FAIR ranking!", ""), ("3", "Other", "C.")))
    assert s.dropped == 1 and len(s.entries) == 2
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE, site=s)
    assert next(x for x in result.records if x.urls.doi == D1).abstract is None
    assert next(x for x in result.records if x.urls.doi == D2).abstract == "C."
    assert (result.reports[0].site_ambiguous, result.reports[0].abstract_attached) == (1, 1)


def test_a_row_dropped_for_no_abstract_still_makes_a_shared_doi_ambiguous() -> None:
    entries = [facct_site.SiteAbstract("1", "Fair", D1, "A.", 0, 0, URL25, T, "e"),
               facct_site.SiteAbstract("2", "x", D2, "B.", 0, 0, URL25, T, "e")]  # fmt: skip
    s = facct_site.SiteYear(URL25, "doi", entries, [T], 1, (), (D1.lower(),))
    got = facct_site.match([(D1, "Fair"), (D2, "x")], s)
    assert set(got.by_doi) == {D2} and (got.unmatched, got.ambiguous) == (0, 1)


def test_the_reader_keeps_a_dropped_rows_doi_for_the_doi_join(tmp_path: Path) -> None:
    table = SITE_TABLE.replace(URL26, URL25).replace("facct2026_csv", "facct2025_csv").replace('"title"', '"doi"')
    text = ("TYPE,ID,ABSTRACT,AUTHOR,TITLE,URL,URL-OLD\n"
            f"archival,7,Official.,Synthetic Author,A title,https://doi.org/{D1},\n"
            f"archival,8,,Synthetic Author,B title,https://doi.org/{D1.upper()},\n"
            f"archival,9,Third.,Synthetic Author,C title,https://doi.org/{D2},\n")  # fmt: skip
    seed(tmp_path, "facct_site", URL25, text)
    f, _ = fetcher(tmp_path / "facct_site", None, facct_site.HOSTS, expect="text")
    s = facct_site.read_year(2023, f, table=facct_site.load(table))
    assert s is not None and (s.dropped, s.dropped_dois) == (1, (D1.lower(),))
    got = facct_site.match([(D1, "A title"), (D2, "C title")], s)
    assert set(got.by_doi) == {D2} and (got.unmatched, got.ambiguous) == (0, 1)


def test_a_near_title_is_never_joined(tmp_path: Path) -> None:
    _whole(
        tmp_path,
        api.work(D1, title="Fair Ranking Revisited"),
        api.work(D2, title="Other"),
        api.work(NP),
        total=3,
    )
    s = site(tmp_path, csv26(("1", "Fair Rankings Revisited", "A."), ("2", "x", "B."), ("3", "y", "C.")))
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE, site=s)
    assert all(r.abstract is None for r in result.records) and result.reports[0].site_unmatched == 3


def test_a_doi_join_never_falls_back_to_the_title() -> None:
    entries = [facct_site.SiteAbstract("1", "Fair", D1, "A.", 0, 0, URL25, T, "e"),
               facct_site.SiteAbstract("2", "Other", None, "B.", 0, 0, URL25, T, "e"),
               facct_site.SiteAbstract("3", "x", D2, "C.", 0, 0, URL25, T, "e"),
               facct_site.SiteAbstract("4", "y", D2, "D.", 0, 0, URL25, T, "e")]  # fmt: skip
    s = facct_site.SiteYear(URL25, "doi", entries, [T], 0)
    got = facct_site.match([(D1, "Fair"), (D2, "Other"), ("10.1145/3715275.9", "Other")], s)
    assert set(got.by_doi) == {D1} and (got.unmatched, got.ambiguous) == (
        1,
        2,
    )  # no DOI → unmatched, never by title


def test_a_doi_join_counts_a_doi_no_paper_has_as_unmatched() -> None:
    entries = [facct_site.SiteAbstract("1", "Fair", D1.upper(), "A.", 0, 0, URL25, T, "e"),
               facct_site.SiteAbstract("2", "Other", "10.1145/3593013.1", "B.", 0, 0, URL25, T, "e")]  # fmt: skip
    got = facct_site.match([(D1, "Fair")], facct_site.SiteYear(URL25, "doi", entries, [T], 0))
    assert set(got.by_doi) == {D1} and (got.unmatched, got.ambiguous) == (1, 0)


def test_a_doi_join_attaches_by_doi_in_the_miner_and_says_so(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1, title="Crossref's wording"), api.work(D2), api.work(NP), total=3)
    entries = [
        facct_site.SiteAbstract("7", "The site's wording", D1, "Official.", 0, 0, URL25, T, f"{URL25} row 7")
    ]
    s = facct_site.SiteYear(URL25, "doi", entries, [T], 0)
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE, site=s)
    r = next(x for x in result.records if x.urls.doi == D1)
    (claim,) = r.claims("abstract")
    assert r.abstract == "Official." and claim.evidence == f"{URL25} row 7; joined to {D1} by DOI"
    assert T in result.reports[0].fetched


@pytest.mark.parametrize(("bom", "eol"), [(False, "\n"), (True, "\r\n"), (True, "\n"), (False, "\r\n")])
def test_the_csv_reads_with_or_without_a_byte_order_mark_and_either_line_end(bom: bool, eol: str) -> None:
    got = facct_site.facct2026_csv(
        csv26(("1", "A, title", "An abstract."), ("2", "B", "Other."), bom=bom, eol=eol)
    )
    assert [(e.key, e.title, e.abstract, e.doi) for e in got] == [
        ("1", "A, title", "An abstract.", None), ("2", "B", "Other.", None)]  # fmt: skip


def test_a_quoted_abstract_keeps_its_line_breaks_as_one_field() -> None:
    (e,) = facct_site.facct2026_csv('Paper ID,Title,Authors,Abstract\n4,T,A,"one\ntwo, ""three"""\n')
    assert e.abstract == 'one\ntwo, "three"'


@pytest.mark.parametrize(
    ("text", "reason"),
    [("a,b\n1,2\n", "site_format"), (csv26(("1", "x", "y")), "site_count"),
     (csv26(("1", "x", "y"), ("1", "z", "w"), ("3", "q", "r")), "site_duplicate_key"),
     ("Paper ID,Title,Authors,Abstract\n1,x,y\n2,a,b,c\n3,a,b,c\n", "site_format"),
     ("Paper ID,Title,Authors,Abstract\n1,x,y,z,extra\n2,a,b,c\n3,a,b,c\n", "site_format")],
)  # fmt: skip
def test_a_page_that_is_not_what_the_table_says_stops(tmp_path: Path, text: str, reason: str) -> None:
    with pytest.raises(CrawlError) as e:
        site(tmp_path, text)
    assert e.value.reason == reason


def test_a_page_that_is_gone_stops(tmp_path: Path) -> None:
    seed(tmp_path, "facct_site", URL26, "", status=404)
    f, _ = fetcher(tmp_path / "facct_site", None, facct_site.HOSTS, expect="text")
    with pytest.raises(CrawlError) as e:
        facct_site.read_year(2023, f, table=facct_site.load(SITE_TABLE))
    assert e.value.reason == "site_missing"


def test_a_year_with_no_page_reads_nothing(tmp_path: Path) -> None:
    f, _ = fetcher(tmp_path / "facct_site", None, facct_site.HOSTS, expect="text")
    assert facct_site.read_year(2024, f, table=facct_site.load(SITE_TABLE)) is None


@pytest.mark.parametrize(
    ("edit", "message"),
    [(lambda s: s.replace('join = "title"', 'join = "fuzzy"'), "join"),
     (lambda s: s.replace('parser = "facct2026_csv"', 'parser = "nope"'), "parser"),
     (lambda s: s.replace("facctconference.org", "example.org"), "facctconference.org"),
     (lambda s: s.replace("https://", "http://"), "facctconference.org"),
     (lambda s: s.replace("rows = 3", "rows = 0"), "positive"),
     (lambda s: s.replace("rows = 3", "rows = true"), "positive"),
     (lambda s: s.replace("year = 2023", "year = 2017"), "FAccT"),
     (lambda s: s.replace('note = "test"', 'note = ""'), "note"),
     (lambda s: s.replace("verified = 2026-10-10", 'verified = "x"'), "date"),
     (lambda s: s.replace('note = "test"', 'note = "test"\nextra = 1'), "columns"),
     (lambda s: s + s, "one page per year")],
)  # fmt: skip
def test_bad_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        facct_site.load(edit(SITE_TABLE))


def test_the_2025_csv_reads_its_doi_from_the_url_column() -> None:
    text = ("TYPE,ID,ABSTRACT,AUTHOR,TITLE,URL,URL-OLD\narchival,7,An abstract.,Synthetic Author,A title,"
            "https://doi.org/10.1145/3715275.3732001,https://facctconference.org/x.pdf\n"
            "nonarchival,8,Other.,Synthetic Author,B title,,\n"
            "nonarchival,9,Third.,Synthetic Author,C title,https://arxiv.org/abs/2501.00001,\n")  # fmt: skip
    (a, b, c) = facct_site.facct2025_csv(text)
    assert (a.key, a.doi, b.doi, c.doi) == ("7", "10.1145/3715275.3732001", None, None)


def test_the_2022_page_reads_each_entry_and_never_its_doi_links() -> None:
    page = """<html><body><div class="container"><div class="page-header"><h1>Accepted</h1></div></div>
<div class="container"><div class="row"><div class="col-lg-12">
    <h4 id="1002"><b>First &amp; Title</b></h4>
    <p><i>Synthetic Author 1 and Synthetic Author 2</i></p> <br>
    <p>An abstract with <i>emphasis</i>.</p>
    <p><span class="label label-primary"><a href="https://doi.org/10.1145/3531146.3533237">Paper</a></span>
      </p>
      <p><span class="label label-primary"><a href="https://www.youtube.com/watch?v=x">Video</a></span></p>
    <h4 id = "17"><b>Second title</b></h4>
    <h5>Co-Winner: Distinguished Paper Award</h5>
    <p><i>Synthetic Author 3</i></p><br>
    <p>Second abstract.</p>
    <p><span class="label label-primary"><a href="https://doi.org/10.1145/3531146.3533072">Paper</a></span></p>
</div></div></div><footer><div class="col-lg-6">CC-BY</div></footer></body></html>"""
    got = facct_site.facct2022_html(page)
    assert [(e.key, e.title, e.abstract, e.doi) for e in got] == [
        ("1002", "First & Title", "An abstract with emphasis.", None), ("17", "Second title", "Second abstract.", None)]  # fmt: skip


@pytest.mark.parametrize(
    "edit",
    [lambda p: p.replace("<p>Second abstract.</p>", ""),
     lambda p: p.replace("<p>Second abstract.</p>", "<p>One.</p><p>Two.</p>"),
     lambda p: p.replace('class="col-lg-12"', 'class="col-lg-11"')],
)  # fmt: skip
def test_a_2022_page_whose_structure_moved_stops(edit) -> None:
    page = """<div class="container"><div class="row"><div class="col-lg-12">
    <h4 id="1"><b>T</b></h4><p><i>A</i></p><br><p>First abstract.</p>
    <h4 id="2"><b>U</b></h4><p><i>B</i></p><br><p>Second abstract.</p>
    </div></div></div>"""
    with pytest.raises(CrawlError) as e:
        facct_site.facct2022_html(edit(page))
    assert e.value.reason == "site_format"


def test_the_fetcher_takes_a_csv_served_as_octet_stream(tmp_path: Path) -> None:
    text = csv26(("1", "x", "y"), ("2", "z", "w"), ("3", "q", "r"))
    t = FakeTransport({URL26: response(text, headers={"content-type": "application/octet-stream"})})
    seen: list[str] = []
    inner = t.__call__

    def spy(request, timeout):
        seen.append(request.headers["Accept"])
        return inner(request, timeout)

    f = crawl.facct_site_fetcher(tmp_path, offline=False, transport=spy, min_interval=0)
    got = facct_site.read_year(2023, f, table=facct_site.load(SITE_TABLE))
    assert got is not None and len(got.entries) == 3
    assert (
        seen and "*/*" in seen[0]
    )  # a server that answers octet-stream is never refused by the Accept header
    assert f.policy.min_interval == facct_site.MIN_INTERVAL and f.policy.hosts == facct_site.HOSTS
