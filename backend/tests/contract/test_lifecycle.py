"""Index lifecycle (task-034 AC1, AC3's /healthz): loaded once at startup, swapped atomically on SIGHUP, a
request or stream in flight finishes on the engine it started with, a failed swap keeps serving, and the
index name can't leave `<data_dir>/indexes/`."""

from __future__ import annotations

import os
import signal
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.api import ApiConfig
from openproceedings.api.state import IndexSelectionError, IndexState, index_path, install_sighup
from openproceedings.engine.tantivy_engine import TantivyEngine
from pydantic import ValidationError

from tests.contract.conftest import Store, make_app, point_current


def wait_for(condition: Callable[[], bool], timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.01)


def test_healthz_reports_the_loaded_index_and_versions(client: TestClient, store: Store) -> None:
    body = client.get("/api/v1/healthz").json()
    assert body == {
        "index_loaded": True,
        "index_version": store.big,
        "tokenizer_version": body["tokenizer_version"],
        "query_version": body["query_version"],
    }
    assert body["tokenizer_version"] and body["query_version"]


def test_the_index_is_loaded_once_at_startup(data_dir: Path) -> None:
    opened: list[Path] = []

    def opener(path: Path) -> TantivyEngine:
        opened.append(path)
        return TantivyEngine(path)

    with TestClient(make_app(data_dir, opener=opener)) as c:
        for _ in range(5):
            assert c.get("/api/v1/search", params={"q": "trust"}).status_code == 200
    assert len(opened) == 1


def test_healthz_answers_while_loading_and_search_is_503_until_loaded(data_dir: Path, store: Store) -> None:
    release = threading.Event()

    def slow(path: Path) -> TantivyEngine:
        release.wait(20)
        return TantivyEngine(path)

    app = make_app(data_dir, opener=slow, load_in_background=True)
    with TestClient(app) as c:
        assert c.get("/api/v1/healthz").json()["index_loaded"] is False
        r = c.get("/api/v1/search", params={"q": "trust"})
        assert r.status_code == 503
        assert r.json() == {
            "error": {"code": "API_INDEX_NOT_LOADED", "message": r.json()["error"]["message"]}
        }
        release.set()
        wait_for(lambda: c.get("/api/v1/healthz").json()["index_loaded"])
        assert c.get("/api/v1/search", params={"q": "trust"}).json()["index_version"] == store.big


def test_a_failed_startup_load_serves_503_and_logs_one_error(
    tmp_path: Path, logs: Callable[[], list[dict[str, Any]]]
) -> None:
    (tmp_path / "indexes").mkdir()  # no `current`
    with TestClient(make_app(tmp_path)) as c:
        assert c.get("/api/v1/healthz").json()["index_loaded"] is False
        assert c.get("/api/v1/search", params={"q": "x"}).json()["error"]["code"] == "API_INDEX_NOT_LOADED"
    failed = [line for line in logs() if line["event"] == "index_load_failed"]
    assert len(failed) == 1 and failed[0]["level"] == "ERROR"
    assert failed[0]["error"] == "IndexSelectionError" and failed[0]["index_version_kept"] is None


def test_sighup_swaps_atomically_and_a_request_in_flight_keeps_its_engine(
    data_dir: Path, store: Store
) -> None:
    hold, entered = threading.Event(), threading.Event()
    app = make_app(data_dir, hold=hold, entered=entered)
    state: IndexState = app.state.index
    restore = install_sighup(state)  # the lifespan does this on the main thread under uvicorn
    try:
        with TestClient(app) as c, ThreadPoolExecutor(1) as pool:
            before = state.engine
            assert before is not None and before.index_version == store.big
            in_flight = pool.submit(c.get, "/api/v1/_probe/hold")
            assert entered.wait(10)  # it holds the 5k engine now
            point_current(data_dir, store.small)
            os.kill(os.getpid(), signal.SIGHUP)
            wait_for(lambda: state.engine is not before)
            after = state.engine
            assert after is not None and after.index_version == store.small
            assert c.get("/api/v1/healthz").json()["index_version"] == store.small
            assert c.get("/api/v1/search", params={"q": "trust"}).json()["index_version"] == store.small
            hold.set()
            finished = in_flight.result(10).json()
            assert finished == {"index_version": store.big, "total": 5_000}  # its whole answer from one index
            assert before.index_version == store.big  # the old engine was replaced, never mutated
    finally:
        restore()


