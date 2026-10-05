"""TASK-176: a query's concept groups (`query/groups.py`), each group's count alone (`TantivyEngine.count`),
and `search.run(groups=…)`, over the synthetic 5k corpus.

The oracle for a count is ReferenceEngine: `len(match_ids(the query with every other group removed))`. The
property generates ANDs of several trees with extra top-level filters, since those are the groups and what is
kept for each. A search asked for its groups is the search without them, field for field, plus the counts."""

from __future__ import annotations

import dataclasses
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from openproceedings import search
from openproceedings.engine.protocol import EngineInputError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import Scope, TantivyEngine
from openproceedings.query.ast import And, Node, Not
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.defaults import apply_defaults
from openproceedings.query.groups import Groups, split
from openproceedings.query.parser import parse

from tests.fixtures.corpus.synthetic_5k import records, vocab
from tests.golden.test_trust_evals import STRINGS
from tests.strategies import SPAN, engine_asts, filters
from tests.unit.engine.test_exclusions import tantivy_of

RECORDS = list(records())
type Engines = tuple[ReferenceEngine, TantivyEngine, TantivyEngine]


@pytest.fixture(scope="module")
def engines(tmp_path_factory: pytest.TempPathFactory) -> Engines:
    """The oracle and two engines over one 5k index, each with its own memos: one runs the search with its
    groups, the other without, so neither answer can come from the other's work."""
    root = tmp_path_factory.mktemp("groups")
    first = tantivy_of(RECORDS, root)
    (built,) = (p for p in (root / "indexes").iterdir() if p.is_dir() and not p.is_symlink())
    return ReferenceEngine(RECORDS), first, TantivyEngine(built)


# --- which conjuncts are groups ------------------------------------------------------------------------------
def spans(q: str, mode: str = "native") -> tuple[list[str], list[str]]:
    """`q`'s groups and what is kept for each, as the text at each node's span (`""` for an inserted default)."""
    parsed = parse(q, mode)  # type: ignore[arg-type]
    assert parsed.effective_ast is not None, parsed.errors
    found = split(parsed.effective_ast)
    return [q[slice(*g.span)] for g in found.groups], [q[slice(*k.span)] for k in found.kept]


@pytest.mark.parametrize(
    ("q", "mode", "groups", "kept"),
    [
        # the review's shape: OR groups, ANDed, then limits; the defaults are kept too
        (
            '(trust OR reliance) AND calib* "language model" year:2020..2022',
            "native",
            ["(trust OR reliance)", "calib*", '"language model"'],
            ["year:2020..2022", "", ""],
        ),
        ("trust model", "native", ["trust", "model"], ["", ""]),  # bare words are ANDed: two groups
        ("trust", "native", ["trust"], ["", ""]),
        # a negated conjunct is kept for every group (the builder's leave-out terms), never a group
        ("trust model NOT survey", "native", ["trust", "model"], ["NOT survey", "", ""]),
        ("NOT NOT (trust OR model) calibration", "native", ["(trust OR model)", "calibration"], ["", ""]),
        # judged on the canonical form, which has no De Morgan rule: this NOT stays a NOT, so it is kept
        (
            "NOT (NOT trust OR NOT model) calibration",
            "native",
            ["calibration"],
            ["NOT (NOT trust OR NOT model)", "", ""],
        ),
        # a parenthesised AND flattens into groups; an OR of filters searches no text, so it is kept
        (
            "(trust model) (venue:ICLR OR track:workshop)",
            "native",
            ["trust", "model"],
            ["(venue:ICLR OR track:workshop)", "", ""],
        ),
        # an OR holding a term is a group even beside a filter; a NEAR is one too
        (
            "(calibration OR track:workshop) AND (model NEAR/3 language)",
            "native",
            ["(calibration OR track:workshop)", "(model NEAR/3 language)"],
            ["", ""],
        ),
        ("trust AND trust AND model", "native", ["trust", "model"], ["", ""]),  # canonical: one `trust`
        (
            "(trust|reliance) LLM$ source:ICLR",
            "scholar",
            ["(trust|reliance)", "LLM$"],
            ["source:ICLR", "", ""],
        ),
        # the user's own track and status clauses: no default is added, theirs are kept
        (
            "trust model track:workshop status:rejected",
            "native",
            ["trust", "model"],
            ["track:workshop", "status:rejected"],
        ),
    ],
)
def test_groups_are_the_positive_text_conjuncts(
    q: str, mode: str, groups: list[str], kept: list[str]
) -> None:
    assert spans(q, mode) == (groups, kept)


