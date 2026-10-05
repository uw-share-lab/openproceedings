"""Spec 03 performance budgets on the fixture index (spec 07 §E; performance-profiler agent; task-031).

Benchmarks are off in ordinary runs (`--benchmark-disable` in pyproject's addopts: each function then runs
once, as a test). The `bench` workflow runs `--benchmark-enable --benchmark-only` on a pull request's base
and head, fails a regression of the minimum over 20% (the least noise-prone statistic), and these tests
assert the budgets from the timings measured:
- a search returning the first 50 hits: p95 < 100 ms (every Trust-Evals protocol string, Scholar mode), with
  and without its display records and highlights (task-073; exclusion accounting has its own budget), and
  as the `/search` endpoint runs it, with exclusion accounting, facets, each hit's `abstract_source` and its
  concept groups' counts at `ApiConfig`'s bounds too (first page, facet memo cold; TASK-134, TASK-176), a
  warm later page of each, and a query of ten one-word groups (the most `/search` counts);
- `match_ids` with exclusion accounting: p95 < 300 ms;
- a wildcard expansion of up to 200 terms: p95 < 50 ms.
The ~80k corpus and the position-verified cases are measured by `backend/tests/bench/report_80k.py` into
`docs/results/` (a report, not a gate: spec 03 records their exception).
"""

from __future__ import annotations

import time
from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from openproceedings import search
from openproceedings.api.config import ApiConfig
from openproceedings.api.search import page_attributions
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.compile import FIELDS
from openproceedings.engine.exclusions import ORDER, excluded
from openproceedings.engine.highlight import Highlighter
from openproceedings.engine.protocol import MAX_EXPANSIONS, EngineInputError
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.ingest.snapshot import RecordFile
from openproceedings.query.ast import Node, Wildcard
from openproceedings.query.parser import ParseResult, parse
from openproceedings.search import Shown

from tests.contract.conftest import attributed, build
from tests.fixtures.corpus.synthetic_5k import records
from tests.golden.test_trust_evals import STRINGS
from tests.unit.engine.test_exclusions import tantivy_of

ROUNDS = 30
ENDPOINT_ROUNDS = 100  # the `/search` rows: its p95 over fewer rounds is little more than the slowest one
# what the `/search` route passes `search.run` for its concept groups, at an instance's defaults (api/search.py)
_DEFAULTS = {name: field.default for name, field in ApiConfig.model_fields.items()}
# each `search.run` argument and the `ApiConfig` field the route passes as it
GROUP_FIELDS = {
    "groups": "max_counted_groups",
    "groups_terms": "max_counted_terms",
    "groups_ids": "max_counted_ids",
    "groups_wait": "group_count_wait_seconds",
    "groups_grace": "group_count_grace_seconds",
}
GROUPS: dict[str, Any] = {arg: _DEFAULTS[field] for arg, field in GROUP_FIELDS.items()}
# ten one-word groups (`max_counted_groups`), the fixture's commonest words: 20 collections when counted
TEN_GROUPS = "agent ai benchmark calibration language bias dataset human trust model"


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


def measure(benchmark: Any, f: Callable[[], object], rounds: int = ROUNDS) -> object:
    """ROUNDS rounds of at least ~1 ms each: a sub-millisecond call is repeated within a round, so a 20% gate
    compares real work, not timer and scheduler noise."""
    f()  # the first call is cold (compile, expansion, verified clauses): size the rounds on a warm one
    t = time.perf_counter()
    f()
    once = time.perf_counter() - t
    iterations = max(1, min(1_000, round(0.001 / max(once, 1e-7))))
    return benchmark.pedantic(f, rounds=rounds, iterations=iterations, warmup_rounds=1)


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


def search_with_highlights(engine: TantivyEngine, ast: Node, limit: int = 50) -> list[object]:
    """A search's first `limit` hits as `search.run` assembles them for the API, less exclusion accounting
    (budgeted on its own, 300 ms) and facets: the page, its display records and each hit's highlights, the
    part no engine cache holds, so every call pays for it (task-073)."""
    _total, page = engine.page(ast, limit=limit)
    shown = engine.display([i for i, _score in page])
    lit = Highlighter(ast, engine.expansions(ast))
    return [lit(Shown.of(shown[i])) for i, _score in page]


@pytest.mark.parametrize("name", list(STRINGS))
def test_search_first_50_hits_with_highlights(benchmark: Any, engine: TantivyEngine, name: str) -> None:
    ast = trust_evals(name).effective_ast
    assert ast is not None
    measure(benchmark, lambda: search_with_highlights(engine, ast))
    time = p95(benchmark)
    assert time is None or time < 0.100, f"p95 {time * 1000:.1f} ms"


