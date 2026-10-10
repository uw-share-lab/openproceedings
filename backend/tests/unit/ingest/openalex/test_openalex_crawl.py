"""`op ingest openalex` (decision-049): the harvest into a pinned, content-addressed extract and its marker; the key
in a header only; the listing count checked; a dry run that fetches nothing."""

import json
import logging

import pytest
from openproceedings.ingest.sources import crawl, openalex
from openproceedings.ingest.sources.common import CrawlError

from tests.unit.ingest.openalex import api
from tests.unit.ingest.openalex.test_openalex_fill import D1, TABLE, rec
from tests.unit.ingest.proceedings_helpers import FakeTransport, response


def _seed_doi_batch(t: FakeTransport, *works) -> None:
    from openproceedings.ingest.sources.http import canonical

    t.script[canonical(openalex.doi_url([D1]), keep_query=True)] = [
        response(api.page(*works), headers=api.JSON)
    ]


def test_a_crawl_writes_a_pinned_extract_the_build_replays_offline(tmp_path, monkeypatch) -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    monkeypatch.setattr(crawl, "replay_all", lambda cache: ([r], []))
    t = FakeTransport({})
    _seed_doi_batch(t, api.work("W1", D1, text="An OpenAlex abstract."))
    out = crawl.ingest_openalex(tmp_path, transport=t, min_interval=0, table=openalex_table_empty())
    marker = json.loads((tmp_path / "openalex" / "crawls" / "openalex.json").read_text())
    assert marker == {"source": "openalex", "format": "1", "extract": out["extract"]}
    assert (tmp_path / "openalex" / "extract" / f"{out['extract']}.json").exists()
    extract = openalex.load_extract(tmp_path)
    assert extract is not None and extract.sha256 == out["extract"]
    (filled,), _report = openalex.fill([r], extract, openalex_table_empty())
    assert filled.abstract_kind == "openalex"


def test_the_replay_reads_only_the_marked_extract_and_refuses_a_changed_one(tmp_path, monkeypatch) -> None:
    test_a_crawl_writes_a_pinned_extract_the_build_replays_offline(tmp_path, monkeypatch)
    sha = json.loads((tmp_path / "openalex" / "crawls" / "openalex.json").read_text())["extract"]
    (tmp_path / "openalex" / "extract" / ("f" * 64 + ".json")).write_text("{}")  # another extract: ignored
    assert openalex.load_extract(tmp_path).sha256 == sha
    path = tmp_path / "openalex" / "extract" / f"{sha}.json"
    path.chmod(0o644)
    original = path.read_text()
    path.write_text(original.replace('"OpenAlex"', '"Changed"'))  # one word of the kept inverted index
    assert path.read_text() != original
    with pytest.raises(CrawlError) as e:
        openalex.load_extract(tmp_path)
    assert e.value.reason == "extract_changed"


def test_no_marker_means_no_fill(tmp_path) -> None:
    assert openalex.load_extract(tmp_path) is None


def test_the_key_goes_in_a_header_and_nowhere_else(tmp_path, monkeypatch, caplog) -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    monkeypatch.setattr(crawl, "replay_all", lambda cache: ([r], []))
    t = FakeTransport({})
    _seed_doi_batch(t, api.work("W1", D1))
    caplog.set_level(logging.DEBUG)
    crawl.ingest_openalex(
        tmp_path, transport=t, min_interval=0, table=openalex_table_empty(), key="sk-secret"
    )
    assert "sk-secret" not in caplog.text
    assert all("sk-secret" not in p.read_text() for p in tmp_path.rglob("*.json"))
    assert t.requests[0].headers["Authorization"] == "Bearer sk-secret"  # the FakeTransport's request log