def test_a_group_alone_is_the_query_without_the_other_groups() -> None:
    parsed = parse("(trust OR reliance) AND model NOT survey year:2020..2022")
    assert parsed.effective_ast is not None
    found = split(parsed.effective_ast)
    assert [render(canonicalize(found.alone(g))) for g in found.groups] == [
        "((trust OR reliance) AND NOT survey AND year:2020..2022 AND "
        "track:(datasets_benchmarks OR main OR position) AND status:accepted)",
        "(model AND NOT survey AND year:2020..2022 AND track:(datasets_benchmarks OR main OR position) "
        "AND status:accepted)",
    ]
    assert [render(canonicalize(found.without(g))) for g in found.groups] == [
        "(model AND NOT survey AND year:2020..2022 AND track:(datasets_benchmarks OR main OR position) "
        "AND status:accepted)",
        "((trust OR reliance) AND NOT survey AND year:2020..2022 AND "
        "track:(datasets_benchmarks OR main OR position) AND status:accepted)",
    ]
    three = split(parse("trust model calibration track:workshop status:rejected").effective_ast)  # type: ignore[arg-type]
    assert render(canonicalize(three.without(three.groups[1]))) == (
        "(trust AND calibration AND track:workshop AND status:rejected)"
    )
    lone = split(parse("trust track:workshop status:rejected").effective_ast)  # type: ignore[arg-type]
    assert not split(lone.groups[0]).kept and split(lone.groups[0]).alone(lone.groups[0]) == lone.groups[0]


# --- TantivyEngine.count and counts against the oracle ------------------------------------------------------------------
@st.composite
def grouped_asts(draw: st.DrawFn) -> Node:
    """An AND of several trees (each a group, a leave-out, or a filter clause) and extra top-level filters."""
    parts: list[Node] = draw(st.lists(engine_asts(vocab()), min_size=1, max_size=4))
    parts += [
        Not(span=SPAN, child=f) if draw(st.booleans()) else f for f in draw(st.lists(filters(), max_size=3))
    ]
    if len(parts) == 1:
        return parts[0]
    return And(span=SPAN, children=tuple(draw(st.permutations(parts))))


def outcome(f: Any, *args: Any) -> Any:
    try:
        return f(*args)
    except EngineInputError as e:
        return ("refused", e.code)


def expected_pairs(reference: ReferenceEngine, found: Groups) -> tuple[tuple[tuple[int, int], int, int], ...]:
    """Each group's span with the oracle's two counts: the group alone, and the query without it."""
    return tuple(
        (g.span, len(reference.match_ids(found.alone(g))), len(reference.match_ids(found.without(g))))
        for g in found.groups
    )


# each example evaluates up to nine trees with the oracle over the 5k corpus: no per-example deadline
@settings(max_examples=150, deadline=None)
@given(tree=grouped_asts())
def test_each_groups_counts_are_the_oracles(engines: Engines, tree: Node) -> None:
    reference, tantivy, _other = engines
    tantivy.faceted.clear()  # a fresh collection as often as a memoised one
    ast = canonicalize(tree)
    found = split(ast)
    whole = outcome(lambda n: len(reference.match_ids(n)), ast)
    trees = [ast, *map(found.alone, found.groups[:4])]
    if len(found.groups) >= 2:
        trees += map(found.without, found.groups[:4])
    for counted in trees:
        q = render(canonicalize(counted))
        expected = outcome(lambda n: len(reference.match_ids(n)), counted)
        assert outcome(tantivy.count, counted) == expected, q
        assert outcome(lambda n: len(tantivy.match_ids(n)), counted) == expected, q
        if isinstance(expected, int) and isinstance(whole, int):
            assert expected >= whole, (
                q
            )  # a group alone, and the query without a group, hold the query's matches
    # all of them in one call (shared conjuncts, as `search.run` asks): the same counts
    assert outcome(lambda ts: tantivy.counts(ts), trees) == outcome(
        lambda ts: [len(reference.match_ids(t)) for t in ts], trees
    )


