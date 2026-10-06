"""Round 5 of the M3a review gate (spec 04 §Rate limit; decision-010): a request's cold verifications get
`max_verification_seconds` of wall time, past which the loop stops (503 `API_BUSY`, nothing stored, the
verified charge refunded, a replay a 503 too: it is transient); and the slot-time debit charges the
verifying thread's CPU, not wall time other requests' load inflates."""

from __future__ import annotations

import itertools
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings import cli
from openproceedings.api import RateLimit
from openproceedings.api import server as api_server
from openproceedings.api import state as state_module
from openproceedings.api.config import ApiConfig

from tests.contract.conftest import Store, make_app
from tests.contract.test_abuse_limits import error
from tests.contract.test_records import save

SEARCH = "/api/v1/search"
HEAVY = '"tru* tru*" OR "calibrat* model*"'  # clauses with hundreds to thousands of candidates each


def slowed(c: TestClient, per_doc: float) -> None:
    engine = c.app.state.index.engine  # type: ignore[attr-defined]
    read = engine.read

    def slow(*args: Any) -> Any:
        for doc in read(*args):
            time.sleep(per_doc)
            yield doc

    engine.read = slow


def test_the_default_deadline_is_30_seconds() -> None:
    assert ApiConfig(data_dir=Path("x")).max_verification_seconds == 30.0


def test_a_verification_past_its_deadline_is_a_503_with_nothing_stored(store: Store, logs: Any) -> None:
    limit = RateLimit(capacity=60, refill_per_second=0.001, export_weight=10)
    with TestClient(make_app(store.indexes.parent, rate_limit=limit, max_verification_seconds=0.05)) as c:
        slowed(c, 0.0002)  # every clause-field takes 0.1 s or more: the second starts past the deadline
        engine = c.app.state.index.engine  # type: ignore[attr-defined]
        r = c.get(SEARCH, params={"q": HEAVY})
        e = error(r, 503, "API_BUSY")
        assert r.headers["retry-after"] == "5" and "ran past the time" in e["message"]
        assert engine.compiled == {}  # the tree never compiled
        # whatever `verified` holds is whole: each entry equals a fresh, unhurried verification
        fresh = engine_of(store)
        for key, ids in engine.verified.items():
            assert ids == fresh_ids(fresh, key)
    [line] = [x for x in logs() if x["event"] == "request"]
    assert line["code"] == "API_BUSY" and line["verify_ms"] > 50


def engine_of(store: Store) -> Any:
    from openproceedings.engine.tantivy_engine import TantivyEngine

    return TantivyEngine(store.indexes / store.big)


def fresh_ids(engine: Any, key: tuple[str, str]) -> list[str]:
    from openproceedings.engine.compile import Compiler
    from openproceedings.query.ast import Near, Phrase
    from pydantic import TypeAdapter

    field, clause = key
    node: Phrase | Near = TypeAdapter(Phrase | Near).validate_json(clause)
    compiler = Compiler(engine.index.schema, engine.expansions(node), engine.read)
    return compiler.verify(node, field, compiler.candidates(node, field))  # type: ignore[arg-type]


def test_a_deadline_503_gives_the_verified_charge_back(store: Store) -> None:
    limit = RateLimit(capacity=30, refill_per_second=0.001, export_weight=10, verify_token_ms=1e9)
    app = make_app(
        store.indexes.parent, rate_limit=limit, max_verified_clauses=2, max_verification_seconds=0.05
    )
    with TestClient(app) as c:
        slowed(c, 0.0002)
        for _ in range(3):  # 30 a time without the refund: the second would be a 429
            error(c.get(SEARCH, params={"q": HEAVY}), 503, "API_BUSY")


def test_a_replay_past_its_deadline_is_a_503_not_a_refusal(data_dir: Path) -> None:
    """Transient (load decides it), so it is the client's retry, not the record's `refused`."""
    with TestClient(make_app(data_dir)) as c:
        rid = save(c, HEAVY)
    with TestClient(make_app(data_dir, max_verification_seconds=0.05)) as c:
        slowed(c, 0.0002)
        error(c.get(f"/api/v1/records/{rid}"), 503, "API_BUSY")


