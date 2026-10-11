"""PMLR miner and the volume table (task-053), against the recorded, scrubbed fixtures (decision-004)."""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import pytest
from openproceedings.ingest import urls, volumes
from openproceedings.ingest.dedup import dedup
from openproceedings.ingest.sources import pmlr
from openproceedings.ingest.sources.common import MinerError
from openproceedings.ingest.sources.crawl import ingest_pmlr, load_crawls
from openproceedings.ingest.sources.html import MAX_DEPTH
from openproceedings.ingest.volumes import ICML_PMLR_VOLUMES, VOLUMES, icml_volume, load

from tests.unit.ingest.proceedings_helpers import (
    T0,
    T1,
    FakeTransport,
    fetcher,
    fixture_text,
    fixture_url,
    response,
    seed,
    seed_fixture,
)

V28, V202, V235, V267 = (
    "pmlr/v28/volume-index.json",
    "pmlr/v202/volume-index.json",
    "pmlr/v235/volume-index.json",
    "pmlr/v267/volume-index.json",
)
V28_KEYS = ("sznitman13", "muandet13", "boots13")
V235_KEYS = ("abad-rocamora24a", "abe24a", "abhyankar24a")


# --- the volume table ------------------------------------------------------------------------------------


def test_every_row_has_a_source_and_a_verified_date() -> None:
    for v in VOLUMES.values():  # the 2026-09-27 table, and v81 (FAccT 2018) from the census of 2026-10-10
        assert v.source and v.verified == (date(2026, 10, 10) if v.number == 81 else date(2026, 9, 27)), (
            v.number
        )


def test_the_icml_volumes_2013_on() -> None:
    assert {v.year: n for n, v in VOLUMES.items() if v.venue == "ICML" and v.ingested} == {
        2013: 28, 2014: 32, 2015: 37, 2016: 48, 2017: 70, 2018: 80, 2019: 97, 2020: 119, 2021: 139,
        2022: 162, 2023: 202, 2024: 235, 2025: 267,
    }  # fmt: skip
    assert {n: VOLUMES[n].role for n in ICML_PMLR_VOLUMES} == {
        n: "primary" if n <= 162 else "confirm" for n in ICML_PMLR_VOLUMES
    }
    assert icml_volume(2026) is None  # not on PMLR on 2026-09-27: added when its index page appears


def test_competition_and_workshop_volumes_are_classified_and_never_ingested() -> None:
    competition = {n for n, v in VOLUMES.items() if v.track == "competition"}
    workshop = {n for n, v in VOLUMES.items() if v.track == "workshop"}
    assert competition == {123, 133, 176, 220}
    assert workshop == {27, 184, 251, 292, 116, 136, 137, 163, 181, 187, 210, 226, 239, 262}
    for n in competition | workshop:
        assert VOLUMES[n].role == "out_of_scope" and not VOLUMES[n].ingested and n not in ICML_PMLR_VOLUMES
    assert {VOLUMES[n].venue for n in competition} == {"NeurIPS"}


def test_the_table_agrees_with_the_recorded_pmlr_index() -> None:
    """Every volume the recorded index lists that the table has: the same index title."""
    listed = dict(
        (int(m.group(1)), m.group(2).strip())
        for m in re.finditer(
            r'<li><a href="v(\d+)"><b>Volume \d+</b></a> ([^<]+)</li>', fixture_text("pmlr/index.json")
        )
    )
    checked = {n for n in listed if n in VOLUMES}
    assert checked >= set(ICML_PMLR_VOLUMES) | {123, 133, 176, 220, 251, 292}
    for n in checked:
        assert VOLUMES[n].index_title == listed[n], n
    assert 318 in listed and 318 not in VOLUMES  # the Canadian Conference on AI: never ICML


@pytest.mark.parametrize(
    ("rel", "number"),
    [(V28, 28), (V202, 202), (V235, 235), (V267, 267), ("pmlr/v220/volume-index.json", 220),
     ("pmlr/v81/volume-index.json", 81)],
)  # fmt: skip
def test_the_table_agrees_with_the_recorded_volume_headings(rel: str, number: int) -> None:
    found = pmlr.heading(fixture_text(rel))
    heading = VOLUMES[number].heading
    assert found is not None and heading is not None
    assert found[0] == number and found[1].startswith(heading)