class Parsed:
    """What `search.run` reads of a ParseResult, for a generated tree (no string to parse)."""

    def __init__(self, tree: Node, tokenizer: str) -> None:
        done = apply_defaults(tree, 0)
        self.effective_ast, self.identification_ast = done.effective, done.identification
        self.defaults, self.tokenizer_version = done.defaults, tokenizer


# each example runs the search twice and the oracle over the 5k corpus: no per-example deadline
@settings(max_examples=100, deadline=None)
@given(tree=grouped_asts())
def test_a_generated_search_with_groups_is_the_search_without_them(engines: Engines, tree: Node) -> None:
    """On generated trees, both engines: asking for the groups changes no other field of the search, and the
    counts are the oracle's, none below the oracle's own count of the query."""
    reference, tantivy, other = engines
    parsed: Any = Parsed(tree, tantivy.tokenizer_version)
    tantivy.faceted.clear()

    def searched(engine: TantivyEngine, **kw: Any) -> Any:
        try:
            return search.run(engine, parsed, facets=True, **kw)
        except EngineInputError as e:
            return ("refused", e.code)

    got, plain = searched(tantivy, groups=10), searched(other)
    if not isinstance(got, search.Search):
        assert got == plain
        return
    assert dataclasses.replace(got, groups=None) == plain
    found = split(parsed.effective_ast)
    assert got.total == len(reference.match_ids(parsed.effective_ast))
    assert got.groups is not None and got.groups.found == len(found.groups)
    if 2 <= len(found.groups) <= 10:
        assert got.groups.counts == expected_pairs(reference, found)
        assert all(min(alone, without) >= got.total for _span, alone, without in got.groups.counts)
    else:
        assert got.groups.counts == () and got.groups.not_counted is not None


def test_a_count_is_the_same_from_the_memo_and_under_a_read_only_scope(engines: Engines) -> None:
    reference, tantivy, _other = engines
    ast = parse("(trust OR reliance) AND calibrat* year:2019..2024").effective_ast
    assert ast is not None
    expected = len(reference.match_ids(ast))
    tantivy.faceted.clear()
    scope = Scope()
    tantivy.compile(ast, scope)
    assert [tantivy.count(ast, scope=s) for s in (scope.reader(), None, scope)] == [expected] * 3


# --- search.run(groups=…) ------------------------------------------------------------------------------------
QUERIES = [
    ("(trust OR reliance) AND calibrat* AND model*", "native"),
    ('"language model" benchmark* NOT survey year:2019..2024', "native"),
    ("trust model track:workshop status:rejected", "native"),
    ("(trust AND track:workshop) OR calibration", "native"),  # one group: a top-level OR
    ("trust (venue:ICLR OR track:workshop) evaluation", "native"),
    ("(agents NEAR/3 reliance) AND (trust OR calibrat*)", "native"),
    *((STRINGS[n], "scholar") for n in STRINGS if STRINGS[n].strip()),
]


@pytest.mark.parametrize(("q", "mode"), QUERIES)
def test_a_search_with_groups_is_the_search_without_them_plus_the_oracles_counts(
    engines: Engines, q: str, mode: str
) -> None:
    reference, tantivy, other = engines
    parsed = parse(q, mode)  # type: ignore[arg-type]
    assert parsed.effective_ast is not None
    found = split(parsed.effective_ast)
    for offset in (0, 50):
        tantivy.faceted.clear()  # the counts run on the worker, not from the memo
        got = search.run(tantivy, parsed, offset=offset, facets=True, highlight=True, groups=10)
        plain = search.run(other, parsed, offset=offset, facets=True, highlight=True)
        assert plain.groups is None and dataclasses.replace(got, groups=None) == plain
        assert got.groups is not None and (got.groups.found, got.groups.limit) == (len(found.groups), 10)
        if len(found.groups) < 2:
            assert got.groups == search.GroupCounts((), len(found.groups), 10, "fewer_than_two_groups")
            continue
        assert got.groups.not_counted is None
        assert got.groups.counts == expected_pairs(reference, found)
        assert all(min(alone, without) >= got.total for _span, alone, without in got.groups.counts)


