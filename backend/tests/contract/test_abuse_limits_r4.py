"""Round 4 of the M3a review gate (spec 04 §Rate limit; decision-010): the verification time a request used is
charged after the fact, so no client holds the one verification slot for more than its share; the access
context is reset even if the access line fails; a wide wildcard phrase costs what its candidates say."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient
from openproceedings.api import RateLimit
from openproceedings.api import middleware as mw
from openproceedings.api.config import ApiConfig
from openproceedings.api.errors import current_access
from openproceedings.api.middleware import AccessLog, TokenBucket

from tests.contract.conftest import Store, make_app
from tests.contract.test_abuse_limits import error

SEARCH = "/api/v1/search"
READ_S = 0.15  # each cold verification (one clause, one field) takes at least this long here


def slowed(c: TestClient) -> None:
    engine = c.app.state.index.engine  # type: ignore[attr-defined]
    read = engine.read

    def slow(*args: Any) -> Any:
        time.sleep(READ_S)
        return read(*args)

    engine.read = slow


def test_a_debit_can_take_a_bucket_below_zero_and_the_wait_repays_it() -> None:
    now = [0.0]
    bucket = TokenBucket(10, 1.0, 10, clock=lambda: now[0])
    assert bucket.take("a", 1) == 0  # 9 left
    bucket.debit("a", 14)  # -5
    assert bucket.take("a", 1) == pytest.approx(6.0)  # 6 s until 1 token is back
    now[0] = 6.0
    assert bucket.take("a", 1) == 0


def test_the_default_verify_token_ms() -> None:
    assert ApiConfig(data_dir=Path("x")).rate_limit.verify_token_ms == 100


def test_back_to_back_cold_queries_are_throttled_to_their_share_and_another_client_gets_the_slot(
    store: Store, logs: Any
) -> None:
    """Client A sends cold verified queries back to back (each NEAR distance a new, cold clause). The first
    holds the slot ≥ 2 × 150 ms, so it is debited ≥ 3 tokens (one per 100 ms) after the fact and A's bucket
    goes below zero: its next query is a 429 whose `Retry-After` is the debt's repayment, not a turn at the
    slot. Client B, on another network, gets the slot for its own cold query meanwhile."""
    limit = RateLimit(capacity=3, refill_per_second=0.01, export_weight=1, verified_weight=0.1)
    app = make_app(store.indexes.parent, rate_limit=limit, trusted_proxies=("10.0.0.0/8",))
    with TestClient(app, client=("10.0.0.5", 4000)) as c:
        slowed(c)

        def search(xff: str, k: int) -> Any:
            return c.get(SEARCH, params={"q": f"trust NEAR/{k} trust"}, headers={"X-Forwarded-For": xff})

        assert search("203.0.113.1", 3).status_code == 200  # A: cold, ~300 ms of slot
        r = search("203.0.113.1", 4)  # A again, cold: refused before it reaches the slot
        e = error(r, 429, "API_RATE_LIMITED")
        assert int(r.headers["retry-after"]) >= 100 and "try again" in e["message"]  # the debt, at 0.01/s
        assert search("198.51.100.7", 5).status_code == 200  # B: its own cold verification, served
    lines = [x for x in logs() if x["event"] == "request" and x["status"] == 200]
    first = lines[0]
    assert first["verify_ms"] >= 2 * READ_S * 1000 and first["verify_tokens"] == pytest.approx(
        first["verify_ms"] / 100, abs=0.01
    )


def test_a_warm_query_is_not_debited(client: TestClient, logs: Any) -> None:
    assert client.get(SEARCH, params={"q": "trust NEAR/7 trust"}).status_code == 200  # cold
    assert client.get(SEARCH, params={"q": "trust NEAR/7 trust"}).status_code == 200  # cached: no slot held
    cold, warm = [x for x in logs() if x["event"] == "request"]
    assert cold["verify_tokens"] > 0 and "verify_tokens" not in warm and "verify_ms" not in warm


def test_the_access_context_is_reset_when_the_access_line_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def app(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    def failing(*_a: Any, **_kw: Any) -> None:
        raise RuntimeError("the log handler failed")

    monkeypatch.setattr(mw.log, "log", failing)

    async def run() -> None:
        async def receive() -> Any:
            return {"type": "http.request"}

        async def send(_message: Any) -> None:
            return None

        with pytest.raises(RuntimeError):
            await AccessLog(app)(
                {"type": "http", "method": "GET", "path": "/x", "headers": []}, receive, send
            )
        assert current_access.get() is None  # not left pointing at the failed request's fields

    anyio.run(run)
