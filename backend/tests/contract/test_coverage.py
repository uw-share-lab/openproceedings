"""`GET /api/v1/coverage` (task-038; spec 04 §Endpoints, spec 07 §C).

The expected numbers are counted here, independently, from the raw lines of the snapshot's records.jsonl
(plain JSON, not `PaperRecord` or the manifest code), and checked against the manifest (AC1) and the
index's document count.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.query import QUERY_VERSION
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.timestamps import utc_z
from openproceedings.vocab import STATUSES, TRACKS

from tests.contract.conftest import Store, make_app, point_current

Logs = Callable[[], list[dict[str, Any]]]


def error(r: Any, status: int, code: str) -> dict[str, Any]:
    assert r.status_code == status, r.text
    assert set(r.json()) == {"error"} and r.json()["error"]["code"] == code
    return r.json()["error"]  # type: ignore[no-any-return]


def snapshot_of(data_dir: Path, version: str) -> Path:
    manifest = json.loads((data_dir / "indexes" / version / "manifest.json").read_text())
    return data_dir / "snapshots" / manifest["snapshot"]


def raw_records(snapshot: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in (snapshot / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def flatten(body: dict[str, Any]) -> Counter[tuple[str, int, str, str]]:
    return Counter(
        {
            (vy["venue"], vy["year"], c["track"], c["status"]): c["count"]
            for vy in body["venue_years"]
            for c in vy["cells"]
        }
    )


def test_counts_equal_an_independent_count_of_the_snapshot_records(client: TestClient, store: Store) -> None:
    r = client.get("/api/v1/coverage")
    assert r.status_code == 200, r.text
    body = r.json()
    records = raw_records(snapshot_of(store.indexes.parent, store.big))
    assert flatten(body) == Counter((x["venue"], x["year"], x["track"], x["status"]) for x in records)
    per_vy = {(vy["venue"], vy["year"]): vy for vy in body["venue_years"]}
    assert set(per_vy) == {(x["venue"], x["year"]) for x in records}
    for key, fn in (
        ("records", lambda x: True),
        ("abstract_missing", lambda x: x["abstract"] is None),
        ("unknown_track", lambda x: x["track"] == "unknown"),
        ("unknown_status", lambda x: x["status"] == "unknown"),
    ):
        expected = Counter((x["venue"], x["year"]) for x in records if fn(x))
        assert {vy: v[key] for vy, v in per_vy.items()} == {vy: expected[vy] for vy in per_vy}, key
        assert body["totals"][key] == sum(expected.values()), key
    # the fixture exercises what must never be folded away
    assert body["totals"]["abstract_missing"] > 0
    assert body["totals"]["unknown_track"] > 0 and body["totals"]["unknown_status"] > 0


def test_totals_equal_the_index_document_count(client: TestClient, store: Store) -> None:
    body = client.get("/api/v1/coverage").json()
    index = json.loads((store.indexes / store.big / "manifest.json").read_text())
    ids = (store.indexes / store.big / "ids.txt").read_text().splitlines()
    assert body["totals"]["records"] == index["doc_count"] == len(ids) == 5000
    assert sum(vy["records"] for vy in body["venue_years"]) == index["doc_count"]
    assert sum(flatten(body).values()) == index["doc_count"]


def test_numbers_match_the_snapshot_manifest_exactly(client: TestClient, store: Store) -> None:
    """AC1: every count and date is the manifest's."""
    body = client.get("/api/v1/coverage").json()
    snapshot = snapshot_of(store.indexes.parent, store.big)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert flatten(body) == Counter(
        {
            (venue, int(year), track, status): n
            for venue, years in manifest["counts"].items()
            for year, tracks in years.items()
            for track, statuses in tracks.items()
            for status, n in statuses.items()
        }
    )
    for key in ("abstract_missing", "unknown_track"):
        assert {(vy["venue"], str(vy["year"])): vy[key] for vy in body["venue_years"]} == {
            (venue, year): n for venue, years in manifest[key].items() for year, n in years.items()
        }
    assert body["totals"]["records"] == manifest["record_count"]
    assert sorted(manifest["sources"]) == ["ris"]
    assert body["snapshot"] == {
        "name": snapshot.name,
        "snapshot_hash": manifest["snapshot_hash"],
        "crawl_date": manifest["crawl_date"],
        # a search record's `crawl_dates` shape; every timestamp in the one UTC `…Z` form (spec 04). Format 2
        # records each claim source's own window too (TASK-082): here one source, so the same window
        "crawl_dates": {
            "*": {k: utc_z(v) for k, v in manifest["crawl_window"].items()},
            "ris": {k: utc_z(v) for k, v in manifest["crawl_windows"]["ris"].items()},
        },
        "built_at": utc_z(manifest["built_at"]),
        "sources": sorted(manifest["sources"]),
        # derived as a search record's (TASK-091): the fixture's one source is RIS, a bootstrap source
        "crawl_dates_kind": {"*": "scholar_query_dates", "ris": "scholar_query_dates"},
        "identification_citable": False,
    }
    assert manifest["built_at"].endswith("+00:00") and body["snapshot"]["built_at"].endswith("Z")