def search_endpoint(
    engine: TantivyEngine,
    parsed: ParseResult,
    offset: int = 0,
    first: bool = True,
    records: RecordFile | None = None,
) -> search.Search:
    """The whole of `GET /api/v1/search`'s engine work: `search.run` with facets, highlights and the concept
    groups' counts at the route's default bounds (page, display records, highlights, exclusion accounting,
    disjunctive facets and the counts, the last two on worker threads overlapping the page, so its wall time
    is below its CPU time), and with `records` each hit's `abstract_source` (TASK-134: a lookup in what the
    snapshot reader computed at load, then the response object). `first` forgets the facet memo, which the
    counts' collections share, so the call pays as a query's first page does (compiled queries and verified
    clauses stay warm); otherwise it is a later page of the same query, its counts from the memo."""
    if first:
        engine.faceted.clear()
    found = search.run(engine, parsed, offset=offset, limit=50, facets=True, highlight=True, **GROUPS)
    if records is not None:
        page_attributions(records, [h.id for h in found.hits])
    return found


# a round with one of these skipped the counting it is timed for (the grace or the wait ran out, or the pool was
# full): its time is a search without counts, so a measured round must have none
SKIPPED = ("busy", "count_failed", "timed_out")


class Outcomes:
    """`f` called as before, with how each warm call's groups came back (`counted`, or the `not_counted`
    reason): what the measured rounds measured. The first call, the cold one `measure` leaves untimed, is not
    recorded."""

    def __init__(self, f: Callable[[], search.Search]) -> None:
        self.f, self.calls, self.seen = f, 0, Counter[str]()

    def __call__(self) -> search.Search:
        found = self.f()
        self.calls += 1
        if self.calls > 1:
            assert found.groups is not None
            self.seen[found.groups.not_counted or "counted"] += 1
        return found

    def check(self, time: float | None) -> None:
        """When the rounds were timed, none of them skipped its counting (PERF-R2-N: at a 50 ms grace a
        busy machine's rounds can come back `timed_out`, and the p95 would then time less work)."""
        assert time is None or not set(self.seen) & set(SKIPPED), dict(self.seen)


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> tuple[TantivyEngine, RecordFile]:
    """The 5k corpus as the API serves it: its index and its snapshot's reader, the records carrying authors
    and abstract claims (`attributed`), so `abstract_source` is built for most hits."""
    root = tmp_path_factory.mktemp("bench-served")
    version = build(list(records()), root / "snapshots", "bench", root / "indexes", attributed)
    return TantivyEngine(root / "indexes" / version), RecordFile(root / "snapshots" / "bench")


@pytest.mark.parametrize("name", list(STRINGS))
def test_search_endpoint_first_page(
    benchmark: Any, served: tuple[TantivyEngine, RecordFile], name: str
) -> None:
    engine, snapshot = served
    parsed = trust_evals(name)
    rounds = Outcomes(lambda: search_endpoint(engine, parsed, records=snapshot))
    measure(benchmark, rounds, ENDPOINT_ROUNDS)  # facets overlap
    time = p95(benchmark)
    assert time is None or time < 0.100, f"p95 {time * 1000:.1f} ms"
    rounds.check(time)


@pytest.mark.parametrize("name", list(STRINGS))
def test_search_endpoint_later_page(
    benchmark: Any, served: tuple[TantivyEngine, RecordFile], name: str
) -> None:
    """The second page of the same query: every memo warm (facets and counts collected by the first)."""
    engine, snapshot = served
    parsed = trust_evals(name)
    search_endpoint(engine, parsed, records=snapshot)  # the first page
    rounds = Outcomes(lambda: search_endpoint(engine, parsed, 50, first=False, records=snapshot))
    measure(benchmark, rounds, ENDPOINT_ROUNDS)
    time = p95(benchmark)
    assert time is None or time < 0.100, f"p95 {time * 1000:.1f} ms"
    rounds.check(time)


def test_search_endpoint_ten_groups(benchmark: Any, served: tuple[TantivyEngine, RecordFile]) -> None:
    """The most groups `/search` counts, each a common word: 20 collections on a first page."""
    engine, snapshot = served
    parsed = parse(TEN_GROUPS)
    rounds = Outcomes(lambda: search_endpoint(engine, parsed, records=snapshot))
    measure(benchmark, rounds, ENDPOINT_ROUNDS)
    time = p95(benchmark)
    assert time is None or time < 0.100, f"p95 {time * 1000:.1f} ms"
    rounds.check(time)
    assert time is None or set(rounds.seen) == {"counted"}, dict(
        rounds.seen
    )  # every timed round counted all ten


def test_the_endpoint_bench_counts_groups(served: tuple[TantivyEngine, RecordFile]) -> None:
    """The endpoint rows measure counting: the ten-group query and the Trust-Evals strings within the
    default bounds are counted (a patient grace here: what is checked is that they are asked for and fit)."""
    engine, _snapshot = served
    patient = {**GROUPS, "groups_grace": 30.0, "groups_wait": 30.0}
    ten = search.run(engine, parse(TEN_GROUPS), limit=50, facets=True, **patient).groups
    assert ten is not None and ten.not_counted is None and len(ten.counts) == 10
    counted = [search.run(engine, trust_evals(n), limit=50, **patient).groups for n in STRINGS]
    assert all(g is not None for g in counted)
    assert any(g is not None and g.not_counted is None for g in counted)


