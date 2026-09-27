"""Spec 03 performance budgets on the fixture index (spec 07 §E; performance-profiler agent; task-031).

Benchmarks are off in ordinary runs (`--benchmark-disable` in pyproject's addopts: each function then runs
once, as a test). The `bench` workflow runs `--benchmark-enable --benchmark-only` on a pull request's base
and head, fails a regression of the minimum over 20% (the least noise-prone statistic), and these tests
assert the budgets from the timings measured:
- a search returning the first 50 hits: p95 < 100 ms (every Trust-Evals protocol string, Scholar mode);
- `match_ids` with exclusion accounting: p95 < 300 ms;
- a wildcard expansion of up to 200 terms: p95 < 50 ms.
The ~80k corpus and the position-verified cases are measured by `backend/tests/bench/report_80k.py` into
`docs/results/` (a report, not a gate: spec 03 records their exception).
"""

from __future__ import annotations

import time
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.compile import FIELDS
from openproceedings.engine.exclusions import excluded
from openproceedings.engine.protocol import MAX_EXPANSIONS, EngineInputError
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.ast import Wildcard
from openproceedings.query.parser import ParseResult, parse

from tests.fixtures.corpus.synthetic_5k import records
from tests.golden.test_trust_evals import STRINGS
from tests.unit.engine.test_exclusions import tantivy_of

ROUNDS = 30


@pytest.fixture(scope="module")
def engine(tmp_path_factory: pytest.TempPathFactory) -> TantivyEngine:
    return tantivy_of(list(records()), tmp_path_factory.mktemp("bench"))


def p95(benchmark: Any) -> float | None:
    """The 95th-percentile time of the measured rounds, in seconds; None when benchmarks are disabled."""
    stats = getattr(benchmark, "stats", None)
    if stats is None:
        return None
    data = sorted(stats.stats.data)
    return data[min(len(data) - 1, int(0.95 * len(data)))]


def measure(benchmark: Any, f: Callable[[], object]) -> object:
    """ROUNDS rounds of at least ~1 ms each: a sub-millisecond call is repeated within a round, so a 20% gate
    compares real work, not timer and scheduler noise."""
    t = time.perf_counter()
    f()
    once = time.perf_counter() - t
    iterations = max(1, min(1_000, round(0.001 / max(once, 1e-7))))
    return benchmark.pedantic(f, rounds=ROUNDS, iterations=iterations, warmup_rounds=1)


def trust_evals(name: str) -> ParseResult:
    result = parse(STRINGS[name], "scholar")
    assert result.effective_ast is not None
    return result


@pytest.mark.parametrize("name", list(STRINGS))
def test_search_first_50_hits(benchmark: Any, engine: TantivyEngine, name: str) -> None:
    ast = trust_evals(name).effective_ast
    assert ast is not None
    measure(benchmark, lambda: engine.search(ast, limit=50))
    time = p95(benchmark)
    assert time is None or time < 0.100, f"p95 {time * 1000:.1f} ms"


@pytest.mark.parametrize("name", list(STRINGS))
def test_match_ids_with_exclusion_accounting(benchmark: Any, engine: TantivyEngine, name: str) -> None:
    result = trust_evals(name)
    ast = result.effective_ast
    assert ast is not None

    def run() -> object:
        engine.verified.clear()  # a cold verified-clause cache, as for a new query
        ids = engine.match_ids(ast)
        return excluded(engine, result, len(ids))

    measure(benchmark, run)
    time = p95(benchmark)
    assert time is None or time < 0.300, f"p95 {time * 1000:.1f} ms"


SHAPES = {
    "broad": "the",  # thousands of matches: the whole-set collection and the facets dominate
    "widest wildcard": None,  # the widest expansion under the cap, inside a search (filled in below)
    "multi-token NEAR": '"large language" NEAR/3 model',
    "nested NOT": "trust NOT (model NOT (language OR NOT agent))",
}


