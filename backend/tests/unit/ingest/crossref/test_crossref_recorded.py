"""Recorded Crossref pages (2026-10-10, scrubbed: real DOIs, cursors and counts; synthetic titles and authors)
pinned to the shipped table: FAccT 2019's chain mines to its table count."""

from pathlib import Path

from openproceedings.ingest import acm_table
from openproceedings.ingest.sources import crossref
from openproceedings.ingest.sources.http import Fetcher, PageCache

from tests.unit.ingest.proceedings_helpers import fixture, seed

CR = Path(__file__).parents[3] / "fixtures" / "http" / "crossref"


def test_facct_2019_mines_to_its_table_count(tmp_path: Path) -> None:
    for p in CR.glob("facct-2019-*.json"):
        f = fixture(f"crossref/{p.name}")
        seed(tmp_path, "crossref", f["request"]["url"], f["response"]["text"], keep_query=True)
    offline = Fetcher(
        PageCache(tmp_path / "crossref"), None, hosts=crossref.HOSTS, expect="json", keep_query=True
    )
    result = crossref.mine_proceedings("FAccT", 2019, offline)
    assert len(result.records) == acm_table.TABLE.expected("FAccT", 2019)
    assert all(r.title.startswith("Synthetic title") for r in result.records)
    report = result.reports[0]
    assert (report.count_ok, report.pages, report.no_authors) == (True, 2, 0)
    assert report.window_works == 44  # the trimmed page: the 41 plus 3 foreign works
