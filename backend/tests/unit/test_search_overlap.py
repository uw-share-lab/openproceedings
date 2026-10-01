"""`search.run` with its facet aggregation on a worker thread (task-088; M3a review gate round 2): the same
`Search`, field for field, as the sequential path it replaced (a frozen copy below), on the Trust-Evals strings
over the synthetic 5k fixture and on random queries; the worker's errors re-raised as they were, the caller's
first; the request's log context carried into the worker; the pool restartable after `shutdown`."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from openproceedings import logs, search
from openproceedings.engine.exclusions import excluded
from openproceedings.engine.highlight import Highlighter
from openproceedings.engine.protocol import EngineInputError, EngineInternalError
from openproceedings.engine.tantivy_engine import SORTS, Scope, TantivyEngine
from openproceedings.query.parser import ParseResult, parse
from openproceedings.search import Hit, Search, Shown

from tests.fixtures.corpus.synthetic_5k import records
from tests.golden.test_trust_evals import STRINGS
from tests.strategies import queries
from tests.unit.engine.test_exclusions import tantivy_of


# --- frozen: search.run before the overlap (30756ce) ---------------------------------------------------------
def sequential(
    engine: TantivyEngine,
    parsed: ParseResult,
    *,
    sort: str = "relevance",
    offset: int = 0,
    limit: int = 50,
    facets: bool = False,
    highlight: bool = False,
) -> Search:
    ast = parsed.effective_ast
    assert ast is not None
    expansions = search.expanded(engine, ast)
    total, page = engine.page(ast, sort=sort, offset=offset, limit=limit)
    gone = excluded(engine, parsed, total)
    shown = engine.display([i for i, _score in page])
    lit = Highlighter(ast, expansions) if highlight else None
    hits = tuple(
        Hit(id=i, score=score, record=shown[i], highlights=lit(Shown.of(shown[i])) if lit else None)
        for i, score in page
    )
    return Search(total, hits, gone, expansions, engine.facets(ast) if facets else None)


# ------------------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pair(tmp_path_factory: pytest.TempPathFactory) -> tuple[TantivyEngine, TantivyEngine]:
    """Two engines over one 5k index: the overlapped path and the frozen sequential one, each with its own
    memos, so neither result can come from the other's work."""
    root = tmp_path_factory.mktemp("overlap")
    first = tantivy_of(list(records()), root)
    (built,) = (p for p in (root / "indexes").iterdir() if p.is_dir() and not p.is_symlink())
    return first, TantivyEngine(built)


def outcome(f: Any, engine: TantivyEngine, parsed: ParseResult, **kw: Any) -> Any:
    """`f`'s Search, or the type, code and message of its refusal."""
    try:
        return f(engine, parsed, **kw)
    except EngineInputError as e:
        return (type(e), e.code, e.message)


@pytest.mark.parametrize("name", [n for n in STRINGS if STRINGS[n].strip()])
def test_the_trust_evals_strings_give_the_sequential_search(
    pair: tuple[TantivyEngine, TantivyEngine], name: str
) -> None:
    overlapped, reference = pair
    parsed = parse(STRINGS[name], "scholar")
    for offset in (0, 50):
        overlapped.faceted.clear()  # the aggregation runs on the worker, not from the memo
        got = search.run(overlapped, parsed, offset=offset, limit=50, facets=True, highlight=True)
        assert got == sequential(reference, parsed, offset=offset, limit=50, facets=True, highlight=True)
        assert got.facets is not None


@settings(max_examples=150, deadline=None)
@given(q=queries())
def test_random_queries_give_the_sequential_search(pair: tuple[TantivyEngine, TantivyEngine], q: str) -> None:
    overlapped, reference = pair
    parsed = parse(q)
    if parsed.effective_ast is None:
        return
    for sort in SORTS:
        overlapped.faceted.clear()
        got = outcome(search.run, overlapped, parsed, sort=sort, limit=7, facets=True, highlight=True)
        assert got == outcome(sequential, reference, parsed, sort=sort, limit=7, facets=True, highlight=True)


