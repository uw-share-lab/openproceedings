# backend/tests/unit/ingest/crossref/test_crossref_mine.py
from pathlib import Path

import pytest
from openproceedings.ingest import acm_table
from openproceedings.ingest.dedup import attribution, dedup
from openproceedings.ingest.sources import crossref
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.sources.http import canonical

from tests.unit.ingest.crossref import api
from tests.unit.ingest.proceedings_helpers import FakeTransport, fetcher, response, seed

TABLE = acm_table.load(api.TABLE_TEXT)
ROW = TABLE.proceedings[("FAccT", 2023)]
D1, D2, NP = "10.1145/3593013.3594011", "10.1145/3593013.3594012", "10.1145/3593013.3594100"
FOREIGN = "10.1145/3600000.3600001"


@pytest.fixture(autouse=True)
def _acm(monkeypatch):
    monkeypatch.setattr(acm_table, "TABLE", TABLE)  # urls.native reads it: records must name themselves


def _seed_chain(cache: Path, *pages: str, head: str | None = None) -> None:
    """Seed the proceedings record and a cursor chain: page i's next cursor is `c<i+1>`, read by page i+1's URL."""
    seed(cache, "crossref", crossref.proceedings_url(ROW.doi), head or api.proceedings(), keep_query=True)
    for i, text in enumerate(pages):
        seed(
            cache, "crossref", crossref.works_url(ROW, "*" if i == 0 else f"c{i + 1}"), text, keep_query=True
        )


def _offline(cache: Path):
    f, _ = fetcher(
        cache / "crossref", None, crossref.HOSTS, accept="application/json", expect="json", keep_query=True
    )
    return f


def _whole(cache: Path, *items, total: int = 5) -> None:
    _seed_chain(
        cache,
        api.works_page(*items[:2], cursor="c2", total=total),
        api.works_page(*items[2:], cursor="c3", total=total),
        api.works_page(cursor="c4", total=total),
    )


def test_a_chain_becomes_records_foreign_dois_dropped_not_paper_counted(tmp_path: Path) -> None:
    _whole(
        tmp_path,
        api.work(D1, authors=(("Jane", "Doe"), ("Ada", "Lovelace"))),
        api.work(FOREIGN),
        api.work(D2),
        api.work(NP, title="Tutorial: Synthetic"),
        api.work("10.1145/3600000.3600002"),
    )
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    by = {r.native: r for r in result.records}
    assert set(by) == {"doi-3593013.3594011", "doi-3593013.3594012"}
    r = by["doi-3593013.3594011"]
    assert (r.id, r.venue, r.year, r.track, r.status, r.abstract) == (
        "op:facct:2023:doi-3593013.3594011",
        "FAccT",
        2023,
        "main",
        "accepted",
        None,
    )
    assert r.authors == ("Jane Doe", "Ada Lovelace") and r.urls.doi == D1
    assert r.urls.proceedings == f"https://doi.org/{D1}"
    assert {c.url for c in r.provenance} == {f"https://api.crossref.org/works/{D1}"}  # never a cursor page
    (report,) = result.reports
    assert (
        report.stated,
        report.listed,
        report.records,
        report.window_works,
        report.pages,
        report.count_ok,
    ) == (3, 3, 2, 5, 3, True)
    assert report.skipped == {"not_paper": 1}
    assert len(dedup(result.records).records) == 2


def test_an_abstract_from_crossref_would_be_credited_to_the_doi_link() -> None:
    from openproceedings.ingest.record import Claim

    from tests.unit.ingest.crossref.test_crossref_parse import T

    claim = Claim(
        field="abstract",
        value="T",
        source="crossref",
        url=f"https://api.crossref.org/works/{D1}",
        fetched_at=T,
    )
    got = attribution(
        "T", [claim], forum=None, proceedings=f"https://doi.org/{D1}", native="doi-3593013.3594011"
    )
    assert got.url == f"https://doi.org/{D1}"


