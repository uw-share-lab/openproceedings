"""What one request, network or connection can make the service spend, round 2 of the M3a security review
(spec 04 §Rate limit, §Error handling; spec 08 §Deploy): a cap on position-verified clauses with a charge per
clause (replays included), a per-network save ceiling beside the instance one with its log lines and
refunds, trusted proxies no wider than /8 (IPv4) or /32 (IPv6), Swagger UI off unless configured, and
uvicorn's keep-alive and concurrency bounds."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient
from openproceedings import cli
from openproceedings.api import RateLimit
from openproceedings.api import server as api_server
from openproceedings.api.config import ApiConfig
from openproceedings.api.deps import verified_clauses
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import BodyLimit, TokenBucket
from openproceedings.api.records import SaveCeiling
from openproceedings.engine.compile import verifies
from openproceedings.query.parser import parse
from pydantic import ValidationError

from tests.contract.conftest import Store, make_app
from tests.contract.test_abuse_limits import VERIFIED, error

SEARCH = "/api/v1/search"
Logs = Callable[[], list[dict[str, Any]]]


def clause(i: int) -> str:
    return f'"trust calibrat{"*" if i % 2 == 0 else "$"} w{i}"'


def many_verified(n: int) -> str:
    """A query of `n` position-verified clauses (phrases with a wildcard item), each distinct."""
    return " OR ".join(clause(i) for i in range(n))


# --- the verified-clause cap and the charge per clause ---------------------------------------------------------
@pytest.mark.parametrize(
    "q",
    ['title:"trust calibrat*"', "title:trust NEAR/3 title:trust", 'title:"trust model"',
     'title:"trust calibrat*" OR title:"trust calibrat*" OR title:"calibrat* model"',
     'NOT title:"calibrat* x" trust', "title:trust NEAR/2 title:model", "trust OR model"],
)  # fmt: skip
def test_verified_clauses_counts_what_the_compiler_verifies(client: TestClient, q: str) -> None:
    """Counted from the AST before compiling, by `verifies`'s rule: one per clause the compiler sends down
    the position-verified path (each clause here names one field, so the compiler lists it once)."""
    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    ast = parse(q).effective_ast
    assert ast is not None
    clauses = verified_clauses(ast)
    assert bool(clauses) == verifies(ast)
    assert len(clauses) == len(engine.compile(ast).verified)


def test_a_query_over_the_verified_clause_cap_is_a_located_422_before_it_compiles(store: Store) -> None:
    q = many_verified(3)
    with TestClient(make_app(store.indexes.parent, max_verified_clauses=2)) as c:
        engine = c.app.state.index.engine  # type: ignore[attr-defined]
        compile_ = engine.compile
        engine.compile = lambda *a: pytest.fail("compiled")
        try:
            e = error(c.get(SEARCH, params={"q": q}), 422, "API_TOO_MANY_VERIFIED_CLAUSES")
            error(c.post("/api/v1/records", json={"q": q}), 422, "API_TOO_MANY_VERIFIED_CLAUSES")
            r = c.get("/api/v1/export", params={"q": q, "format": "ris"})
            error(r, 422, "API_TOO_MANY_VERIFIED_CLAUSES")
        finally:
            engine.compile = compile_
        assert "3 clauses" in e["message"] and "at most 2" in e["message"]
        assert [q[d["span"][0] : d["span"][1]] for d in e["diagnostics"]] == [clause(i) for i in range(3)]
        assert c.get(SEARCH, params={"q": many_verified(2)}).status_code == 200  # at the cap: served


def test_the_default_cap_is_16_clauses() -> None:
    assert ApiConfig(data_dir=Path("x")).max_verified_clauses == 16


def test_each_verified_clause_costs_the_verified_weight(store: Store) -> None:
    limit = RateLimit(capacity=25, refill_per_second=0.001, export_weight=10, verified_weight=10)
    with TestClient(make_app(store.indexes.parent, rate_limit=limit, max_verified_clauses=2)) as c:
        assert c.get(SEARCH, params={"q": many_verified(2)}).status_code == 200  # 20 of 25
        assert c.get(SEARCH, params={"q": "trust"}).status_code == 200  # 21
        error(c.get(SEARCH, params={"q": VERIFIED}), 429, "API_RATE_LIMITED")  # 10 more: only 4 left


def test_a_cap_times_a_weight_over_the_bucket_is_refused_so_no_clause_rides_free() -> None:
    """Round 3: capping a charge at the bucket made every clause past capacity / weight free (8 cost what 6
    did). Now a configured weight × the cap must fit the smaller bucket, and the default weight is lowered to
    fit, so each clause up to the cap costs its share."""
    with pytest.raises(ValidationError, match=r"max_verified_clauses \(3\) × verified_weight \(10\)"):
        ApiConfig(
            data_dir=Path("x"),
            rate_limit=RateLimit(capacity=25, export_weight=10, verified_weight=10),
            max_verified_clauses=3,
        )
    small_network = RateLimit(capacity=100, export_weight=10, verified_weight=10, network_capacity=20)
    with pytest.raises(ValidationError, match="smaller rate-limit bucket"):
        ApiConfig(data_dir=Path("x"), rate_limit=small_network, max_verified_clauses=3)
    ApiConfig(  # off: nothing is charged, so nothing has to fit
        data_dir=Path("x"),
        rate_limit=RateLimit(enabled=False, capacity=25, export_weight=10, verified_weight=10),
        max_verified_clauses=3,
    )
    default = ApiConfig(data_dir=Path("x"))
    assert default.verified_cost == 3.75  # min(export_weight 10, 60 / 16)
    assert (default.verified_charge(12), default.verified_charge(16)) == (
        45,
        60,
    )  # 16 fits the bucket exactly
    assert default.verified_charge(16) <= default.rate_limit.smallest_capacity


def test_a_query_at_the_cap_empties_the_bucket_exactly(store: Store) -> None:
    limit = RateLimit(capacity=24, refill_per_second=0.001, export_weight=10)  # 8 per clause, cap 3
    with TestClient(make_app(store.indexes.parent, rate_limit=limit, max_verified_clauses=3)) as c:
        assert c.get(SEARCH, params={"q": many_verified(3)}).status_code == 200  # 24 of 24
        error(c.get(SEARCH, params={"q": "trust"}), 429, "API_RATE_LIMITED")  # the bucket is empty


def test_a_replay_is_charged_per_verified_clause(data_dir: Path) -> None:
    with TestClient(make_app(data_dir)) as c:
        rid = c.post("/api/v1/records", json={"q": many_verified(2)}).json()["record_id"]
    limit = RateLimit(capacity=30, refill_per_second=0.001, export_weight=10, verified_weight=10)
    with TestClient(make_app(data_dir, rate_limit=limit, max_verified_clauses=2)) as c:
        assert c.get(f"/api/v1/records/{rid}").status_code == 200  # 10 on the way in, 20 for its clauses
        error(c.get(f"/api/v1/records/{rid}/diff"), 429, "API_RATE_LIMITED")  # 10 in, then 10 more: no


# a replay over the cap: tests/contract/test_abuse_limits_r3.py (withheld, 200, never a 422)


# --- the save ceilings ---------------------------------------------------------------------------------------
def test_one_network_cannot_spend_the_instance_save_ceiling(data_dir: Path) -> None:
    app = make_app(data_dir, record_saves_network_burst=1, trusted_proxies=("10.0.0.0/8",))
    with TestClient(app, client=("10.0.0.5", 4000)) as c:

        def save(xff: str, word: str) -> Any:
            return c.post("/api/v1/records", json={"q": f"trust {word}"}, headers={"X-Forwarded-For": xff})

        assert save("203.0.113.1", "a").status_code == 201
        r = save("203.0.113.2", "b")  # the same /24
        e = error(r, 429, "API_RATE_LIMITED")
        assert int(r.headers["retry-after"]) > 0 and e["message"].startswith("Your network")
        assert save("198.51.100.1", "c").status_code == 201  # another network still saves


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def ceiling(clock: FakeClock, burst: int, network_burst: int) -> SaveCeiling:
    return SaveCeiling(
        TokenBucket(burst, 1.0, 1, clock),
        TokenBucket(network_burst, 1.0, 100, clock),
        (),
        {"instance": (burst, 3600.0), "network": (network_burst, 3600.0)},
    )


def request_from(address: str) -> Any:
    return SimpleNamespace(scope={"client": (address, 1)})


@pytest.mark.parametrize(
    ("burst", "network_burst", "scope", "levels"),
    [(1, 5, "instance", ("WARNING", "INFO")), (5, 1, "network", ("DEBUG", "DEBUG"))],
)
def test_a_save_ceiling_logs_once_when_it_throttles_and_once_when_it_recovers(
    logs: Logs, burst: int, network_burst: int, scope: str, levels: tuple[str, str]
) -> None:
    """The instance ceiling is everyone's (WARNING, then INFO); one network's throttling is DEBUG (round 3)."""
    clock = FakeClock()
    saves = ceiling(clock, burst, network_burst)
    saves.take(request_from("203.0.113.1"))
    for _ in range(3):
        with pytest.raises(ApiError):
            saves.take(request_from("203.0.113.1"))
    clock.now += 2  # refilled
    saves.take(request_from("203.0.113.1"))
    lines = [x for x in logs() if x["event"].startswith("record_saves")]
    assert [(x["event"], x["level"], x["scope"]) for x in lines] == [
        ("record_saves_throttled", levels[0], scope),
        ("record_saves_recovered", levels[1], scope),
    ]
    assert (lines[0]["burst"], lines[0]["per_hour"]) == (min(burst, network_burst), 3600.0)
    assert "203.0.113" not in json.dumps(lines)  # never the client's network


def test_a_refund_gives_the_save_back_to_both_ceilings() -> None:
    saves = ceiling(FakeClock(), 1, 1)
    network = saves.take(request_from("203.0.113.1"))
    saves.refund(network)
    saves.take(request_from("203.0.113.1"))  # both buckets had it back
    with pytest.raises(ApiError):
        saves.take(request_from("203.0.113.1"))


def test_a_save_whose_query_fails_to_run_is_refunded(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import openproceedings.engine.tantivy_engine as te

    monkeypatch.setattr(te, "MAX_EXPANSIONS", 1)  # calibrat* has 2: refused while the save runs
    with TestClient(make_app(data_dir, record_saves_burst=1)) as c:
        error(c.post("/api/v1/records", json={"q": "calibrat*"}), 422, "WILDCARD_TOO_MANY_EXPANSIONS")
        assert c.post("/api/v1/records", json={"q": "trust"}).status_code == 201  # the burst of 1 is intact


# --- trusted proxies, docs, uvicorn --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("network", "ok"),
    [("10.0.0.0/7", False), ("10.0.0.0/8", True), ("2001:db8::/31", False), ("2001:db8::/32", True),
     ("192.0.2.1", True), ("2001:db8::1", True)],
)  # fmt: skip
def test_a_trusted_proxy_wider_than_8_or_32_bits_is_refused(network: str, ok: bool) -> None:
    if ok:
        ApiConfig(data_dir=Path("x"), trusted_proxies=(network,))
    else:
        with pytest.raises(ValidationError, match="wider than"):
            ApiConfig(data_dir=Path("x"), trusted_proxies=(network,))


def test_swagger_ui_is_off_unless_configured(store: Store) -> None:
    with TestClient(make_app(store.indexes.parent)) as c:
        error(c.get("/api/v1/docs"), 404, "API_NOT_FOUND")
        assert c.get("/api/v1/openapi.json").status_code == 200  # the document itself is always served
    with TestClient(make_app(store.indexes.parent, serve_docs=True)) as c:
        assert c.get("/api/v1/docs").status_code == 200


@pytest.mark.parametrize(
    ("flags", "docs"),
    [(["--host", "127.0.0.1"], True), (["--host", "0.0.0.0"], False), (["--host", "0.0.0.0", "--docs"], True),
     (["--host", "::1", "--no-docs"], False)],
)  # fmt: skip
def test_op_serve_serves_docs_on_loopback_only_by_default(
    flags: list[str], docs: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    served: list[ApiConfig] = []
    monkeypatch.setattr(api_server, "serve", lambda config, *a: served.append(config))
    assert cli.main(["--data-dir", str(tmp_path), "serve", *flags]) == 0
    assert served[0].serve_docs is docs


def test_uvicorn_closes_idle_keep_alive_connections(tmp_path: Path) -> None:
    default = api_server.uvicorn_config(ApiConfig(data_dir=tmp_path), "127.0.0.1", 0)
    assert (default.timeout_keep_alive, default.limit_concurrency) == (5, 256)
    config = ApiConfig(data_dir=tmp_path, keep_alive_seconds=2)
    assert api_server.uvicorn_config(config, "127.0.0.1", 0).timeout_keep_alive == 2


# --- the body cap at its boundary, and the body it replays (qa-auditor round 2) --------------------------------
CAP = 64 * 1024


def through_body_limit(body: bytes, *, declared: bool) -> tuple[int, bytes]:
    """`body` sent through `BodyLimit(CAP)` to an app that reads it whole and echoes it: (status, echoed).
    By `Content-Length` (`declared`) or chunked, in two messages. Bounded in time: a middleware that loses
    the body leaves the app waiting on `receive` forever, which fails here in 5 s instead of hanging."""
    sent: list[dict[str, Any]] = []
    half = len(body) // 2
    messages = [
        {"type": "http.request", "body": body[:half], "more_body": True},
        {"type": "http.request", "body": body[half:], "more_body": False},
    ]

    async def receive() -> dict[str, Any]:
        if messages:
            return messages.pop(0)
        await anyio.sleep_forever()  # the server's next message: none until the client goes away
        raise AssertionError  # pragma: no cover

    async def app(scope: Any, receive_: Any, send: Any) -> None:
        got = b""
        while True:
            message = await receive_()
            got += message.get("body", b"")
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": got})

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    headers = [(b"content-length", str(len(body)).encode())] if declared else []
    scope = {"type": "http", "method": "POST", "headers": headers}

    async def run() -> None:
        with anyio.fail_after(5):
            await BodyLimit(app, CAP)(scope, receive, send)

    anyio.run(run)
    return int(sent[0]["status"]), b"".join(m.get("body", b"") for m in sent[1:])


@pytest.mark.parametrize("declared", [True, False], ids=["content-length", "chunked"])
@pytest.mark.parametrize(("size", "status"), [(CAP - 1, 200), (CAP, 200), (CAP + 1, 413)])
def test_the_body_cap_serves_exactly_its_size_and_refuses_one_byte_more(
    size: int, status: int, declared: bool
) -> None:
    body = bytes(range(256)) * (size // 256) + b"x" * (size % 256)
    got, echoed = through_body_limit(body, declared=declared)
    assert got == status
    if status == 200:
        assert echoed == body  # replayed to the app whole, in order
    else:
        assert b"API_BODY_TOO_LARGE" in echoed


def test_an_api_busy_refusal_comes_back_at_once_never_queued(client: TestClient) -> None:
    """While a cold verification holds the one slot, another is refused within a second, not after waiting
    for the slot (a `acquire(timeout=…)` would still answer 503, but only once the wait ran out)."""
    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    read = engine.read
    entered, release = threading.Event(), threading.Event()

    def slow(*args: Any) -> Any:
        entered.set()
        assert release.wait(20)
        return read(*args)

    engine.read = slow
    try:
        with ThreadPoolExecutor(1) as pool:
            first = pool.submit(client.get, SEARCH, params={"q": VERIFIED})
            assert entered.wait(10)
            started = time.monotonic()
            error(client.get(SEARCH, params={"q": '"calibrat* model"'}), 503, "API_BUSY")
            assert time.monotonic() - started < 1.0
            release.set()
            assert first.result(20).status_code == 200
    finally:
        release.set()
        engine.read = read
