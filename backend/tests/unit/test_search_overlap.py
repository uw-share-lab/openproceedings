"""`search.run` with its facet aggregation on a worker thread (task-088; M3a review gate round 2): the same
`Search`, field for field, as the sequential path it replaced (a frozen copy below), on the Trust-Evals strings
over the synthetic 5k fixture and on random queries; the worker's errors re-raised as they were, the caller's
first; the request's log context carried into the worker; the pool restartable after `shutdown`."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from openproceedings import logs, search
from openproceedings.engine.exclusions import excluded
from openproceedings.engine.highlight import Highlighter
from openproceedings.engine.protocol import EngineInputError
from openproceedings.engine.tantivy_engine import SORTS, TantivyEngine
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


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
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

    def facets(ast: Any) -> Any:
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

    def facets(ast: Any) -> Any:
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
    monkeypatch.setattr(engine, "facets", lambda ast: calls.append(ast))
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

    def spy(*a: Any) -> Any:
        seen.append((threading.current_thread().name, dict(logs._context.get())))
        return facets(*a)

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
