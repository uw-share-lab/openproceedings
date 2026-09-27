"""The engine's memos are bounded by what they hold (ids, terms), not by their entry count (security review of
M3a): one verified clause can hold every id in the index, so a count bound let a long-running API hold GBs.
Each memo is cleared once the weights charged to it pass its `TantivyEngine.MAX_*` budget, and a clear never
changes a result (guarantee 4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from openproceedings.engine.index import build_index
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.parser import parse

from tests.unit.engine.test_compile import BUILT, CORPUS
from tests.unit.engine.test_concurrency import QUERIES, outcome
from tests.unit.engine.test_index import snapshot_of

# distinct verified clauses (a term with itself, a wildcard phrase): each is a new key in `verified`
VERIFIED = [f"alpha NEAR/{k} alpha" for k in range(8)] + [f'"alpha x*" NEAR/{k} beta' for k in range(8)]
# distinct wildcards: each is a new key in `expanded`
WILDCARDS = ["trust*", "trust$", "alph*", "lang*", "delt*", "gam*", "bet*", "vis*", "mod*", "trustw*"]


@pytest.fixture(scope="module")
def index_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("budget")
    return build_index(snapshot_of(CORPUS, root / "snap"), root / "indexes", BUILT).path


def unbounded(index_path: Path) -> TantivyEngine:
    engine = TantivyEngine(index_path)
    engine.MAX_COMPILED_UNITS = engine.MAX_VERIFIED_IDS = engine.MAX_EXPANDED_TERMS = (
        engine.MAX_FACET_BUCKETS
    ) = 10**9
    return engine


def verified_held(engine: TantivyEngine) -> int:
    return sum(len(ids) + 1 for ids in engine.verified.values())


def expanded_held(engine: TantivyEngine) -> int:
    return sum(1 if isinstance(t, int) else len(t) + 1 for t in engine.expanded.values())


def run(engine: TantivyEngine, q: str) -> tuple[Any, ...]:
    parsed = parse(q)
    assert parsed.ast is not None, parsed.errors
    return outcome(engine, parsed)


def test_the_ledger_charges_what_each_memo_holds(index_path: Path) -> None:
    engine = unbounded(index_path)
    for q in VERIFIED + WILDCARDS:
        run(engine, q)
    assert verified_held(engine) == sum(engine.charges["verified"]) > len(engine.verified)
    assert expanded_held(engine) == sum(engine.charges["expanded"]) > len(engine.expanded)
    held = sum(c.held + 1 for c in engine.compiled.values())
    assert held == sum(engine.charges["compiled"]) > len(engine.compiled)
    # a verified clause's ids are held by the compiled query too (its term set), so they count there as well
    ast = parse(VERIFIED[-1]).ast
    assert ast is not None
    ids = [engine.verified[(f, ast.model_dump_json())] for f in ("title", "abstract")]
    assert sum(map(len, ids)) > 0
    assert engine.compile(ast).held >= sum(map(len, ids)) + len(engine.compile(ast).explain)


def test_a_verified_memo_over_budget_is_cleared_and_never_holds_more(index_path: Path) -> None:
    engine, reference = TantivyEngine(index_path), unbounded(index_path)
    budget = 6
    engine.MAX_VERIFIED_IDS = budget
    most = 0  # the most one compile stores: the only overshoot a clear allows
    clears = 0
    for q in VERIFIED * 2:  # the second pass re-verifies what the clears dropped
        before = len(engine.charges["verified"])
        assert run(engine, q) == run(reference, q), q  # a clear never changes a result
        most = max(most, sum(engine.charges["verified"][before:]))
        clears += len(engine.charges["verified"]) < before
        assert verified_held(engine) <= budget + most, q  # fails for a trim that ignores the budget
    assert clears >= 2
    assert verified_held(reference) > budget + most  # the corpus needs the budget: the test can fail


def test_an_expanded_memo_over_budget_is_cleared(index_path: Path) -> None:
    engine, reference = TantivyEngine(index_path), unbounded(index_path)
    budget = 4
    engine.MAX_EXPANDED_TERMS = budget
    for q in WILDCARDS * 2:
        assert run(engine, q) == run(reference, q), q
        largest = max((len(t) + 1 for t in engine.expanded.values() if not isinstance(t, int)), default=1)
        assert expanded_held(engine) <= budget + largest, q
    assert expanded_held(reference) > 2 * budget


def test_a_compiled_memo_over_budget_is_cleared(index_path: Path) -> None:
    engine, reference = TantivyEngine(index_path), unbounded(index_path)
    budget = 20
    engine.MAX_COMPILED_UNITS = budget
    for q in (QUERIES + VERIFIED) * 2:
        assert run(engine, q) == run(reference, q), q
        largest = max(c.held + 1 for c in engine.compiled.values())
        assert sum(c.held + 1 for c in engine.compiled.values()) <= budget + largest, q
    assert sum(c.held + 1 for c in reference.compiled.values()) > 2 * budget


def test_a_clear_by_hand_only_overcounts(index_path: Path) -> None:
    """Tests and benches clear a memo directly (a cold run); the ledger then over-counts, which only makes the
    next clear come early, never lets the memo grow past its budget."""
    engine = TantivyEngine(index_path)
    engine.MAX_VERIFIED_IDS = 6
    run(engine, VERIFIED[0])
    engine.verified.clear()
    assert sum(engine.charges["verified"]) >= verified_held(engine)


class Counting:
    """The engine's searcher, counting `aggregate` calls (each is one collection of its query)."""

    def __init__(self, searcher: Any) -> None:
        self.searcher, self.aggregates = searcher, 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.searcher, name)

    def aggregate(self, *args: Any, **kwargs: Any) -> Any:
        self.aggregates += 1
        return self.searcher.aggregate(*args, **kwargs)


