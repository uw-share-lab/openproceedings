"""Recorded OpenAlex answers (the census of 2026-10-10, keyless; scrubbed: real work ids, DOIs, years, source ids and
counts; synthetic titles; every `abstract_inverted_index` rebuilt from synthetic text of the same word count, so
every one is dense) pinned to the parser, the rebuild and the shipped listing table."""

import re
from pathlib import Path

from openproceedings.ingest import openalex_table
from openproceedings.ingest.sources import openalex
from openproceedings.ingest.sources.http import Fetcher, PageCache

from tests.unit.ingest.proceedings_helpers import fixture, seed

OA = Path(__file__).parents[3] / "fixtures" / "http" / "openalex"
FIXTURES = ("openalex/doi-batch.json", "openalex/listing-1984.json")
# the census: AAAI 1980-2008's held years, each listed under S4306420577 (not held: 1981, 1985, 1989, 1995, 2001,
# 2003; dblp has no AAAI 2009)
CENSUS_YEARS = (1980, 1982, 1983, 1984, 1986, 1987, 1988, 1990, 1991, 1992, 1993, 1994, 1996, 1997, 1998, 1999,
                2000, 2002, 2004, 2005, 2006, 2007, 2008)  # fmt: skip


def _page(rel: str) -> openalex.WorksPage:
    return openalex.parse_works(fixture(rel)["response"]["text"])


def test_every_recorded_answer_parses_and_every_index_rebuilds() -> None:
    assert sorted(f"openalex/{p.name}" for p in OA.glob("*.json")) == sorted(FIXTURES)
    for rel in FIXTURES:
        page = _page(rel)
        assert page.works and page.total == len(page.works) and page.next_cursor is None
        for w in page.works:
            assert w.title is not None and w.title.startswith("Synthetic title")
            rebuilt = openalex.rebuild(w.inverted)
            assert rebuilt.refused is None
            assert (rebuilt.text is None) == (w.inverted is None)


def test_the_doi_batch_returns_only_what_it_asked_for() -> None:
    """FAccT 2023, 50 DOIs: the census found no DOI returned twice, cut off or unrequested in this batch (the five
    duplicates it found are in other batches)."""
    f = fixture("openalex/doi-batch.json")
    m = re.search(r"filter=doi:([^&]+)", f["request"]["url"])
    assert m is not None
    requested = m.group(1).split("|")
    assert len(requested) == 50 and all(d.startswith("10.1145/3593013.") for d in requested)
    assert f["request"]["url"] == openalex.doi_url(requested)  # the URL `op ingest openalex` asks
    returned = [w.doi for w in _page("openalex/doi-batch.json").works]
    assert sorted(d for d in returned if d) == sorted(requested)  # each once, none foreign
    assert all(
        w.sources == ("S4363608463",) and w.year == 2023 for w in _page("openalex/doi-batch.json").works
    )


def test_the_shipped_table_holds_the_census_years() -> None:
    rows = openalex_table.TABLE.listings
    assert sorted(rows) == [("AAAI", y) for y in CENSUS_YEARS]
    assert {r.source_ids for r in rows.values()} == {("S4306420577",)}
    assert sum(r.works for r in rows.values()) == 1902


def test_the_1984_listing_replays_against_its_table_row(tmp_path: Path) -> None:
    """The recorded page is the table row's own URL, and its count is the row's verified `works`: the crawl's
    listing step reads it offline without a `count_mismatch`."""
    row = openalex_table.TABLE.listings[("AAAI", 1984)]
    f = fixture("openalex/listing-1984.json")
    assert f["request"]["url"] == openalex.listing_url(row)
    seed(tmp_path, openalex.CACHE_DIR, f["request"]["url"], f["response"]["text"], keep_query=True)
    offline = Fetcher(PageCache(tmp_path / openalex.CACHE_DIR), None, hosts=openalex.HOSTS, expect="json",
                      keep_query=True)  # fmt: skip
    lookup = openalex._listing(row, offline, refresh=False)
    assert len(lookup.works) == row.works == 32
    assert all(w.sources == row.source_ids and w.year == 1984 for w in lookup.works)