@pytest.mark.parametrize("sort", ["relevance", "year_desc", "year_asc", "title"])
@pytest.mark.parametrize("shape", list(SHAPES))
def test_search_shapes_and_sorts(benchmark: Any, engine: TantivyEngine, shape: str, sort: str) -> None:
    q = SHAPES[shape] or f"{widest_stem(engine)[0]}*"
    ast = parse(q).effective_ast
    assert ast is not None
    measure(benchmark, lambda: engine.search(ast, sort=sort, limit=50))
    time_ = p95(benchmark)
    assert time_ is None or time_ < 0.100, f"p95 {time_ * 1000:.1f} ms"


def test_match_ids_with_exclusions_on_a_broad_query(benchmark: Any, engine: TantivyEngine) -> None:
    result = parse("the")
    ast = result.effective_ast
    assert ast is not None
    measure(benchmark, lambda: excluded(engine, result, len(engine.match_ids(ast))))
    time_ = p95(benchmark)
    assert time_ is None or time_ < 0.300, f"p95 {time_ * 1000:.1f} ms"


def test_an_export_drains_every_document(benchmark: Any, engine: TantivyEngine) -> None:
    ast = parse("the").effective_ast
    assert ast is not None
    measure(benchmark, lambda: sum(1 for _ in engine.documents(ast)[1]))


def test_a_small_index_build(benchmark: Any, tmp_path_factory: pytest.TempPathFactory) -> None:
    # 500 records in one process: the build's own path (normalizing, title ranks, writing), for the 20% gate
    from datetime import UTC, datetime

    from openproceedings.engine.index import build_index

    from tests.unit.engine.test_exclusions import BUILT, DedupResult, as_paper, render

    papers = tuple(sorted((as_paper(r) for r in records()[:500]), key=lambda p: p.id))
    snap = tmp_path_factory.mktemp("snap")
    for name, data in render(DedupResult(papers, (), ()), [], BUILT).items():
        (snap / name).write_bytes(data)

    def build() -> object:
        return build_index(snap, tmp_path_factory.mktemp("idx"), datetime(2026, 9, 26, tzinfo=UTC), workers=1)

    benchmark.pedantic(build, rounds=5, iterations=1, warmup_rounds=0)


def widest_stem(engine: TantivyEngine) -> tuple[str, int]:
    """The stem whose `*` expansion over the index is the largest at or under the cap."""
    terms = sorted({t for f in FIELDS for t, _df in engine.searcher.terms_with_prefix(f, "")})
    best = ("", 0)
    for stem in sorted({t[:k] for t in terms for k in range(2, len(t))}):
        n = bisect_right(terms, stem + "\U0010ffff") - bisect_left(terms, stem)
        if best[1] < n <= MAX_EXPANSIONS:
            best = (stem, n)
    return best


def test_a_wildcard_of_up_to_200_terms(benchmark: Any, engine: TantivyEngine) -> None:
    stem, n = widest_stem(engine)
    assert n >= 100  # the fixture has an expansion near the cap (117 terms)
    w = Wildcard(span=(0, 0), stem=stem, op="*")

    def run() -> list[str]:
        engine.expanded.clear()  # expansion is memoised per engine: measure the dictionary walk
        return engine.expand(w)

    assert len(measure(benchmark, run)) == n  # type: ignore[arg-type]
    time = p95(benchmark)
    assert time is None or time < 0.050, f"p95 {time * 1000:.1f} ms"


def test_a_wildcard_past_the_cap_is_refused_as_fast(benchmark: Any, engine: TantivyEngine) -> None:
    w = Wildcard(span=(0, 0), stem="co", op="*")  # ~1,100 terms: counted, then refused

    def run() -> object:
        engine.expanded.clear()
        try:
            return engine.expand(w)
        except EngineInputError as e:
            return e.code

    assert measure(benchmark, run) == DiagnosticCode.WILDCARD_TOO_MANY_EXPANSIONS
    time = p95(benchmark)
    assert time is None or time < 0.050, f"p95 {time * 1000:.1f} ms"


def test_benchmarks_are_off_in_ordinary_runs() -> None:
    import tomllib

    addopts = tomllib.loads((Path(__file__).parents[3] / "pyproject.toml").read_text())["tool"]["pytest"][
        "ini_options"
    ]["addopts"]
    assert "--benchmark-disable" in addopts  # the bench workflow turns them on
