"""The one pinned-index loader, `IndexState.pinned(version) -> Pinned(engine, reason)` (spec 04 §Exports,
§Search records; task-036/037 reviews): a version resolves to itself or is `absent`; an engine that won't
open is `unloadable` (WARNING) or `tampered` (ERROR), refused once and remembered until the TTL or a
reload; engines are held in an LRU of the configured size; a cache hit never waits for another version's
open, and one version is opened once however many ask at the same time."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from openproceedings.api.state import IndexState, Pinned
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.index import IndexBuildError
from openproceedings.engine.protocol import EngineInternalError

from tests.contract.conftest import Store

Logs = Callable[[], list[dict[str, Any]]]
VERSIONS = ("aaaa01", "bbbb02", "cccc03")


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class Opener:
    """Counts opens; a fake engine names the directory it opened, unless told to fail or lie."""

    def __init__(self) -> None:
        self.opened: list[str] = []
        self.fail: dict[str, BaseException] = {}
        self.names: dict[str, str] = {}  # directory -> the index_version its engine reports
        self.gate: dict[str, threading.Event] = {}  # directory -> wait on this before opening

    def __call__(self, path: Path) -> Any:
        self.opened.append(path.name)
        if path.name in self.gate:
            assert self.gate[path.name].wait(10)
        if path.name in self.fail:
            raise self.fail[path.name]
        return SimpleNamespace(index_version=self.names.get(path.name, path.name))


@pytest.fixture
def indexes(tmp_path: Path) -> Path:
    """A data directory whose indexes/ holds three version-named directories (the fake opener reads none)."""
    for v in VERSIONS:
        (tmp_path / "indexes" / v).mkdir(parents=True)
    return tmp_path


def state(data_dir: Path, opener: Opener, clock: Clock | None = None, keep: int = 2) -> IndexState:
    return IndexState(
        data_dir, "current", opener, keep_pinned=keep, refusal_seconds=60.0, clock=clock or Clock()
    )


def test_a_version_opens_once_and_is_served_from_the_cache(indexes: Path) -> None:
    opener = Opener()
    s = state(indexes, opener)
    first = s.pinned("aaaa01")
    assert first.reason == "ok" and first.engine is not None and first.engine.index_version == "aaaa01"
    assert s.pinned("aaaa01").engine is first.engine
    assert opener.opened == ["aaaa01"]


def test_the_lru_drops_the_least_recently_used_and_reopens_it(indexes: Path) -> None:
    opener = Opener()
    s = state(indexes, opener, keep=2)
    s.pinned("aaaa01")
    s.pinned("bbbb02")
    s.pinned("aaaa01")  # used again: bbbb02 is now the least recent
    s.pinned("cccc03")  # a third version: bbbb02 goes
    assert opener.opened == ["aaaa01", "bbbb02", "cccc03"]
    s.pinned("aaaa01")  # still held
    assert opener.opened == ["aaaa01", "bbbb02", "cccc03"]
    s.pinned("bbbb02")  # dropped, so opened (and hashed) again
    assert opener.opened == ["aaaa01", "bbbb02", "cccc03", "bbbb02"]


@pytest.mark.parametrize("name", ["current", "../indexes", "ABC", "dddd04", ""])
def test_a_name_that_is_not_an_index_here_is_absent_without_opening(indexes: Path, name: str) -> None:
    opener = Opener()
    assert state(indexes, opener).pinned(name) == Pinned(None, "absent")
    assert opener.opened == []


def test_a_symlink_named_like_a_version_is_absent_not_the_version_it_points_to(indexes: Path) -> None:
    (indexes / "indexes" / "eeee05").symlink_to("aaaa01")
    opener = Opener()
    assert state(indexes, opener).pinned("eeee05") == Pinned(None, "absent")
    assert opener.opened == []  # never opened as eeee05, never mistaken for aaaa01


def test_an_engine_reporting_another_version_is_tampered(indexes: Path, logs: Logs) -> None:
    opener = Opener()
    opener.names["aaaa01"] = "bbbb02"
    assert state(indexes, opener).pinned("aaaa01") == Pinned(None, "tampered")
    (line,) = [x for x in logs() if x["event"] == "pinned_index_unavailable"]
    assert line["level"] == "ERROR" and line["reason"] == "tampered"


@pytest.mark.parametrize(
    "error, reason, level",
    [
        (IndexBuildError("its files don't match its manifest"), "tampered", "ERROR"),
        (EngineInternalError(DiagnosticCode.API_INTERNAL, "another tokenizer"), "unloadable", "WARNING"),
        (ValueError("corrupt segment"), "unloadable", "WARNING"),  # what Tantivy raises
        (OSError("unreadable"), "unloadable", "WARNING"),
    ],
)
def test_an_index_that_wont_open_is_refused_with_its_reason_and_logged_once(
    indexes: Path, logs: Logs, error: BaseException, reason: str, level: str
) -> None:
    opener = Opener()
    opener.fail["aaaa01"] = error
    s = state(indexes, opener)
    for _ in range(3):
        assert s.pinned("aaaa01") == Pinned(None, reason)  # type: ignore[arg-type]
    assert opener.opened == ["aaaa01"]  # remembered: not re-verified per request
    lines = [x for x in logs() if x["event"] == "pinned_index_unavailable"]
    assert [(x["level"], x["reason"], x["error"]) for x in lines] == [(level, reason, type(error).__name__)]
    assert "unreadable" not in str(lines) and "corrupt" not in str(lines)  # the type, never the message


def test_a_refusal_is_forgotten_after_its_ttl_and_on_reload(indexes: Path) -> None:
    opener, clock = Opener(), Clock()
    opener.fail["aaaa01"] = ValueError("corrupt")
    s = state(indexes, opener, clock)
    s.pinned("aaaa01")
    clock.now += 59
    s.pinned("aaaa01")
    assert opener.opened == ["aaaa01"]
    clock.now += 2  # past the TTL
    s.pinned("aaaa01")
    assert opener.opened == ["aaaa01", "aaaa01"]
    s.load()  # a reload (SIGHUP) forgets every refusal (its own load fails here: no `current`)
    del opener.fail["aaaa01"]
    assert s.pinned("aaaa01").reason == "ok"


def test_absent_versions_are_remembered_too(indexes: Path, logs: Logs) -> None:
    s = state(indexes, Opener())
    for _ in range(3):
        assert s.pinned("dddd04").reason == "absent"
    lines = [x for x in logs() if x["event"] == "pinned_index_unavailable"]
    assert [(x["level"], x["reason"]) for x in lines] == [("DEBUG", "absent")]  # a client can name any


def test_a_cache_hit_never_waits_for_another_versions_open(indexes: Path) -> None:
    opener = Opener()
    s = state(indexes, opener, keep=3)
    s.pinned("bbbb02")
    opener.gate["aaaa01"] = threading.Event()
    with ThreadPoolExecutor(1) as pool:
        slow = pool.submit(s.pinned, "aaaa01")  # opening, held at the gate
        while "aaaa01" not in opener.opened:
            time.sleep(0.001)
        started = time.monotonic()
        assert s.pinned("bbbb02").reason == "ok"  # served while aaaa01 is still opening
        s.pinned("cccc03")  # and another version opens alongside
        assert time.monotonic() - started < 5
        opener.gate["aaaa01"].set()
        assert slow.result(10).reason == "ok"


def test_one_version_asked_for_at_once_is_opened_once(indexes: Path) -> None:
    opener = Opener()
    opener.gate["aaaa01"] = gate = threading.Event()
    s = state(indexes, opener)
    with ThreadPoolExecutor(4) as pool:
        futures = [pool.submit(s.pinned, "aaaa01") for _ in range(4)]
        time.sleep(0.05)
        gate.set()
        engines = {id(f.result(10).engine) for f in futures}
    assert opener.opened == ["aaaa01"] and len(engines) == 1


def test_the_served_engine_is_returned_without_opening(data_dir: Path, store: Store) -> None:
    from openproceedings.engine.tantivy_engine import TantivyEngine

    opened: list[str] = []

    def opener(path: Path) -> TantivyEngine:
        opened.append(path.name)
        return TantivyEngine(path)

    s = IndexState(data_dir, "current", opener)
    assert s.load()
    assert s.pinned(store.big) == Pinned(s.engine, "ok")
    assert opened == [store.big]  # the startup load only


def test_available_leaves_out_refused_versions(data_dir: Path, store: Store) -> None:
    from openproceedings.engine.tantivy_engine import TantivyEngine

    fail = {store.small}

    def opener(path: Path) -> TantivyEngine:
        if path.name in fail:
            raise ValueError("corrupt segment")
        return TantivyEngine(path)

    s = IndexState(data_dir, "current", opener)
    assert s.load()
    assert s.available(s.engine) == sorted([store.big, store.small])
    assert s.pinned(store.small).reason == "unloadable"
    assert s.available(s.engine) == [store.big]
