"""Round 2 of the M3a observability review (logging-standards; spec 04 §Implementation notes): the access
line names the error envelope's code; one log line per change of state even across threads; the configured
index name on a failed load; no `cause: null`; an unreadable manifest under `/meta` says why at DEBUG; and a
pinned name this instance doesn't hold never waits for another version's open."""

from __future__ import annotations

import contextlib
import inspect
import json
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from openproceedings.api.deps import strict_query
from openproceedings.api.state import IndexState
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.records import RecordStore, RecordStoreFull

from tests.contract.conftest import Store, make_app
from tests.contract.test_abuse_limits import VERIFIED, error

SEARCH = "/api/v1/search"
Logs = Callable[[], list[dict[str, Any]]]


def access(logs: Logs) -> list[dict[str, Any]]:
    return [line for line in logs() if line["event"] == "request"]


# --- the access line's `code` --------------------------------------------------------------------------------
def test_the_access_line_carries_the_envelope_code(client: TestClient, logs: Logs) -> None:
    client.post("/api/v1/parse", content=b"x" * 70_000)  # 413, from BodyLimit
    client.get(SEARCH, params={"q": "(trust"})  # 422, a parse refusal
    client.get("/api/v1/nope")  # 404, routing
    client.get("/api/v1/_probe/boom/x")  # 500
    client.get(SEARCH, params={"q": "trust"})  # 200: no code
    assert [(x["status"], x.get("code")) for x in access(logs)] == [
        (413, "API_BODY_TOO_LARGE"),
        (422, "PARSE_UNBALANCED_PAREN"),
        (404, "API_NOT_FOUND"),
        (500, "API_INTERNAL"),
        (200, None),
    ]


def test_a_rate_limited_line_carries_its_code(store: Store, logs: Logs) -> None:
    from openproceedings.api import RateLimit

    limit = RateLimit(capacity=1, refill_per_second=0.001, export_weight=1)
    with TestClient(make_app(store.indexes.parent, rate_limit=limit)) as c:
        c.get(SEARCH, params={"q": "trust"})
        c.get(SEARCH, params={"q": "trust"})
    assert [(x["status"], x.get("code")) for x in access(logs)] == [(200, None), (429, "API_RATE_LIMITED")]


def test_an_api_busy_line_carries_its_code(client: TestClient, logs: Logs) -> None:
    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    read = engine.read
    entered, release = threading.Event(), threading.Event()

    def slow(*args: Any) -> Any:
        entered.set()
        assert release.wait(10)
        return read(*args)

    engine.read = slow
    try:
        with ThreadPoolExecutor(1) as pool:
            first = pool.submit(client.get, SEARCH, params={"q": VERIFIED})
            assert entered.wait(10)
            error(client.get(SEARCH, params={"q": '"calibrat* model"'}), 503, "API_BUSY")
            release.set()
            assert first.result(10).status_code == 200
    finally:
        engine.read = read
    busy = [x for x in access(logs) if x["status"] == 503]
    assert [x.get("code") for x in busy] == ["API_BUSY"]


# --- one line per change of state, under a lock --------------------------------------------------------------
def blocked_while_held(lock: threading.Lock, work: Callable[[], object]) -> None:
    """`work` waits on `lock`: it doesn't finish while the test holds it, and does once released."""
    with lock:
        thread = threading.Thread(target=work)
        thread.start()
        thread.join(0.3)
        assert thread.is_alive(), "the state flip didn't take the lock"
    thread.join(10)
    assert not thread.is_alive()


def test_the_listing_state_flips_under_its_lock(tmp_path: Path) -> None:
    state = IndexState(tmp_path, "current", TantivyEngine)  # no indexes/: the listing fails
    blocked_while_held(state._listing_lock, lambda: state.available(None))


def test_the_store_full_state_flips_under_its_lock(tmp_path: Path) -> None:
    store = RecordStore(tmp_path / "records", max_bytes=1)

    def save() -> None:
        with contextlib.suppress(RecordStoreFull):
            store._check_room()

    blocked_while_held(store._full_lock, save)


# --- other lines ------------------------------------------------------------------------------------------
def test_a_failed_load_names_the_configured_index(tmp_path: Path, logs: Logs) -> None:
    (tmp_path / "indexes").mkdir()
    assert IndexState(tmp_path, "current", TantivyEngine).load() is False
    (failed,) = [x for x in logs() if x["event"] == "index_load_failed"]
    assert (failed["index_name"], failed["reason"]) == ("current", "not_found")


def test_an_internal_error_without_a_cause_has_no_cause_key(client: TestClient, logs: Logs) -> None:
    client.get("/api/v1/_probe/boom/x")
    (failed,) = [x for x in logs() if x["event"] == "request_failed"]
    assert "cause" not in failed and "cause_frames" not in failed


def test_an_unreadable_manifest_is_left_out_of_meta_with_a_debug_line(
    data_dir: Path, store: Store, logs: Logs
) -> None:
    (data_dir / "indexes" / "abc123").mkdir()  # named like a version, no manifest
    with TestClient(make_app(data_dir)) as c:
        assert "abc123" not in c.get("/api/v1/meta").json()["index_versions"]
    lines = [x for x in logs() if x["event"] == "index_manifest_unreadable"]
    assert [(x["level"], x["index_version"], x["reason"]) for x in lines] == [("DEBUG", "abc123", "ENOENT")]
    assert str(data_dir) not in json.dumps(lines)


def test_an_absent_pin_never_waits_for_another_versions_open(data_dir: Path) -> None:
    state = IndexState(data_dir, "current", TantivyEngine)
    found: list[str] = []
    with state._open_slot:  # another version is being opened (re-hashed) meanwhile
        thread = threading.Thread(target=lambda: found.append(state.pinned("deadbeef00").reason))
        thread.start()
        thread.join(5)
        assert not thread.is_alive() and found == ["absent"]


def test_the_declared_parameters_cache_never_outlives_its_route(tmp_path: Path) -> None:
    """Cached on the route itself, never under `id(route)`: once an app's routes are collected, a new route
    that reuses an old id must not get the old route's parameter names (a spurious 422)."""
    import gc

    from fastapi.routing import APIRoute
    from openproceedings.api import deps

    for _ in range(30):
        app = make_app(tmp_path)
        for route in app.routes:
            if isinstance(route, APIRoute):
                assert deps.declared_query(route) == frozenset(deps._query_names(route.dependant)), route.path
        probe = next(r for r in app.routes if isinstance(r, APIRoute) and r.name == "probe_boom")
        assert probe.__dict__[deps.DECLARED_ATTR] == {"q"}  # held by the route: a per-app one
        del app, route, probe
        gc.collect()


def test_strict_query_runs_on_the_event_loop() -> None:
    """It does no I/O, so it needs no worker thread (FastAPI runs a sync dependency in the pool)."""
    assert inspect.iscoroutinefunction(strict_query)
