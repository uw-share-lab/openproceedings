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
    assert body["snapshot"] == {
        "name": snapshot.name,
        "snapshot_hash": manifest["snapshot_hash"],
        "crawl_date": manifest["crawl_date"],
        "crawl_from": manifest["crawl_window"]["from"],
        "crawl_to": manifest["crawl_window"]["to"],
        "built_at": manifest["built_at"],
        "sources": sorted(manifest["sources"]),
    }


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


def test_the_order_is_stable_and_unknown_is_its_own_cell(client: TestClient) -> None:
    first = client.get("/api/v1/coverage")
    assert first.content == client.get("/api/v1/coverage").content  # byte-identical
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


def test_a_missing_snapshot_is_a_500_never_partial_coverage(store: Store, tmp_path: Path, logs: Logs) -> None:
    data = tmp_path / "data"
    shutil.copytree(store.indexes, data / "indexes", symlinks=True)  # indexes only
    with TestClient(make_app(data)) as c:
        e = error(c.get("/api/v1/coverage"), 500, "API_INTERNAL")
    assert "snapshot" not in e["message"]
    (failed,) = [line for line in logs() if line["event"] == "request_failed"]
    assert failed["cause"] == "SnapshotError"


def _writable_copy(store: Store, tmp_path: Path) -> Path:
    data = tmp_path / "data"
    shutil.copytree(store.indexes, data / "indexes", symlinks=True)
    shutil.copytree(store.indexes.parent / "snapshots" / "big", data / "snapshots" / "big")
    for path in (data / "snapshots" / "big", *(data / "snapshots" / "big").iterdir()):
        os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR)
    return data


@pytest.mark.parametrize(
    "tamper",
    [
        "move_a_cell",  # the counts no longer describe the records' index (a cell's count moved)
        "fold_unknown",  # unknown track folded into main: the unknown_track map disagrees
        "record_count",
        "track_outside_vocabulary",
        "hash",  # the manifest names another snapshot
    ],
)
def test_a_manifest_that_doesnt_describe_the_index_is_a_500(
    store: Store, tmp_path: Path, tamper: str
) -> None:
    data = _writable_copy(store, tmp_path)
    path = data / "snapshots" / "big" / "manifest.json"
    manifest = json.loads(path.read_text())
    venue = next(iter(manifest["counts"]))
    year = next(iter(manifest["counts"][venue]))
    cell = manifest["counts"][venue][year]
    if tamper == "move_a_cell":
        track = next(iter(cell))
        status = next(iter(cell[track]))
        cell[track][status] += 1
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
        error(c.get("/api/v1/coverage"), 500, "API_INTERNAL")


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