def test_crawl_dates_are_a_search_records(recorded_coverage: tuple[dict[str, Any], dict[str, Any]]) -> None:
    """One shape for the crawl window everywhere (M3a review): `/coverage` and a record of the same index."""
    coverage, record = recorded_coverage
    assert coverage["snapshot"]["crawl_dates"] == record["crawl_dates"]


def test_crawl_kind_and_citability_are_a_search_records(
    recorded_coverage: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """TASK-091: `/coverage` says what kind its window is and whether counts are citable, as a record does."""
    coverage, record = recorded_coverage
    for key in ("sources", "crawl_dates_kind", "identification_citable"):
        assert coverage["snapshot"][key] == record[key]


@pytest.fixture
def recorded_coverage(data_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    with TestClient(make_app(data_dir)) as c:
        created = c.post("/api/v1/records", json={"q": "trust"}).json()
        record = c.get(f"/api/v1/records/{created['record_id']}").json()["record"]
        return c.get("/api/v1/coverage").json(), record


def test_the_response_carries_the_three_versions(client: TestClient, store: Store) -> None:
    body = client.get("/api/v1/coverage").json()
    assert (body["index_version"], body["tokenizer_version"], body["query_version"]) == (
        store.big,
        TOKENIZER_VERSION,
        QUERY_VERSION,
    )
    assert set(body) == {
        "index_version",
        "tokenizer_version",
        "query_version",
        "snapshot",
        "totals",
        "venue_years",
    }


def test_the_order_is_stable_and_unknown_is_its_own_cell(client: TestClient, store: Store) -> None:
    first = client.get("/api/v1/coverage")
    with TestClient(make_app(store.indexes.parent)) as fresh:  # computed again, by another app
        assert first.content == fresh.get("/api/v1/coverage").content  # byte-identical
    body = first.json()
    keys = [(vy["venue"], vy["year"]) for vy in body["venue_years"]]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    unknown_cells = 0
    for vy in body["venue_years"]:
        order = [(TRACKS.index(c["track"]), STATUSES.index(c["status"])) for c in vy["cells"]]
        assert order == sorted(order) and len(set(order)) == len(order)
        assert all(c["count"] > 0 for c in vy["cells"])
        assert vy["records"] == sum(c["count"] for c in vy["cells"])
        unknown_cells += sum(c["track"] == "unknown" or c["status"] == "unknown" for c in vy["cells"])
    assert unknown_cells > 0


def test_it_is_computed_once_per_index_and_follows_a_hot_swap(
    store: Store, data_dir: Path, logs: Logs
) -> None:
    with TestClient(make_app(data_dir)) as c:
        big = c.get("/api/v1/coverage").json()
        assert c.get("/api/v1/coverage").json() == big
        point_current(data_dir, store.small)
        assert c.app.state.index.load()  # type: ignore[attr-defined]
        small = c.get("/api/v1/coverage").json()
        assert c.get("/api/v1/coverage").json() == small
    assert (big["index_version"], big["totals"]["records"]) == (store.big, 5000)
    assert (small["index_version"], small["totals"]["records"]) == (store.small, 300)
    records = raw_records(snapshot_of(data_dir, store.small))
    assert flatten(small) == Counter((x["venue"], x["year"], x["track"], x["status"]) for x in records)
    computed = [line for line in logs() if line["event"] == "coverage_computed"]
    assert [(line["index_version"], line["records"]) for line in computed] == [
        (store.big, 5000),
        (store.small, 300),
    ]
    requests = [line for line in logs() if line["event"] == "request"]
    assert {(line["route"], line["status"]) for line in requests} == {("/api/v1/coverage", 200)}


def test_it_answers_503_before_an_index_loads(tmp_path: Path) -> None:
    (tmp_path / "indexes").mkdir()
    with TestClient(make_app(tmp_path)) as c:
        error(c.get("/api/v1/coverage"), 503, "API_INDEX_NOT_LOADED")


def load_failed(logs: Logs) -> list[str]:
    """The `reason` of each `index_load_failed` line (a constant, never a path)."""
    return [line["reason"] for line in logs() if line["event"] == "index_load_failed"]


def test_a_missing_snapshot_fails_the_load_never_partial_coverage(
    store: Store, tmp_path: Path, logs: Logs
) -> None:
    data = tmp_path / "data"
    shutil.copytree(store.indexes, data / "indexes", symlinks=True)  # indexes only
    with TestClient(make_app(data)) as c:
        error(c.get("/api/v1/coverage"), 503, "API_INDEX_NOT_LOADED")
    assert load_failed(logs) == ["snapshot_missing"]


def _writable_copy(store: Store, tmp_path: Path) -> Path:
    data = tmp_path / "data"
    shutil.copytree(store.indexes, data / "indexes", symlinks=True)
    shutil.copytree(store.indexes.parent / "snapshots" / "big", data / "snapshots" / "big")
    for path in (data / "snapshots" / "big", *(data / "snapshots" / "big").iterdir()):
        os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR)
    return data


def _move_a_cell(manifest: dict[str, Any]) -> None:
    """−1 in one cell, +1 in another of the same venue-year (neither `unknown`): every sum and map in the
    manifest still agrees with itself; only the records disagree."""
    for years in manifest["counts"].values():
        for cell in years.values():
            known = [(t, st) for t, ss in cell.items() if t != "unknown" for st in ss]
            source = next(((t, st) for t, st in known if cell[t][st] >= 2), None)
            if source is not None and len(known) >= 2:
                target = next(k for k in known if k != source)
                cell[source[0]][source[1]] -= 1
                cell[target[0]][target[1]] += 1
                return
    raise AssertionError("no venue-year to move a record within")


def _no_missing_abstracts(manifest: dict[str, Any]) -> None:
    """Zero one venue-year's missing abstracts, per track too, so the manifest still agrees with itself."""
    venue, year = next(
        (v, y) for v, ys in manifest["abstract_missing"].items() for y, n in ys.items() if n > 0
    )
    manifest["abstract_missing"][venue][year] = 0
    tracks = manifest["abstract_missing_by_track"][venue][year]
    manifest["abstract_missing_by_track"][venue][year] = dict.fromkeys(tracks, 0)


def _move_a_missing_abstract(manifest: dict[str, Any]) -> None:
    """One missing abstract moved to another track of the same venue-year: every sum still agrees."""
    for venue, years in manifest["abstract_missing_by_track"].items():
        for year, tracks in years.items():
            size = {t: sum(ss.values()) for t, ss in manifest["counts"][venue][year].items()}
            source = next((t for t, n in tracks.items() if n > 0), None)
            target = next((t for t in tracks if t != source and tracks[t] < size[t]), None)
            if source is not None and target is not None:
                tracks[source] -= 1
                tracks[target] += 1
                return
    raise AssertionError("no venue-year to move a missing abstract within")


@pytest.mark.parametrize(
    ("tamper", "reason"),
    [
        ("move_a_cell", "counts_mismatch"),  # consistent with itself, not with the records
        ("abstract_missing_zero", "abstract_missing_mismatch"),
        ("move_a_missing_abstract", "track_facts_mismatch"),  # TASK-082: per track, consistent but wrong
        ("track_sources", "track_facts_mismatch"),  # a source no record of the track has a claim from
        ("statuses_too_few", "manifest_invalid"),  # a venue-year holding a status it says it can't
        ("fold_unknown", "manifest_invalid"),  # the unknown_track map disagrees with the cells
        ("record_count", "manifest_invalid"),
        ("track_outside_vocabulary", "manifest_invalid"),
        ("hash", "snapshot_hash_mismatch"),  # the manifest names another snapshot
    ],
)
def test_a_manifest_that_doesnt_describe_the_index_fails_the_load(
    store: Store, tmp_path: Path, logs: Logs, tamper: str, reason: str
) -> None:
    data = _writable_copy(store, tmp_path)
    path = data / "snapshots" / "big" / "manifest.json"
    manifest = json.loads(path.read_text())
    venue = next(iter(manifest["counts"]))
    year = next(iter(manifest["counts"][venue]))
    cell = manifest["counts"][venue][year]
    if tamper == "move_a_cell":
        _move_a_cell(manifest)
    elif tamper == "abstract_missing_zero":
        _no_missing_abstracts(manifest)
    elif tamper == "move_a_missing_abstract":
        _move_a_missing_abstract(manifest)
    elif tamper == "track_sources":
        track = next(iter(manifest["sources_by_track"][venue][year]))
        manifest["sources_by_track"][venue][year][track] = ["openreview_v2", "ris"]
    elif tamper == "statuses_too_few":
        venue, year = next(
            (v, y) for v, ys in manifest["counts"].items() for y, ts in ys.items()
            if any(st != "accepted" for ss in ts.values() for st in ss)
        )  # fmt: skip
        manifest["statuses_indexed"][venue][year] = ["accepted"]
    elif tamper == "fold_unknown":
        venue, year = next(
            (v, y) for v, ys in manifest["counts"].items() for y, ts in ys.items() if "unknown" in ts
        )
        cell = manifest["counts"][venue][year]
        for status, n in cell.pop("unknown").items():
            cell.setdefault("main", {})[status] = cell.get("main", {}).get(status, 0) + n
    elif tamper == "record_count":
        manifest["record_count"] += 1
    elif tamper == "track_outside_vocabulary":
        cell["plenary"] = cell.pop(next(iter(cell)))
    else:
        manifest["snapshot_hash"] = "0" * 64
    path.write_text(json.dumps(manifest))
    with TestClient(make_app(data)) as c:
        error(c.get("/api/v1/coverage"), 503, "API_INDEX_NOT_LOADED")
        error(c.get("/api/v1/search", params={"q": "trust"}), 503, "API_INDEX_NOT_LOADED")
    assert load_failed(logs) == [reason]


def test_records_that_arent_the_indexs_documents_fail_the_load(
    store: Store, data_dir: Path, logs: Logs
) -> None:
    """The snapshot's counts, record_count and records agree with one another, but not with the index's
    document count (an opener that drops one id stands in for a mismatched index)."""
    from openproceedings.engine.tantivy_engine import TantivyEngine

    def short(path: Path) -> TantivyEngine:
        engine = TantivyEngine(path)
        engine.ids = engine.ids[:-1]
        return engine

    with TestClient(make_app(data_dir, opener=short)) as c:
        error(c.get("/api/v1/coverage"), 503, "API_INDEX_NOT_LOADED")
    assert load_failed(logs) == ["doc_count_mismatch"]


def test_a_swap_to_an_index_with_a_bad_manifest_keeps_the_old_coverage(
    store: Store, tmp_path: Path, logs: Logs
) -> None:
    data = _writable_copy(store, tmp_path)  # the small index's snapshot isn't there
    app = make_app(data)
    with TestClient(app) as c:
        before = c.get("/api/v1/coverage").json()
        point_current(data, store.small)
        assert app.state.index.load() is False  # type: ignore[attr-defined]
        assert c.get("/api/v1/coverage").json() == before
    assert load_failed(logs) == ["snapshot_missing"]


def test_the_openapi_document_describes_coverage(client: TestClient) -> None:
    doc = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/coverage" in doc["paths"]
    schema = doc["components"]["schemas"]["CoverageResponse"]
    assert {
        "index_version",
        "tokenizer_version",
        "query_version",
        "snapshot",
        "totals",
        "venue_years",
    } <= set(schema["required"])


# --- TASK-082: tracks, statuses indexed, per-source windows ------------------------------------------------
def test_tracks_equal_an_independent_count_of_the_snapshot_records(client: TestClient, store: Store) -> None:
    """Per venue × year × track (spec 07 §C's cell): records, indexed accepted, missing abstracts and the claim
    sources, counted here from the raw lines; no official count is sourced yet, so nothing is gated."""
    body = client.get("/api/v1/coverage").json()
    records = raw_records(snapshot_of(store.indexes.parent, store.big))
    got = {(vy["venue"], vy["year"], t["track"]): t for vy in body["venue_years"] for t in vy["tracks"]}
    keys = {(x["venue"], x["year"], x["track"]) for x in records}
    assert set(got) == keys
    for key in keys:
        mine = [x for x in records if (x["venue"], x["year"], x["track"]) == key]
        row = got[key]
        assert row["records"] == len(mine)
        assert row["indexed_accepted"] == sum(x["status"] == "accepted" for x in mine)
        assert row["abstract_missing"] == sum(x["abstract"] is None for x in mine)
        assert row["sources"] == sorted({c["source"] for x in mine for c in x["provenance"]})
        assert row["official_accepted"] is None and row["delta"] is None and row["delta_pct"] is None
        assert (row["gated"], row["within_gate"], row["official_citation"]) == (False, None, None)
    for vy in body["venue_years"]:  # tracks in vocabulary order; they partition the venue-year
        held = {c["track"] for c in vy["cells"]}
        assert [t["track"] for t in vy["tracks"]] == [t for t in TRACKS if t in held]
        assert sum(t["records"] for t in vy["tracks"]) == vy["records"]
        assert sum(t["abstract_missing"] for t in vy["tracks"]) == vy["abstract_missing"]


def test_statuses_indexed_follow_the_source_table(client: TestClient, store: Store) -> None:
    """AC1: a venue-year's statuses indexed are what its sources can contain (`ingest/statuses.py`, spec 01), in
    vocabulary order, and include every status it holds; the manifest records them at build. (The synthetic
    fixture holds every status in every venue-year; the proceedings-only cases are unit tests.)"""
    from openproceedings.ingest.statuses import statuses_indexed

    body = client.get("/api/v1/coverage").json()
    manifest = json.loads((snapshot_of(store.indexes.parent, store.big) / "manifest.json").read_text())
    for vy in body["venue_years"]:
        held = vy["statuses_indexed"]
        present = {c["status"] for c in vy["cells"]}
        sources = {s for t in vy["tracks"] for s in t["sources"]}
        assert held == [st for st in STATUSES if st in held] and present <= set(held)
        assert held == statuses_indexed(sources, vy["venue"], vy["year"], present)
        assert held == manifest["statuses_indexed"][vy["venue"]][str(vy["year"])]


def test_a_format_1_snapshot_still_serves_its_tracks_from_the_records(store: Store, tmp_path: Path) -> None:
    """A snapshot built before TASK-082 has no per-track keys: the load takes them from its verified records,
    the statuses indexed from the source table, and `crawl_dates` has only `*`."""
    data = _writable_copy(store, tmp_path)
    path = data / "snapshots" / "big" / "manifest.json"
    manifest = json.loads(path.read_text())
    with TestClient(make_app(store.indexes.parent)) as c:
        current = c.get("/api/v1/coverage").json()
    for key in ("abstract_missing_by_track", "sources_by_track", "statuses_indexed", "crawl_windows"):
        del manifest[key]
    manifest["format_version"] = "1"
    path.write_text(json.dumps(manifest))
    with TestClient(make_app(data)) as c:
        old = c.get("/api/v1/coverage").json()
    assert old["venue_years"] == current["venue_years"]
    assert set(old["snapshot"]["crawl_dates"]) == {"*"}
