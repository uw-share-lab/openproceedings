# backend/tests/unit/ingest/test_dblp_aaai.py
"""AAAI 1980-2008 from the pinned dblp release (decision-049, milestone B): the check, the records, the counts, the
replay. Synthetic release (test_dblp_slices.AAAI_BODY). No network."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from openproceedings.ingest import dblp_aaai_table, urls
from openproceedings.ingest.dedup import dedup
from openproceedings.ingest.sources import crawl, dblp, dblp_aaai
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.statuses import statuses_indexed

from tests.unit.ingest import test_dblp_slices
from tests.unit.ingest.test_dblp_aaai_table import GOOD, SECTIONS
from tests.unit.ingest.test_dblp_slices import on_disk


def setup(tmp_path: Path, text: str = GOOD):
    table, rel, dtd = on_disk(tmp_path)
    aaai = dblp_aaai_table.load(text, pins=table)
    extract = dblp.write_extracts(tmp_path, rel, dtd, table, dblp.SLICES)["AAAI"]
    return table, aaai, extract


def test_aaai_records_from_the_release(tmp_path: Path) -> None:
    _table, aaai, extract = setup(tmp_path)
    dblp_aaai.check_extract(extract, aaai)
    (report,), records = (
        (r := dblp_aaai.mine_year(1986, extract, table=aaai)).reports,
        {x.id: x for x in r.records},
    )
    assert set(records) == {"op:aaai:1986:dblp-Synthetic86a", "op:aaai:1986:dblp-Synthetic86b"}
    a = records["op:aaai:1986:dblp-Synthetic86a"]
    assert (a.venue, a.year, a.track, a.status, a.title, a.abstract) == (
        "AAAI",
        1986,
        "main",
        "accepted",
        "Synthetic AAAI title 1",
        None,
    )
    assert a.authors == (
        "Synthetic Author 1",
        "Synthütic Author 2",
    )  # the homonym number dropped, the entity read
    assert (
        a.urls.proceedings == "https://dblp.org/rec/conf/aaai/Synthetic86a"
        and a.urls.doi == "10.5555/synthetic.1"
    )
    assert a.urls.pdf is None and {c.source for c in a.provenance} == {"dblp"}
    assert records["op:aaai:1986:dblp-Synthetic86b"].title == "Synthetic AAAI title 2?"
    assert (report.venue, report.stated, report.listed, report.records, report.count_ok) == (
        "AAAI",
        4,
        4,
        2,
        True,
    )
    assert report.skipped == {"not_paper": 1, "publtype_withdrawn": 1}


def test_a_record_that_will_not_build_stops_the_crawl_naming_the_key(tmp_path: Path, monkeypatch) -> None:
    _table, aaai, extract = setup(tmp_path)

    def boom(*_a, **_k):
        raise ValueError("no title")

    monkeypatch.setattr(dblp_aaai, "_record", boom)
    with pytest.raises(CrawlError, match=r"conf/aaai/Synthetic86a.*ValueError") as caught:
        dblp_aaai.mine_year(1986, extract, table=aaai)
    assert caught.value.reason == "invalid_record"


def test_a_workshop_key_gives_track_workshop(tmp_path: Path) -> None:
    _t, aaai, extract = setup(tmp_path)
    tracks = {r.native: r.track for r in dblp_aaai.mine_year(2006, extract, table=aaai).records}
    assert tracks == {"dblp-Main06": "main", "dblp-Workshop06": "workshop"}


@pytest.mark.parametrize(("raw", "kept"), [("Wei Wang 0001", "Wei Wang"), ("Wei Wang 0042", "Wei Wang"),
                                           ("A. B. 12", "A. B. 12"), ("Ada 0001x", "Ada 0001x")])  # fmt: skip
def test_clean_author_drops_only_a_four_digit_homonym(raw: str, kept: str) -> None:
    assert dblp.clean_author(raw) == kept


def test_a_count_that_differs_from_the_table_stops_the_year_and_its_replay(tmp_path: Path) -> None:
    _t, aaai, extract = setup(tmp_path, GOOD.replace("papers = 4", "papers = 5"))
    with pytest.raises(CrawlError, match="1986") as e:
        dblp_aaai.mine_year(1986, extract, table=aaai)
    assert e.value.reason == "count_mismatch"


@pytest.mark.parametrize(
    ("edit", "reason"),
    [(lambda s: s.replace('"conf/aaai/2006"]', '"conf/aaai/2006x"]'), "unlisted_proceedings"),  # the release's 2006 key is unlisted
     (lambda s: s.replace("not_held = [1981, 1985, 1989, 2001, 2003, 2009]", "not_held = [1981, 1985, 1989, 2001, 2003, 2006, 2009]")
      .split("[[year]]\nyear = 2006")[0], "table_mismatch"),
     (lambda s: s.replace('key = "conf/aaai/Invited86"', 'key = "conf/aaai/Nowhere86"'), "table_mismatch"),
     # the release's own key stays listed; a second key the release lacks reaches the "named" check
     (lambda s: s.replace('"conf/aaai/2006"]', '"conf/aaai/2006", "conf/aaai/2006-absent"]'), "table_mismatch"),
     # a key the release holds, dated another year (2024: outside the years the first loop checks)
     (lambda s: s.replace('"conf/aaai/1986-2"]', '"conf/aaai/1986-2", "conf/aaai/2024"]'), "table_mismatch")],
)  # fmt: skip
def test_the_check_stops_on_an_unlisted_key_a_not_held_year_or_an_absent_row(
    tmp_path: Path, edit, reason
) -> None:
    _t, aaai, extract = setup(tmp_path, edit(GOOD))
    with pytest.raises(CrawlError) as e:
        dblp_aaai.check_extract(extract, aaai)
    assert e.value.reason == reason


def test_2010_on_is_never_read(tmp_path: Path) -> None:
    _t, aaai, extract = setup(tmp_path)
    dblp_aaai.check_extract(extract, aaai)  # conf/aaai/2024 is in the extract and unlisted: ignored
    with pytest.raises(CrawlError):
        dblp_aaai.mine_year(2024, extract, table=aaai)


def test_an_aaai_dblp_record_names_itself_and_passes_dedup(tmp_path: Path) -> None:
    _t, aaai, extract = setup(tmp_path)
    records = dblp_aaai.mine_year(1986, extract, table=aaai).records
    assert len(dedup(records).records) == 2  # dedup's self-naming check: urls.native reads /rec/conf/aaai/
    assert urls.native("https://dblp.org/rec/conf/aaai/Synthetic86a") == "dblp-Synthetic86a"
    assert statuses_indexed(["dblp"], "AAAI", 1986) == ["accepted"]


def test_ingest_marks_each_year_and_the_replay_rebuilds_it(tmp_path: Path, monkeypatch) -> None:
    table, aaai, _ = setup(tmp_path)
    monkeypatch.setattr(dblp_aaai, "TABLE", aaai)
    out = crawl.ingest_dblp_aaai(range(1985, 1987), tmp_path, offline=True, table=table, aaai=aaai)
    assert out["not_held"] == [1985] and [x["year"] for x in out["listings"]] == [1986]
    marker = json.loads((tmp_path / "dblp" / "aaai-crawls" / "1986.json").read_text())
    assert marker == {"source": "dblp", "venue": "AAAI", "year": 1986, "release": table.release.doi}
    assert not (tmp_path / "dblp" / "crawls").exists()  # ICML's replay never sees an AAAI marker
    monkeypatch.setattr(crawl, "DBLP_TABLE", table)
    (replayed,) = crawl.DBLP_AAAI.replay(tmp_path)
    assert sorted(r.id for r in replayed.records) == [
        "op:aaai:1986:dblp-Synthetic86a",
        "op:aaai:1986:dblp-Synthetic86b",
    ]


def test_a_marker_from_another_dblp_release_never_replays(tmp_path: Path, monkeypatch) -> None:
    table, aaai, _ = setup(tmp_path)
    monkeypatch.setattr(dblp_aaai, "TABLE", aaai)
    crawl.ingest_dblp_aaai([1986], tmp_path, offline=True, table=table, aaai=aaai)
    marker = tmp_path / "dblp" / "aaai-crawls" / "1986.json"
    marker.write_text(json.dumps(json.loads(marker.read_text()) | {"release": "10.4230/dblp.xml.1999-01-01"}))
    monkeypatch.setattr(crawl, "DBLP_TABLE", table)  # pinned to the release the extract was written from
    with pytest.raises(crawl.MinerError, match=re.escape("10.4230/dblp.xml.1999-01-01")) as e:
        crawl.DBLP_AAAI.replay(tmp_path)
    assert e.value.reason == "release_changed"


def test_a_year_outside_the_table_is_refused(tmp_path: Path) -> None:
    table, aaai, _ = setup(tmp_path)
    with pytest.raises(CrawlError, match="AAAI 1990"):
        crawl.ingest_dblp_aaai([1990], tmp_path, offline=True, table=table, aaai=aaai)


def test_a_2024_key_is_never_a_record_and_never_a_counted_paper(tmp_path: Path) -> None:
    _t, aaai, extract = setup(tmp_path)
    assert any(e.key == "conf/aaai/Late24" for e in extract.entries)  # the extract holds it
    made = [(y, dblp_aaai.mine_year(y, extract, table=aaai)) for y in aaai.years]
    assert all("Late24" not in r.id for _y, m in made for r in m.records)
    assert all(rep.listed == rep.stated for _y, m in made for rep in m.reports)  # nothing extra counted
    assert all(not any("2024" in k for k in rep.skipped) for _y, m in made for rep in m.reports)
    with pytest.raises(CrawlError) as e:
        dblp_aaai.mine_year(2024, extract, table=aaai)
    assert e.value.reason == "no_year"


# TASK-226: the official contents' sections as dblp start-page ranges, and a key row for a page typo
_PAGED = "".join(
    f'<inproceedings mdate="2020-01-01" key="conf/aaai/{key}"><author>Synthetic Author 9</author>'
    f"<title>Synthetic {key}.</title>{f'<pages>{pages}</pages>' if pages else ''}<year>2006</year>"
    "<crossref>conf/aaai/2006</crossref></inproceedings>\n"
    for key, pages in [("Stud06", "1853-1854"), ("Cons06", "1904-1905"), ("Typo06", "855-1856"),
                       ("Late06", "1931-1932")]
)  # fmt: skip


def paged(tmp_path: Path, text: str, main06_pages: str | None = "10-15"):
    body = test_dblp_slices.FULL.replace("</dblp>\n", _PAGED + "</dblp>\n")
    if main06_pages is not None:  # the synthetic release gives Main06 no pages; a sectioned year needs one
        body = body.replace("<title>Synthetic main paper.</title>",
                            f"<title>Synthetic main paper.</title><pages>{main06_pages}</pages>")  # fmt: skip
    gz = test_dblp_slices.gzip.compress((test_dblp_slices.HEAD + body).encode("latin-1"), mtime=0)
    table, rel, dtd = on_disk(tmp_path, gz)
    aaai = dblp_aaai_table.load(text.replace("papers = 1\ntitle = \"Synthetic AAAI 2006\"",
                                             "papers = 5\ntitle = \"Synthetic AAAI 2006\""), pins=table)  # fmt: skip
    return aaai, dblp.write_extracts(tmp_path, rel, dtd, table, dblp.SLICES)["AAAI"]


def test_a_section_range_or_a_track_row_gives_a_main_key_entry_its_track(tmp_path: Path) -> None:
    aaai, extract = paged(tmp_path, GOOD + SECTIONS)
    dblp_aaai.check_extract(extract, aaai)
    records = {r.native: r for r in dblp_aaai.mine_year(2006, extract, table=aaai).records}
    assert {n: r.track for n, r in records.items()} == {
        "dblp-Main06": "main", "dblp-Late06": "main", "dblp-Stud06": "student_abstract",
        "dblp-Cons06": "consortium", "dblp-Typo06": "student_abstract", "dblp-Workshop06": "workshop"}  # fmt: skip
    claim = next(c for c in records["dblp-Stud06"].provenance if c.field == "track")
    assert claim.evidence == (
        'crossref conf/aaai/2006, dblp pages 1853-1854 (start page 1853): in AAAI 2006\'s official contents section '
        '"Student Abstracts", pp. 1853-1903 (dblp_aaai.toml [[section]], verified 2026-10-10; test contents page)'
    )  # fmt: skip
    typo = next(c for c in records["dblp-Typo06"].provenance if c.field == "track")
    assert "dblp_aaai.toml [[track]]" in typo.evidence and "a typo" in typo.evidence
    main = next(c for c in records["dblp-Late06"].provenance if c.field == "track")
    assert main.evidence == "crossref conf/aaai/2006: AAAI 2006 main conference (dblp_aaai.toml)"  # unchanged


def test_a_section_that_holds_no_paper_stops_the_year(tmp_path: Path) -> None:
    aaai, extract = paged(tmp_path, GOOD + SECTIONS.replace("pages = [1904, 1930]", "pages = [1990, 1999]"))
    with pytest.raises(CrawlError, match="Doctoral Consortium") as e:
        dblp_aaai.mine_year(2006, extract, table=aaai)
    assert e.value.reason == "stale_section"


@pytest.mark.parametrize("key", ["conf/aaai/Nowhere06", "conf/aaai/Workshop06", "conf/aaai/Synthetic86a"])
def test_a_track_row_must_name_a_main_entry_of_its_year(tmp_path: Path, key: str) -> None:
    aaai, extract = paged(tmp_path, GOOD + SECTIONS.replace('key = "conf/aaai/Typo06"', f'key = "{key}"'))
    with pytest.raises(CrawlError, match="track row") as e:
        dblp_aaai.check_extract(extract, aaai)
    assert e.value.reason == "table_mismatch"


@pytest.mark.parametrize("pages", [None, "I-IV", "1" * 5000])
def test_an_entry_a_sectioned_year_cannot_place_stops_the_year(tmp_path: Path, pages: str | None) -> None:
    aaai, extract = paged(tmp_path, GOOD + SECTIONS, main06_pages=pages)
    with pytest.raises(CrawlError, match="Main06") as e:
        dblp_aaai.mine_year(2006, extract, table=aaai)
    assert e.value.reason == "unplaced_page"
    # a key row places it, and a year with no section rows reads it as main
    row = '\n[[track]]\nkey = "conf/aaai/Main06"\nyear = 2006\ntrack = "other"\nreason = "r"\nverified = 2026-10-10\nsource = "s"\n'
    aaai, extract = paged(tmp_path / "b", GOOD + SECTIONS + row, main06_pages=pages)
    assert {r.native: r.track for r in dblp_aaai.mine_year(2006, extract, table=aaai).records}[
        "dblp-Main06"
    ] == "other"
    aaai, extract = paged(tmp_path / "c", GOOD, main06_pages=pages)
    assert {r.native: r.track for r in dblp_aaai.mine_year(2006, extract, table=aaai).records}[
        "dblp-Main06"
    ] == "main"


def test_a_pageless_entry_of_a_year_without_its_own_section_rows_is_main(tmp_path: Path) -> None:
    """Only a year with its own section rows refuses a pageless entry: here only 1986 has one."""
    other_year = SECTIONS.split("[[section]]")[1].replace("year = 2006", "year = 1986", 1)
    aaai, extract = paged(tmp_path, GOOD + "[[section]]" + other_year, main06_pages=None)
    assert [s.year for s in aaai.sections] == [1986]
    tracks = {r.native: r.track for r in dblp_aaai.mine_year(2006, extract, table=aaai).records}
    assert tracks["dblp-Main06"] == "main"