@pytest.mark.parametrize(
    ("bad", "reason"), [("10.1145/3593013.3594011a", "odd_doi"), ("10.1145/3593013.x", "odd_doi")]
)
def test_an_odd_doi_under_the_proceedings_stops(tmp_path: Path, bad: str, reason: str) -> None:
    _whole(tmp_path, api.work(D1), api.work(bad), api.work(NP), total=3)
    with pytest.raises(CrawlError, match=bad) as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == reason


def test_a_count_that_differs_from_the_table_stops(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1), api.work(NP), total=2)
    with pytest.raises(CrawlError, match=r"2.*3|3.*2") as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "count_mismatch"


def test_a_not_paper_row_the_harvest_lacks_stops(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1), api.work(D2), api.work("10.1145/3593013.3594013"), total=3)
    with pytest.raises(CrawlError, match=NP) as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "stale_not_paper"


def test_a_work_with_no_title_stops_unless_a_not_paper_row_names_it(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1), api.work(D2, title=None), api.work(NP, title=None), total=3)
    with pytest.raises(CrawlError, match=D2) as e:  # NP has no title either, and is fine: it is no paper
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "no_title"


def test_a_work_of_another_type_stops_unless_a_not_paper_row_names_it(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1), api.work(D2, type_="proceedings"), api.work(NP, type_="other"), total=3)
    with pytest.raises(
        CrawlError, match=D2
    ) as e:  # NP is no article either, and is fine: a [[not_paper]] row
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "unexpected_type"


def test_an_author_with_no_name_is_dropped_and_counted_in_the_manifest_only_when_there_is_one(
    tmp_path: Path,
) -> None:
    unnamed = {"sequence": "additional", "affiliation": []}
    _whole(tmp_path, api.work(D1, author=[{"given": "Jane", "family": "Doe"}, unnamed, {"name": " "}]),
           api.work(D2), api.work(NP), total=3)  # fmt: skip
    report = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE).reports[0]
    assert report.unnamed_authors == 2 and report.to_manifest()["unnamed_authors"] == 2
    clean = tmp_path / "clean"
    _whole(clean, api.work(D1), api.work(D2), api.work(NP), total=3)
    other = crossref.mine_proceedings("FAccT", 2023, _offline(clean), table=TABLE).reports[0]
    assert other.unnamed_authors == 0 and "unnamed_authors" not in other.to_manifest()


def test_a_work_with_no_authors_is_kept_and_counted(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1, authors=()), api.work(D2), api.work(NP), total=3)
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert next(r for r in result.records if r.urls.doi == D1).authors == ()
    assert result.reports[0].no_authors == 1


def test_a_total_that_moves_mid_chain_stops(tmp_path: Path) -> None:
    _seed_chain(
        tmp_path,
        api.works_page(api.work(D1), cursor="c2", total=3),
        api.works_page(api.work(D2), api.work(NP), cursor="c3", total=4),
        api.works_page(cursor="c4", total=4),
    )
    with pytest.raises(CrawlError) as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "listing_changed"


def test_a_chain_that_returns_more_works_than_its_stated_total_stops(tmp_path: Path) -> None:
    # page 2 repeats D1 (a looping chain): 4 works of a stated 3, though the DOIs alone would count right
    _seed_chain(
        tmp_path,
        api.works_page(api.work(D1), api.work(D2), cursor="c2", total=3),
        api.works_page(api.work(NP), api.work(D1), cursor="c3", total=3),
        api.works_page(cursor="c4", total=3),
    )
    with pytest.raises(CrawlError, match="4 works of a stated 3") as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "listing_changed"


def test_a_doi_listed_twice_identically_is_skipped_and_counted(tmp_path: Path) -> None:
    _seed_chain(
        tmp_path,
        api.works_page(api.work(D1), api.work(D2), cursor="c2", total=4),
        api.works_page(api.work(D2), api.work(NP), cursor="c3", total=4),
        api.works_page(cursor="c4", total=4),
    )
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    (report,) = result.reports
    assert (report.listed, report.count_ok, report.records) == (3, True, 2)
    assert report.skipped == {"duplicate": 1, "not_paper": 1}