def test_some_group_narrows_a_real_review_string(engines: Engines) -> None:
    """The counts say something: on the fixture, the groups of a Trust-Evals string differ, each is above the
    query's total, and removing one of them lets more papers in than removing another."""
    _reference, tantivy, _other = engines
    name = next(n for n in STRINGS if len(split(parse(STRINGS[n], "scholar").effective_ast).groups) >= 3)  # type: ignore[arg-type]
    got = search.run(tantivy, parse(STRINGS[name], "scholar"), groups=10)
    assert got.groups is not None
    alone = [a for _span, a, _w in got.groups.counts]
    without = [w for _span, _a, w in got.groups.counts]
    assert len(set(alone)) > 1 and min(alone) > got.total
    assert len(set(without)) > 1 and max(without) > got.total


def test_a_query_over_the_limit_gets_its_search_and_no_counts(
    engines: Engines, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reference, tantivy, other = engines
    parsed = parse("trust model calibration")
    plain = search.run(other, parsed, facets=True)

    def never(*_a: Any, **_kw: Any) -> list[int]:
        raise AssertionError("a query over the limit counts no group")

    monkeypatch.setattr(tantivy, "counts", never)
    got = search.run(tantivy, parsed, facets=True, groups=2)
    assert got.groups == search.GroupCounts((), 3, 2, "too_many_groups")
    assert dataclasses.replace(got, groups=None) == plain
    monkeypatch.undo()
    at = search.run(tantivy, parsed, facets=True, groups=3).groups
    assert at is not None and at.not_counted is None and len(at.counts) == 3


def test_group_counts_need_no_facets(engines: Engines) -> None:
    """`run` compiles the query before its counting worker starts, asked for facets or not."""
    reference, tantivy, _other = engines
    parsed = parse("trust (model NEAR/2 model*)")
    assert parsed.effective_ast is not None
    found = split(parsed.effective_ast)
    tantivy.verified.clear(), tantivy.compiled.clear(), tantivy.faceted.clear()
    got = search.run(tantivy, parsed, groups=10)
    assert got.facets is None and got.groups is not None
    assert got.groups.counts == expected_pairs(reference, found)


# --- the counts are an extra: they never cost the search its answer -------------------------------------------
def test_a_count_that_fails_leaves_the_search_whole(
    engines: Engines, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Any error of the counting worker (here a RuntimeError whose message quotes a secret): the search is the
    plain one, `groups` says `count_failed`, and one ERROR line carries the type and a number, not the message."""
    _reference, tantivy, other = engines
    parsed = parse("trust model calibration")
    plain = search.run(other, parsed, facets=True, highlight=True)

    def broken(*_a: Any, **_kw: Any) -> list[int]:
        raise RuntimeError("zzsecretreviewdesign")

    monkeypatch.setattr(tantivy, "counts", broken)
    for pool_down in (False, True):  # the worker's failure, and the caller's own when no worker took the job
        if pool_down:
            closed = ThreadPoolExecutor(1)
            closed.shutdown()
            monkeypatch.setattr(search, "_POOL", closed)
        caplog.clear()
        got = search.run(tantivy, parsed, facets=True, highlight=True, groups=10)
        assert got.groups == search.GroupCounts((), 3, 10, "count_failed")
        assert dataclasses.replace(got, groups=None) == plain
        (line,) = [r for r in caplog.records if r.message == "group_count_failed"]
        assert (line.levelname, line.groups, line.error) == ("ERROR", 3, "RuntimeError")  # type: ignore[attr-defined]
        assert "zzsecretreviewdesign" not in caplog.text


def test_a_count_that_is_late_leaves_the_search_whole(
    engines: Engines, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A counting worker still running `groups_wait` after the rest is done: the search answers without the
    counts (`timed_out`), having waited no longer than that."""
    _reference, tantivy, other = engines
    parsed = parse("trust model calibration")
    plain = search.run(other, parsed, facets=True, highlight=True)
    release = threading.Event()
    counts = tantivy.counts

    def held(*a: Any, **kw: Any) -> list[int]:
        release.wait(30)
        return counts(*a, **kw)

    monkeypatch.setattr(tantivy, "counts", held)
    try:
        started = time.monotonic()
        got = search.run(tantivy, parsed, facets=True, highlight=True, groups=10, groups_wait=0.05)
        waited = time.monotonic() - started
    finally:
        release.set()
    assert got.groups == search.GroupCounts((), 3, 10, "timed_out")
    assert dataclasses.replace(got, groups=None) == plain
    assert waited < 10  # bounded by the wait, not by the worker (held for 30 s)
    (line,) = [r for r in caplog.records if r.message == "group_count_timed_out"]
    assert (line.levelname, line.groups, line.wait_ms) == ("WARNING", 3, 50)  # type: ignore[attr-defined]
    search.shutdown()  # the released worker finishes before the next test reads the engine's memos


def test_counting_groups_verifies_no_clause_again(tmp_path: Any) -> None:
    """A group's tree holds only clauses of the query, verified once in the caller's thread before the counting
    worker starts: the worker never enters the verification gate (decision-010: no cost of its own)."""
    engine = tantivy_of(RECORDS, tmp_path)
    entered: list[str] = []

    @contextmanager
    def gate() -> Iterator[None]:
        entered.append(threading.current_thread().name)
        yield

    engine.verification_gate = gate
    parsed = parse("(model NEAR/2 model*) AND (trust NEAR/3 trust*) AND calibrat*")
    got = search.run(engine, parsed, facets=True, groups=10)
    assert got.groups is not None and len(got.groups.counts) == 3
    assert len(entered) == 4  # 2 clauses × title and abstract, each verified once
    assert not [name for name in entered if name.startswith("op-facets")]


def test_counting_groups_stores_nothing_in_the_compiled_memo(tmp_path: Any) -> None:
    """Ten one-word groups and a kept verified clause (`NOT (model NEAR/10 model*)`): the twenty trees counted
    are never stored in `compiled` (each would hold the kept clause's ids against the shared budget), and the
    kept clause's id set is built once more for all of them, not once a tree."""
    root = tmp_path / "a"
    plain_engine = tantivy_of(RECORDS, root)
    (built,) = (p for p in (root / "indexes").iterdir() if p.is_dir() and not p.is_symlink())
    engine = TantivyEngine(built)
    q = "trust model data learning method results training network approach performance NOT (model NEAR/10 model*)"
    parsed = parse(q)

    def measured(e: TantivyEngine, **kw: Any) -> tuple[search.Search, int, set[str], int]:
        builds = 0
        id_set = e.id_set

        def counted(ids: list[str]) -> Any:
            nonlocal builds
            builds += 1
            return id_set(ids)

        e.id_set = counted  # type: ignore[method-assign]
        got = search.run(e, parsed, facets=True, **kw)
        search.shutdown()  # every worker done: the memos are final
        return got, builds, set(e.compiled), sum(e.charges["compiled"])

    plain, plain_builds, plain_keys, plain_units = measured(plain_engine)
    got, builds, keys, units = measured(engine, groups=10)
    assert got.groups is not None and len(got.groups.counts) == 10
    assert dataclasses.replace(got, groups=None) == plain
    assert (keys, units) == (
        plain_keys,
        plain_units,
    )  # not one entry, not one unit, more than the plain search
    assert builds - plain_builds <= 2  # the kept clause, once a field, whatever the number of groups
    assert len(engine.faceted) - len(plain_engine.faceted) <= 20  # two memoised collections a group


def test_a_counting_worker_that_would_verify_is_recounted_in_the_caller(
    engines: Engines, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The safety net, as for the facets: should the worker's read-only scope miss a clause (a bug), `run`
    counts the groups in the caller and logs `group_worker_recounted`; the client gets its counts."""
    reference, _tantivy, _other = engines
    engine = tantivy_of(RECORDS, tmp_path)
    parsed = parse("(model NEAR/2 model*) AND trust")
    assert parsed.effective_ast is not None
    found = split(parsed.effective_ast)
    monkeypatch.setattr(Scope, "reader", lambda self: Scope({}, may_verify=False))  # the bug: an empty view
    counts = engine.counts

    def cold_in_the_worker(*a: Any, **kw: Any) -> Any:
        if threading.current_thread().name.startswith("op-facets"):
            engine.verified.clear(), engine.compiled.clear(), engine.faceted.clear()
        return counts(*a, **kw)

    monkeypatch.setattr(engine, "counts", cold_in_the_worker)
    got = search.run(engine, parsed, groups=10)
    assert got.groups is not None
    assert got.groups.counts == expected_pairs(reference, found)
    assert [r.message for r in caplog.records if r.message == "group_worker_recounted"] == [
        "group_worker_recounted"
    ]


def test_a_pool_shut_down_under_a_search_counts_the_groups_in_the_caller(
    engines: Engines, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reference, tantivy, other = engines
    parsed = parse("trust model")
    expected = search.run(other, parsed, facets=True, groups=10)
    closed = ThreadPoolExecutor(1)
    closed.shutdown()
    monkeypatch.setattr(search, "_POOL", closed)
    tantivy.faceted.clear()
    assert search.run(tantivy, parsed, facets=True, groups=10) == expected


def test_the_callers_error_comes_before_the_counting_workers(
    engines: Engines, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reference, tantivy, _other = engines

    def broken(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("the page failed")

    def also_broken(*_a: Any, **_kw: Any) -> list[int]:
        raise ValueError("the count failed")

    monkeypatch.setattr(tantivy, "page", broken)
    monkeypatch.setattr(tantivy, "counts", also_broken)
    with pytest.raises(RuntimeError, match="the page failed"):
        search.run(tantivy, parse("trust model"), groups=10)


# --- concurrency: searches with groups from several threads while the memos are cleared -------------------------
def test_concurrent_searches_with_groups_give_the_oracles_counts(engines: Engines) -> None:
    """Eight threads search queries with groups over and over while another clears `faceted` and `compiled`
    under them: every answer has the oracle's counts and the plain search's total (task-080's rules hold for
    the counting worker too: a cleared memo only costs a recomputation)."""
    reference, tantivy, other = engines
    cases = []
    for q in (
        "(trust OR reliance) AND calibrat* AND model*",
        "trust model NOT survey year:2019..2024",
        "(agents NEAR/3 reliance) AND (trust OR calibrat*)",
        '"language model" benchmark* evaluation',
    ):
        parsed = parse(q)
        assert parsed.effective_ast is not None
        want = expected_pairs(reference, split(parsed.effective_ast))
        cases.append((parsed, want, search.run(other, parsed, facets=True).total))
    stop = threading.Event()

    def clear() -> None:
        while not stop.is_set():
            tantivy.faceted.clear()
            tantivy.compiled.clear()
            time.sleep(0.001)

    def searching(worker: int) -> list[str]:
        wrong = []
        for round_ in range(12):
            parsed, want, total = cases[(worker + round_) % len(cases)]
            got = search.run(tantivy, parsed, facets=True, groups=10, groups_wait=60)
            if got.groups is None or got.groups.counts != want or got.total != total:
                wrong.append(f"worker {worker} round {round_}: {got.groups}")
        return wrong

    clearer = threading.Thread(target=clear)
    clearer.start()
    try:
        with ThreadPoolExecutor(8) as pool:
            wrong = [w for found in pool.map(searching, range(8)) for w in found]
    finally:
        stop.set()
        clearer.join()
    assert wrong == []