def test_the_recorded_v81_index_lists_every_not_paper_key() -> None:
    """The shipped v81 row's preface and two keynotes are on the recorded index (2026-10-10), so the live crawl's
    `stale_not_paper` check passes on the same page."""
    rel = "pmlr/v81/volume-index.json"
    entries, _ = pmlr.parse_volume_index(fixture_text(rel), fixture_url(rel))
    keys = {p[1] for e in entries if (p := urls.pmlr(e.url)) is not None and p[0] == 81}
    row = VOLUMES[81]
    assert (row.venue, row.year, row.papers, len(row.not_papers)) == ("FAccT", 2018, 20, 3)
    assert set(row.not_papers) <= keys


ROW = 'number = 1\nvenue = "ICML"\nyear = 2019\ntrack = "main"\nrole = "primary"\npapers = 3\nheading = "ICML"\nverified = 2026-09-27\nsource = "x"\n'


@pytest.mark.parametrize(
    ("text", "error"),
    [
        (f"[[volume]]\n{ROW}[[volume]]\n{ROW}", "listed twice"),
        (f"[[volume]]\n{ROW}[[volume]]\n{ROW.replace('number = 1', 'number = 2')}", "two ingested volumes"),
        (f"[[volume]]\n{ROW.replace('track = "main"', 'track = "workshop"')}", "never ingested"),
        (f"[[volume]]\n{ROW.replace('venue = "ICML"', 'venue = "NeurIPS"')}", "only ICML"),
        (f"[[volume]]\n{ROW.replace('heading = "ICML"', '')}", "needs its year, paper count and heading"),
        (f"[[volume]]\n{ROW.replace('source = "x"', '')}", "missing columns"),
        (f"[[volume]]\n{ROW}colour = 1\n", "unknown columns"),
        (f"[[volume]]\n{ROW.replace('track = "main"', 'track = "poster"')}", "not a spec 01 track"),
        (f"[[volume]]\n{ROW.replace('year = 2019', 'year = 1950')}", "held"),
        (f"[[volume]]\n{ROW.replace('verified = 2026-09-27', 'verified = "yesterday"')}", "verified date"),
    ],
)
def test_a_malformed_table_is_refused(text: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        load(text)


# --- the miner -------------------------------------------------------------------------------------------


def seed_v28(cache: Path) -> None:
    seed_fixture(cache, "pmlr", V28)
    seed_fixture(cache, "pmlr", "pmlr/v28/paper.json")
    for key in ("sznitman13", "boots13"):
        seed(cache, "pmlr", f"https://proceedings.mlr.press/v28/{key}.html", "", status=404)


def seed_v235(cache: Path, *, match: bool = True) -> None:
    seed_fixture(cache, "pmlr", V235)
    seed_fixture(
        cache, "pmlr", "pmlr/v235/paper.json",
        edit=(lambda t: t.replace("Synthetic title 9", "Synthetic title 2")) if match else None,
    )  # fmt: skip
    for key in ("abad-rocamora24a", "abhyankar24a"):
        seed(cache, "pmlr", f"https://proceedings.mlr.press/v235/{key}.html", "", status=404)


def mine(cache: Path, number: int) -> pmlr.VolumeResult:
    f, _ = fetcher(cache / "pmlr", None, pmlr.HOSTS)
    return pmlr.mine_volume(number, f)


def test_v28_icml_2013_records_come_from_the_table(tmp_path: Path) -> None:
    seed_v28(tmp_path)
    result = mine(tmp_path, 28)
    records = {r.id: r for r in result.records}
    assert set(records) == {f"op:icml:2013:pmlr-v28-{k}" for k in V28_KEYS}
    r = records["op:icml:2013:pmlr-v28-muandet13"]
    assert (r.venue, r.year, r.track, r.status, r.title) == (
        "ICML",
        2013,
        "main",
        "accepted",
        "Synthetic title 2",
    )
    assert r.authors == ("Synthetic authors 5",) and r.abstract is None  # recorded page title mismatches
    assert r.urls.proceedings == "https://proceedings.mlr.press/v28/muandet13.html"
    assert r.urls.pdf == "http://proceedings.mlr.press/v28/muandet13.pdf"  # not the -supp.pdf beside it
    [year] = r.claims("year")
    assert year.source == "pmlr" and year.evidence == "volume table v28 (primary, verified 2026-09-27)"
    report = result.report
    assert (report.volume, report.stated, report.listed, report.count_ok) == (28, 283, 3, False)  # trimmed
    assert (report.abstract_missing, report.page_missing, report.abstract_title_mismatch, report.role) == (
        3,
        2,
        1,
        "primary",
    )


def test_the_recorded_pre_openreview_paper_page_exercises_its_real_shape() -> None:
    page = pmlr.parse_paper_page(fixture_text("pmlr/v28/paper.json"))
    assert page.title == "Synthetic title 10"
    assert page.authors == ("Synthetic Author 12", "Synthetic Author 13", "Synthetic Author 11")
    assert page.abstract == "Synthetic abstract 5"
    assert page.pdf == "http://proceedings.mlr.press/v28/muandet13.pdf"


@pytest.mark.parametrize("rel", [V202, V267])
def test_the_recorded_openreview_era_indexes_carry_forum_links(rel: str) -> None:
    entries, unlinked = pmlr.parse_volume_index(fixture_text(rel), fixture_url(rel))
    assert unlinked == 0 and len(entries) == 3
    assert all(entry.forum for entry in entries)


def test_an_index_entry_with_two_forum_ids_is_skipped_before_dedup() -> None:
    """An ambiguous external identity must not reach title-based dedup without its identity."""
    page = """
    <div class="paper">
      <p class="title">One paper</p><span class="authors">One Author</span>
      <a href="paper.html">abs</a>
      <a href="https://openreview.net/forum?id=FirstForum1">OpenReview A</a>
      <a href="https://openreview.net/forum?id=SecondForum2">OpenReview B</a>
    </div>
    """
    entries, unlinked = pmlr.parse_volume_index(page, "https://proceedings.mlr.press/v235/")
    assert entries == [] and unlinked == 1


def test_index_parser_is_attribute_order_independent_and_ignores_decoy_elements() -> None:
    page = """<h1 class='decoy'>Proceedings</h1><h2 data-x='1' class='x'>Volume 235: International Conference</h2>
    <div class='paper-count'><a href='decoy24a.html'>not a paper block</a></div>
    <div data-x='1' class='extra paper'>
      <span class='author-note'>Decoy Person</span>
      <p data-x='1' class='extra title'>Actual Title</p>
      <p class='details'><span data-x='1' class='extra authors'>Actual One, Actual Two</span></p>
      <p class='links'>[<a href='https://example.org/decoy.html'>decoy</a>][<a target='_blank' href='abe24a.html'>abs</a>]
        [<a href='abe24a-supp.pdf'>Supplementary PDF</a>][<a target='_blank' href='abe24a.pdf'>Download PDF</a>]
        [<a target='_blank' href='https://openreview.net/forum?id=9U29U3cDKq'>OpenReview</a>]</p>
    </div>"""
    assert pmlr.heading(page) == (235, "International Conference")
    entries, unlinked = pmlr.parse_volume_index(page, "https://proceedings.mlr.press/v235/")
    assert unlinked == 0
    assert entries == [
        pmlr.Entry("https://proceedings.mlr.press/v235/abe24a.html", "Actual Title", ("Actual One", "Actual Two"),
                   "https://proceedings.mlr.press/v235/abe24a.pdf", "9U29U3cDKq"),
    ]  # fmt: skip


def test_v235_abstract_forum_link_and_unknown_track(tmp_path: Path) -> None:
    seed_v235(tmp_path)
    result = mine(tmp_path, 235)
    r = {x.id: x for x in result.records}["op:icml:2024:pmlr-v235-abe24a"]
    assert (r.track, r.abstract) == ("unknown", "Synthetic abstract 4")  # v235 mixes main and position papers
    assert r.authors == tuple(f"Synthetic Author {n}" for n in (12, 13, 10, 11))
    assert r.urls.forum == "https://openreview.net/forum?id=9U29U3cDKq"  # the join to OpenReview (2023+)
    assert r.urls.pdf == "https://raw.githubusercontent.com/mlresearch/v235/main/assets/abe24a/abe24a.pdf"
    assert (result.report.unknown_track, result.report.role) == (3, "confirm")


def test_v235_page_title_mismatch_drops_the_abstract(tmp_path: Path) -> None:
    seed_v235(tmp_path, match=False)
    result = mine(tmp_path, 235)
    r = {x.id: x for x in result.records}["op:icml:2024:pmlr-v235-abe24a"]
    assert r.abstract is None and r.authors == ("Synthetic authors 5",)
    assert result.report.abstract_title_mismatch == 1


@pytest.mark.parametrize(
    ("number", "reason"),
    [(220, "out_of_scope_volume"), (184, "out_of_scope_volume"), (318, "unlisted_volume")],
)
def test_competition_workshop_and_unlisted_volumes_are_refused(
    tmp_path: Path, number: int, reason: str
) -> None:
    with pytest.raises(MinerError) as e:
        mine(tmp_path, number)
    assert e.value.reason == reason


def test_a_heading_the_table_doesnt_name_stops_the_crawl(tmp_path: Path) -> None:
    seed_fixture(
        tmp_path, "pmlr", V28,
        edit=lambda t: t.replace("Volume 28: International Conference on Machine Learning", "Volume 28: Something Else"),
    )  # fmt: skip
    with pytest.raises(MinerError) as e:
        mine(tmp_path, 28)
    assert e.value.reason == "heading_mismatch"


def test_ingest_by_year_marks_the_volume_and_the_snapshot_path_re_mines_it(tmp_path: Path) -> None:
    pages = {"https://proceedings.mlr.press/v28/": response(fixture_text(V28))}
    pages |= {f"https://proceedings.mlr.press/v28/{k}.html": response("", 404) for k in V28_KEYS}
    t = FakeTransport(pages)
    out = ingest_pmlr([2013], tmp_path, transport=t, min_interval=0)
    assert out["requests"] == 4 and [lst["volume"] for lst in out["listings"]] == [28]
    assert (tmp_path / "pmlr" / "crawls" / "v28.json").is_file()
    records, sources = load_crawls(tmp_path)
    assert len(records) == 3 and [lst["volume"] for lst in sources["pmlr"]["listings"]] == [28]
    with pytest.raises(MinerError, match="no verified PMLR volume"):
        ingest_pmlr([2026], tmp_path, transport=t, min_interval=0)


def test_a_marked_crawl_whose_pages_are_gone_is_an_error(tmp_path: Path) -> None:
    seed_v28(tmp_path)
    ingest_pmlr([2013], tmp_path, offline=True)
    next((tmp_path / "pmlr" / "pages").rglob("*.json")).unlink()
    with pytest.raises(MinerError, match="marked crawled"):
        load_crawls(tmp_path)


def test_a_paper_page_past_the_html_budget_is_a_debug_line_counted_in_one_listing_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """TASK-116: a record-level anomaly is DEBUG (with the page's URL); the volume's one `listing_attention`
    WARNING counts it (its `listing_count_mismatch` is a listing-level line: this fixture is trimmed)."""
    seed_v28(tmp_path)
    paper = "https://proceedings.mlr.press/v28/muandet13.html"
    seed(tmp_path, "pmlr", paper, "<html>" + "<div>" * (MAX_DEPTH + 1) + "</html>")
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        result = mine(tmp_path, 28)
    assert result.report.skipped["invalid"] == 1
    [invalid] = [r for r in caplog.records if r.getMessage() == "pmlr_record_invalid"]
    assert (invalid.levelno, invalid.__dict__["url"], invalid.__dict__["error"]) == (
        logging.DEBUG, paper, "HTMLBudgetError",
    )  # fmt: skip
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert [r.getMessage() for r in warnings] == ["listing_count_mismatch", "listing_attention"]
    assert warnings[1].__dict__["skipped"] == {"invalid": 1}


def test_a_volume_heading_past_the_html_budget_names_the_index_url() -> None:
    from openproceedings.ingest.sources.html import HTMLBudgetError

    url = "https://proceedings.mlr.press/v28/"
    with pytest.raises(HTMLBudgetError, match=re.escape(f"{url}: HTML nesting exceeds")):
        pmlr.heading("<div>" * (MAX_DEPTH + 1), url)


def test_the_reports_first_fetch_is_the_index_page(tmp_path: Path) -> None:
    """`ListingReport.fetched[0]` is the volume index's read (reconcile dates its absence claims by it)."""
    seed_fixture(tmp_path, "pmlr", V28, at=T1)  # the index page read after its paper pages
    seed_fixture(tmp_path, "pmlr", "pmlr/v28/paper.json", at=T0)
    for key in ("sznitman13", "boots13"):
        seed(tmp_path, "pmlr", f"https://proceedings.mlr.press/v28/{key}.html", "", status=404, at=T0)
    report = mine(tmp_path, 28).report
    assert report.fetched[0] == T1 and T0 in report.fetched[1:]


def test_a_listed_title_with_a_control_character_keeps_its_paper() -> None:
    """decision-036 (TASK-180 review): a dropped listing would also turn the paper's OpenReview acceptance into
    `unknown` at reconcile. The control character becomes a space; the claim's evidence says so."""
    from openproceedings.ingest.sources.http import Page

    volume = VOLUMES[235]
    entry = pmlr.Entry(
        "https://proceedings.mlr.press/v235/abe24a.html", "Induc\x02tive Trust\x00", ("A One",), None, None
    )
    index = Page(volume.index_url, 200, "", T0)
    record, missing, _ = pmlr._record(volume, "pmlr-v235-abe24a", entry, index, Page(entry.url, 404, "", T0))
    assert (record.title, missing) == ("Induc tive Trust", "page_missing")
    [title] = record.claims("title")
    assert title.evidence == f"volume index {volume.index_url} (2 control characters replaced by a space)"
    clean, _, _ = pmlr._record(volume, "pmlr-v235-abe24a", pmlr.Entry(entry.url, "Inductive  Trust", ("A One",), None, None),
                            index, Page(entry.url, 404, "", T0))  # fmt: skip
    assert clean.title == "Inductive Trust"
    assert [c.evidence for c in clean.claims("title")] == [f"volume index {volume.index_url}"]


def test_a_page_abstract_with_a_control_character_is_imported_with_a_space() -> None:
    """decision-044 (TASK-188): the title rule, for abstracts; the claim's evidence says so."""
    from openproceedings.ingest.sources.http import Page

    volume = VOLUMES[235]
    entry = pmlr.Entry(
        "https://proceedings.mlr.press/v235/abe24a.html", "Inductive Trust", ("A One",), None, None
    )
    html = (
        '<meta name="citation_title" content="Inductive Trust">'
        '<div id="abstract">The LiDAR modal\x02ity, 500x\x02 longer.</div>'
    )
    index = Page(volume.index_url, 200, "", T0)
    record, missing, cleaned = pmlr._record(
        volume, "pmlr-v235-abe24a", entry, index, Page(entry.url, 200, html, T0)
    )
    assert (record.abstract, missing, cleaned.spaced, cleaned.pdf_codes) == (
        "The LiDAR modal ity, 500x longer.",
        None,
        2,
        0,
    )
    [abstract] = record.claims("abstract")
    assert (
        abstract.evidence
        == "div#abstract (citation_title matches the listing) (2 control characters replaced by a space)"
    )
    only = html.replace("The LiDAR modal\x02ity, 500x\x02 longer.", "\x02\x00")
    bare, missing, _ = pmlr._record(volume, "pmlr-v235-abe24a", entry, index, Page(entry.url, 200, only, T0))
    assert (bare.abstract, missing, bare.claims("abstract")) == (None, "no_abstract", ())


def test_a_volume_counts_the_abstracts_that_lost_a_control_character(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """TASK-199 (decision-044): from the miner's own count, in the report, its manifest when above 0 and the
    volume's done line; never a WARNING for it. A volume with none keeps its manifest shape."""
    seed_fixture(tmp_path, "pmlr", V235)
    seed_fixture(
        tmp_path, "pmlr", "pmlr/v235/paper.json",
        edit=lambda t: t.replace("Synthetic title 9", "Synthetic title 2").replace("Synthetic abstract 4", "Synthetic\x02abstract 4"),
    )  # fmt: skip
    for key in ("abad-rocamora24a", "abhyankar24a"):
        seed(tmp_path, "pmlr", f"https://proceedings.mlr.press/v235/{key}.html", "", status=404)
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.sources"):
        result = mine(tmp_path, 235)
    assert {x.id: x for x in result.records}[
        "op:icml:2024:pmlr-v235-abe24a"
    ].abstract == "Synthetic abstract 4"
    report = result.report
    assert report.abstract_control_characters == 1 == report.to_manifest()["abstract_control_characters"]
    [done] = [r for r in caplog.records if r.getMessage() == "pmlr_volume_mined"]
    assert done.__dict__["abstract_control_characters"] == 1
    plain = tmp_path / "plain"
    seed_v235(plain)
    clean = mine(plain, 235).report
    assert clean.abstract_control_characters == 0 and "abstract_control_characters" not in clean.to_manifest()


# --- FAccT 2018 (v81): PMLR beside ICML (decision-049, milestone B) ---------------------------------------

FACCT = """
[[volume]]
number = 81
venue = "FAccT"
year = 2018
track = "main"
role = "primary"
papers = 3
not_papers = ["preface18a"]
heading = "Conference on Fairness, Accountability and Transparency"
verified = 2026-10-10
source = "test"
"""
V81_INDEX = """<html><body><h1>Volume 81: Conference on Fairness, Accountability and Transparency, 23-24 February 2018,
New York, NY, USA</h1>
<div class="paper"><p class="title">Synthetic preface</p><span class="authors">Synthetic Editor</span>
<a href="https://proceedings.mlr.press/v81/preface18a.html">abs</a></div>
<div class="paper"><p class="title">Synthetic title 1</p><span class="authors">Synthetic Author 1, Synthetic Author 2</span>
<a href="https://proceedings.mlr.press/v81/one18a.html">abs</a>
<a href="https://proceedings.mlr.press/v81/one18a/one18a.pdf">pdf</a></div>
<div class="paper"><p class="title">Synthetic title 2</p><span class="authors">Synthetic Author 3</span>
<a href="https://proceedings.mlr.press/v81/two18a.html">abs</a></div>
</body></html>"""


@pytest.fixture
def facct_table(monkeypatch):
    table = {**volumes.VOLUMES, **load(FACCT)}
    native = {**volumes.PMLR_NATIVE_VOLUMES, 81: ("FAccT", 2018, "main")}
    monkeypatch.setattr(volumes, "VOLUMES", table)
    monkeypatch.setattr(pmlr, "VOLUMES", table)
    monkeypatch.setattr(volumes, "PMLR_NATIVE_VOLUMES", native)
    return table


def seed_v81(cache: Path, index: str = V81_INDEX) -> None:
    seed(cache, "pmlr", "https://proceedings.mlr.press/v81/", index)
    for key in ("one18a", "two18a"):
        seed(cache, "pmlr", f"https://proceedings.mlr.press/v81/{key}.html", "", status=404)


def test_v81_is_faccts_2018_and_the_preface_is_counted_never_a_record(tmp_path: Path, facct_table) -> None:
    seed_v81(tmp_path)
    result = mine(tmp_path, 81)
    assert sorted(r.id for r in result.records) == [
        "op:facct:2018:pmlr-v81-one18a",
        "op:facct:2018:pmlr-v81-two18a",
    ]
    r = next(r for r in result.records if r.native == "pmlr-v81-one18a")
    assert (r.venue, r.year, r.track, r.status) == ("FAccT", 2018, "main", "accepted")
    assert r.urls.pdf == "https://proceedings.mlr.press/v81/one18a/one18a.pdf"
    report = result.report
    assert (report.venue, report.stated, report.listed, report.records, report.count_ok) == (
        "FAccT",
        3,
        3,
        2,
        True,
    )
    assert report.skipped == {"not_paper": 1}
    assert not list((tmp_path / "pmlr").rglob("preface18a*"))  # never fetched
    assert len(dedup(result.records).records) == 2  # each names itself: urls.native knows v81


def test_a_non_icml_volume_whose_count_differs_stops(tmp_path: Path, facct_table) -> None:
    seed_v81(
        tmp_path,
        V81_INDEX.replace(
            '<div class="paper"><p class="title">Synthetic title 2',
            '<div class="x"><p class="title">Synthetic title 2',
        ),
    )
    with pytest.raises(MinerError) as e:
        mine(tmp_path, 81)
    assert e.value.reason == "count_mismatch"


def test_a_not_paper_key_the_index_lacks_stops(tmp_path: Path, facct_table) -> None:
    seed_v81(tmp_path, V81_INDEX.replace("preface18a", "other18a"))
    with pytest.raises(MinerError) as e:
        mine(tmp_path, 81)
    assert e.value.reason == "stale_not_paper"


def test_icml_is_untouched() -> None:
    assert set(volumes.ICML_PMLR_VOLUMES) == {28, 32, 37, 48, 70, 80, 97, 119, 139, 162, 202, 235, 267}
    assert volumes.icml_volume(2013).number == 28 and volumes.ingested_volume("ICML", 2013).number == 28


@pytest.mark.parametrize(
    ("row", "error"),
    [(FACCT.replace('venue = "FAccT"', 'venue = "AIES"'), "only ICML and FAccT"),
     (FACCT.replace('role = "primary"', 'role = "confirm"'), "primary"),
     (FACCT.replace('not_papers = ["preface18a"]', 'not_papers = ["a", "a"]'), "not_papers"),
     (FACCT.replace('not_papers = ["preface18a"]', 'not_papers = ["a b"]'), "not_papers"),
     (FACCT.replace("papers = 3", "papers = 1"), "fewer not_papers than papers")],
)  # fmt: skip
def test_a_malformed_non_icml_row_is_refused(row: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        load(row)
