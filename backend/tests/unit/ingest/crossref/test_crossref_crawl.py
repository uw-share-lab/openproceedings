# backend/tests/unit/ingest/crossref/test_crossref_crawl.py
import json
import logging

import pytest
from openproceedings.ingest import acm_table
from openproceedings.ingest.sources import crawl, crossref

from tests.unit.ingest.crossref import api
from tests.unit.ingest.crossref.test_crossref_mine import D1, D2, NP, ROW, TABLE, _script, _whole
from tests.unit.ingest.proceedings_helpers import FakeTransport


@pytest.fixture(autouse=True)
def _acm(monkeypatch):
    monkeypatch.setattr(acm_table, "TABLE", TABLE)


def test_offline_ingest_marks_the_proceedings_and_the_replay_rebuilds_them(tmp_path, monkeypatch) -> None:
    _whole(tmp_path, api.work(D1), api.work(D2), api.work(NP), total=3)
    out = crawl.ingest_crossref([("FAccT", 2023)], tmp_path, offline=True, table=TABLE)
    assert [x["records"] for x in out["listings"]] == [2]
    assert json.loads((tmp_path / "crossref" / "crawls" / "FAccT-2023.json").read_text()) == {
        "source": "crossref",
        "venue": "FAccT",
        "year": 2023,
    }
    (replayed,) = crawl.CROSSREF.replay(
        tmp_path
    )  # acm_table.TABLE is monkeypatched by the autouse fixture's module
    assert len(replayed.records) == 2


def test_a_live_crawl_sends_the_contact_in_the_user_agent_and_nowhere_else(tmp_path, caplog) -> None:
    t = FakeTransport({})
    _script(t, crossref.proceedings_url(ROW.doi), api.proceedings())
    _script(
        t,
        crossref.works_url(ROW),
        api.works_page(api.work(D1), api.work(D2), api.work(NP), cursor="c2", total=3),
    )
    _script(t, crossref.works_url(ROW, "c2"), api.works_page(cursor="c3", total=3))
    caplog.set_level(logging.DEBUG)
    crawl.ingest_crossref([("FAccT", 2023)], tmp_path, transport=t, min_interval=0, table=TABLE,
                          mailto="reviewer@example.org")  # fmt: skip
    assert "reviewer@example.org" not in caplog.text
    assert all("reviewer@example.org" not in p.read_text() for p in tmp_path.rglob("*.json"))


def test_a_proceedings_the_table_lacks_is_refused(tmp_path) -> None:
    with pytest.raises(crawl.MinerError, match="AIES 2019"):
        crawl.ingest_crossref([("AIES", 2019)], tmp_path, offline=True, table=TABLE)


def test_crossref_is_replayed_last() -> None:
    assert crawl.SOURCES[-2:] == (crawl.DBLP_AAAI, crawl.CROSSREF)


def test_the_contact_is_sent_in_the_user_agent_when_given_and_absent_when_not(tmp_path, monkeypatch) -> None:
    from openproceedings.ingest.sources.http import USER_AGENT

    agents: list[str] = []

    def run(cache, mailto, env=None):
        t = FakeTransport({})
        _script(t, crossref.proceedings_url(ROW.doi), api.proceedings())
        _script(
            t,
            crossref.works_url(ROW),
            api.works_page(api.work(D1), api.work(D2), api.work(NP), cursor="c2", total=3),
        )
        _script(t, crossref.works_url(ROW, "c2"), api.works_page(cursor="c3", total=3))
        inner = t.__call__

        def spy(request, timeout):
            agents.append(request.headers["User-Agent"])
            return inner(request, timeout)

        crawl.ingest_crossref(
            [("FAccT", 2023)], cache, transport=spy, min_interval=0, table=TABLE, mailto=mailto
        )

    monkeypatch.delenv("CROSSREF_MAILTO", raising=False)
    monkeypatch.setattr(crawl, "repo_dotenv", lambda: None)
    run(tmp_path / "a", "reviewer@example.org")
    assert agents and all("mailto:reviewer@example.org" in a for a in agents)
    agents.clear()
    run(tmp_path / "b", None)  # no contact: the crawl goes on, with the plain User-Agent (the public pool)
    assert agents and set(agents) == {USER_AGENT}


