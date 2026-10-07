"""ICML 1988-2012 from the pinned dblp release (TASK-205, decision-047): the table, the release on disk and its
extract, the check against the table, and the records.

The release is the synthetic excerpt of `test_dblp_xml.py` (decision-004: real keys and framing, synthetic text),
pinned by its own sha256 in a test table, and served by a scripted streaming transport. No network.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from openproceedings.ingest import dblp_table
from openproceedings.ingest.dedup import dedup
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.sources import dblp, dblp_xml, icml_sites
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.sources.http import CacheMiss
from openproceedings.ingest.statuses import statuses_indexed

from tests.unit.ingest.proceedings_helpers import FakeTransport, response
from tests.unit.ingest.test_dblp_xml import BODY, DTD, DTD_NAME, HEAD, Stream

GZ = gzip.compress((HEAD + BODY).encode("latin-1"), mtime=0)
REAL = dblp_table.TABLE


def table_text(*, papers: int = 1, extra: str = "", sha: str | None = None) -> str:
    return f"""
[release]
doi = "10.4230/dblp.xml.2026-10-03"
url = "https://drops.dagstuhl.de/storage/artifacts/dblp/xml/2026/dblp-test.xml.gz"
size = {len(GZ)}
sha256 = "{sha or hashlib.sha256(GZ).hexdigest()}"
license = "CC0 1.0"
verified = 2026-10-06

[dtd]
doi = "10.4230/dblp.xml.dtd.2023-06-28"
url = "https://drops.dagstuhl.de/storage/artifacts/dblp/xml/2023/{DTD_NAME}"
size = {len(DTD)}
sha256 = "{hashlib.sha256(DTD).hexdigest()}"
license = "CC0 1.0"
verified = 2026-10-06

[[year]]
year = 1990
proceedings = ["conf/icml/1990"]
papers = {papers}
title = "Machine Learning, Proceedings of the Seventh International Conference on Machine Learning"
verified = 2026-10-06
source = "test"

[[year]]
year = 2009
proceedings = ["conf/icml/2009"]
papers = 1
title = "ICML 2009"
verified = 2026-10-06
source = "test"

