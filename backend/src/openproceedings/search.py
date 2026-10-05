"""One ranked search, as `op search` and `GET /api/v1/search` both run it (spec 04 §SearchResponse; task-035).

The API adds transport, not behaviour: both callers pass a parsed query and an engine to `run`, so a page's
ids, scores, `total` and `excluded` are the same for the same query and `index_version`. The API also asks
for the disjunctive facets and each hit's highlights; the CLI, which prints neither, doesn't pay for them.

Order of work, on one engine: every wildcard is expanded first (the 200-term cap refuses a query before
anything is compiled), then the effective tree is compiled, so any cold position-verified clause is checked
here, in the calling thread, holding at most one verification slot (task-088). When facets are asked for,
their aggregation (one collection of the query without its top-level filters, `TantivyEngine.facets`) then
runs on a worker thread while the caller collects the page, reads its display records and highlights it:
Tantivy releases the GIL while it collects, so the two collections overlap. The facet tree's verified
clauses are the effective tree's, just checked: the request keeps the ids it verified (its `scope`, passed to
every compile it makes), so a page whose compiled entry was trimmed and exclusion accounting read them there,
never verifying a clause twice however the engine's memos are trimmed meanwhile; the worker gets a read-only
view (`Scope.reader`) and never verifies, so it never takes a verification slot, and a caller that fails while
the worker runs leaves no slot held (M3a review gate round 3). Then exclusion accounting reuses `total`
and the facet memo. The result is the sequential one, field for field
(`tests/unit/test_search_overlap.py`); only wall time changes, not CPU time. A search without facets (`op search`,
a record's save or replay) doesn't pay for every facet combination its exclusion accounting would never read:
it aggregates only the two default fields (`TantivyEngine.facets`' `over`; TASK-166), the same counts.

When asked (`groups`, the API's `max_counted_groups`; TASK-176), a query that is an AND of two or more
concept groups (`query/groups.py`) also gets two counts a group: the group alone (the query with every other
group removed) and the query without it (leave-one-out), counted by `TantivyEngine.counts` on a second worker,
beside the facets. Those trees hold only clauses of the effective tree, compiled first, so their worker never
verifies either; the counts read nothing the page, `total`, the facets or `excluded` are computed from, and
change none of them. They are an extra, so they can never cost the search its answer: a worker that fails,
or isn't done `GROUP_COUNT_WAIT_SECONDS` after everything else is, leaves the search whole with no counts and
the reason (`count_failed`, `timed_out`), and the late job stops before its next collection; a job no
worker has started within a short grace is dropped at once (`busy`). And they are
bounded before they start: a query whose counting would read more than `groups_terms` terms or `groups_ids`
verified ids (`Groups.read`: every tree counted reads the kept clauses again) gets no counts and `too_costly`.
They run on their own two workers, so the facets never queue behind them (`tests/unit/test_group_counts.py`).
"""

from __future__ import annotations

import atexit
import contextvars
import logging
import os
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal

from openproceedings.diagnostics import Diagnostic, DiagnosticCode
from openproceedings.engine.compile import FIELDS, verified_clauses, wildcards
from openproceedings.engine.exclusions import ORDER, Excluded, excluded
from openproceedings.engine.highlight import Highlighter
from openproceedings.engine.protocol import EngineInputError, EngineInternalError, Expansions
from openproceedings.engine.tantivy_engine import COMBO, Scope, TantivyEngine, WouldVerify
from openproceedings.query.ast import Node, Span, TextField
from openproceedings.query.groups import Groups, split
from openproceedings.query.parser import ParseResult

type Spans = Mapping[TextField, list[tuple[int, int]]]
# why a search asked for its groups' counts has none (spec 04 §SearchResponse, `groups.not_counted`)
NotCounted = Literal[
    "fewer_than_two_groups", "too_many_groups", "too_costly", "busy", "count_failed", "timed_out"
]
# the most terms the counting of one query's groups may read, summed over the trees counted
# (`Groups.terms_read`): over it the search answers without counts (`too_costly`). The API passes its own
# (`ApiConfig.max_counted_terms`)
MAX_COUNTED_TERMS = 5_000
# and the most verified ids: a position-verified clause (a wildcard phrase, a NEAR) is an id set in its tree's
# query, resolved id by id in every collection that reads it, however few terms it has
MAX_COUNTED_IDS = 300_000


