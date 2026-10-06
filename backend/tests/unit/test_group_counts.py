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
from openproceedings.engine.compile import conjuncts
from openproceedings.engine.protocol import EngineInputError, EngineInternalError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import COMBO, Scope, TantivyEngine, _filter_field, _Parts
from openproceedings.query.ast import And, Filter, Node, Not, Phrase, Term, Wildcard
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


PRODUCTION_GRACE = search.GROUP_COUNT_GRACE_SECONDS  # read at import, before `a_patient_grace` raises it


@pytest.fixture(autouse=True)
def a_patient_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests are about the counts, on a machine that may be busy: a counting job gets 30 s to be taken
    by a worker, not the 50 ms a served search gives it (the tests of `busy` pass their own grace)."""
    monkeypatch.setattr(search, "GROUP_COUNT_GRACE_SECONDS", 30.0)


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
            monkeypatch.setattr(search, "_GROUP_POOL", closed)
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
    assert (line.levelname, line.groups, line.threshold_ms) == ("WARNING", 3, 50.0)  # type: ignore[attr-defined]
    search.shutdown()  # the released worker finishes before the next test reads the engine's memos


def test_a_worker_that_raises_a_timeout_of_its_own_failed_and_did_not_time_out(
    engines: Engines, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`TimeoutError` is also what waiting on a future raises: a job that finished by raising one is a failed
    count, not a late one."""
    _reference, tantivy, _other = engines

    def broken(*_a: Any, **_kw: Any) -> list[int]:
        raise TimeoutError("not the wait's")

    monkeypatch.setattr(tantivy, "counts", broken)
    got = search.run(tantivy, parse("trust model calibration"), facets=True, groups=10)
    assert got.groups == search.GroupCounts((), 3, 10, "count_failed")


def test_a_timed_out_job_stops_within_one_collection(tmp_path: Any) -> None:
    """A job its search stopped waiting for does no more than finish the collection it is in: of the six a
    three-group query has, it makes one."""
    engine = tantivy_of(RECORDS, tmp_path)
    parsed = parse("trust model calibration")
    release, inside = threading.Event(), threading.Event()
    collected: list[str] = []
    combos = engine.combos

    def slow(*a: Any, **kw: Any) -> Any:
        if threading.current_thread().name.startswith("op-groups"):
            collected.append(threading.current_thread().name)
            inside.set()
            release.wait(30)  # the collection the job is in when its search gives up
        return combos(*a, **kw)

    engine.combos = slow  # type: ignore[method-assign]
    try:
        got = search.run(engine, parsed, facets=True, groups=10, groups_wait=0.2)
        assert inside.wait(10)
    finally:
        release.set()
    search.shutdown()  # the job has ended, one way or the other
    assert got.groups == search.GroupCounts((), 3, 10, "timed_out")
    assert len(collected) == 1
    # and a search of the same query afterwards counts all of it
    engine.combos = combos  # type: ignore[method-assign]
    again = search.run(engine, parsed, facets=True, groups=10).groups
    assert again is not None and again.not_counted is None and len(again.counts) == 3