[[excluded]]
key = "conf/icml/2006sna"
year = 2007
reason = "a workshop"
{extra}"""


TABLE = dblp_table.load(table_text())


def stream() -> Stream:
    return Stream((200, DTD), (200, GZ))


def prepared(tmp_path: Path, table: dblp_table.Table = TABLE) -> dblp.Extract:
    release, dtd = dblp.fetch_release(tmp_path, stream(), table)
    extract = dblp.write_extract(tmp_path, release, dtd, table)
    assert dblp.load_extract(tmp_path, table) == extract  # the replay reads back what was written
    return extract


# --- the table -------------------------------------------------------------------------------------------------


def test_the_shipped_table_pins_one_release_and_every_year_1988_to_2012() -> None:
    assert REAL.release.doi == "10.4230/dblp.xml.2026-10-03" and REAL.dtd.filename == DTD_NAME
    assert REAL.release.file.sha256 == "20e45961bec5610dc07b8e932ccd27a2387534cfa12c92a24289fe873aebe969"
    assert REAL.dtd.file.sha256 == hashlib.sha256(DTD).hexdigest()  # the fixture is the pinned DTD
    assert sorted(REAL.years) == list(range(1988, 2013))
    assert sum(y.papers for y in REAL.years.values()) == 2676
    assert all(y.proceedings == (f"conf/icml/{y.year}",) for y in REAL.years.values())
    assert set(REAL.excluded) == {
        "conf/icml/2006sna",
        "conf/icml/2010ltr",
        "conf/icml/2011otee",
        "conf/icml/2011utl",
    }


@pytest.mark.parametrize(
    ("edit", "why"),
    [
        (lambda t: t.replace("year = 2009\n", "year = 2013\n"), "a year from 1988 to 2012"),
        (lambda t: t.replace('"conf/icml/2009"]', '"conf/icml/2009", "conf/icml/1990"]'), "under two years"),
        (lambda t: t.replace("drops.dagstuhl.de/storage/artifacts/dblp/xml/2026", "dblp.org/xml/release"),
         "dblp.org forbids crawling"),
        (lambda t: t + '\n[[excluded]]\nkey = "conf/icml/1990"\nyear = 1990\nreason = "x"\n', "both excluded and"),
        (lambda t: t.replace('source = "test"', 'source = "test"\nextra = 1', 1), "unknown columns"),
    ],
)  # fmt: skip
def test_a_malformed_table_is_refused(edit: object, why: str) -> None:
    with pytest.raises(ValueError, match=why):
        dblp_table.load(edit(table_text()))  # type: ignore[operator]


# --- the release and its extract ---------------------------------------------------------------------------------


def test_the_release_is_fetched_once_read_into_its_extract_and_replayed_from_it(tmp_path: Path) -> None:
    extract = prepared(tmp_path)
    assert (extract.doi, extract.sha256) == (TABLE.release.doi, TABLE.release.file.sha256)
    assert [e.key for e in extract.entries][:2] == ["conf/icml/Synthetic90", "conf/icml/1990"]
    saved = json.loads(dblp.extract_path(tmp_path, TABLE).read_text())
    assert (saved["release_doi"], saved["dtd_sha256"]) == (TABLE.release.doi, TABLE.dtd.file.sha256)
    # offline the verified copies are used, and an extract naming another release is refused
    dblp.fetch_release(tmp_path, None, TABLE)
    other = dblp_table.load(table_text(sha="0" * 64))
    with pytest.raises(CrawlError, match="no dblp extract"):
        dblp.load_extract(tmp_path, other)
    with pytest.raises(CacheMiss):
        dblp.fetch_release(tmp_path, None, other)


def test_an_unclassified_icml_proceedings_key_or_a_stale_table_stops_the_ingest(tmp_path: Path) -> None:
    extract = prepared(tmp_path)
    dblp.check_extract(extract, TABLE)  # 2006sna is excluded; 1990 is listed
    no_exclusion = dblp_table.load(table_text().split("[[excluded]]")[0])
    with pytest.raises(CrawlError, match="neither a main conference nor excluded") as e:
        dblp.check_extract(extract, no_exclusion)
    assert e.value.reason == "unlisted_proceedings"
    # the table names conf/icml/2009, which this release doesn't hold as a proceedings record
    stale = dblp_table.load(table_text())
    assert "conf/icml/2009" in stale.years[2009].proceedings
    with pytest.raises(CrawlError, match="doesn't hold it") as e:
        dblp.check_extract(dblp.Extract(extract.doi, extract.sha256, extract.fetched_at,
                                        tuple(x for x in extract.entries if x.key != "conf/icml/1990")), stale)  # fmt: skip
    assert e.value.reason == "table_mismatch"


# --- records -------------------------------------------------------------------------------------------------------


def test_a_main_conference_paper_becomes_an_accepted_main_icml_record_naming_the_release(
    tmp_path: Path,
) -> None:
    extract = prepared(tmp_path)
    result = dblp.mine_year(1990, extract, table=TABLE)
    [r] = result.records
    assert r.id == "op:icml:1990:dblp-Synthetic90"
    assert (r.venue, r.year, r.track, r.status, r.abstract) == ("ICML", 1990, "main", "accepted", None)
    assert r.title == "Synthetic title with markup 1"  # dblp's closing period dropped
    assert r.authors == ("Synthetic Author 2", "Synthütic Author 3")  # homonym number dropped
    assert r.urls.doi == "10.1016/b978-1-55860-141-3.50001-0" and r.urls.pdf is None  # wikidata dropped
    assert (
        r.urls.proceedings == "https://dblp.org/rec/conf/icml/Synthetic90"
    )  # names the native id; never fetched
    assert r.venue_name == "International Conference on Machine Learning (ICML 1990)"
    for c in r.provenance:
        assert c.source == "dblp" and c.url == "https://doi.org/10.4230/dblp.xml.2026-10-03"
        assert c.fetched_at == extract.fetched_at
    [status] = r.claims("status")
    assert "conf/icml/Synthetic90" in (status.evidence or "") and "10.4230/dblp.xml.2026-10-03" in (
        status.evidence or ""
    )
    [report] = result.reports
    assert (report.stated, report.listed, report.records, report.count_ok) == (1, 1, 1, True)
    assert (report.abstract_missing, report.role, report.source) == (1, "primary", "dblp")
    assert report.to_manifest()["listing"] == "https://doi.org/10.4230/dblp.xml.2026-10-03"


def test_withdrawn_and_workshop_papers_are_counted_never_records(tmp_path: Path) -> None:
    extract = prepared(tmp_path)
    r2009 = dblp.mine_year(2009, extract, table=TABLE)
    assert r2009.records == [] and dict(r2009.reports[0].skipped) == {"publtype_withdrawn": 1}
    table = dblp_table.load(table_text(extra='\n[[year]]\nyear = 2006\nproceedings = ["conf/icml/2006"]\npapers = 1\n'
                                       'title = "x"\nverified = 2026-10-06\nsource = "test"\n'))  # fmt: skip
    r2006 = dblp.mine_year(2006, extract, table=table)
    assert r2006.records == [] and dict(r2006.reports[0].skipped) == {"excluded_proceedings": 1}
    assert r2006.reports[0].count_ok is False  # the table says 1; the release lists none: a WARNING, reported
    with pytest.raises(CrawlError, match="no row"):
        dblp.mine_year(2013, extract, table=TABLE)


@pytest.mark.parametrize(
    ("raw", "title"),
    [
        ("A title.", "A title"),
        ("Is it?", "Is it?"),
        ("Yes!", "Yes!"),
        ("Wait..", "Wait.."),
        ("No period", "No period"),
    ],
)
def test_only_dblps_closing_period_is_dropped(raw: str, title: str) -> None:
    assert dblp.clean_title(raw) == title


def test_links_keep_the_dblp_page_dois_and_icml_pdfs_only() -> None:
    assert dblp.links("conf/icml/WestonWWB12", [
        "https://www.wikidata.org/entity/Q1", "https://doi.org/10.1145/1553374.1553502",
        "http://icml.cc/2012/papers/12.pdf", "http://www.aaai.org/Library/ICML/2003/icml03-068.php",
        "https://orkg.org/paper/R1",
    ]) == {
        "urls.proceedings": "https://dblp.org/rec/conf/icml/WestonWWB12",
        "urls.doi": "10.1145/1553374.1553502", "urls.pdf": "http://icml.cc/2012/papers/12.pdf",
    }  # fmt: skip


def test_dblp_records_are_proceedings_only_accepted_and_merge_with_nothing_else(tmp_path: Path) -> None:
    records = dblp.mine_year(1990, prepared(tmp_path), table=TABLE).records
    assert statuses_indexed({"dblp"}, "ICML", 1990) == ["accepted"]
    result = dedup(records)
    assert [r.id for r in result.records] == [r.id for r in records] and not result.merges


def test_a_proceedings_record_with_no_readable_year_must_be_classified(tmp_path: Path) -> None:
    extract = prepared(tmp_path)
    no_year = dblp_xml.DblpEntry("proceedings", "conf/icml/odd", "2020-01-01", None, {"title": "x"}, {})
    with pytest.raises(CrawlError, match="no year") as e:
        dblp.check_extract(dblp.Extract(extract.doi, extract.sha256, extract.fetched_at,
                                        (*extract.entries, no_year)), TABLE)  # fmt: skip
    assert e.value.reason == "unlisted_proceedings"


def test_a_stale_extract_is_written_again_from_the_cached_release(tmp_path: Path) -> None:
    prepared(tmp_path)
    path = dblp.extract_path(tmp_path, TABLE)
    stale = json.loads(path.read_text())
    stale["format"] = "0"
    path.write_text(json.dumps(stale))
    with pytest.raises(CrawlError, match="malformed"):
        dblp.load_extract(tmp_path, TABLE)
    again = dblp.prepare(tmp_path, None, TABLE)  # offline: the release is on disk, so it is read again
    assert json.loads(path.read_text())["format"] == dblp.EXTRACT_FORMAT and again.entries


def test_a_year_marked_under_another_release_is_refused_on_replay(tmp_path: Path) -> None:
    from openproceedings.ingest.sources import crawl

    with pytest.raises(CrawlError, match="not the pinned") as e:
        crawl._replay_dblp(tmp_path, (1990, "10.4230/dblp.xml.2026-09-01"))
    assert e.value.reason == "release_changed"


@pytest.mark.parametrize("year", [2013, 2024])  # PMLR's years; before 1988 the venue name refuses it first
def test_a_dblp_id_outside_1988_to_2012_is_refused(tmp_path: Path, year: int) -> None:
    [r] = dblp.mine_year(1990, prepared(tmp_path), table=TABLE).records
    with pytest.raises(ValueError, match="ICML 1988-2012"):
        PaperRecord.model_validate(
            r.model_dump(exclude={"venue_name"}) | {"id": f"op:icml:{year}:dblp-Synthetic90", "year": year},
            context={"rehash": True},
        )


def test_a_table_year_the_release_dates_otherwise_or_a_later_icml_key_are_judged_right(
    tmp_path: Path,
) -> None:
    extract = prepared(tmp_path)
    # a conf/icml/ proceedings record of 2013 on is PMLR's years: never classified here (the real release has 25)
    later = dblp_xml.DblpEntry("proceedings", "conf/icml/2025p", "2025-07-01", None, {"year": "2025"}, {})
    dblp.check_extract(dblp.Extract(extract.doi, extract.sha256, extract.fetched_at,
                                    (*extract.entries, later)), TABLE)  # fmt: skip
    # the table names conf/icml/1990 for 1990, but this release dates it 1991
    moved = tuple(
        dblp_xml.DblpEntry(e.type, e.key, e.mdate, e.publtype, e.fields | {"year": "1991"}, e.lists)
        if e.key == "conf/icml/1990" else e for e in extract.entries
    )  # fmt: skip
    with pytest.raises(CrawlError, match="doesn't hold it") as e:
        dblp.check_extract(dblp.Extract(extract.doi, extract.sha256, extract.fetched_at, moved), TABLE)
    assert e.value.reason == "table_mismatch"


def test_an_informal_or_repeated_paper_is_counted_never_a_record(tmp_path: Path) -> None:
    extract = prepared(tmp_path)
    [paper] = [e for e in extract.entries if e.key == "conf/icml/Synthetic90"]
    informal = dblp_xml.DblpEntry(
        paper.type, "conf/icml/Informal90", paper.mdate, "informal", paper.fields, paper.lists
    )
    more = dblp.Extract(extract.doi, extract.sha256, extract.fetched_at, (*extract.entries, informal, paper))
    result = dblp.mine_year(1990, more, table=TABLE)
    assert [r.id for r in result.records] == ["op:icml:1990:dblp-Synthetic90"]
    assert dict(result.reports[0].skipped) == {"publtype_informal": 1, "duplicate": 1}


# --- `op ingest dblp` and the replay `op snapshot build` runs --------------------------------------------------

SITE = "https://icml.cc/Conferences/1990/abstracts.html"
SITE_PAGE = (
    "<html><table border><tr><th>Synthetic title with markup 1</th></tr><tr><td>Synthetic Author 2</td></tr>"
    "<tr><td><pre>Synthetic abstract from the official page.</pre></td></tr></table></html>"
)


def site_pages() -> dict[int, tuple[icml_sites.SitePage, ...]]:
    return {1990: (icml_sites.SitePage(1990, SITE, SITE, "cyberchair", "cp1252", 1, date(2026, 10, 6), "t"),)}


def test_ingest_dblp_marks_each_year_under_the_release_and_the_replay_gives_the_same_records(
    tmp_path: Path,
) -> None:
    from openproceedings.ingest.sources import crawl

    pages = FakeTransport({SITE: response(SITE_PAGE)})
    out = crawl.ingest_dblp(
        [1990], tmp_path, stream=stream(), transport=pages, table=TABLE, pages=site_pages()
    )
    [listing] = out["listings"]
    assert (listing["records"], listing["abstract_attached"], listing["sites"]) == (1, 1, [SITE])
    marker = json.loads((tmp_path / "dblp" / "crawls" / "1990.json").read_text())
    assert marker == {"source": "dblp", "year": 1990, "release": TABLE.release.doi}
    [record] = dblp.mine_year(1990, dblp.load_extract(tmp_path, TABLE), table=TABLE,
                              site=icml_sites.read_year(1990, crawl.fetcher(
                                  tmp_path, icml_sites.CACHE_DIR, frozenset({"icml.cc"}), offline=True),
                                  pages=site_pages())).records  # fmt: skip
    replayed = crawl._replay_dblp(tmp_path, (1990, TABLE.release.doi), TABLE, site_pages())
    assert replayed.records == [record] and record.abstract == "Synthetic abstract from the official page."
    # offline, from the files already on disk: the same records, nothing fetched
    again = crawl.ingest_dblp([1990], tmp_path, offline=True, table=TABLE, pages=site_pages())
    assert again["requests"] == 0 and again["listings"] == out["listings"]


def test_ingest_dblp_dry_run_fetches_nothing_and_a_year_off_the_table_is_refused(tmp_path: Path) -> None:
    from openproceedings.ingest.sources import crawl

    dry = crawl.ingest_dblp([1990], tmp_path, dry_run=True, stream=Stream(), table=TABLE, pages=site_pages())
    assert dry == {"dry_run": True, "release_on_disk": False, "extract_on_disk": False,
                   "years": [{"year": 1990, "pages": 1, "to_fetch": 1}], "requests": 0, "cached": 0}  # fmt: skip
    with pytest.raises(CrawlError, match="covers ICML") as e:
        crawl.ingest_dblp([2013], tmp_path, table=TABLE, pages=site_pages())
    assert e.value.reason == "no_year"
