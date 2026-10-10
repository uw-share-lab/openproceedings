import json

import pytest
from openproceedings.ingest.sources import crawl, ojs
from openproceedings.ingest.sources.common import MinerError
from openproceedings.ingest.sources.http import canonical

from tests.unit.ingest.ojs import oai
from tests.unit.ingest.ojs.test_ojs_mine import TABLE, _seed  # the 3-paper AAAI v34 table and chain seeder
from tests.unit.ingest.proceedings_helpers import (
    FakeTransport,
    response,
)


def test_offline_ingest_writes_a_marker_and_replay_rebuilds_the_same_records(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ojs, "TABLE", TABLE)  # the replay reads the shipped table
    cache = tmp_path
    _seed(cache, oai.page(oai.record(1), oai.record(2), oai.record(3, "AAAI:IAAI")))
    out = crawl.ingest_ojs(["AAAI"], cache, offline=True, table=TABLE)
    assert out["listings"][0]["records"] == 3
    marker = json.loads((cache / "ojs" / "crawls" / "AAAI.json").read_text())
    assert marker == {"source": "ojs", "journal": "AAAI"}
    (replayed,) = crawl.OJS.replay(cache)
    assert sorted(r.id for r in replayed.records) == sorted(f"op:aaai:2020:ojs-{n}" for n in (1, 2, 3))


def test_dry_run_writes_no_marker(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1), oai.record(2), oai.record(3, "AAAI:IAAI")))
    out = crawl.ingest_ojs(["AAAI"], tmp_path, offline=True, dry_run=True, table=TABLE)
    assert out["journals"] == [
        {"journal": "AAAI", "first_page_cached": True, "sets_on_first_page": 1, "more_pages": False}
    ]
    assert not (tmp_path / "ojs" / "crawls").exists() or not list((tmp_path / "ojs" / "crawls").iterdir())


def test_unknown_journal_is_refused(tmp_path) -> None:
    with pytest.raises(MinerError, match=r"not in ojs_sections\.toml"):
        crawl.ingest_ojs(["XYZ"], tmp_path, offline=True, table=TABLE)


def test_ojs_is_replayed_last() -> None:
    assert crawl.SOURCES[-1] is crawl.OJS


def _live(first: str, **kw):
    transport = FakeTransport({})
    transport.script = {canonical(ojs.sets_url("AAAI"), keep_query=True): [response(first, **kw)]}
    return transport


def test_live_dry_run_fetches_only_the_first_page_and_caches_it(tmp_path) -> None:
    transport = _live(
        oai.sets_page("AAAI:AISI", token="s1"), headers={"content-type": "text/xml; charset=utf-8"}
    )
    out = crawl.ingest_ojs(["AAAI"], tmp_path, dry_run=True, transport=transport, table=TABLE)
    assert out["journals"] == [
        {"journal": "AAAI", "first_page_cached": False, "sets_on_first_page": 1, "more_pages": True}
    ]
    assert (out["requests"], len(transport.calls)) == (1, 1)
    assert (tmp_path / "ojs").exists() and list((tmp_path / "ojs").rglob("*.*"))
    assert not (tmp_path / "ojs" / "crawls").exists()
    again = crawl.ingest_ojs(["AAAI"], tmp_path, dry_run=True, transport=transport, table=TABLE)
    assert again["journals"][0]["first_page_cached"] is True and len(transport.calls) == 1


def test_dry_run_refuses_a_non_ok_first_page(tmp_path) -> None:
    transport = _live("gone", status=404, headers={"content-type": "text/xml"})
    with pytest.raises(MinerError, match="HTTP 404"):
        crawl.ingest_ojs(["AAAI"], tmp_path, dry_run=True, transport=transport, table=TABLE)
