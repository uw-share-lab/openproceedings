"""Recorded ojs.aaai.org pages (2026-10-09, scrubbed by `fixtures/http/scrub.py`'s OAI branch) pinned to the shipped
table: each parses, every live record's (volume, set) has a row, and IASEAI, recorded whole, mines to its 57 papers."""

from pathlib import Path

import pytest
from openproceedings.ingest.ojs_table import TABLE
from openproceedings.ingest.sources import ojs
from openproceedings.ingest.sources.http import Fetcher, PageCache

from tests.unit.ingest.proceedings_helpers import T0, fixture, seed

OJS = Path(__file__).parents[3] / "fixtures" / "http" / "ojs"
LIST_PAGES = sorted(p.name for p in OJS.glob("*.json") if "-first-page" in p.name or "-set-" in p.name)


def _text(name: str) -> str:
    return str(fixture(f"ojs/{name}")["response"]["text"])


def test_the_recorded_pages_are_there() -> None:
    assert {"aaai-first-page.json", "aies-first-page.json", "iaseai-sets.json", "iaseai-inventory.json"} <= {
        p.name for p in OJS.glob("*.json")
    }
    assert all(p.stat().st_size < 300_000 for p in OJS.glob("*.json"))


@pytest.mark.parametrize("name", LIST_PAGES)
def test_every_live_record_has_a_table_row(name: str) -> None:
    journal = name.split("-")[0].upper()
    records, _token = ojs.parse_page(_text(name))
    live = [r for r in records if not r.deleted]
    assert live or name == "iaseai-set-ART-1.json"  # IASEAI:ART is an empty set (noRecordsMatch)
    for r in live:
        assert r.volume is not None and (journal, r.volume, r.set_spec) in TABLE.sections, (
            r.article,
            r.set_spec,
        )


def test_the_recorded_text_is_synthetic() -> None:
    records, _ = ojs.parse_page(_text("aaai-first-page.json"))
    live = [r for r in records if not r.deleted]
    assert len(live) == 100
    assert all((r.title or "").startswith("Synthetic title") for r in live)
    assert all((r.description or "").startswith("Synthetic abstract") for r in live if r.description)


def _iaseai_cache(tmp_path: Path) -> Fetcher:
    for p in OJS.glob("iaseai-*.json"):
        fx = fixture(f"ojs/{p.name}")
        seed(tmp_path, "ojs", fx["request"]["url"], fx["response"]["text"], at=T0, keep_query=True)
    return Fetcher(PageCache(tmp_path / "ojs"), None, hosts=ojs.HOSTS, expect="xml", keep_query=True)


def test_iaseai_recorded_whole_mines_to_its_57_papers(tmp_path: Path) -> None:
    result = ojs.mine_journal("IASEAI", _iaseai_cache(tmp_path))
    assert len(result.records) == 57 and {r.track for r in result.records} == {"main"}
    assert {(r.venue, r.year, r.status) for r in result.records} == {("IASEAI", 2026, "accepted")}
    (report,) = result.reports
    assert (report.stated, report.listed, report.count_ok) == (57, 57, True)
    assert (result.deleted, result.front_matter, result.unavailable, result.duplicates) == (57, 1, 0, 0)


def test_the_iaseai_inventory_and_sets_parse() -> None:
    headers, token = ojs.parse_identifiers(_text("iaseai-inventory.json"))
    assert token is None and len(headers) == 115 and sum(h.deleted for h in headers) == 57
    sets, token = ojs.parse_sets(_text("iaseai-sets.json"))
    assert token is None and {"IASEAI:IASEAI", "IASEAI:FMT", "IASEAI:ART"} <= set(sets)
    assert sets["IASEAI:IASEAI"] == "Main Track"
