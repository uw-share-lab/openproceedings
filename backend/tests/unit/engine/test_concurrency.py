"""One TantivyEngine shared by FastAPI's thread pool (task-080): its memos (compiled trees, position-verified
clauses, wildcard expansions) are read and cleared from many threads at once. No request may fail because
another thread cleared a memo, and every result must equal a serial run's (guarantee 4)."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from openproceedings.engine.exclusions import excluded
from openproceedings.engine.index import build_index
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.parser import ParseResult, parse

from tests.unit.engine.test_compile import BUILT, CORPUS
from tests.unit.engine.test_index import snapshot_of

# every memo in play: plain terms, wildcards (expanded), verified phrases and NEARs (wildcard items, a term
# with itself, phrase operands), filters and NOT, so each search compiles, expands and verifies
QUERIES = [
    "alpha",
    "alpha OR trust*",
    '"alpha x*" NEAR/2 beta',
    '"in lang*"',
    "alpha NEAR/1 alpha",
    '"alpha x" NEAR/1 beta',
    'beta NEAR/0 "x y"',
    "trust$ AND NOT gamma",
    '"trust*" language',
    "gamma venue:ICLR",
    "(alpha OR gamma) year:2023",
    "delta* OR alph* OR lang$",
]
THREADS = 8
ROUNDS = 12

type Outcome = tuple[object, ...]


def outcome(engine: TantivyEngine, parsed: ParseResult) -> Outcome:
    """Everything a request reads from the engine: the set, pages with exact scores, every sort, facets,
    the exclusion accounting and the explain text (the memo's copy)."""
    ast = parsed.ast
    assert ast is not None
    total = len(engine.match_ids(ast))
    return (
        engine.match_ids(ast),
        engine.page(ast, limit=100),
        engine.page(ast, sort="year_desc", offset=1, limit=3),
        engine.ranked(ast, "title"),
        engine.facets(ast),
        engine.explain(ast),
        excluded(engine, parsed, total).to_json(),
    )


class Yielding(dict[Any, Any]):
    """A memo that gives the GIL away inside every operation, after doing it. CPython 3.12 checks for a
    thread switch only at calls and backward jumps, so on a plain dict `if k in d: d[k]` happens never to be
    interrupted; a free-threaded build, or any Python-level hook, interrupts it. This makes every gap between
    two memo operations one where another thread may run (and clear the memo)."""

    def __contains__(self, key: object) -> bool:
        found = super().__contains__(key)
        time.sleep(0)
        return found

    def __getitem__(self, key: Any) -> Any:
        value = super().__getitem__(key)
        time.sleep(0)
        return value

    def get(self, key: Any, default: Any = None) -> Any:
        value = super().get(key, default)
        time.sleep(0)
        return value

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        time.sleep(0)

    def clear(self) -> None:
        super().clear()
        time.sleep(0)

    def __len__(self) -> int:
        n = super().__len__()
        time.sleep(0)
        return n


@pytest.fixture
def index_path(tmp_path: Path) -> Path:
    return build_index(snapshot_of(CORPUS, tmp_path / "snap"), tmp_path / "indexes", BUILT).path


@pytest.fixture
def engine(index_path: Path, monkeypatch: pytest.MonkeyPatch) -> TantivyEngine:
    # bound 0: every miss clears the memo, so reads race clears as often as they can
    for bound in ("MAX_COMPILED", "MAX_VERIFIED", "MAX_EXPANDED"):
        monkeypatch.setattr(TantivyEngine, bound, 0)
    engine = TantivyEngine(index_path)
    engine.compiled, engine.verified, engine.expanded = Yielding(), Yielding(), Yielding()
    return engine


@pytest.fixture
def switch_often() -> Iterator[None]:
    """Hand the GIL over as often as CPython allows, so check-then-read windows interleave."""
    before = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        yield
    finally:
        sys.setswitchinterval(before)


@pytest.mark.usefixtures("switch_often")
def test_concurrent_searches_with_clearing_memos_equal_a_serial_run(
    engine: TantivyEngine, index_path: Path
) -> None:
    asts = [parse(q) for q in QUERIES]
    # the reference comes from a separate engine with plain, default-bounded memos, so a memo bug that is
    # wrong the same way every time can't make the threaded results and their reference agree
    fresh = TantivyEngine(index_path)
    fresh.MAX_COMPILED = fresh.MAX_VERIFIED = fresh.MAX_EXPANDED = 10_000
    serial = [outcome(fresh, ast) for ast in asts]
    assert serial == [outcome(engine, ast) for ast in asts]  # the racing engine agrees before any thread runs

    start = threading.Barrier(THREADS)
    errors: list[BaseException] = []
    got: list[list[tuple[int, Outcome]]] = [[] for _ in range(THREADS)]

    def run(t: int) -> None:
        start.wait()
        try:
            for r in range(ROUNDS):
                for k in range(len(asts)):
                    i = (k + t + r) % len(asts)  # each thread walks the queries from its own offset
                    got[t].append((i, outcome(engine, asts[i])))
        except BaseException as e:  # collected, then asserted empty on the main thread
            errors.append(e)

    threads = [threading.Thread(target=run, args=(t,)) for t in range(THREADS)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert not errors, [repr(e) for e in errors]
    assert sum(map(len, got)) == THREADS * ROUNDS * len(asts)
    for results in got:
        for i, result in results:
            assert result == serial[i], QUERIES[i]