def test_a_malformed_contact_stops_a_live_crawl_without_echoing_it(tmp_path, monkeypatch) -> None:
    import pytest

    monkeypatch.setenv("CROSSREF_MAILTO", "not an address")
    monkeypatch.setattr(crawl, "repo_dotenv", lambda: None)
    with pytest.raises(crawl.MinerError) as e:
        crawl.ingest_crossref([("FAccT", 2023)], tmp_path, transport=FakeTransport({}), table=TABLE)
    assert e.value.reason == "bad_contact" and "not an address" not in str(e.value)


def test_an_explicit_malformed_mailto_stops_a_live_crawl_like_the_environment_one(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("CROSSREF_MAILTO", raising=False)
    monkeypatch.setattr(crawl, "repo_dotenv", lambda: None)
    with pytest.raises(crawl.MinerError) as e:
        crawl.ingest_crossref([("FAccT", 2023)], tmp_path, transport=FakeTransport({}), table=TABLE,
                              mailto="bad contact")  # fmt: skip
    assert e.value.reason == "bad_contact" and "bad contact" not in str(e.value)


def test_a_dry_run_reads_the_cache_only_and_writes_no_marker(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CROSSREF_MAILTO", "not an address")  # a dry run never reads the contact
    _whole(tmp_path, api.work(D1), api.work(D2), api.work(NP), total=3)
    out = crawl.ingest_crossref([("FAccT", 2023)], tmp_path, dry_run=True, table=TABLE)
    assert out["proceedings"] == [
        {"venue": "FAccT", "year": 2023, "record_cached": True, "first_page_cached": True}
    ]
    assert not (tmp_path / "crossref" / "crawls").exists()


def test_the_contact_never_reaches_the_cache_or_an_error(tmp_path, monkeypatch) -> None:
    import pytest

    monkeypatch.setattr(crawl, "repo_dotenv", lambda: None)
    t = FakeTransport({})
    _script(t, crossref.proceedings_url(ROW.doi), api.proceedings())
    _script(t, crossref.works_url(ROW), api.works_page(api.work(D1), cursor="c2", total=3))
    _script(t, crossref.works_url(ROW, "c2"), api.works_page(cursor="c3", total=3))
    with pytest.raises(crawl.MinerError) as e:  # a count mismatch stops the crawl
        crawl.ingest_crossref([("FAccT", 2023)], tmp_path, transport=t, min_interval=0, table=TABLE,
                              mailto="reviewer@example.org")  # fmt: skip
    assert e.value.reason == "count_mismatch" and "reviewer@example.org" not in str(e.value)
    assert all("reviewer@example.org" not in p.read_text() for p in tmp_path.rglob("*") if p.is_file())
    assert not (tmp_path / "crossref" / "crawls").exists()  # no marker for a stopped crawl


def test_the_ingest_and_the_replay_attach_the_same_official_abstract(tmp_path, monkeypatch) -> None:
    from openproceedings.ingest.sources import facct_site

    from tests.unit.ingest.crossref.test_facct_site import SITE_TABLE, URL26, csv26
    from tests.unit.ingest.proceedings_helpers import seed

    monkeypatch.setattr(facct_site, "TABLE", facct_site.load(SITE_TABLE))
    _whole(tmp_path, api.work(D1, title="Fair Ranking"), api.work(D2), api.work(NP), total=3)
    seed(
        tmp_path,
        "facct_site",
        URL26,
        csv26(("1", "Fair Ranking", "Official."), ("2", "x", "y"), ("3", "z", "w")),
    )
    out = crawl.ingest_crossref([("FAccT", 2023)], tmp_path, offline=True, table=TABLE)
    (listing,) = out["listings"]
    assert (listing["sites"], listing["abstract_attached"], listing["site_unmatched"]) == ([URL26], 1, 2)
    (replayed,) = crawl.CROSSREF.replay(tmp_path)
    r = next(x for x in replayed.records if x.urls.doi == D1)
    assert r.abstract == "Official." and r.claims("abstract")[0].url == URL26
    assert replayed.reports[0].to_manifest() == listing


def test_aies_never_reads_the_facct_site(tmp_path, monkeypatch) -> None:
    from openproceedings.ingest.sources import facct_site

    calls: list[int] = []
    monkeypatch.setattr(facct_site, "read_year", lambda y, *a, **k: calls.append(y))
    assert crawl._facct_site("AIES", 2023, None) is None and calls == []  # type: ignore[arg-type]