def test_a_listing_whose_count_differs_from_the_table_stops(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(crawl, "replay_all", lambda cache: ([], []))
    t = FakeTransport({})
    row = TABLE.listings[("AAAI", 1990)]
    from openproceedings.ingest.sources.http import canonical

    t.script[canonical(openalex.listing_url(row), keep_query=True)] = [
        response(api.page(api.work("W5", None, year=1990), count=2, cursor="c2"), headers=api.JSON)
    ]
    t.script[canonical(openalex.listing_url(row, "c2"), keep_query=True)] = [
        response(api.page(api.work("W6", None, year=1990), count=2), headers=api.JSON)
    ]
    with pytest.raises(CrawlError) as e:  # 2 listed, the table verified 3
        crawl.ingest_openalex(tmp_path, transport=t, min_interval=0, table=TABLE)
    assert e.value.reason == "count_mismatch"


def test_a_dry_run_fetches_nothing_and_writes_no_marker(tmp_path, monkeypatch) -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    monkeypatch.setattr(crawl, "replay_all", lambda cache: ([r], []))
    out = crawl.ingest_openalex(tmp_path, dry_run=True, table=openalex_table_empty())
    assert out["dry_run"] and out["candidates"] == 1 and out["doi_batches"] == 1 and out["requests"] == 0
    assert not (tmp_path / "openalex" / "crawls").exists()


def openalex_table_empty():
    from openproceedings.ingest import openalex_table

    return openalex_table.load("")


def _marker(cache, body) -> None:
    (cache / "openalex" / "crawls").mkdir(parents=True, exist_ok=True)
    (cache / "openalex" / "crawls" / "openalex.json").write_text(json.dumps(body))


@pytest.mark.parametrize("body", [{"source": "openalex", "format": "1"}, {"source": "openalex", "format": "2",
                                  "extract": "0" * 64}, {"source": "openalex", "format": "1", "extract": "../x"}])  # fmt: skip
def test_a_marker_naming_no_extract_is_invalid(tmp_path, body) -> None:
    _marker(tmp_path, body)
    with pytest.raises(CrawlError) as e:
        openalex.load_extract(tmp_path)
    assert e.value.reason == "crawl_file_invalid"


def test_a_marked_extract_that_is_gone_is_not_cached(tmp_path) -> None:
    _marker(tmp_path, {"source": "openalex", "format": "1", "extract": "a" * 64})
    with pytest.raises(CrawlError) as e:
        openalex.load_extract(tmp_path)
    assert e.value.reason == "not_cached"


def test_a_malformed_extract_with_its_own_hash_is_invalid(tmp_path) -> None:
    import hashlib

    body = b'{"format":"1","lookups":[{"route":"doi"}]}'
    sha = hashlib.sha256(body).hexdigest()
    (tmp_path / "openalex" / "extract").mkdir(parents=True)
    (tmp_path / "openalex" / "extract" / f"{sha}.json").write_bytes(body)
    _marker(tmp_path, {"source": "openalex", "format": "1", "extract": sha})
    with pytest.raises(CrawlError) as e:
        openalex.load_extract(tmp_path)
    assert e.value.reason == "crawl_file_invalid"


def test_the_extract_round_trips_and_a_rewrite_of_the_same_lookups_keeps_its_name(tmp_path) -> None:
    from tests.unit.ingest.openalex.test_openalex_fill import _listing, doi_lookup

    lookups = (
        doi_lookup(api.work("W1", D1, raw={"a": [0], "b": [2]})),
        _listing(api.work("W5", None, year=1990)),
    )
    sha = openalex.write_extract(tmp_path, lookups)
    path = tmp_path / "openalex" / "extract" / f"{sha}.json"
    assert (
        openalex.write_extract(tmp_path, reversed(lookups)) == sha
        and oct(path.stat().st_mode & 0o777) == "0o444"
    )
    extract = openalex.load_extract(tmp_path)
    assert extract is not None and extract.lookups == tuple(sorted(lookups, key=lambda lk: lk.url))


def test_a_doi_batch_matching_more_works_than_its_page_holds_stops(tmp_path, monkeypatch) -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    monkeypatch.setattr(crawl, "replay_all", lambda cache: ([r], []))
    t = FakeTransport({})
    from openproceedings.ingest.sources.http import canonical

    t.script[canonical(openalex.doi_url([D1]), keep_query=True)] = [
        response(api.page(api.work("W1", D1), count=51), headers=api.JSON)
    ]
    with pytest.raises(CrawlError) as e:
        crawl.ingest_openalex(tmp_path, transport=t, min_interval=0, table=openalex_table_empty())
    assert e.value.reason == "doi_batch_incomplete"
    assert not (tmp_path / "openalex" / "crawls").exists()


def test_a_dry_run_counts_a_doi_no_filter_can_carry(tmp_path, monkeypatch) -> None:
    odd = rec(
        "op:facct:2023:doi-3593013.3594012", "FAccT", 2023, doi="10.1145/3593013.3594012"
    )  # "unsafe" here
    monkeypatch.setattr(openalex, "queryable", lambda d: d != "10.1145/3593013.3594012")
    monkeypatch.setattr(crawl, "replay_all", lambda cache: ([odd, rec("op:facct:2023:doi-3593013.3594011", "FAccT",
                                                                      2023, doi=D1)], []))  # fmt: skip
    out = crawl.ingest_openalex(tmp_path, dry_run=True, table=TABLE)
    assert (out["candidates"], out["doi_batches"], out["doi_unqueryable"], out["listings"]) == (2, 1, 1, 1)


def test_a_changed_extract_refuses_the_snapshot_build(tmp_path, monkeypatch) -> None:
    from openproceedings.ingest.dedup import DedupResult
    from openproceedings.ingest.snapshot import SnapshotError, fill_openalex

    test_a_crawl_writes_a_pinned_extract_the_build_replays_offline(tmp_path, monkeypatch)
    sha = json.loads((tmp_path / "openalex" / "crawls" / "openalex.json").read_text())["extract"]
    path = tmp_path / "openalex" / "extract" / f"{sha}.json"
    path.chmod(0o644)
    path.write_text(path.read_text().replace('"OpenAlex"', '"Changed"'))
    with pytest.raises(SnapshotError) as e:
        fill_openalex(DedupResult((), (), ()), tmp_path)
    assert e.value.reason == "extract_changed"


def test_a_lone_surrogate_from_openalex_is_kept_in_the_extract_and_refused_at_the_fill(tmp_path) -> None:
    from tests.unit.ingest.openalex.test_openalex_fill import doi_lookup, ext

    lookup = doi_lookup(api.work("W1", D1, title="T\ud800", raw={"a\ud800": [0]}), requested=(D1,))
    openalex.write_extract(tmp_path, (lookup,))
    extract = openalex.load_extract(tmp_path)
    assert extract is not None and extract.lookups == (lookup,)
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    (out,), report = openalex.fill([r], ext(*extract.lookups), TABLE)
    assert out.abstract is None and report.refused == {"abstract_unusable": 1}