class _Abandoned(Exception):
    """A counting job whose search no longer waits for it (it timed out, or failed): stopped between
    collections, never reported."""


# how long a finished search waits for its counting worker before answering without the counts: the page,
# the facets and the exclusion accounting are done by then, so this is the most the counts can add to a
# response (they take milliseconds; a worker this late is queued behind others or stuck)
GROUP_COUNT_WAIT_SECONDS = 2.0
# and how long it waits for a counting job that has not STARTED (every counting worker is busy with other
# searches' jobs): past this grace the search answers `busy` at once, so other clients' counting can cost a
# search its counts but no more than this of its time. An idle worker starts a job in well under a millisecond
GROUP_COUNT_GRACE_SECONDS = 0.05
# one group's two counts: the query with every other group removed, and the query with this group removed
type Pair = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Shown:
    """A display record as `engine/highlight.py` reads it (the `Searchable` protocol)."""

    id: str
    title: str
    abstract: str | None
    venue: str
    year: int
    track: str
    status: str

    @classmethod
    def of(cls, record: Mapping[str, Any]) -> Shown:
        return cls(**{f: record[f] for f in ("id", "title", "abstract", "venue", "year", "track", "status")})


@dataclass(frozen=True, slots=True)
class Hit:
    id: str
    score: float  # the exact field-weighted BM25 score (0.0-based sorts keep it too)
    record: Mapping[str, Any]  # the stored display record (`TantivyEngine.display`)
    highlights: Spans | None  # None unless asked for


@dataclass(frozen=True, slots=True)
class GroupCounts:
    """Each concept group's two counts (`query/groups.py`): the group alone (the query with every other group
    removed) and the query without it."""

    # (the group's span in `q`, its count alone, the query's count without it), in query order
    counts: tuple[tuple[Span, int, int], ...]
    found: int  # how many groups the query has
    limit: int  # the most groups this search would count
    not_counted: NotCounted | None  # why `counts` is empty; None exactly when the groups were counted


@dataclass(frozen=True, slots=True)
class Search:
    total: int  # |match_ids(effective_ast)|: independent of sort, offset and limit (guarantee 5)
    hits: tuple[Hit, ...]  # the page, in the engine's order
    excluded: Excluded
    expansions: Expansions  # every wildcard's terms (guarantee 6)
    facets: dict[str, dict[str, int]] | None  # None unless asked for
    groups: GroupCounts | None = None  # None unless asked for


def expansions_json(expansions: Expansions) -> dict[str, list[str]]:
    """Every wildcard's terms keyed `<stem><op>` (`calibrat*`), sorted by key: the shape `GET /search`'s
    `query.expansions` and a search record's `expansions` share."""
    return {f"{stem}{op}": list(terms) for (stem, op), terms in sorted(expansions.items())}


