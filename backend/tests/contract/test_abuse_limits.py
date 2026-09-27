"""What one client can make the service spend (M3a security review; spec 04 §Error handling, §Rate limit):
a body cap before anything reads the body (task-079), a position-verified query charged its weight and
refused rather than queued when verification is saturated, a per-network bucket beside the per-client one,
an instance-wide ceiling on record saves, and `op serve`'s refusal of settings that switch the limits off
for everyone."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient
from openproceedings import cli
from openproceedings.api import RateLimit
from openproceedings.api import server as api_server
from openproceedings.api.config import ApiConfig
from openproceedings.api.middleware import BodyLimit, network_key
from openproceedings.engine.compile import verifies
from openproceedings.query.parser import MAX_QUERY_LENGTH, parse
from pydantic import ValidationError

from tests.contract.conftest import Store, make_app

SEARCH = "/api/v1/search"
VERIFIED = '"trust calibrat*"'  # a phrase with a wildcard item: position-verified (spec 03)
Logs = Callable[[], list[dict[str, Any]]]


def error(r: Any, status: int, code: str) -> dict[str, Any]:
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"} and body["error"]["code"] == code, body
    return dict(body["error"])


# --- the body cap (task-079) -------------------------------------------------------------------------------------
def test_a_body_over_the_cap_is_413_by_its_content_length(client: TestClient, logs: Logs) -> None:
    body = json.dumps({"q": "trust " * 20_000})  # 120 KB
    error(client.post("/api/v1/parse", content=body, headers={"Content-Type": "application/json"}), 413,
          "API_BODY_TOO_LARGE")  # fmt: skip
    (line,) = [x for x in logs() if x["event"] == "request"]
    assert line["status"] == 413


def test_a_chunked_body_over_the_cap_is_413_once_the_bytes_pass_it(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:  # no Content-Length: httpx sends it chunked
        yield b'{"q": "'
        for _ in range(100):
            yield b"trust " * 200  # 1.2 KB each, 120 KB in all
        yield b'"}'

    r = client.post("/api/v1/records", content=chunks(), headers={"Content-Type": "application/json"})
    error(r, 413, "API_BODY_TOO_LARGE")


def test_the_cap_comes_before_anything_else_an_unloaded_index_included(tmp_path: Path) -> None:
    (tmp_path / "indexes").mkdir()
    with TestClient(make_app(tmp_path)) as c:
        error(c.post("/api/v1/parse", content=b"x" * 70_000), 413, "API_BODY_TOO_LARGE")
        error(c.post("/api/v1/parse", json={"q": "trust"}), 503, "API_INDEX_NOT_LOADED")  # within the cap


def test_the_longest_valid_query_fits_under_the_cap(client: TestClient) -> None:
    """2,000 astral code points as JSON escapes (12 bytes each: a surrogate pair) is ~24 KB."""
    body = json.dumps({"q": "𝔸" * MAX_QUERY_LENGTH}, ensure_ascii=True).encode()
    assert 24_000 < len(body) < ApiConfig(data_dir=Path("x")).max_body_bytes
    r = client.post("/api/v1/parse", content=body, headers={"Content-Type": "application/json"})
    assert (
        r.status_code == 200
    )  # admitted and parsed (its canonical form may then be over the cap: decision-008)


def test_a_declared_length_over_the_cap_is_refused_without_reading_a_byte() -> None:
    sent: list[dict[str, Any]] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        raise AssertionError("the app ran")

    async def receive() -> dict[str, Any]:
        raise AssertionError("the body was read")

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "headers": [(b"content-length", b"300000000")]}
    anyio.run(BodyLimit(app, 64 * 1024), scope, receive, send)
    assert sent[0]["status"] == 413 and b"API_BODY_TOO_LARGE" in sent[1]["body"]


# --- a position-verified query ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "q",
    [VERIFIED, "trust NEAR/3 trust", '"trust model"', "trust NEAR/2 model", 'NOT "calibrat* x" trust',
     'trust NEAR/2 "a b"', "trust OR model"],
)  # fmt: skip
def test_verifies_is_what_the_compiler_does(client: TestClient, q: str) -> None:
    """The charge is decided from the AST before compiling; it must match the compiler's own path."""
    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    ast = parse(q).effective_ast
    assert ast is not None
    assert verifies(ast) == bool(engine.compile(ast).verified)


def test_a_verified_query_costs_the_verified_weight(store: Store) -> None:
    # the per-clause admission charge alone: slot time is all but free here (its debit: test_abuse_limits_r4)
    limit = RateLimit(
        capacity=12, refill_per_second=0.001, export_weight=10, verified_weight=10, verify_token_ms=1e9
    )
    with TestClient(make_app(store.indexes.parent, rate_limit=limit, max_verified_clauses=1)) as c:
        assert c.get(SEARCH, params={"q": VERIFIED}).status_code == 200  # 10 of 12
        r = c.get(SEARCH, params={"q": '"calibrat* model"'})  # 1 taken on the way in, then 9 more: no
        error(r, 429, "API_RATE_LIMITED")
        assert int(r.headers["retry-after"]) > 0
        assert c.get(SEARCH, params={"q": "trust"}).status_code == 200  # a plain query still costs 1