def test_facets_are_served_while_slow_counting_jobs_hold_every_counting_worker(
    engines: Engines, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eight concurrent searches whose counting never finishes (every counting worker held, the rest queued):
    each still answers with its facets and no counts (`timed_out`, or `busy` for a job no worker took), after
    its own wait or grace and no longer. The
    counts have their own workers, so no facet job queues behind one."""
    _reference, tantivy, other = engines
    parsed = parse("trust model calibration")
    plain = search.run(other, parsed, facets=True)
    release = threading.Event()

    def stuck(*_a: Any, **_kw: Any) -> list[int]:
        release.wait(60)
        raise RuntimeError("released")

    monkeypatch.setattr(tantivy, "counts", stuck)

    def one(_i: int) -> tuple[search.Search, float]:
        started = time.monotonic()
        got = search.run(tantivy, parsed, facets=True, groups=10, groups_wait=0.3, groups_grace=0.05)
        return got, time.monotonic() - started

    try:
        with ThreadPoolExecutor(8) as pool:
            answers = list(pool.map(one, range(8)))
        assert search._GROUP_POOL is not None and search._GROUP_POOL._max_workers == search.GROUP_WORKERS
        reasons = [got.groups.not_counted for got, _took in answers if got.groups is not None]
        # the two a worker took waited their 0.3 s; the six left queued were answered after the 50 ms grace
        assert set(reasons) <= {"busy", "timed_out"} and len(reasons) == 8
        assert reasons.count("timed_out") <= search.GROUP_WORKERS and reasons.count("busy") >= 6
        for got, took in answers:
            assert got.groups is not None and got.groups.counts == ()
            assert dataclasses.replace(got, groups=None) == plain
            assert took < 20  # its own grace or wait, not the 60 s the counting workers are held
        # a search that asks for no counts is untouched while they are still held
        assert search.run(tantivy, parsed, facets=True) == plain
    finally:
        release.set()
        search.shutdown()


def test_a_light_search_answers_within_the_grace_while_every_counting_worker_is_taken(
    engines: Engines, caplog: pytest.LogCaptureFixture
) -> None:
    """Other searches' counting jobs hold both counting workers: a light two-group search is answered `busy`
    after the grace (50 ms), not after the 30 s it would wait for a job of its own that had started, and
    everything but `groups` is the plain search's. Once a worker is free, the same search has its counts."""
    reference, tantivy, other = engines
    parsed = parse("trust model")
    assert parsed.effective_ast is not None
    plain = search.run(other, parsed, facets=True, highlight=True)
    release = threading.Event()
    holding = [search._start(lambda: release.wait(60), counts=True) for _ in range(search.GROUP_WORKERS)]
    assert all(h is not None for h in holding)
    try:
        started = time.monotonic()
        got = search.run(
            tantivy, parsed, facets=True, highlight=True, groups=10, groups_wait=30, groups_grace=0.05
        )
        took = time.monotonic() - started
    finally:
        release.set()
    assert got.groups == search.GroupCounts((), 2, 10, "busy")
    assert dataclasses.replace(got, groups=None) == plain
    assert took < 10  # the grace and the search itself, never the 30 s wait
    assert not [r for r in caplog.records if r.levelname in ("WARNING", "ERROR")]  # a state, not an alarm
    search.shutdown()  # the held workers are released: the cancelled job never ran
    free = search.run(tantivy, parsed, facets=True, groups=10).groups
    assert free is not None and free.counts == expected_pairs(reference, split(parsed.effective_ast))


def test_a_kept_verified_clause_of_many_ids_is_too_costly(engines: Engines) -> None:
    """The other costly shape: few terms, but a position-verified kept clause whose id set every tree's
    collection resolves. Its ids are counted before anything is counted (`_ids_read`: N·G + 2·N·K in ids)."""
    reference, tantivy, other = engines
    parsed = parse("trust model NOT (model NEAR/10 model*)")
    assert parsed.effective_ast is not None
    found = split(parsed.effective_ast)
    (near,) = [k for k in found.kept if isinstance(k, Not) and not isinstance(k.child, Filter)]
    matched = reference.match_ids(near.child)  # the clause's matches, in either field
    scope = Scope()
    tantivy.compile(parsed.effective_ast, scope)
    read = search._ids_read(found, scope)
    assert read == 2 * 2 * sum(len(ids) for ids in scope.ids.values()) >= 2 * 2 * len(matched) > 0
    assert (
        found.terms_read(tantivy.expansions(parsed.effective_ast)) < 1_000
    )  # few terms: only the ids say so
    plain = search.run(other, parsed, facets=True)
    at = search.run(tantivy, parsed, facets=True, groups=10, groups_ids=read)
    assert at.groups is not None and at.groups.counts == expected_pairs(reference, found)
    over = search.run(tantivy, parsed, facets=True, groups=10, groups_ids=read - 1)
    assert over.groups == search.GroupCounts((), 2, 10, "too_costly")
    assert dataclasses.replace(over, groups=None) == plain


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
    assert not [name for name in entered if name.startswith(("op-facets", "op-groups"))]


def measured(engine: TantivyEngine, parsed: Any, **kw: Any) -> tuple[search.Search, int, set[str], int, int]:
    """A search on a fresh engine, with what it cost the shared memos: the id term sets it built, the `compiled`
    memo's keys and charged units, and the `faceted` memo's entries, once every worker is done."""
    builds = 0
    id_set = engine.id_set

    def counted(ids: list[str]) -> Any:
        nonlocal builds
        builds += 1
        return id_set(ids)

    engine.id_set = counted  # type: ignore[method-assign]
    got = search.run(engine, parsed, facets=True, **kw)
    search.shutdown()  # every worker done: the memos are final
    return got, builds, set(engine.compiled), sum(engine.charges["compiled"]), len(engine.faceted)


def two_engines(tmp_path: Any) -> tuple[TantivyEngine, TantivyEngine]:
    """Two fresh engines over one 5k index, with empty memos."""
    first = tantivy_of(RECORDS, tmp_path / "a")
    (built,) = (p for p in (tmp_path / "a" / "indexes").iterdir() if p.is_dir() and not p.is_symlink())
    return first, TantivyEngine(built)


def test_counting_groups_stores_nothing_in_the_compiled_memo(tmp_path: Any) -> None:
    """Ten one-word groups and a kept verified clause (`NOT (model NEAR/10 model*)`): the twenty trees counted
    are never stored in `compiled` (each would hold the kept clause's ids against the shared budget), and the
    kept clause's id set is built once more for all of them, not once a tree."""
    plain_engine, engine = two_engines(tmp_path)
    q = "trust model data learning method results training network approach performance NOT (model NEAR/10 model*)"
    parsed = parse(q)
    plain, plain_builds, plain_keys, plain_units, plain_faceted = measured(plain_engine, parsed)
    got, builds, keys, units, faceted = measured(engine, parsed, groups=10)
    assert got.groups is not None and len(got.groups.counts) == 10
    assert dataclasses.replace(got, groups=None) == plain
    assert (keys, units) == (
        plain_keys,
        plain_units,
    )  # not one entry, not one unit, more than the plain search
    assert builds - plain_builds <= 2  # the kept clause, once a field, whatever the number of groups
    assert faceted - plain_faceted <= 20  # two memoised collections a group


def wide_kept_query(engine: TantivyEngine) -> str:
    """Ten one-word groups and one kept `NOT (… every three-letter stem under the expansion cap …)`, as long as
    a query may be: the shape that made every counted tree recompile, and re-read, thousands of terms."""
    stems = sorted(
        {
            t[:3]
            for f in ("title", "abstract")
            for t, _n in engine.searcher.terms_with_prefix(f, "")
            if len(t) > 3
        }
    )
    groups = "trust model data learning neural network training language agent task"
    kept: list[str] = []
    for stem in stems:
        if not (stem.isascii() and stem.isalpha()):
            continue
        tree = parse(f"{stem}*").effective_ast
        if tree is None:
            continue
        try:
            engine.expansions(tree)
        except EngineInputError:
            continue  # over the 200-term cap
        if len(f"{groups} NOT ({' OR '.join([*kept, stem + '*'])})") > 2000:
            break
        kept.append(f"{stem}*")
    return f"{groups} NOT ({' OR '.join(kept)})"


def test_a_long_kept_clause_costs_the_memos_nothing_and_is_too_costly_by_default(tmp_path: Any) -> None:
    """The review's shape (10 groups, a kept NOT of every stem under the cap: thousands of expanded terms, no
    verified clause, one rate-limit token). Counted (the bound lifted), it adds no `compiled` entry or unit
    to the plain search's and at most 20 `faceted` entries; at the default bound it is not counted at all."""
    plain_engine, engine = two_engines(tmp_path)
    q = wide_kept_query(plain_engine)
    parsed = parse(q)
    assert parsed.effective_ast is not None
    found = split(parsed.effective_ast)
    read = found.terms_read(plain_engine.expansions(parsed.effective_ast))
    assert len(found.groups) == 10 and read > 50_000  # 10 groups × 2 × thousands of kept terms
    plain, _builds, plain_keys, plain_units, plain_faceted = measured(plain_engine, parsed)
    got, _builds, keys, units, faceted = measured(engine, parsed, groups=10, groups_terms=read)
    assert got.groups is not None and got.groups.not_counted is None and len(got.groups.counts) == 10
    assert dataclasses.replace(got, groups=None) == plain
    assert (keys, units) == (plain_keys, plain_units)
    assert faceted - plain_faceted <= 20
    # one term under what it reads: refused before any counting, the search whole, the memos the plain search's
    _first, fresh = two_engines(tmp_path / "again")

    def never(*_a: Any, **_kw: Any) -> list[int]:
        raise AssertionError("a query over the bound counts no group")

    fresh.counts = never  # type: ignore[method-assign]
    for bound in (read - 1, search.MAX_COUNTED_TERMS):
        refused = search.run(fresh, parsed, facets=True, groups=10, groups_terms=bound)
        assert refused.groups == search.GroupCounts((), 10, 10, "too_costly")
        assert dataclasses.replace(refused, groups=None) == plain
    search.shutdown()
    assert (set(fresh.compiled), sum(fresh.charges["compiled"])) == (plain_keys, plain_units)


def test_terms_read_is_the_terms_of_every_tree_counted(engines: Engines) -> None:
    """N groups of G terms and K kept terms: N·G + 2·N·K (the docstring's arithmetic), a wildcard counting its
    expansions, a phrase and a NEAR their items, a filter nothing; equal to the sum over the trees counted."""
    _reference, tantivy, _other = engines
    q = '(trust OR calibrat*) "language model" (agents NEAR/3 reliance) NOT (survey OR bias*) year:2020..2024'
    ast = parse(q).effective_ast
    assert ast is not None
    expansions = tantivy.expansions(ast)
    calibrat, bias = len(expansions[("calibrat", "*")]), len(expansions[("bias", "*")])
    found = split(ast)
    in_groups, in_kept = (1 + calibrat) + 2 + 2, 1 + bias
    assert found.terms_read(expansions) == 3 * in_groups + 2 * 3 * in_kept

    def terms(tree: Node) -> int:
        return split(tree).terms_read(expansions) // max(1, len(split(tree).groups))

    one = split(parse("trust").effective_ast)  # type: ignore[arg-type]
    assert one.terms_read({}) == 1  # one group, nothing kept but filters
    assert terms(found.alone(found.groups[1])) == 2 + 2 * in_kept  # itself a query of one group


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
        if threading.current_thread().name.startswith("op-groups"):
            engine.verified.clear(), engine.compiled.clear(), engine.faceted.clear()
            kw.pop("compiled")  # and without the request's compile: it compiles each conjunct itself
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
    monkeypatch.setattr(search, "_GROUP_POOL", closed)
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


@pytest.mark.parametrize("failing", ["facets", "excluded"])
def test_a_search_that_fails_after_its_page_abandons_its_running_counting_job(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    """The facet worker's error (re-raised by `faceting.result()`) or the exclusion accounting's, while the
    counting job is inside its first collection: the search raises it, and the job, which nobody will wait
    for, stops once that collection ends (one of the six a three-group query has), not after all six."""
    engine = tantivy_of(RECORDS, tmp_path)
    release, inside = threading.Event(), threading.Event()
    collected: list[str] = []
    combos = engine.combos

    def slow(*a: Any, **kw: Any) -> Any:
        if threading.current_thread().name.startswith("op-groups"):
            collected.append(threading.current_thread().name)
            inside.set()
            release.wait(30)
        return combos(*a, **kw)

    def broken(*_a: Any, **_kw: Any) -> Any:
        assert inside.wait(30)  # the counting job is running
        raise RuntimeError(f"the {failing} failed")

    engine.combos = slow  # type: ignore[method-assign]
    if failing == "facets":
        monkeypatch.setattr(engine, "facets", broken)  # the facet worker's job
    else:
        monkeypatch.setattr(search, "excluded", broken)
    try:
        with pytest.raises(RuntimeError, match=f"the {failing} failed"):
            search.run(engine, parse("trust model calibration"), facets=True, groups=10)
    finally:
        release.set()
    search.shutdown()  # the job has ended, one way or the other
    assert len(collected) == 1


def test_at_the_production_waits_a_search_is_busy_at_once_while_the_counting_workers_are_taken(
    engines: Engines, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`run`'s own grace and wait, which this module's other tests raise: with both counting workers held, a
    ten-group-limit search that passes neither answers `busy` in well under a second, never the 2 s wait."""
    monkeypatch.setattr(search, "GROUP_COUNT_GRACE_SECONDS", PRODUCTION_GRACE)  # back from the patient grace
    assert (search.GROUP_COUNT_GRACE_SECONDS, search.GROUP_COUNT_WAIT_SECONDS) == (0.05, 2.0)
    _reference, tantivy, other = engines
    parsed = parse("trust model calibration")
    plain = search.run(other, parsed, facets=True)
    search.run(tantivy, parsed, facets=True)  # warm: what is timed is the wait, not a first compile
    release = threading.Event()
    held = [search._start(lambda: release.wait(60), counts=True) for _ in range(search.GROUP_WORKERS)]
    assert all(h is not None for h in held)
    try:
        started = time.monotonic()
        got = search.run(tantivy, parsed, facets=True, groups=10)
        took = time.monotonic() - started
    finally:
        release.set()
        search.shutdown()
    assert got.groups == search.GroupCounts((), 3, 10, "busy")
    assert dataclasses.replace(got, groups=None) == plain
    assert took < 1.0


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
        SHARED_VERIFIED,  # counted from bitmaps (TASK-197), the per-value ones rebuilt under it
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
            tantivy._masks = None
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


# --- TASK-197: the request's compile, and each shared costly conjunct collected once ----------------------------
@st.composite
def verified_grouped_asts(draw: st.DrawFn) -> Node:
    """`grouped_asts` with a position-verified conjunct (a phrase with a wildcard item), a group or negated (kept):
    the shape whose counting collects each conjunct once, as a bitmap (`_Parts.bitwise`)."""
    stem = draw(st.sampled_from(["model", "trust", "learn", "data", "language"]))
    word = draw(vocab().term())
    phrase = Phrase(span=SPAN, items=(Term(span=SPAN, token=word), Wildcard(span=SPAN, stem=stem, op="*")))
    clause: Node = Not(span=SPAN, child=phrase) if draw(st.booleans()) else phrase
    rest = draw(grouped_asts())
    others = list(rest.children) if isinstance(rest, And) else [rest]
    return And(span=SPAN, children=tuple(draw(st.permutations([clause, *others]))))


def request_counts(engine: TantivyEngine, ast: Node, trees: list[Node]) -> list[int]:
    """`counts` as `search.run`'s worker asks: with the request's compile of `ast` and a read-only scope."""
    scope = Scope()
    compiled = engine.compile(ast, scope)
    return engine.counts(trees, scope=scope.reader(), compiled=(ast, compiled))


def counted_trees(ast: Node) -> list[Node]:
    found = split(ast)
    return [*map(found.alone, found.groups), *map(found.without, found.groups)]


# each example evaluates every counted tree with the oracle over the 5k corpus: no per-example deadline
@settings(max_examples=150, deadline=None)
@given(tree=st.one_of(grouped_asts(), verified_grouped_asts()))
def test_counts_with_the_requests_compile_are_the_counts_without_it_and_the_oracles(
    engines: Engines, tree: Node
) -> None:
    """The conjunct queries the request's compile built (`Compiled.conjuncts`), and the bitmaps the shared
    costly ones are collected into, give the counts a fresh compile gives, and ReferenceEngine's."""
    reference, tantivy, other = engines
    ast = canonicalize(tree)
    trees = counted_trees(ast) if len(split(ast).groups) >= 2 else [ast]
    expected = outcome(lambda ts: [len(reference.match_ids(t)) for t in ts], trees)
    tantivy.faceted.clear(), other.faceted.clear()
    assert outcome(lambda ts: request_counts(tantivy, ast, ts), trees) == expected, render(ast)
    assert outcome(lambda ts: other.counts(ts), trees) == expected, render(ast)


def bases_of(tree: Node) -> list[list[Node]]:
    """Every base a tree's counting collects: the whole tree's, and each of its non-filter conjuncts' alone."""
    base = [c for c in conjuncts(tree) if _filter_field(c) is None]
    return [base, *([c] for c in base)] if base else [base]


@settings(max_examples=150, deadline=None)
@given(tree=st.one_of(grouped_asts(), verified_grouped_asts()))
def test_a_bases_combos_from_bitmaps_are_the_aggregations(engines: Engines, tree: Node) -> None:
    """Each (venue, year, track, status) combination's count, read from the conjuncts' bitmaps and the engine's
    per-value bitmaps, is what the nested terms aggregation of the base's query counts."""
    _reference, tantivy, _other = engines
    for base in bases_of(canonicalize(tree)):
        try:
            tantivy.faceted.clear()
            aggregated = tantivy.combos(base)
        except EngineInputError:
            return  # over the expansion cap: refused either way (`counts` checks it first)
        parts = _Parts(tantivy, None)
        parts.bitwise = True
        tantivy.faceted.clear()
        assert tantivy.combos(base, parts=parts) == aggregated, render(canonicalize(tree))


def test_every_documents_combo_from_bitmaps_is_the_aggregations(engines: Engines) -> None:
    _reference, tantivy, _other = engines
    tantivy.faceted.clear()
    whole = tantivy.combos([])
    assert tantivy._combos_of((1 << len(tantivy.ids)) - 1) == whole
    assert sum(n for _combo, n in whole) == len(tantivy.ids)


class Collections:
    """A searcher that counts the collections it runs (`search` and `aggregate`), by thread."""

    def __init__(self, searcher: Any) -> None:
        self.searcher, self.searches, self.aggregates = searcher, 0, 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.searcher, name)

    def search(self, *a: Any, **kw: Any) -> Any:
        self.searches += 1
        return self.searcher.search(*a, **kw)

    def aggregate(self, *a: Any, **kw: Any) -> Any:
        self.aggregates += 1
        return self.searcher.aggregate(*a, **kw)


SHARED_VERIFIED = '"model* learning" AND (trust OR "data* set") AND calibrat* AND evaluat*'


# three groups and a kept verified NOT: its child's query is the request's too (`Compiled.conjuncts`)
KEPT_VERIFIED_NOT = '"model* learning" AND calibrat* AND evaluat* NOT "data* set"'


@pytest.mark.parametrize(("q", "groups"), [(SHARED_VERIFIED, 4), (KEPT_VERIFIED_NOT, 3)])
def test_each_shared_costly_conjunct_is_collected_once_and_nothing_is_compiled_again(
    tmp_path: Any, q: str, groups: int
) -> None:
    """Groups each holding a verified clause or not (and a kept verified NOT): the request's compile is reused
    (no clause is compiled, a NOT's child included, so no candidate is counted or read again), each of the four
    non-filter conjuncts is collected once, and no tree is aggregated (its combos come from the bitmaps); the
    counts are the oracle's."""
    engine = tantivy_of(RECORDS, tmp_path)
    reference = ReferenceEngine(RECORDS)
    ast = parse(q).effective_ast
    assert ast is not None
    found = split(ast)
    assert len(found.groups) == groups
    trees = counted_trees(ast)
    scope = Scope()
    compiled = engine.compile(ast, scope)
    engine._combos_of(0)  # the per-value bitmaps, built once per engine, are not this call's
    fresh: list[Node] = []
    real = engine._fresh

    def compiling(n: Node, s: Scope | None) -> Any:
        fresh.append(n)
        return real(n, s)

    engine._fresh = compiling  # type: ignore[method-assign, assignment]
    searcher = engine.searcher = Collections(engine.searcher)  # type: ignore[assignment]
    got = engine.counts(trees, scope=scope.reader(), compiled=(ast, compiled))
    assert got == [len(reference.match_ids(t)) for t in trees]
    assert fresh == []
    assert (searcher.searches, searcher.aggregates) == (4, 0)


def test_without_a_shared_costly_conjunct_each_tree_is_aggregated_as_before(tmp_path: Any) -> None:
    """No verified clause: one aggregation per distinct base, nothing collected into a bitmap, and the
    request's compile still reused."""
    engine = tantivy_of(RECORDS, tmp_path)
    ast = parse("(trust OR reliance) AND calibrat* AND model*").effective_ast
    assert ast is not None
    trees = counted_trees(ast)
    scope = Scope()
    compiled = engine.compile(ast, scope)
    searcher = engine.searcher = Collections(engine.searcher)  # type: ignore[assignment]
    engine.counts(trees, scope=scope.reader(), compiled=(ast, compiled))
    assert (searcher.searches, searcher.aggregates) == (0, 6)
    assert engine._masks is None  # never built for a query that doesn't need them


def test_a_stopped_bitwise_count_stops_before_its_next_collection(tmp_path: Any) -> None:
    """`check` is asked before each conjunct's collection too, not only before each tree: a job its search
    stopped waiting for makes no more collections, however many conjuncts its first tree has."""
    engine = tantivy_of(RECORDS, tmp_path)
    ast = parse(SHARED_VERIFIED).effective_ast
    assert ast is not None
    scope = Scope()
    compiled = engine.compile(ast, scope)
    engine._combos_of(0)
    searcher = engine.searcher = Collections(engine.searcher)  # type: ignore[assignment]
    asked = 0

    def check() -> None:
        nonlocal asked
        asked += 1
        if asked > 2:  # before the first tree, then before its first conjunct: stop at the second
            raise search._Abandoned

    with pytest.raises(search._Abandoned):
        engine.counts(counted_trees(ast), scope=scope.reader(), check=check, compiled=(ast, compiled))
    assert searcher.searches == 1


def test_a_compile_of_another_tree_is_refused(engines: Engines) -> None:
    """`compiled` must be the compile of the tree whose conjuncts are counted: one whose conjuncts don't line up
    with it is a caller's bug, an internal error, never a count of the wrong queries."""
    _reference, tantivy, _other = engines
    ast = parse("trust model calibration").effective_ast
    wrong = parse("trust model").effective_ast
    assert ast is not None and wrong is not None
    with pytest.raises(EngineInternalError):
        tantivy.counts(counted_trees(ast), compiled=(ast, tantivy.compile(wrong)))


def test_bitwise_counting_costs_the_memos_nothing_more(tmp_path: Any) -> None:
    """A search of SHARED_VERIFIED with its counts, against the same search without: no `compiled` entry or
    unit more, no clause verified or id set built again, at most two `faceted` entries a group, and the
    per-value bitmaps one per facet value (held for the engine's life, as the ord table is)."""
    plain_engine, engine = two_engines(tmp_path)
    parsed = parse(SHARED_VERIFIED)
    plain, plain_builds, plain_keys, plain_units, plain_faceted = measured(plain_engine, parsed)
    got, builds, keys, units, faceted = measured(engine, parsed, groups=10)
    assert got.groups is not None and got.groups.not_counted is None and len(got.groups.counts) == 4
    assert dataclasses.replace(got, groups=None) == plain
    assert (keys, units, builds) == (plain_keys, plain_units, plain_builds)
    assert sum(engine.charges["verified"]) == sum(plain_engine.charges["verified"])
    assert faceted - plain_faceted <= 8
    assert engine._masks is not None
    whole = engine.combos([])
    assert [len(values) for values in engine._masks] == [
        len({c[i] for c, _n in whole}) for i in range(len(COMBO))
    ]


def test_bitwise_counting_never_makes_more_collections_than_its_distinct_bases(tmp_path: Any) -> None:
    """Two groups and three kept text conjuncts, one of them verified: five conjuncts but two distinct bases (a
    group alone is the query without the other), so each base is aggregated as before, two collections, not
    five conjuncts collected."""
    engine = tantivy_of(RECORDS, tmp_path)
    reference = ReferenceEngine(RECORDS)
    ast = parse('trust model NOT "data* set" NOT survey NOT bias').effective_ast
    assert ast is not None
    trees = counted_trees(ast)
    assert len(split(ast).groups) == 2 and len(trees) == 4
    scope = Scope()
    compiled = engine.compile(ast, scope)
    searcher = engine.searcher = Collections(engine.searcher)  # type: ignore[assignment]
    got = engine.counts(trees, scope=scope.reader(), compiled=(ast, compiled))
    assert got == [len(reference.match_ids(t)) for t in trees]
    assert (searcher.searches, searcher.aggregates) == (
        0,
        2,
    )  # the two distinct bases; the rest from the memo


# --- gate round 1 (TASK-197): what the kept conjuncts cost, the masks' stop, the compile's tree -----------------
def query_units(engine: TantivyEngine, tree: Node) -> int:
    """What `held` charges for the Tantivy queries a compile of `tree` keeps: less its explain lines and the
    Python lists of verified ids (`Compiled.ids`), which no query copies."""
    c = engine.compile(tree)
    return c.held - len(c.explain) - sum(len(ids) for ids in c.ids.values())


def test_held_charges_every_copy_of_a_conjunct_the_compile_keeps(engines: Engines) -> None:
    """tantivy-py's `boolean_query` deep-copies its subqueries, so a conjunct kept in `Compiled.conjuncts` is a
    second copy of its terms and ids beside the one inside the whole query, and a NOT's kept child a third (the
    child, the NOT that copies it, the whole query that copies the NOT): `held` charges each copy, so the
    compiled memo's budget stays honest (task-080). A tree that is its one conjunct keeps no second copy."""
    _reference, tantivy, _other = engines
    tantivy.compiled.clear()
    calibrat = Wildcard(span=SPAN, stem="calibrat", op="*")
    model = Wildcard(span=SPAN, stem="model", op="*")
    phrase = Phrase(
        span=SPAN, items=(Term(span=SPAN, token="language"), Wildcard(span=SPAN, stem="model", op="*"))
    )
    trust = Term(span=SPAN, token="trust")
    a, b, v = (query_units(tantivy, n) for n in (calibrat, model, phrase))
    assert a > 0 and b > 0 and v > 0
    assert query_units(tantivy, Not(span=SPAN, child=model)) == 2 * b
    assert (
        query_units(tantivy, And(span=SPAN, children=(calibrat, Not(span=SPAN, child=model))))
        == 2 * a + 3 * b
    )
    assert query_units(tantivy, And(span=SPAN, children=(phrase, trust))) == 2 * v
    nested = And(span=SPAN, children=(And(span=SPAN, children=(calibrat, trust)), model))
    assert query_units(tantivy, nested) == 2 * a + 2 * b


def test_building_the_value_masks_stops_before_its_next_collection(tmp_path: Any) -> None:
    """The per-value bitmaps are about 30 collections, built inside the first bitwise count: `check` is asked
    before each, so a job its search stopped waiting for stops within one, and keeps no partial masks."""
    engine = tantivy_of(RECORDS, tmp_path)
    ast = parse(SHARED_VERIFIED).effective_ast
    assert ast is not None
    scope = Scope()
    compiled = engine.compile(ast, scope)
    searcher = engine.searcher = Collections(engine.searcher)  # type: ignore[assignment]
    asked = 0

    def check() -> None:
        nonlocal asked
        asked += 1
        if asked > 4:  # the tree, its conjunct, then two values' bitmaps: stop at the third value
            raise search._Abandoned

    with pytest.raises(search._Abandoned):
        engine.counts(counted_trees(ast), scope=scope.reader(), check=check, compiled=(ast, compiled))
    assert searcher.searches == 3  # the conjunct and two values
    assert engine._masks is None
    # and a later count builds them whole, with the oracle's counts
    reference = ReferenceEngine(RECORDS)
    got = engine.counts(counted_trees(ast), scope=scope.reader(), compiled=(ast, compiled))
    assert got == [len(reference.match_ids(t)) for t in counted_trees(ast)]


def test_a_compile_of_another_tree_with_as_many_conjuncts_is_refused(engines: Engines) -> None:
    _reference, tantivy, _other = engines
    ast = parse("trust model calibration").effective_ast
    other = parse("trust model evaluation").effective_ast
    assert ast is not None and other is not None
    assert len(conjuncts(ast)) == len(conjuncts(other))
    with pytest.raises(EngineInternalError):
        tantivy.counts(counted_trees(ast), compiled=(ast, tantivy.compile(other)))
    tantivy.faceted.clear()
    assert tantivy.counts(counted_trees(ast), compiled=(ast, tantivy.compile(ast))) == tantivy.counts(
        counted_trees(ast)
    )


def test_a_search_with_group_counts_hands_its_compile_to_the_counting_worker(tmp_path: Any) -> None:
    """`search.run` passes the request's compile to the counting job (TASK-197): the worker compiles nothing,
    neither a conjunct nor a kept NOT's child, on a fresh engine whose memos hold nothing to fall back on."""
    engine = tantivy_of(RECORDS, tmp_path)
    reference = ReferenceEngine(RECORDS)
    parsed = parse(KEPT_VERIFIED_NOT)
    assert parsed.effective_ast is not None
    in_counting: list[Node] = []
    real = engine._fresh

    def compiling(n: Node, s: Scope | None) -> Any:
        if threading.current_thread().name.startswith("op-groups"):
            in_counting.append(n)
        return real(n, s)

    engine._fresh = compiling  # type: ignore[method-assign, assignment]
    got = search.run(engine, parsed, facets=True, groups=10)
    search.shutdown()
    assert got.groups is not None and got.groups.counts == expected_pairs(
        reference, split(parsed.effective_ast)
    )
    assert in_counting == []