def run(
    engine: TantivyEngine,
    parsed: ParseResult,
    *,
    sort: str = "relevance",
    offset: int = 0,
    limit: int = 50,
    facets: bool = False,
    highlight: bool = False,
    groups: int | None = None,
    groups_terms: int = MAX_COUNTED_TERMS,
    groups_ids: int = MAX_COUNTED_IDS,
    groups_wait: float = GROUP_COUNT_WAIT_SECONDS,
    groups_grace: float | None = None,
) -> Search:
    """One page of `parsed`'s search on `engine`, with its total, exclusion accounting and expansions (and,
    when asked, the disjunctive facets, each hit's code-point highlight spans, and each concept group's counts
    when the query has from two to `groups` of them and counting them reads at most `groups_terms` terms and
    `groups_ids` verified ids, waited for at most `groups_wait` seconds once the rest is done, and only
    `groups_grace` (default `GROUP_COUNT_GRACE_SECONDS`) if their job hasn't started by then). `parsed` must have
    parsed: a query with errors never reaches an engine (spec 03 §Error handling)."""
    ast = _runnable(engine, parsed)
    expansions = expanded(engine, ast)
    scope = Scope()  # the ids this request verifies, for its every compile (module docstring)
    faceting: Future[dict[str, dict[str, int]]] | None = None
    found = None if groups is None else split(ast)
    why = None if found is None or groups is None else _uncountable(found, groups, groups_terms, expansions)
    countable = found is not None and why is None
    counting: Future[tuple[Pair, ...]] | None = None
    abandoned = threading.Event()  # set when this search stops waiting for its counting job
    taken = threading.Event()  # set by the counting job when a worker takes it
    if facets or countable:
        engine.check_page(sort, offset, limit)  # a bad argument is refused before any work, as before
        # compiled first, here: a cold verified clause takes its slot in this thread, and the worker's facet
        # tree (the same clauses, less top-level filters) then finds each one in `scope` (it never verifies)
        engine.compile(ast, scope)
    if facets:
        faceting = _submit(engine, ast, scope)
    if found is not None and countable and _ids_read(found, scope) > groups_ids:
        why, countable = "too_costly", False  # known only now: the ids are the compile's
    if found is not None and countable:
        counting = _start(partial(_alone, engine, found, scope.reader(), abandoned, taken), counts=True)
    try:
        # one collection: ids and scores
        total, page = engine.page(ast, sort=sort, offset=offset, limit=limit, scope=scope)
        shown = engine.display([i for i, _score in page])
        # one per page: the query's work done once
        lit = Highlighter(ast, expansions, engine.tokenizer_version) if highlight else None
        hits = tuple(
            Hit(
                id=i,
                score=score,
                record=shown[i],
                highlights=lit(Shown.of(shown[i])) if lit else None,
            )
            for i, score in page
        )
    except BaseException:
        abandoned.set()  # a counting job already running stops before its next collection
        for started in (faceting, counting):
            if started is not None:
                started.cancel()  # not started yet: never run; running: its result (or error) is dropped
        raise  # the caller's error first, as when facets ran after the page
    counted: dict[str, dict[str, int]] | None = None
    if faceting is not None:
        try:
            counted = faceting.result()  # the worker's error, re-raised as it was raised
        except WouldVerify:
            # a clause the request should have held (a bug, never the client's): count here, where verifying
            # is allowed, rather than answer 500 (round 4); logged so the bug is seen
            log.warning("facet_worker_recounted", extra={"reason": "would_verify"})
            counted = engine.facets(ast, scope=scope)
    elif facets:
        counted = engine.facets(
            ast, scope=scope
        )  # no worker (the pool is shutting down): counted here instead
    # with facets, the combos the worker just collected; without, only the default fields' (TASK-166)
    over = COMBO if facets else ORDER
    gone = excluded(engine, parsed, total, facets=partial(engine.facets, scope=scope, over=over))
    grouped = None
    if found is not None and groups is not None:
        if why is not None:
            grouped = GroupCounts((), len(found.groups), groups, why)
        else:
            grace = GROUP_COUNT_GRACE_SECONDS if groups_grace is None else groups_grace
            grouped = _grouped(engine, found, groups, counting, scope, (grace, groups_wait), abandoned, taken)
    return Search(total, hits, gone, expansions, counted, grouped)


def _uncountable(found: Groups, limit: int, terms: int, expansions: Expansions) -> NotCounted | None:
    """Why `found`'s groups are not counted, decided from the query and its expansions before anything is
    compiled for them: it is not an AND of groups, has more groups than `limit`, or counting them would read
    more than `terms` terms. None when they may be (`run` then checks the verified ids too: `_ids_read`)."""
    n = len(found.groups)
    if n < 2:
        return "fewer_than_two_groups"
    if n > limit:
        return "too_many_groups"
    return "too_costly" if found.terms_read(expansions) > terms else None


def _ids_read(found: Groups, scope: Scope) -> int:
    """How many verified ids counting `found`'s groups reads, summed over the trees counted (`Groups.read`):
    each position-verified clause's ids, per field, as the request's compile of the query left them in
    `scope`. A clause's id set is resolved id by id in every collection whose tree holds the clause, so a kept
    `NOT (model NEAR/10 model*)` of few terms and many ids costs every tree its ids. An upper bound: a clause
    most of whose candidates match is compiled as the candidates that fail, a shorter list."""

    def ids(conjunct: Node) -> int:
        return sum(
            len(scope.ids.get((f, clause.model_dump_json()), ()))
            for clause in verified_clauses(conjunct)
            for f in ((clause.field,) if clause.field else FIELDS)
        )

    return found.read(ids)