def test_a_second_cold_verification_is_refused_not_queued(client: TestClient) -> None:
    """One verification slot (the default): while one cold verification runs, another is 503 `API_BUSY`
    with `Retry-After` at once; a query that needs none, or whose clause is cached, is served."""
    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    read = engine.read
    entered, release = threading.Event(), threading.Event()

    def slow(*args: Any) -> Any:
        entered.set()
        assert release.wait(10)
        return read(*args)

    engine.read = slow
    try:
        with ThreadPoolExecutor(1) as pool:
            first = pool.submit(client.get, SEARCH, params={"q": VERIFIED})
            assert entered.wait(10)
            busy = client.get(SEARCH, params={"q": '"calibrat* model"'})
            e = error(busy, 503, "API_BUSY")
            assert busy.headers["retry-after"] == "5" and "5 s" in e["message"]
            assert client.get(SEARCH, params={"q": "trust"}).status_code == 200  # no verification
            release.set()
            assert first.result(10).status_code == 200
    finally:
        engine.read = read
    assert client.get(SEARCH, params={"q": VERIFIED}).status_code == 200  # cached now: no slot needed


def test_a_verified_weight_that_could_never_be_paid_is_refused() -> None:
    with pytest.raises(ValidationError):
        RateLimit(capacity=5, export_weight=5, verified_weight=6)


# --- the network bucket ----------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("client_key", "network"),
    [
        ("203.0.113.7", "203.0.113.0/24"),
        ("2001:db8:1:2::/64", "2001:db8:1::/48"),
        ("testclient", "testclient"),  # not an address: its own network
    ],
)
def test_network_key(client_key: str, network: str) -> None:
    assert network_key(client_key) == network


def test_many_addresses_of_one_network_share_its_bucket(store: Store) -> None:
    limit = RateLimit(capacity=2, refill_per_second=0.001, export_weight=2, network_capacity=3)
    app = make_app(store.indexes.parent, rate_limit=limit, trusted_proxies=("10.0.0.0/8",))
    with TestClient(app, client=("10.0.0.5", 4000)) as c:

        def get(xff: str) -> int:
            return c.get(SEARCH, params={"q": "trust"}, headers={"X-Forwarded-For": xff}).status_code

        assert [get("203.0.113.1"), get("203.0.113.1")] == [200, 200]
        assert [get("203.0.113.2"), get("203.0.113.3")] == [200, 429]  # the /24 held 3
        assert get("198.51.100.1") == 200  # another network
        # a refusal by one bucket spends nothing from the other: .2 still holds a client token
        assert get("198.51.100.1") == 200 and get("198.51.100.2") == 200


# --- the record-save ceiling -------------------------------------------------------------------------------------
def test_record_saves_are_held_to_an_instance_wide_ceiling(data_dir: Path) -> None:
    app = make_app(data_dir, record_saves_burst=2, record_saves_per_hour=1)
    with TestClient(app) as c:
        assert [c.post("/api/v1/records", json={"q": f"trust {w}"}).status_code for w in "ab"] == [201, 201]
        r = c.post("/api/v1/records", json={"q": "trust c"})
        e = error(r, 429, "API_RATE_LIMITED")
        assert int(r.headers["retry-after"]) > 0 and "saving search records" in e["message"]
        # a query that doesn't parse costs no save
        error(c.post("/api/v1/records", json={"q": "(trust"}), 422, "PARSE_UNBALANCED_PAREN")


# --- op serve ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("flags", "says"),
    [
        (["--trusted-proxy", "0.0.0.0/0"], "invalid serve options"),
        (["--trusted-proxy", "::/0"], "invalid serve options"),
        (["--no-rate-limit", "--host", "0.0.0.0"], "--no-rate-limit is for a local instance only"),
        (["--no-rate-limit", "--host", "example.org"], "--no-rate-limit is for a local instance only"),
    ],
)
def test_op_serve_refuses_settings_that_open_the_limits_to_everyone(
    flags: list[str],
    says: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(api_server, "serve", lambda *a: pytest.fail("served"))
    assert cli.main(["--data-dir", str(tmp_path), "serve", *flags]) == 1
    assert says in capsys.readouterr().err


def test_op_serve_allows_no_rate_limit_on_loopback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    served: list[ApiConfig] = []
    monkeypatch.setattr(api_server, "serve", lambda config, *a: served.append(config))
    for host in ("127.0.0.1", "::1", "localhost"):
        assert cli.main(["--data-dir", str(tmp_path), "serve", "--no-rate-limit", "--host", host]) == 0
    assert [c.rate_limit.enabled for c in served] == [False] * 3


def test_uvicorn_bounds_its_concurrency(tmp_path: Path) -> None:
    config = ApiConfig(data_dir=tmp_path, limit_concurrency=7)
    assert api_server.uvicorn_config(config, "127.0.0.1", 0).limit_concurrency == 7
