"""The one pinned-index loader, `IndexState.pinned(version) -> Pinned(engine, reason)` (spec 04 §Exports,
§Search records; task-036/037 reviews): a version resolves to itself or is `absent`; an engine that won't
open is `unloadable` (WARNING) or `tampered` (ERROR), refused once and remembered until the TTL or a
reload; engines are held in an LRU of the configured size; a cache hit never waits for another version's
open, and one version is opened once however many ask at the same time."""

from __future__ import annotations

import errno
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from openproceedings.api.errors import ApiError
from openproceedings.api.state import IndexState, Pinned, open_pinned
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.index import IndexBuildError
from openproceedings.engine.protocol import EngineInternalError
from openproceedings.engine.tantivy_engine import IndexUnservable

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
    "error, reason, level, cause",
    [
        (
            IndexBuildError("its files don't match its manifest", reason="files_mismatch"),
            "tampered",
            "ERROR",
            "files_mismatch",
        ),
        (
            IndexUnservable(
                DiagnosticCode.API_INTERNAL, "another tokenizer", reason="tokenizer_version_mismatch"
            ),
            "unloadable",
            "WARNING",
            "tokenizer_version_mismatch",
        ),
        (
            EngineInternalError(DiagnosticCode.API_INTERNAL, "another tokenizer"),
            "unloadable",
            "WARNING",
            None,
        ),
        (ValueError("corrupt segment"), "unloadable", "WARNING", None),  # what Tantivy raises
        (OSError("unreadable"), "unloadable", "WARNING", None),
        (PermissionError(errno.EACCES, "unreadable"), "unloadable", "WARNING", "EACCES"),  # the errno's name
    ],
)
def test_an_index_that_wont_open_is_refused_with_its_reason_and_logged_once(
    indexes: Path, logs: Logs, error: BaseException, reason: str, level: str, cause: str | None
) -> None:
    opener = Opener()
    opener.fail["aaaa01"] = error
    s = state(indexes, opener)
    for _ in range(3):
        assert s.pinned("aaaa01") == Pinned(None, reason)  # type: ignore[arg-type]
    assert opener.opened == ["aaaa01"]  # remembered: not re-verified per request
    lines = [x for x in logs() if x["event"] == "pinned_index_unavailable"]
    assert [(x["level"], x["reason"], x["error"], x.get("cause_reason")) for x in lines] == [
        (level, reason, type(error).__name__, cause)
    ]
    assert "unreadable" not in str(lines) and "corrupt" not in str(lines)  # the type, never the message


@pytest.mark.parametrize(
    "version, fail, names, want, cause",
    [
        ("aaaa01", None, {}, "ok", None),
        ("current", None, {}, "absent", "name_invalid"),  # a name, never a version
        ("dddd04", None, {}, "absent", "not_found"),
        ("eeee05", None, {}, "absent", "alias"),
        ("aaaa01", IndexBuildError("x", reason="files_mismatch"), {}, "tampered", "files_mismatch"),
        ("aaaa01", ValueError("corrupt"), {}, "unloadable", None),  # no reason constant: the key is left out
        ("aaaa01", None, {"aaaa01": "bbbb02"}, "tampered", "index_version_mismatch"),
    ],
)
def test_open_pinned_is_the_rule_without_the_cache(
    indexes: Path,
    logs: Logs,
    version: str,
    fail: BaseException | None,
    names: dict[str, str],
    want: str,
    cause: str | None,
) -> None:
    """`open_pinned`, the one function behind `IndexState.pinned` and `op record replay`: each call decides
    afresh (nothing is remembered), with one line per refusal whose `cause_reason` is left out when none."""
    (indexes / "indexes" / "eeee05").symlink_to("aaaa01")
    opener = Opener()
    opener.names.update(names)
    if fail is not None:
        opener.fail["aaaa01"] = fail
    for _ in range(2):
        found = open_pinned(indexes, version, opener)
        assert found.reason == want and (found.engine is not None) == (want == "ok")
    lines = [x for x in logs() if x["event"] == "pinned_index_unavailable"]
    assert len(lines) == (0 if want == "ok" else 2)
    for line in lines:
        assert line["reason"] == want and line.get("cause_reason", "left out") == (cause or "left out")


def test_a_pinned_engine_takes_the_states_verification_slots(indexes: Path) -> None:
    """`IndexState.pinned` gates what `open_pinned` opens (cold verification on a pinned index takes the same
    slots as on the served one, spec 04 §Rate limit); the CLI's ungated open leaves the engine's own."""
    s = state(indexes, Opener())
    engine = s.pinned("aaaa01").engine
    assert engine is not None and engine.verification_gate == s.verification_slot
    assert not hasattr(open_pinned(indexes, "aaaa01", Opener()).engine, "verification_gate")


