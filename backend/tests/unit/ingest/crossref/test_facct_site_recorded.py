"""The recorded FAccT site pages (2026-10-10, scrubbed: real ids, URLs, DOIs and page structure; synthetic titles,
authors and abstracts; trimmed to 20 entries each) read with the shipped table's parsers, and the shipped table."""

import re
from datetime import date
from pathlib import Path

import pytest
from openproceedings.ingest.sources import facct_site
from openproceedings.ingest.sources.http import Fetcher, PageCache

from tests.unit.ingest.proceedings_helpers import fixture, seed

FIXTURES = {2022: "facct_site/2022-acceptedpapers.json", 2025: "facct_site/2025-final.json",
            2026: "facct_site/2026-final.json"}  # fmt: skip


def _trimmed(rel: str) -> int:
    m = re.match(r"([0-9]+) of ([0-9]+)", fixture(rel)["_recorded"]["trimmed"])
    assert m is not None
    return int(m.group(1))


def test_the_shipped_table_names_the_three_official_pages_with_their_live_counts() -> None:
    assert set(facct_site.TABLE) == {2022, 2025, 2026}
    t = facct_site.TABLE
    assert (t[2022].join, t[2025].join, t[2026].join) == ("title", "doi", "title")
    assert (t[2022].rows, t[2025].rows, t[2026].rows) == (181, 217, 325)
    for year, rel in FIXTURES.items():
        assert t[year].url == fixture(rel)["request"]["url"]
        assert t[year].verified == date(2026, 10, 10)


@pytest.mark.parametrize("year", sorted(FIXTURES))
def test_each_recorded_page_parses_to_its_trimmed_count(year: int) -> None:
    rel = FIXTURES[year]
    got = facct_site.PARSERS[facct_site.TABLE[year].parser](fixture(rel)["response"]["text"])
    assert len(got) == _trimmed(rel) == 20
    assert len({e.key for e in got}) == 20 and all(e.title and e.abstract for e in got)


@pytest.mark.parametrize("year", sorted(FIXTURES))
def test_each_recorded_page_reads_through_the_fetcher_as_served(tmp_path: Path, year: int) -> None:
    """The page as served (2025 and 2026: `application/octet-stream`, no byte-order mark), read by `read_year`
    with the shipped row's count set to the trimmed one."""
    rel = FIXTURES[year]
    f = fixture(rel)
    assert f["response"]["headers"]["content-type"] == (
        "text/html" if year == 2022 else "application/octet-stream"
    )
    seed(tmp_path, "facct_site", f["request"]["url"], f["response"]["text"])
    offline = Fetcher(PageCache(tmp_path / "facct_site"), None, hosts=facct_site.HOSTS, expect="text")
    row = facct_site.TABLE[year]
    table = facct_site.load(f"""[[page]]
year = {year}
url = "{row.url}"
parser = "{row.parser}"
join = "{row.join}"
rows = 20
verified = {row.verified.isoformat()}
note = "the recorded fixture, trimmed"
""")  # fmt: skip
    got = facct_site.read_year(year, offline, table=table)
    assert got is not None and (len(got.entries), got.dropped, got.join, got.page) == (
        20,
        0,
        row.join,
        row.url,
    )
    assert all(e.evidence == f"{row.url} row {e.key}" for e in got.entries)


def test_the_2026_csv_as_recorded_has_no_byte_order_mark_and_bare_newlines() -> None:
    text = fixture(FIXTURES[2026])["response"]["text"]
    assert not text.startswith("\ufeff") and "\r" not in text and text.count("\n") == 21
    assert all(e.doi is None for e in facct_site.facct2026_csv(text))  # no DOI column: the join is by title


def test_the_2025_dois_all_extend_the_proceedings_and_only_archival_rows_have_one() -> None:
    text = fixture(FIXTURES[2025])["response"]["text"]
    got = facct_site.facct2025_csv(text)
    dois = [e.doi for e in got if e.doi is not None]
    assert len(dois) == 14 and all(d.startswith("10.1145/3715275.") for d in dois)
    assert sum(e.doi is None for e in got) == 6  # the six non-archival rows: SSRN, arXiv or empty URL


def test_the_2022_page_keeps_entry_295_by_title_and_the_spaced_id() -> None:
    got = facct_site.facct2022_html(fixture(FIXTURES[2022])["response"]["text"])
    keys = [e.key for e in got]
    assert {"295", "314", "17"} <= set(keys) and keys[0] == "1002"
    assert all(e.doi is None for e in got)  # entry 295 links entry 314's DOI: no page DOI is ever trusted