def _alone(
    engine: TantivyEngine,
    found: Groups,
    scope: Scope,
    abandoned: threading.Event,
    started: threading.Event | None = None,
) -> tuple[Pair, ...]:
    """Each group's two counts, in query order: alone, and the query without it (`TantivyEngine.counts`: at
    most two collections a group, memoised; every conjunct compiled at most once for all of them). Sets
    `started` when it begins (a worker took the job), and stops before its next collection once `abandoned`
    is set (`_Abandoned`): nobody is waiting for the rest."""
    if started is not None:
        started.set()

    def wanted() -> None:
        if abandoned.is_set():
            raise _Abandoned

    n = len(found.groups)
    trees = [*map(found.alone, found.groups), *map(found.without, found.groups)]
    totals = engine.counts(trees, scope=scope, check=wanted)
    return tuple(zip(totals[:n], totals[n:], strict=True))


def _grouped(
    engine: TantivyEngine,
    found: Groups,
    limit: int,
    counting: Future[tuple[Pair, ...]] | None,
    scope: Scope,
    waits: tuple[float, float],
    abandoned: threading.Event,
    started: threading.Event,
) -> GroupCounts:
    """`run`'s `groups` for a query whose groups are counted: the worker's counts (or the caller's own, when
    no worker took them). Never raises for a count: the search is already computed, and a count that fails or
    is late is reported in `not_counted`, not as the search's failure. `waits` is (grace, wait): a job no
    worker has started after `grace` seconds is cancelled and the answer is `busy` (the workers are doing
    other searches' counting, which must not cost this search its time); a started job not done after `wait`
    seconds is abandoned (`timed_out`) and stops before its next collection."""
    n = len(found.groups)
    grace, wait = waits
    if counting is not None and not counting.done():
        if not started.wait(grace):
            abandoned.set()  # should a worker take it just now, it stops at once
            counting.cancel()
            log.debug("group_count_busy", extra={"groups": n})  # a state under load, not an event to act on
            return GroupCounts((), n, limit, "busy")
        if not wait_for([counting], timeout=wait).done:
            abandoned.set()
            counting.cancel()
            log.warning("group_count_timed_out", extra={"groups": n, "wait_ms": round(wait * 1000)})
            return GroupCounts((), n, limit, "timed_out")
    try:
        if counting is None:  # no worker (the pool is shutting down): counted here instead
            totals = _alone(engine, found, scope, abandoned)
        else:
            try:
                totals = counting.result()  # done: its counts, or its error (a TimeoutError of its own too)
            except WouldVerify:
                # as for the facets: a clause the request should have held (a bug, never the client's)
                log.warning("group_worker_recounted", extra={"reason": "would_verify"})
                totals = _alone(engine, found, scope, abandoned)
    except Exception as e:  # any failure of the extra: logged by type, never the message (it may quote input)
        log.error("group_count_failed", extra={"groups": n, "error": type(e).__name__})
        return GroupCounts((), n, limit, "count_failed")
    return GroupCounts(
        tuple((g.span, alone, without) for g, (alone, without) in zip(found.groups, totals, strict=True)),
        n,
        limit,
        None,
    )


def highlight(engine: TantivyEngine, parsed: ParseResult, shown: Mapping[str, Any]) -> Spans | None:
    """A paper's highlights for `parsed` on `engine`, as `run(..., highlight=True)` gives them when it is a hit:
    `shown` is its display record on `engine` (`engine.display([id])[id]`, which the caller has already read to
    know the paper is there), with the same expansions and `Highlighter` (`GET /papers/{id}?q=`, task-087). None when the query doesn't match the paper (its effective tree, default filters included):
    no collection is run and nothing is position-verified; the evaluation is the highlighter's, which a test
    holds to ReferenceEngine's verdict on every record."""
    ast = _runnable(engine, parsed)
    expansions = expanded(engine, ast)
    return Highlighter(ast, expansions, engine.tokenizer_version).match(Shown.of(shown))


def _runnable(engine: TantivyEngine, parsed: ParseResult) -> Node:
    """`parsed`'s effective tree, if it can run on `engine`: it parsed (a query with errors never reaches an
    engine, spec 03 §Error handling), and with the tokenizer `engine`'s index was built with (its terms are
    that tokenizer's; a caller that parsed with another one is a bug, never the client's)."""
    ast = parsed.effective_ast
    if ast is None:
        raise EngineInputError(DiagnosticCode.API_BAD_PARAM, "a search needs a query that parses.")
    if parsed.tokenizer_version != engine.tokenizer_version:
        raise EngineInternalError(
            DiagnosticCode.API_INTERNAL,
            f"a query parsed with tokenizer {parsed.tokenizer_version} can't run on an index built with "
            f"tokenizer {engine.tokenizer_version}",
        )
    return ast


