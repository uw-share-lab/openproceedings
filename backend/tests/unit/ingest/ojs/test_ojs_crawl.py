import json

import pytest
from openproceedings.ingest.sources import crawl, ojs
from openproceedings.ingest.sources.common import MinerError

from tests.unit.ingest.ojs import oai
from tests.unit.ingest.ojs.test_ojs_mine import TABLE, _seed  # the 3-paper AAAI v34 table and chain seeder


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
    assert out["journals"] == [{"journal": "AAAI", "first_page_cached": True, "more_pages": False}]
    assert not (tmp_path / "ojs" / "crawls").exists() or not list((tmp_path / "ojs" / "crawls").iterdir())


def test_unknown_journal_is_refused(tmp_path) -> None:
    with pytest.raises(MinerError, match=r"not in ojs_sections\.toml"):
        crawl.ingest_ojs(["XYZ"], tmp_path, offline=True, table=TABLE)


def test_ojs_is_replayed_last() -> None:
    assert crawl.SOURCES[-1] is crawl.OJS