def test_a_stream_started_before_a_swap_finishes_on_its_index(data_dir: Path, store: Store) -> None:
    hold, entered = threading.Event(), threading.Event()
    app = make_app(data_dir, hold=hold, entered=entered)
    state: IndexState = app.state.index
    with TestClient(app) as c, ThreadPoolExecutor(1) as pool:
        streaming = pool.submit(c.get, "/api/v1/_probe/stream")
        assert entered.wait(10)  # the first chunk is out
        point_current(data_dir, store.small)
        assert state.load()
        assert state.engine is not None and state.engine.index_version == store.small
        hold.set()
        assert streaming.result(10).text.splitlines() == [store.big, store.big]


def test_a_failed_swap_keeps_serving_the_old_index(
    data_dir: Path, store: Store, logs: Callable[[], list[dict[str, Any]]]
) -> None:
    app = make_app(data_dir)
    with TestClient(app) as c:
        state: IndexState = app.state.index
        before = state.engine
        point_current(data_dir, "0badbadbad00")  # dangling
        assert state.load() is False
        assert state.engine is before
        assert c.get("/api/v1/healthz").json()["index_version"] == store.big
    failed = [line for line in logs() if line["event"] == "index_load_failed"]
    assert len(failed) == 1 and failed[0]["index_version_kept"] == store.big


def test_a_swap_to_a_tampered_index_is_refused(
    data_dir: Path, store: Store, logs: Callable[[], list[dict[str, Any]]]
) -> None:
    victim = data_dir / "indexes" / store.small / "ids.txt"
    victim.chmod(0o644)
    victim.write_text("forged\n", encoding="utf-8")
    app = make_app(data_dir)
    with TestClient(app):
        state: IndexState = app.state.index
        point_current(data_dir, store.small)
        assert state.load() is False
        assert state.engine is not None and state.engine.index_version == store.big
    failed = [line for line in logs() if line["event"] == "index_load_failed"]
    assert failed[-1]["error"] == "IndexBuildError"
    assert "forged" not in str(failed)


def test_reloading_the_same_index_keeps_the_engine(data_dir: Path) -> None:
    app = make_app(data_dir)
    with TestClient(app):
        state: IndexState = app.state.index
        before = state.engine
        assert state.load() is True
        assert state.engine is before


@pytest.mark.parametrize("name", ["../indexes/x", "/etc", "a/b", "CURRENT", "..", "", "abc$", "current/.."])
def test_index_names_are_restricted(name: str, tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ApiConfig(data_dir=tmp_path, index=name)
    with pytest.raises(IndexSelectionError):
        index_path(tmp_path, name)


def test_current_may_not_point_outside_indexes(tmp_path: Path, store: Store) -> None:
    indexes = tmp_path / "indexes"
    indexes.mkdir()
    (indexes / "current").symlink_to(store.indexes / store.big)  # a real index, but elsewhere
    with pytest.raises(IndexSelectionError):
        index_path(tmp_path, "current")
    (indexes / "abc").symlink_to(tmp_path)  # a version-shaped name that escapes
    with pytest.raises(IndexSelectionError):
        index_path(tmp_path, "abc")


def test_a_version_name_resolves_directly(data_dir: Path, store: Store) -> None:
    assert index_path(data_dir, store.small) == (data_dir / "indexes" / store.small).resolve()
    assert index_path(data_dir, "current").name == store.big