def test_open_pinned_holds_the_slot_only_for_the_open(indexes: Path) -> None:
    """A name that isn't here is refused without taking the slot (a stat or two); an open takes it."""
    slot = threading.Lock()
    slot.acquire()  # held by another open: an absent name must not wait for it
    assert open_pinned(indexes, "dddd04", Opener(), slot=slot).reason == "absent"
    slot.release()
    seen: list[bool] = []

    def opener(path: Path) -> Any:
        seen.append(slot.locked())
        return SimpleNamespace(index_version=path.name)

    assert open_pinned(indexes, "aaaa01", opener, slot=slot).reason == "ok"
    assert seen == [True] and not slot.locked()


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
    # a client can name any; why it's absent is the selection's reason constant
    assert [(x["level"], x["reason"], x["cause_reason"]) for x in lines] == [("DEBUG", "absent", "not_found")]


def test_a_pinned_open_logs_one_line_named_pinned_index_opened(indexes: Path, logs: Logs) -> None:
    state(indexes, Opener()).pinned("aaaa01")
    (line,) = [x for x in logs() if x["event"] == "pinned_index_opened"]
    assert line["index_version"] == "aaaa01" and isinstance(line["ms"], float)


@pytest.mark.parametrize(
    ("setup", "reason", "attempted"),
    [
        (lambda d: None, "not_found", None),  # no `current`
        (lambda d: (d / "indexes" / "current").symlink_to("../elsewhere"), "not_found", None),
        (lambda d: (d / "indexes" / "current").symlink_to("aaaa01"), "files_mismatch", "aaaa01"),
    ],
)
def test_a_failed_load_names_its_reason_and_the_version_it_attempted(
    indexes: Path, logs: Logs, setup: Callable[[Path], object], reason: str, attempted: str | None
) -> None:
    """`index_load_failed` says why with a constant and which version it tried (M3a review)."""
    setup(indexes)
    opener = Opener()
    opener.fail["aaaa01"] = IndexBuildError("changed", reason="files_mismatch")
    assert not state(indexes, opener).load()
    (line,) = [x for x in logs() if x["event"] == "index_load_failed"]
    assert (line["reason"], line["index_version_attempted"], line["index_version_kept"]) == (
        reason,
        attempted,
        None,
    )


def test_an_index_name_the_selection_refuses_says_why(indexes: Path) -> None:
    from openproceedings.api.state import IndexSelectionError, index_path

    (indexes / "outside").mkdir()
    (indexes / "indexes" / "ffff06").symlink_to("../outside")
    for name, reason in (("../x", "name_invalid"), ("dddd04", "not_found"), ("ffff06", "outside_indexes")):
        with pytest.raises(IndexSelectionError) as e:
            index_path(indexes, name)
        assert e.value.reason == reason