def test_facets_collect_each_kept_set_once_and_later_pages_reuse_it(index_path: Path) -> None:
    from openproceedings import search

    engine = TantivyEngine(index_path)
    counting = Counting(engine.searcher)
    engine.searcher = counting
    parsed = parse("alpha OR trust*")  # both defaults inserted
    first = search.run(engine, parsed, limit=2, facets=True)
    # kept sets: the effective query (venue, year), without the track default (track), without the status
    # default (status; exclusion accounting's status count too), and exclusion accounting's identified set
    assert counting.aggregates == 4
    again = search.run(engine, parsed, offset=2, limit=2, facets=True)
    assert counting.aggregates == 4  # another page: every count from the memo
    assert (again.facets, again.excluded) == (first.facets, first.excluded)
    assert first.facets == unbounded(index_path).facets(parsed.effective_ast)  # type: ignore[arg-type]
    moved = parse("  alpha   OR trust*")  # the same query written elsewhere: spans never key the memo
    assert engine.facets(moved.effective_ast) == first.facets  # type: ignore[arg-type]
    assert counting.aggregates == 4
    assert first.facets is not None
    first.facets["venue"]["changed"] = 1  # the caller's copy, never the memo's
    assert "changed" not in engine.facets(parsed.effective_ast)["venue"]  # type: ignore[arg-type]


def test_a_facet_memo_over_budget_is_cleared(index_path: Path) -> None:
    engine, reference = TantivyEngine(index_path), unbounded(index_path)
    budget = 12
    engine.MAX_FACET_BUCKETS = budget
    for q in QUERIES * 2:
        parsed = parse(q)
        assert parsed.effective_ast is not None
        assert engine.facets(parsed.effective_ast) == reference.facets(parsed.effective_ast), q
        held = sum(len(c) + 1 for c in engine.faceted.values())
        assert held <= budget + 4 * max(len(c) + 1 for c in engine.faceted.values()), (
            q
        )  # one kept set in flight
    assert sum(len(c) + 1 for c in reference.faceted.values()) > 3 * budget