def test_a_doi_listed_twice_with_different_records_stops(tmp_path: Path) -> None:
    _seed_chain(
        tmp_path,
        api.works_page(api.work(D1), api.work(D2), cursor="c2", total=4),
        api.works_page(api.work(D2, title="Another Title"), api.work(NP), cursor="c3", total=4),
        api.works_page(cursor="c4", total=4),
    )
    with pytest.raises(CrawlError, match=D2) as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "conflicting_duplicate"


def test_a_work_that_will_not_build_stops_the_crawl_naming_the_doi(tmp_path: Path, monkeypatch) -> None:
    from openproceedings.ingest.record import PaperRecord
    from pydantic import ValidationError

    _whole(tmp_path, api.work(D1), api.work(D2), api.work(NP), total=3)
    with pytest.raises(ValidationError) as made:
        PaperRecord.model_validate({})

    def boom(*_a, **_k):
        raise made.value

    monkeypatch.setattr(crossref, "record_from_claims", boom)
    with pytest.raises(CrawlError, match=rf"{D1}.*ValidationError") as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "invalid_record"


@pytest.mark.parametrize(
    "head",
    [
        pytest.param(api.proceedings(title="Another Conference"), id="another-title"),
        pytest.param(api.proceedings(doi="10.1145/9999999"), id="another-doi"),  # the table's title
    ],
)
def test_a_proceedings_record_that_is_not_the_tables_stops(tmp_path: Path, head: str) -> None:
    _whole(tmp_path, api.work(D1), api.work(D2), api.work(NP), total=3)
    seed(tmp_path, "crossref", crossref.proceedings_url(ROW.doi), head, keep_query=True)
    with pytest.raises(CrawlError) as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "proceedings_mismatch"


def _script(t: FakeTransport, url: str, text: str) -> None:
    t.script[canonical(url, keep_query=True)] = [response(text, headers=api.JSON)]


def test_a_resumed_crawl_whose_chain_is_not_whole_starts_again_from_cursor_star(tmp_path: Path) -> None:
    # run 1 cached the first page (cursor "stale") and stopped; by run 2 that cursor has expired
    _seed_chain(tmp_path, api.works_page(api.work(D1), cursor="stale", total=3))
    t = FakeTransport({})
    _script(t, crossref.works_url(ROW), api.works_page(api.work(D1), cursor="fresh", total=3))
    _script(
        t, crossref.works_url(ROW, "fresh"), api.works_page(api.work(D2), api.work(NP), cursor="end", total=3)
    )
    _script(t, crossref.works_url(ROW, "end"), api.works_page(cursor="end2", total=3))
    live, _ = fetcher(tmp_path / "crossref", t, crossref.HOSTS, min_interval=0.0, accept="application/json",
                      expect="json", keep_query=True, user_agent="ua")  # fmt: skip
    result = crossref.mine_proceedings("FAccT", 2023, live, table=TABLE)
    assert (
        canonical(crossref.works_url(ROW, "stale"), keep_query=True) not in t.calls
    )  # the dead cursor is never sent
    assert len(result.records) == 2


def test_the_replay_follows_the_cached_chain_offline(tmp_path: Path) -> None:
    test_a_resumed_crawl_whose_chain_is_not_whole_starts_again_from_cursor_star(tmp_path)
    again = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert sorted(r.id for r in again.records) == [
        "op:facct:2023:doi-3593013.3594011",
        "op:facct:2023:doi-3593013.3594012",
    ]


def test_an_offline_run_without_the_chain_is_refused(tmp_path: Path) -> None:
    seed(tmp_path, "crossref", crossref.proceedings_url(ROW.doi), api.proceedings(), keep_query=True)
    with pytest.raises(CrawlError) as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "not_cached"