def expanded(engine: TantivyEngine, ast: Node) -> Expansions:
    """Every wildcard of `ast` expanded on `engine`, before anything is compiled; an over-cap wildcard is
    refused as the engine's `EngineInputError` with `diagnostics` locating each one in `q` (what `/search`
    and `/export` both answer; the type stays the engine's, so `op search` logs it as before)."""
    try:
        return engine.expansions(ast)
    except EngineInputError as e:
        raise _located(engine, ast, e) from None


def _located(engine: TantivyEngine, ast: Node, error: EngineInputError) -> EngineInputError:
    """`error`, its `diagnostics` set to one per wildcard that raises it on its own (only on this refusal path; the
    engine's expansions are the answer otherwise). A wildcard's span is into `q` (an inserted default has
    no wildcard)."""
    found: list[Diagnostic] = []
    for w in dict.fromkeys(wildcards(ast)):
        try:
            engine.expand(w)
        except EngineInputError as e:
            if e.code == error.code:
                found.append(Diagnostic(code=e.code, message=e.message, span=w.span))
    error.diagnostics = tuple(found)  # the same exception and type: the CLI logs it as before (spec 08)
    return error


# The facet workers (task-088): the aggregation is Tantivy's collection (the GIL released) plus a few ms of
# Python, so more workers than CPUs only queue. Started on first use, forgotten in a forked child (its threads
# don't survive the fork, and the lock may have been held when it happened), and shut down at interpreter exit.
# The group counts (TASK-176) have a small pool of their own: a search waits for its facets without a
# timeout, so no counting job, however slow or however many, may hold a thread the facets need; counting
# jobs queue only behind each other, and one whose search stopped waiting is cancelled or stops itself.
log = logging.getLogger(__name__)
_POOL: ThreadPoolExecutor | None = None
_GROUP_POOL: ThreadPoolExecutor | None = None
_POOL_LOCK = threading.Lock()
GROUP_WORKERS = 2


def _submit(engine: TantivyEngine, ast: Node, scope: Scope) -> Future[dict[str, dict[str, int]]] | None:
    """`engine.facets(ast, scope=scope.reader())` (it never verifies, so never takes a slot) started on a worker, in a copy of the caller's context (a request's log fields
    follow it), or None if the pool is shutting down (`run` then counts them itself)."""
    return _start(partial(engine.facets, ast, scope=scope.reader()))


def _start[T](job: Callable[[], T], *, counts: bool = False) -> Future[T] | None:
    """`job` started on a worker (a facet worker, or with `counts` a group-count worker), in a copy of the
    caller's context, or None if the pool is shutting down."""
    global _POOL, _GROUP_POOL
    with _POOL_LOCK:
        if counts:
            if _GROUP_POOL is None:
                _GROUP_POOL = ThreadPoolExecutor(GROUP_WORKERS, thread_name_prefix="op-groups")
            pool = _GROUP_POOL
        else:
            if _POOL is None:
                _POOL = ThreadPoolExecutor(max(4, os.cpu_count() or 4), thread_name_prefix="op-facets")
            pool = _POOL
    try:
        return pool.submit(contextvars.copy_context().run, job)
    except RuntimeError:  # shut down between the lock and the submit (interpreter exit, or `shutdown()`)
        return None


def shutdown() -> None:
    """Stop the facet and group-count workers (waiting for any in flight); a later search starts new ones.
    Registered at exit."""
    global _POOL, _GROUP_POOL
    with _POOL_LOCK:
        pools, _POOL, _GROUP_POOL = (_POOL, _GROUP_POOL), None, None
    for pool in pools:
        if pool is not None:
            pool.shutdown(wait=True)  # queued work runs too: a search waiting on it gets its counts


def _forget_after_fork() -> None:
    global _POOL, _GROUP_POOL, _POOL_LOCK
    _POOL, _GROUP_POOL, _POOL_LOCK = None, None, threading.Lock()


atexit.register(shutdown)
if hasattr(os, "register_at_fork"):  # POSIX
    os.register_at_fork(after_in_child=_forget_after_fork)