def test_the_debit_charges_cpu_not_wall_time(
    store: Store, logs: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Other requests' load stretches a verification's wall time, not its CPU: the wall clock here leaps 10 s a
    reading (as under heavy GIL contention); the debit follows `verify_cpu_ms`."""
    leaps = itertools.count(0.0, 10.0)
    monkeypatch.setattr(state_module, "_wall", lambda: next(leaps))
    with TestClient(make_app(store.indexes.parent, max_verification_seconds=1e6)) as c:
        assert c.get(SEARCH, params={"q": '"tru* tru*"'}).status_code == 200
    [line] = [x for x in logs() if x["event"] == "request"]
    assert line["verify_ms"] >= 10_000  # the leaping wall clock
    assert line["verify_cpu_ms"] < 5_000  # the thread's own work
    assert line["verify_tokens"] == pytest.approx(line["verify_cpu_ms"] / 100, abs=0.01)


def test_op_serve_takes_the_deadline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, ApiConfig] = {}
    monkeypatch.setattr(api_server, "serve", lambda config, *a: seen.update(config=config))
    assert cli.main(["--data-dir", str(tmp_path), "serve", "--max-verification-seconds", "12.5"]) == 0
    assert seen["config"].max_verification_seconds == 12.5
    assert cli.main(["--data-dir", str(tmp_path), "serve"]) == 0
    assert seen["config"].max_verification_seconds == 30.0


def test_a_bucket_in_debt_is_not_evicted_so_its_debt_is_not_forgiven() -> None:
    from openproceedings.api.middleware import TokenBucket

    now = [0.0]
    bucket = TokenBucket(10, 0.001, 2, clock=lambda: now[0])
    bucket.take("debtor", 1)
    bucket.debit("debtor", 50)  # -41
    bucket.take("b", 1)
    bucket.take("c", 1)  # over max_clients: `b`, the oldest not in debt, goes, not `debtor`
    assert bucket.take("debtor", 1) > 1000  # still owes: 42 tokens at 0.001 a second
    for key in ("d", "e"):  # all but the debtor are replaced; it stays
        bucket.take(key, 1)
    assert bucket.take("debtor", 1) > 1000
    everyone = TokenBucket(10, 0.001, 1, clock=lambda: now[0])
    everyone.debit("x", 50)
    everyone.debit("y", 50)  # every bucket in debt: the map stays bounded, the oldest goes
    assert everyone.take("y", 1) > 1000 and everyone.take("x", 1) == 0


def test_a_compiled_entry_charges_each_copy_of_its_verified_ids(store: Store) -> None:
    """`Compiled.ids` holds them, and so does every Tantivy query that keeps the clause's id set: the whole query,
    and, since TASK-197, the top-level conjunct `Compiled.conjuncts` keeps beside it. tantivy-py's
    `boolean_query` and `const_score_query` deep-copy their subqueries (a 3M-ord term set: 349 MB; wrapped in a
    const score, +46 MB; in a boolean query, +237 MB; again, +112 MB; gate round 1 of TASK-197), so the kept
    conjunct is a second copy of the term set. The compiled memo's budget counts all three: the list once and
    the term set twice, never the list again with the copy."""
    from openproceedings.query.parser import parse

    engine = engine_of(store)
    ast = parse("trust NEAR/3 trust").effective_ast
    compiled = engine.compile(ast)
    ids = sum(len(v) for v in compiled.ids.values())
    # the NEAR is one of the effective tree's conjuncts (beside the default track and status filters), so it is
    # kept: the list, the whole query's term set, the kept conjunct's term set
    assert len(compiled.conjuncts) > 1
    assert ids > 0 and compiled.held == 3 * ids + len(compiled.explain)
    # a tree that is the clause alone keeps no second copy: the list and the one term set
    alone = engine.compile(ast.children[0])  # type: ignore[union-attr]
    assert sum(len(v) for v in alone.ids.values()) == ids and alone.held == 2 * ids + len(alone.explain)
