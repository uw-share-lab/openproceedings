"""TASK-229: a lone UTF-16 surrogate in any source's abstract, one decision for every source.

JSON can carry one (`"\\ud800"`); no record may hold one (`record._utf8`). Every source refuses that abstract claim
and keeps the paper on its title, and its crawl report counts the refusal under `abstract_surrogate` (listed only
when above 0, so a report with none keeps its shape), never silently and never stopping the crawl. A lone surrogate
in a title is not an abstract: it keeps today's behaviour (the paper is skipped as `invalid`, or the crawl stops),
which is loud in every source.

HTML and XML pages can't produce one (the HTML decoder turns `&#xD800;` into U+FFFD, expat refuses it, and every
page is decoded strictly): those sources share the rule through `common.clean_abstract`, so their tests put the
character in after parsing.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.sources import (
    crossref,
    dblp,
    facct_site,
    icml_sites,
    neurips,
    ojs,
    openalex,
    pmlr,
)
from openproceedings.ingest.sources import openreview_v2 as orv
from openproceedings.ingest.sources.common import (
    SURROGATE,
    Cleaned,
    CrawlError,
    ListingReport,
    clean_abstract,
    missing_reason,
)
from openproceedings.ingest.sources.html import unescape
from openproceedings.ingest.sources.http import Page
from openproceedings.ingest.volumes import VOLUMES

from tests.unit.ingest.proceedings_helpers import T0

LONE = "We study trust \ud800 in models."


def refusals(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """The DEBUG lines (a record-level anomaly; the report holds the count), never quoting the text."""
    got = [r for r in caplog.records if r.getMessage() == "abstract_surrogate_refused"]
    assert all(r.levelno == logging.DEBUG and "\ud800" not in str(r.__dict__) for r in got)
    return got


# --- the shared step ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text", [LONE, "\udfff", "a\ud83d", "\ude00b", "x\x02\ud800 (cid:12)"])
def test_the_shared_clean_step_refuses_a_lone_surrogate_and_names_why(text: str) -> None:
    assert clean_abstract(text) == Cleaned(None, refused=SURROGATE)
    assert SURROGATE == "abstract_surrogate"


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        (
            "We study trust 😀 in models.",
            "We study trust 😀 in models.",
        ),  # a pair JSON joined: one code point
        ("Plain text.", "Plain text."),
        ("", None),
        ("… a snippet", None),
    ],
)
def test_valid_text_is_cleaned_as_before_with_no_refusal(text: str, kept: str | None) -> None:
    cleaned = clean_abstract(text)
    assert (cleaned.text, cleaned.refused) == (kept, None)


def test_missing_reason_names_the_refusal_only_when_there_is_no_abstract() -> None:
    assert missing_reason(True, True, None, SURROGATE) == SURROGATE
    assert missing_reason(True, True, None) == "no_abstract"
    assert missing_reason(True, True, "text", SURROGATE) is None
    assert missing_reason(False, False, None, None) == "page_missing"


def test_html_and_xml_pages_cannot_produce_one() -> None:
    """Why the proceedings sources only meet it through the shared step: a reference to a surrogate is U+FFFD in
    HTML (the standard), and ill-formed XML."""
    assert unescape("a&#xD800;b&#55296;") == "a�b�"
    with pytest.raises(CrawlError, match="not XML"):
        ojs._root("<a>&#xD800;</a>")


def test_a_listing_report_counts_the_refusal_of_abstract_missing_and_logs_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    record = PaperRecord.build(
        id="op:icml:2024:pmlr-v235-abe24a",
        title="T",
        abstract=None,
        authors=(),
        venue="ICML",
        year=2024,
        track="main",
        status="accepted",
    )
    report = ListingReport("pmlr", "ICML", 2024, "https://x/", "primary", None)
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        report.count(record, SURROGATE)
    assert (report.abstract_missing, report.abstract_surrogate) == (1, 1)
    assert report.to_manifest()["abstract_surrogate"] == 1
    [line] = refusals(caplog)
    assert line.__dict__["source"] == "pmlr" and line.__dict__["record"] == record.id
    clean = ListingReport("pmlr", "ICML", 2024, "https://x/", "primary", None)
    clean.count(record, "no_abstract")
    assert clean.abstract_surrogate == 0 and "abstract_surrogate" not in clean.to_manifest()


# --- the proceedings miners: PMLR, NeurIPS -------------------------------------------------------------------------


def test_pmlr_keeps_the_paper_on_its_title_with_no_abstract_claim() -> None:
    volume = VOLUMES[235]
    entry = pmlr.Entry(
        "https://proceedings.mlr.press/v235/abe24a.html", "Inductive Trust", ("A One",), None, None
    )
    html = f'<meta name="citation_title" content="Inductive Trust"><div id="abstract">{LONE}</div>'
    index = Page(volume.index_url, 200, "", T0)
    record, missing, cleaned = pmlr._record(
        volume, "pmlr-v235-abe24a", entry, index, Page(entry.url, 200, html, T0)
    )
    assert (record.title, record.abstract, record.claims("abstract")) == ("Inductive Trust", None, ())
    assert (missing, cleaned.refused) == (SURROGATE, SURROGATE)


def test_neurips_keeps_the_paper_on_its_title_with_no_abstract_claim() -> None:
    native = "nips-" + "a" * 32
    url = f"https://proceedings.neurips.cc/paper_files/paper/2024/hash/{'a' * 32}-Abstract-Conference.html"
    listing = "https://proceedings.neurips.cc/paper_files/paper/2024"
    html = f'<meta name="citation_title" content="Inductive Trust"><p class="paper-abstract">{LONE}</p>'
    index, page = Page(listing, 200, "", T0), Page(url, 200, html, T0)
    entry = neurips.Entry(url, "Inductive Trust", ("A One",))
    record, missing, _ = neurips._record(
        2024, native, entry, "main", "track token Conference", listing, index, page
    )
    assert (record.title, record.abstract, record.claims("abstract"), missing) == (
        "Inductive Trust", None, (), SURROGATE
    )  # fmt: skip


# --- OJS -----------------------------------------------------------------------------------------------------------


def test_ojs_keeps_the_paper_and_counts_the_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.unit.ingest.ojs import oai
    from tests.unit.ingest.ojs.test_ojs_mine import TABLE, _offline, _seed

    read = ojs._oai_record

    def lone(rec: ET.Element) -> ojs.OaiRecord:
        got = read(rec)
        return replace(got, description=LONE) if got.article == 1 else got

    monkeypatch.setattr(ojs, "_oai_record", lone)
    _seed(tmp_path, oai.page(oai.record(1), oai.record(2), oai.record(3, "AAAI:IAAI")))
    result = ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    rec = next(r for r in result.records if r.native == "ojs-1")
    assert rec.title and rec.abstract is None and not rec.claims("abstract")
    (report,) = result.reports
    assert (report.records, report.abstract_surrogate, report.to_manifest()["abstract_surrogate"]) == (
        3,
        1,
        1,
    )
    assert report.skipped.get("invalid", 0) == 0


# --- the official ICML pages (through dblp) and the FAccT page (through Crossref) -----------------------------------


def test_an_icml_site_entry_is_dropped_and_counted_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.unit.ingest.test_dblp import TABLE, prepared
    from tests.unit.ingest.test_icml_sites import CYBERCHAIR, one_page

    parse = icml_sites.PARSERS["cyberchair"]

    def lone(text: str, url: str) -> list[icml_sites.Entry]:
        got = parse(text, url)
        return [replace(got[0], abstract=LONE), *got[1:]]

    monkeypatch.setattr(icml_sites, "PARSERS", {**icml_sites.PARSERS, "cyberchair": lone})
    f, pages = one_page(tmp_path, CYBERCHAIR)
    site = icml_sites.read_year(1990, f, pages=pages)
    assert site is not None and (len(site.entries), site.dropped, site.surrogate) == (1, 1, 1)
    report = dblp.mine_year(1990, prepared(tmp_path / "x"), table=TABLE, site=site).reports[0]
    assert (report.site_dropped, report.site_surrogate) == (1, 1)
    assert report.to_manifest()["site_surrogate"] == 1
    plain_f, plain_pages = one_page(tmp_path / "plain", CYBERCHAIR)
    monkeypatch.setattr(icml_sites, "PARSERS", {**icml_sites.PARSERS, "cyberchair": parse})
    plain = icml_sites.read_year(1990, plain_f, pages=plain_pages)
    assert plain is not None and plain.surrogate == 0
    manifest = (
        dblp.mine_year(1990, prepared(tmp_path / "y"), table=TABLE, site=plain).reports[0].to_manifest()
    )
    assert "site_surrogate" not in manifest


def test_a_facct_site_row_is_dropped_and_counted_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openproceedings.ingest import acm_table

    from tests.unit.ingest.crossref import api
    from tests.unit.ingest.crossref.test_crossref_mine import D1, D2, NP, TABLE, _offline, _whole
    from tests.unit.ingest.crossref.test_facct_site import csv26, site

    monkeypatch.setattr(acm_table, "TABLE", TABLE)
    parse = facct_site.PARSERS["facct2026_csv"]

    def lone(text: str) -> list[facct_site.Entry]:
        return [replace(e, abstract=LONE) if e.key == "1" else e for e in parse(text)]

    monkeypatch.setattr(facct_site, "PARSERS", {**facct_site.PARSERS, "facct2026_csv": lone})
    _whole(
        tmp_path,
        api.work(D1, title="Fair Ranking, Revisited"),
        api.work(D2, title="Other"),
        api.work(NP),
        total=3,
    )
    s = site(tmp_path, csv26(("1", "fair ranking revisited", "Official abstract one."),
                             ("2", "A non-archival talk", "Abstract two."), ("3", "Third", "Three.")))  # fmt: skip
    assert (s.dropped, s.surrogate) == (1, 1)
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE, site=s)
    r = next(x for x in result.records if x.urls.doi == D1)
    assert r.title == "Fair Ranking, Revisited" and r.abstract is None
    report = result.reports[0]
    assert (report.site_dropped, report.site_surrogate, report.to_manifest()["site_surrogate"]) == (1, 1, 1)


# --- OpenReview v1 and v2 ------------------------------------------------------------------------------------------


def test_the_response_cache_keeps_a_lone_surrogate_escaped_and_valid_text_as_before(tmp_path: Path) -> None:
    """OpenReview's cache holds the parsed JSON (`EntryCodec`), so a note with `"\\ud800"` once crashed the write
    (UTF-8 can't encode it) before any rule could see it. Such an entry is written as ASCII JSON, escaped as it came;
    every other entry's bytes are unchanged (UTF-8, non-ASCII kept raw)."""
    from openproceedings.ingest.sources.http import PageCache

    cache = PageCache(tmp_path)
    lone, plain = Page("https://x/a", 200, LONE, T0), Page("https://x/b", 200, "Renée’s trust", T0)
    cache.put(lone)
    cache.put(plain)
    assert cache.get(lone.url) == lone and cache.get(plain.url) == plain
    assert b"\\ud800" in cache.path(lone.url).read_bytes()
    assert "Renée’s trust".encode() in cache.path(plain.url).read_bytes()


# --- OpenReview v1 and v2 ------------------------------------------------------------------------------------------


def test_openreview_v2_keeps_the_note_and_counts_the_refusal(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from tests.unit.ingest.test_openreview_v2 import CONF, build, client, recorded_note, world

    note = recorded_note("iclr-2024/notes-accepted.json")
    note["content"]["abstract"]["value"] = LONE
    record = build(note)
    assert isinstance(record, PaperRecord) and record.abstract is None and not record.claims("abstract")
    server = world(accepted=3)
    server.notes[CONF][0]["content"]["abstract"]["value"] = LONE
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        result = orv.crawl(client(tmp_path, server), "ICLR", 2024)
    assert result.report.abstract_surrogate == 1 == result.report.to_manifest()["abstract_surrogate"]
    assert len(refusals(caplog)) == 1
    plain = orv.crawl(client(tmp_path / "plain", world()), "ICLR", 2024).report
    assert plain.abstract_surrogate == 0 and "abstract_surrogate" not in plain.to_manifest()


def test_openreview_v1_keeps_the_note_and_counts_the_refusal(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from tests.unit.ingest.test_openreview_v1 import by_forum, iclr_2017, v1_note

    note = v1_note("iclr-2017/note-rejected-bare-venueid.json")
    note["content"]["abstract"] = LONE
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.sources"):
        crawl = iclr_2017(tmp_path, [note], [])
    record = by_forum(crawl)[note["id"]]
    assert record.title and record.abstract is None and not record.claims("abstract")
    assert crawl.report.abstract_surrogate == 1 == crawl.report.to_manifest()["abstract_surrogate"]
    assert len(refusals(caplog)) == 1


# --- RIS -----------------------------------------------------------------------------------------------------------


def test_ris_refuses_that_claim_takes_the_next_and_counts_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A RIS entry's abstract is the first usable claim in source order: a refused claim is passed over like an
    empty one, and the record is counted whether or not a later claim gave it an abstract."""
    from tests.unit.ingest.test_ris import DB, WORKSHOP, claim, run

    def lone(entries: list[dict[str, Any]]) -> None:
        for entry in entries:
            abstracts = [c for c in entry["claims"] if c["field"] == "abstract"]
            if any(c["value"].startswith("A made-up abstract") for c in abstracts):
                for c in abstracts:
                    c["value"] = LONE  # its only abstract: none left
            elif any(c["value"].startswith("A synthetic datasets-track") for c in abstracts):
                entry["claims"].insert(0, claim("abstract", LONE, "openreview_api", "openreview:x"))

    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest"):
        by_id, report = run(tmp_path, lone)
    assert by_id[WORKSHOP].title and by_id[WORKSHOP].abstract is None
    assert by_id[DB].abstract == "A synthetic datasets-track abstract with extra spaces."
    assert report.abstract_surrogate == 2 == report.to_manifest()["abstract_surrogate"]
    assert len(refusals(caplog)) == 2


# --- OpenAlex ------------------------------------------------------------------------------------------------------


def test_openalex_refuses_it_under_the_shared_name() -> None:
    text = '{"meta": {"count": 1}, "results": [{"id": "W1", "abstract_inverted_index": {"a\\ud800": [0]}}]}'
    (w,) = openalex.parse_works(text).works
    assert openalex.abstract_of(w) == (None, SURROGATE)


# --- titles keep today's behaviour: loud -----------------------------------------------------------------------------


def test_a_lone_surrogate_in_a_title_is_still_loud() -> None:
    """Not an abstract: the paper is never kept without it. PMLR (as NeurIPS, OJS and dblp) refuses the record as
    `invalid`, which its miner counts in `skipped` and its `listing_attention` WARNING; OpenReview stops."""
    from pydantic import ValidationError

    from tests.unit.ingest.test_openreview_v2 import build, recorded_note

    volume = VOLUMES[235]
    entry = pmlr.Entry(
        "https://proceedings.mlr.press/v235/abe24a.html", "Trust \ud800", ("A One",), None, None
    )
    with pytest.raises(ValidationError):
        pmlr._record(
            volume,
            "pmlr-v235-abe24a",
            entry,
            Page(volume.index_url, 200, "", T0),
            Page(entry.url, 404, "", T0),
        )
    note = recorded_note("iclr-2024/notes-accepted.json")
    note["content"]["title"]["value"] = "Trust \ud800"
    with pytest.raises(ValidationError):
        build(note)