def test_a_failing_index_listing_warns_once_per_change_of_state(
    indexes: Path, logs: Logs, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = state(indexes, Opener())
    real = Path.iterdir

    def broken(self: Path) -> Any:
        if self.name == "indexes":
            raise PermissionError(errno.EACCES, "denied")
        return real(self)

    monkeypatch.setattr(Path, "iterdir", broken)
    assert s.available(None) == [] and s.available(None) == []
    monkeypatch.setattr(Path, "iterdir", real)
    s.available(None)
    s.available(None)
    lines = [(x["event"], x["level"], x.get("reason")) for x in logs() if x["event"].startswith("index_list")]
    assert lines == [("index_list_failed", "WARNING", "EACCES"), ("index_list_recovered", "INFO", None)]


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
        assert time.monotonic() - started < 5
        opener.gate["aaaa01"].set()
        assert slow.result(10).reason == "ok"


def test_at_most_one_pinned_index_opens_at_a_time(indexes: Path) -> None:
    """Each open re-hashes a whole index, so opens of different versions take turns (security review);
    the second waits for the first, then opens (never refused, never a second hash in parallel)."""
    opener = Opener()
    opener.gate["aaaa01"] = threading.Event()
    s = state(indexes, opener, keep=3)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(s.pinned, "aaaa01")
        while "aaaa01" not in opener.opened:
            time.sleep(0.001)
        second = pool.submit(s.pinned, "cccc03")
        time.sleep(0.05)
        assert opener.opened == ["aaaa01"]  # cccc03 waits for the slot
        opener.gate["aaaa01"].set()
        assert (first.result(10).reason, second.result(10).reason) == ("ok", "ok")
    assert opener.opened == ["aaaa01", "cccc03"]


def test_a_wait_for_the_open_slot_past_its_bound_is_refused_busy(indexes: Path) -> None:
    """TASK-067: clients rotating through more versions than the LRU holds queued every worker thread behind
    the one open; past `open_wait_seconds` the wait is a 503 API_BUSY with Retry-After, never a queue."""
    opener = Opener()
    opener.gate["aaaa01"] = threading.Event()
    s = IndexState(indexes, "current", opener, keep_pinned=1, open_wait_seconds=0.05, busy_retry_seconds=7)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(s.pinned, "aaaa01")
        deadline = time.monotonic() + 10
        while "aaaa01" not in opener.opened:  # bounded: a first thread that died fails here, never hangs
            assert time.monotonic() < deadline and not first.done(), first
            time.sleep(0.001)
        started = time.monotonic()
        with pytest.raises(ApiError) as e:
            s.pinned("cccc03")
        assert time.monotonic() - started < 5
        assert e.value.code is DiagnosticCode.API_BUSY and e.value.headers == {"Retry-After": "7"}
        opener.gate["aaaa01"].set()
        assert first.result(10).reason == "ok"
    assert s.pinned("cccc03").reason == "ok" and opener.opened == ["aaaa01", "cccc03"]  # not remembered


def test_client_chosen_absent_versions_never_evict_a_remembered_tampered_one(indexes: Path) -> None:
    """`absent` is the one refusal a client causes at will (any name), so it has its own bounded map: naming
    more absent versions than the map holds can't make a tampered index be re-hashed (M3a review)."""
    from openproceedings.api.state import MAX_REFUSALS

    opener = Opener()
    opener.fail["aaaa01"] = IndexBuildError("changed", reason="files_mismatch")
    s = state(indexes, opener)
    assert s.pinned("aaaa01").reason == "tampered"
    for i in range(MAX_REFUSALS + 10):
        assert s.pinned(f"f{i:05x}").reason == "absent"
    assert s.pinned("aaaa01").reason == "tampered"
    assert opener.opened == ["aaaa01"]  # still remembered: not re-verified


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


def test_op_serve_sizes_the_pinned_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """TASK-067: the operator sizes the LRU to the versions the instance holds (spec 04)."""
    from openproceedings import cli
    from openproceedings.api import server as api_server

    served: list[Any] = []
    monkeypatch.setattr(api_server, "serve", lambda config, *a: served.append(config))
    assert cli.main(["--data-dir", str(tmp_path), "serve", "--pinned-indexes", "8"]) == 0
    assert cli.main(["--data-dir", str(tmp_path), "serve"]) == 0
    assert [c.pinned_indexes for c in served] == [8, 4]
    assert cli.main(["--data-dir", str(tmp_path), "serve", "--pinned-indexes", "0"]) == 1


def test_an_export_filename_is_only_ever_hex(tmp_path: Path) -> None:
    """TASK-067: the stored record's `canonical_hash` is an unconstrained string; the Content-Disposition
    filename takes only the hex it should be."""
    from openproceedings.api.export import filename

    assert (
        filename("0019ed0fd2ad", "9a8a63bd309f" + "0" * 52, "csv")
        == "openproceedings-0019ed0fd2ad-9a8a63bd309f.csv"
    )
    assert filename("0019ed0fd2ad", 'ab"\r\nX: y', "ris") == "openproceedings-0019ed0fd2ad-ab.ris"


def test_a_second_request_for_a_version_being_opened_waits_only_the_bound(indexes: Path) -> None:
    """TASK-067 review round 2: a request for the version already opening waits on that version's own lock,
    for at most `open_wait_seconds`, then 503 API_BUSY; and the lock is dropped afterwards."""
    opener = Opener()
    opener.gate["aaaa01"] = threading.Event()
    s = IndexState(indexes, "current", opener, keep_pinned=1, open_wait_seconds=0.05, busy_retry_seconds=7)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(s.pinned, "aaaa01")
        deadline = time.monotonic() + 10
        while "aaaa01" not in opener.opened:
            assert time.monotonic() < deadline and not first.done(), first
            time.sleep(0.001)
        started = time.monotonic()
        with pytest.raises(ApiError) as e:
            s.pinned("aaaa01")
        assert time.monotonic() - started < 5 and e.value.code is DiagnosticCode.API_BUSY
        opener.gate["aaaa01"].set()
        assert first.result(10).reason == "ok"
    assert opener.opened == ["aaaa01"] and s._opening == {}
