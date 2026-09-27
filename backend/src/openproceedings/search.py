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
(`tests/unit/test_search_overlap.py`); only wall time changes, not CPU time.
"""

from __future__ import annotations

import atexit
import contextvars
import logging
import os
import threading
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import Any

from openproceedings.diagnostics import Diagnostic, DiagnosticCode
from openproceedings.engine.compile import wildcards
from openproceedings.engine.exclusions import Excluded, excluded
from openproceedings.engine.highlight import Highlighter
from openproceedings.engine.protocol import EngineInputError, Expansions
from openproceedings.engine.tantivy_engine import Scope, TantivyEngine, WouldVerify
from openproceedings.query.ast import Node, TextField
from openproceedings.query.parser import ParseResult

type Spans = Mapping[TextField, list[tuple[int, int]]]


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
class Search:
    total: int  # |match_ids(effective_ast)|: independent of sort, offset and limit (guarantee 5)
    hits: tuple[Hit, ...]  # the page, in the engine's order
    excluded: Excluded
    expansions: Expansions  # every wildcard's terms (guarantee 6)
    facets: dict[str, dict[str, int]] | None  # None unless asked for


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
) -> Search:
    """One page of `parsed`'s search on `engine`, with its total, exclusion accounting and expansions (and,
    when asked, the disjunctive facets and each hit's code-point highlight spans). `parsed` must have
    parsed: a query with errors never reaches an engine (spec 03 §Error handling)."""
    ast = parsed.effective_ast
    if ast is None:
        raise EngineInputError(DiagnosticCode.API_BAD_PARAM, "a search needs a query that parses.")
    expansions = expanded(engine, ast)
    scope = Scope()  # the ids this request verifies, for its every compile (module docstring)
    faceting: Future[dict[str, dict[str, int]]] | None = None
    if facets:
        engine.check_page(sort, offset, limit)  # a bad argument is refused before any work, as before
        # compiled first, here: a cold verified clause takes its slot in this thread, and the worker's facet
        # tree (the same clauses, less top-level filters) then finds each one in `scope` (it never verifies)
        engine.compile(ast, scope)
        faceting = _submit(engine, ast, scope)
    try:
        # one collection: ids and scores
        total, page = engine.page(ast, sort=sort, offset=offset, limit=limit, scope=scope)
        shown = engine.display([i for i, _score in page])
        lit = Highlighter(ast, expansions) if highlight else None  # one per page: the query's work done once
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
        if faceting is not None:
            faceting.cancel()  # not started yet: never run; running: its result (or error) is dropped
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
    gone = excluded(engine, parsed, total, facets=partial(engine.facets, scope=scope))
    return Search(total, hits, gone, expansions, counted)


def highlight(engine: TantivyEngine, parsed: ParseResult, id: str) -> Spans | None:
    """Paper `id`'s highlights for `parsed` on `engine` (it must hold `id`), as `run(..., highlight=True)` gives
    them when `id` is a hit: the same display record, expansions and `Highlighter` (`GET /papers/{id}?q=`,
    task-087). None when the query doesn't match the paper (its effective tree, default filters included):
    no collection is run and nothing is position-verified; the evaluation is the highlighter's, which a test
    holds to ReferenceEngine's verdict on every record."""
    ast = parsed.effective_ast
    if ast is None:
        raise EngineInputError(DiagnosticCode.API_BAD_PARAM, "a search needs a query that parses.")
    expansions = expanded(engine, ast)
    return Highlighter(ast, expansions).match(Shown.of(engine.display([id])[id]))


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
log = logging.getLogger(__name__)
_POOL: ThreadPoolExecutor | None = None
_POOL_LOCK = threading.Lock()


def _submit(engine: TantivyEngine, ast: Node, scope: Scope) -> Future[dict[str, dict[str, int]]] | None:
    """`engine.facets(ast, scope=scope.reader())` (it never verifies, so never takes a slot) started on a worker, in a copy of the caller's context (a request's log fields
    follow it), or None if the pool is shutting down (`run` then counts them itself)."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = ThreadPoolExecutor(max(4, os.cpu_count() or 4), thread_name_prefix="op-facets")
        pool = _POOL
    try:
        return pool.submit(contextvars.copy_context().run, partial(engine.facets, ast, scope=scope.reader()))
    except RuntimeError:  # shut down between the lock and the submit (interpreter exit, or `shutdown()`)
        return None


def shutdown() -> None:
    """Stop the facet workers (waiting for any in flight); a later search starts new ones. Registered at exit."""
    global _POOL
    with _POOL_LOCK:
        pool, _POOL = _POOL, None
    if pool is not None:
        pool.shutdown(wait=True)  # queued work runs too: a search waiting on it gets its counts


def _forget_after_fork() -> None:
    global _POOL, _POOL_LOCK
    _POOL, _POOL_LOCK = None, threading.Lock()


atexit.register(shutdown)
if hasattr(os, "register_at_fork"):  # POSIX
    os.register_at_fork(after_in_child=_forget_after_fork)