def test_the_group_counts_report_writes_a_row_per_page(
    served: tuple[TantivyEngine, RecordFile], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`group_counts_report.table` (run by hand, never in CI) still runs: one round, a first and a later page
    of one Trust-Evals string, as its Trust-Evals table times every string."""
    from tests.bench import group_counts_report as report

    monkeypatch.setattr(report, "ROUNDS", 1)
    engine, _snapshot = served
    name = next(iter(STRINGS))
    rows = report.table(engine, [(f"`{name}`", trust_evals(name))]).splitlines()[2:]
    assert [r.split(" | ")[0] for r in rows] == [f"| `{name}`"] * 2
    assert [r.split(" | ")[2] for r in rows] == ["first page", "later page"]


def test_the_endpoint_bench_builds_attributions(served: tuple[TantivyEngine, RecordFile]) -> None:
    engine, snapshot = served
    parsed = trust_evals(next(iter(STRINGS)))
    found = search.run(engine, parsed, limit=50)
    built = page_attributions(snapshot, [h.id for h in found.hits])
    assert found.hits and any(a is not None for a in built.values())


@pytest.mark.parametrize("name", list(STRINGS))
def test_match_ids_with_exclusion_accounting(benchmark: Any, engine: TantivyEngine, name: str) -> None:
    """Historical comparison protocol: verified/compiled/expanded cold, facets retained."""
    result = trust_evals(name)
    ast = result.effective_ast
    assert ast is not None

    def run() -> object:
        engine.verified.clear()
        engine.compiled.clear()
        engine.expanded.clear()
        ids = engine.match_ids(ast)
        return excluded(engine, result, len(ids))

    measure(benchmark, run)
    time = p95(benchmark)
    assert time is None or time < 0.300, f"p95 {time * 1000:.1f} ms"


@pytest.mark.parametrize("name", list(STRINGS))
def test_match_ids_with_exclusion_accounting_all_engine_caches_cold(
    benchmark: Any, engine: TantivyEngine, name: str
) -> None:
    """First-query protocol, separately named because the historical benchmark retains facets."""
    result = trust_evals(name)
    ast = result.effective_ast
    assert ast is not None

    def run() -> object:
        engine.verified.clear()
        engine.compiled.clear()
        engine.expanded.clear()
        engine.faceted.clear()
        engine._ords = None
        ids = engine.match_ids(ast)
        return excluded(engine, result, len(ids))

    measure(benchmark, run)
    time = p95(benchmark)
    assert time is None or time < 0.300, f"p95 {time * 1000:.1f} ms"


BROAD = "a OR agent OR ai OR and OR the OR of"  # ~97% of the fixture, without the default filters
SHAPES = {
    "broad": BROAD,  # thousands of matches (no default filters): the whole-set collection dominates
    "widest wildcard": None,  # the widest expansion under the cap, inside a search (filled in below)
    "multi-token NEAR": '"large language" NEAR/3 model',
    "nested NOT": "trust NOT (model NOT (language OR NOT agent))",
}


@pytest.mark.parametrize("sort", ["relevance", "year_desc", "year_asc", "title"])
@pytest.mark.parametrize("shape", list(SHAPES))
def test_search_shapes_and_sorts(benchmark: Any, engine: TantivyEngine, shape: str, sort: str) -> None:
    q = SHAPES[shape] or f"{widest_stem(engine)[0]}*"
    parsed = parse(q)
    ast = parsed.ast if shape == "broad" else parsed.effective_ast  # broad: the raw tree, no default filters
    assert ast is not None
    if shape == "broad":
        assert len(engine.match_ids(ast)) > 2_500  # a floor, so fixture drift can't narrow it silently
    measure(benchmark, lambda: engine.search(ast, sort=sort, limit=50))
    time_ = p95(benchmark)
    assert time_ is None or time_ < 0.100, f"p95 {time_ * 1000:.1f} ms"


def test_match_ids_with_exclusions_on_a_broad_query(benchmark: Any, engine: TantivyEngine) -> None:
    result = parse(BROAD)  # exclusions need the default filters, so the effective tree
    ast = result.effective_ast
    assert ast is not None
    measure(benchmark, lambda: excluded(engine, result, len(engine.match_ids(ast))))
    time_ = p95(benchmark)
    assert time_ is None or time_ < 0.300, f"p95 {time_ * 1000:.1f} ms"


def test_match_ids_with_exclusions_on_a_broad_query_defaults(benchmark: Any, engine: TantivyEngine) -> None:
    """The exclusion-only caller beside the original all-facets benchmark (TASK-166)."""
    result = parse(BROAD)
    ast = result.effective_ast
    assert ast is not None
    count = partial(engine.facets, over=ORDER)
    measure(benchmark, lambda: excluded(engine, result, len(engine.match_ids(ast)), facets=count))
    time_ = p95(benchmark)
    assert time_ is None or time_ < 0.300, f"p95 {time_ * 1000:.1f} ms"


def test_an_export_drains_every_document(benchmark: Any, engine: TantivyEngine) -> None:
    ast = parse(BROAD).ast  # every match, no default filters: the drain is the cost
    assert ast is not None and len(engine.match_ids(ast)) > 2_500
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