class Boom(Exception):
    pass


def test_an_error_in_the_worker_is_re_raised_as_it_was(
    pair: tuple[TantivyEngine, TantivyEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = pair
    raised = Boom("facets failed")

    def facets(ast: Any, *_a: Any, **_kw: Any) -> Any:
        assert threading.current_thread() is not threading.main_thread()  # it ran on the worker
        raise raised

    monkeypatch.setattr(engine, "facets", facets)
    with pytest.raises(Boom) as caught:
        search.run(engine, parse("trust"), facets=True)
    assert caught.value is raised  # the same object, traceback and all


def test_the_callers_error_comes_first(
    pair: tuple[TantivyEngine, TantivyEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    """As when facets ran after the page: the page's error is the one raised, even if the worker fails too."""
    engine, _ = pair
    started = threading.Event()

    def facets(ast: Any, *_a: Any, **_kw: Any) -> Any:
        started.set()
        raise Boom("the worker's")

    def page(*args: Any, **kw: Any) -> Any:
        assert started.wait(10)
        raise EngineInputError(search.DiagnosticCode.API_INTERNAL, "the caller's")

    monkeypatch.setattr(engine, "facets", facets)
    monkeypatch.setattr(engine, "page", page)
    with pytest.raises(EngineInputError, match="the caller's"):
        search.run(engine, parse("trust"), facets=True)


@pytest.mark.parametrize(("kw", "what"), [({"sort": "semantic"}, "sort"), ({"offset": -1}, "offset")])
def test_a_bad_argument_is_refused_before_the_worker_starts(
    pair: tuple[TantivyEngine, TantivyEngine], monkeypatch: pytest.MonkeyPatch, kw: dict[str, Any], what: str
) -> None:
    engine, reference = pair
    calls: list[object] = []
    monkeypatch.setattr(engine, "facets", lambda ast, *_a, **_kw: calls.append(ast))
    parsed = parse("trust")
    got = outcome(search.run, engine, parsed, facets=True, **kw)
    assert got == outcome(sequential, reference, parsed, facets=True, **kw) and what in got[2]
    assert calls == []


def test_the_worker_sees_the_requests_log_fields(
    pair: tuple[TantivyEngine, TantivyEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = pair
    seen: list[tuple[str, object]] = []
    facets, caller = engine.facets, threading.current_thread().name

    def spy(*a: Any, **kw: Any) -> Any:
        seen.append((threading.current_thread().name, dict(logs._context.get())))
        return facets(*a, **kw)

    monkeypatch.setattr(engine, "facets", spy)
    with logs.bind(request_id="r-1"):
        search.run(engine, parse("trust"), facets=True)
    workers = [fields for name, fields in seen if name != caller]  # exclusion accounting's run in the caller
    assert workers == [{"request_id": "r-1"}]
    assert all(fields == {"request_id": "r-1"} for _name, fields in seen)


def test_the_pool_is_shut_down_and_starts_again(pair: tuple[TantivyEngine, TantivyEngine]) -> None:
    engine, reference = pair
    parsed = parse("trust")
    search.run(engine, parsed, facets=True)
    held = search._POOL
    assert held is not None
    search.shutdown()
    assert search._POOL is None and held._shutdown  # type: ignore[attr-defined]
    search.shutdown()  # idempotent
    engine.faceted.clear()
    assert search.run(engine, parsed, facets=True) == sequential(reference, parsed, facets=True)
    assert search._POOL is not None and search._POOL is not held


def test_a_pool_shut_down_under_a_search_counts_the_facets_in_the_caller(
    pair: tuple[TantivyEngine, TantivyEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`shutdown()` (or interpreter exit) between taking the pool and submitting: the search still answers,
    counting its facets in its own thread."""
    engine, reference = pair
    closed = ThreadPoolExecutor(1)
    closed.shutdown()
    monkeypatch.setattr(search, "_POOL", closed)
    parsed = parse("trust OR calibrat*")
    engine.faceted.clear()
    assert search.run(engine, parsed, facets=True) == sequential(reference, parsed, facets=True)


def test_a_forked_child_forgets_the_parents_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Its threads don't survive a fork (and the lock may have been held): the child starts its own."""
    parent_lock = search._POOL_LOCK
    monkeypatch.setattr(search, "_POOL", ThreadPoolExecutor(1))
    search._forget_after_fork()
    try:
        assert search._POOL is None and search._POOL_LOCK is not parent_lock
    finally:
        monkeypatch.setattr(search, "_POOL_LOCK", parent_lock)


# --- a query at the verified-clause cap over the memo budgets (M3a review gate round 3) -------------------------
AT_CAP = " OR ".join(f"model NEAR/{k} model*" for k in range(1, 9))  # 8 verified clauses, each on 2 fields


class Busy(Exception):
    """A verification slot refused (the API's 503 `API_BUSY`)."""


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("at-cap")
    tantivy_of(list(records()), root)
    (path,) = (p for p in (root / "indexes").iterdir() if p.is_dir() and not p.is_symlink())
    return path


@pytest.mark.parametrize("budget", [1, 3000])
@pytest.mark.parametrize("late_page", [False, True])
def test_a_request_verifies_each_clause_once_whatever_its_memos_forget(
    built: Path, budget: int, late_page: bool
) -> None:
    """Memo budgets below one at-cap query (8 `model NEAR/k model*` clauses), one non-blocking slot: its own
    compile clears `verified` mid-way, and the facet worker's base compile (defaults apply, so its tree
    differs) trims `compiled`. The request still verifies each clause once, in the caller's thread: the worker,
    and a page whose compiled entry was trimmed, read what this request verified and never verify it again, so
    the worker never enters the gate and the caller never meets its own slot (a 503 against itself)."""
    engine = TantivyEngine(built)
    engine.MAX_VERIFIED_IDS = engine.MAX_COMPILED_UNITS = budget  # type: ignore[misc]
    slot = threading.BoundedSemaphore(1)
    entered: list[str] = []
    read = engine.read

    def slow(*args: Any) -> Any:
        time.sleep(0.02)  # a verification takes a while, so the worker's compile overlaps the caller's page
        return read(*args)

    @contextmanager
    def gate() -> Iterator[None]:
        entered.append(threading.current_thread().name)
        if not slot.acquire(blocking=False):
            raise Busy(threading.current_thread().name)
        try:
            yield
        finally:
            slot.release()

    engine.read = slow  # type: ignore[method-assign]
    engine.verification_gate = gate
    if late_page:
        page = engine.page

        def delayed(*args: Any, **kw: Any) -> Any:
            time.sleep(0.05)  # the worker's base compile trims `compiled` before the page reads it
            return page(*args, **kw)

        engine.page = delayed  # type: ignore[method-assign]
    parsed = parse(AT_CAP)
    got = search.run(engine, parsed, facets=True)  # served: no Busy
    assert not [name for name in entered if name.startswith("op-facets")]
    assert len(entered) == 16  # 8 clauses × title and abstract, each verified once
    assert got == sequential(TantivyEngine(built), parsed, facets=True)


def test_a_read_only_scope_never_verifies(built: Path) -> None:
    """The facet worker's view (`Scope.reader`): a clause neither it nor the memo holds is an internal error,
    never a cold verification, so the worker can never enter the gate (and hold a slot)."""
    engine = TantivyEngine(built)
    entered: list[str] = []

    @contextmanager
    def gate() -> Iterator[None]:
        entered.append(threading.current_thread().name)
        yield

    engine.verification_gate = gate
    ast = parse("model NEAR/3 model*").effective_ast
    assert ast is not None
    with pytest.raises(EngineInternalError, match="never verifies"):
        engine.facets(ast, scope=Scope().reader())
    assert entered == []
    scope = Scope()
    engine.compile(ast, scope)  # the request verifies it; its reader then finds every clause
    engine.verified.clear()
    engine.compiled.clear()
    engine.faceted.clear()
    assert engine.facets(ast, scope=scope.reader()) == TantivyEngine(built).facets(ast)
    assert len(entered) == 2  # title and abstract, once each, by the compile


def test_a_caller_failing_while_the_worker_runs_leaves_no_slot_held(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page raises while the worker is still collecting: the worker, which never verifies, holds no slot."""
    engine = TantivyEngine(built)
    slot = threading.BoundedSemaphore(1)
    entered: list[str] = []

    @contextmanager
    def gate() -> Iterator[None]:
        entered.append(threading.current_thread().name)
        if not slot.acquire(blocking=False):
            raise Busy(threading.current_thread().name)
        try:
            yield
        finally:
            slot.release()

    engine.verification_gate = gate
    facets = engine.facets
    started = threading.Event()

    def slow_facets(*a: Any, **kw: Any) -> Any:
        started.set()
        time.sleep(0.05)
        return facets(*a, **kw)

    def page(*_a: Any, **_kw: Any) -> Any:
        assert started.wait(10)
        raise Boom("the caller's")

    monkeypatch.setattr(engine, "facets", slow_facets)
    monkeypatch.setattr(engine, "page", page)
    with pytest.raises(Boom):
        search.run(engine, parse(AT_CAP), facets=True)
    search.shutdown()  # waits for the worker: whatever it did is done
    assert not [n for n in entered if n.startswith("op-facets")]
    assert slot.acquire(blocking=False)  # free


# --- a warm compile seeds the request's scope (M3a review gate round 4) --------------------------------------------
def test_a_compiled_memo_hit_seeds_the_scope(built: Path) -> None:
    """The caller's compile is a compiled-memo hit, and `verified` and `faceted` were trimmed by other
    requests: the worker's base (another tree: defaults apply) must find the clauses in the request's scope,
    not reach a verification it may not make (a 500 before round 4)."""
    engine = TantivyEngine(built)
    parsed = parse(AT_CAP)
    assert parsed.effective_ast is not None
    engine.compile(parsed.effective_ast)  # an earlier request compiled this very tree
    engine.verified.clear()
    engine.faceted.clear()
    assert search.run(engine, parsed, facets=True) == sequential(TantivyEngine(built), parsed, facets=True)


def test_a_verified_memo_hit_is_kept_by_the_scope(built: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The caller's compile reads every clause from the shared `verified` memo, which another thread then
    clears before the worker compiles its base: the scope kept what the compile read."""
    engine = TantivyEngine(built)
    parsed = parse(AT_CAP)
    search.run(engine, parsed, facets=True)  # warms `verified`
    engine.compiled.clear()
    engine.faceted.clear()
    compile_ = engine.compile

    def compile_then_trim(ast: Any, scope: Any = None) -> Any:
        out = compile_(ast, scope)
        if scope is not None and scope.may_verify:
            engine.verified.clear()  # another request's store trims the memo right after
        return out

    monkeypatch.setattr(engine, "compile", compile_then_trim)
    assert search.run(engine, parsed, facets=True) == sequential(TantivyEngine(built), parsed, facets=True)


def test_a_worker_that_would_verify_is_recounted_in_the_caller(
    built: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The safety net: should the worker's read-only scope miss a clause anyway (a bug), `run` counts the
    facets in the caller, which may verify, and logs `facet_worker_recounted`; the client gets its answer."""
    engine = TantivyEngine(built)
    parsed = parse(AT_CAP)
    monkeypatch.setattr(Scope, "reader", lambda self: Scope({}, may_verify=False))  # the bug: an empty view
    facets = engine.facets

    def cold_in_the_worker(*a: Any, **kw: Any) -> Any:
        if threading.current_thread().name.startswith("op-facets"):
            engine.verified.clear()
            engine.compiled.clear()
            engine.faceted.clear()
        return facets(*a, **kw)

    monkeypatch.setattr(engine, "facets", cold_in_the_worker)
    got = search.run(engine, parsed, facets=True)
    assert got == sequential(TantivyEngine(built), parsed, facets=True)
    assert [r.message for r in caplog.records if r.message == "facet_worker_recounted"] == [
        "facet_worker_recounted"
    ]
