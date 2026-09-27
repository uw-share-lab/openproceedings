"""Limits (task-034 AC3, AC6): the per-client token bucket (X-Forwarded-For believed only from a trusted
proxy; an export's weight; /healthz free), the exact CORS allowlist without credentials, and the
query-length cap enforced before any parsing."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.api import ApiConfig, RateLimit
from openproceedings.api.deps import checked_query
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import TokenBucket, client_key
from openproceedings.query import parser
from openproceedings.query.parser import MAX_QUERY_LENGTH
from pydantic import ValidationError

from tests.contract.conftest import Store, make_app

SEARCH = "/api/v1/_probe/search"


def limited(store: Store, **rate: Any) -> TestClient:
    settings = {"capacity": 2, "refill_per_second": 0.001, "export_weight": 2, **rate}
    return TestClient(
        make_app(store.indexes.parent, rate_limit=RateLimit(**settings), trusted_proxies=("10.0.0.0/8",)),
        client=("10.0.0.5", 4000),  # the peer is our proxy
    )


def statuses(c: TestClient, n: int, headers: dict[str, str] | None = None, path: str = SEARCH) -> list[int]:
    return [c.get(path, params={"q": "trust"}, headers=headers).status_code for _ in range(n)]


# --- the token bucket --------------------------------------------------------------------------------------
def test_each_forwarded_client_has_its_own_bucket_behind_a_trusted_proxy(store: Store) -> None:
    with limited(store) as c:
        assert statuses(c, 3, {"X-Forwarded-For": "203.0.113.1"}) == [200, 200, 429]
        assert statuses(c, 2, {"X-Forwarded-For": "203.0.113.2"}) == [200, 200]  # someone else


def test_forwarded_for_from_an_untrusted_peer_is_ignored(store: Store) -> None:
    app = make_app(
        store.indexes.parent,
        rate_limit=RateLimit(capacity=2, refill_per_second=0.001, export_weight=2),
        trusted_proxies=("10.0.0.0/8",),
    )
    with TestClient(app, client=("198.51.100.7", 4000)) as c:
        spoofed = [
            c.get(SEARCH, params={"q": "t"}, headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code
            for i in range(3)
        ]
    assert spoofed == [200, 200, 429]  # a fresh XFF each time buys nothing


def test_healthz_costs_nothing_and_an_export_costs_its_weight(store: Store) -> None:
    with limited(store, capacity=3, export_weight=3) as c:
        assert statuses(c, 5, path="/api/v1/healthz") == [200] * 5
        # /export is task-036; the weight is charged before routing, so its 404 still costs 3 tokens
        assert c.get("/api/v1/export").status_code == 404
        assert c.get("/api/v1/export").status_code == 429
        assert statuses(c, 1) == [429]


def test_the_rate_limit_can_be_turned_off(store: Store) -> None:
    with limited(store, enabled=False, capacity=1, export_weight=1) as c:
        assert statuses(c, 5) == [200] * 5


def scope(peer: str, *xff: str) -> dict[str, Any]:
    return {"client": (peer, 1), "headers": [(b"x-forwarded-for", v.encode()) for v in xff]}


TRUSTED = [ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("fd00::/8")]


@pytest.mark.parametrize(
    ("peer", "xff", "key"),
    [
        ("198.51.100.7", ("203.0.113.1",), "198.51.100.7"),  # untrusted peer: XFF ignored
        ("10.0.0.5", ("203.0.113.1",), "203.0.113.1"),
        (
            "10.0.0.5",
            ("1.1.1.1, 203.0.113.1",),
            "203.0.113.1",
        ),  # the right-most untrusted hop, not a forged left
        ("10.0.0.5", ("1.1.1.1, 203.0.113.1, 10.0.0.9",), "203.0.113.1"),  # through two proxies
        ("10.0.0.5", ("1.1.1.1", "203.0.113.1"), "203.0.113.1"),  # repeated headers read in order
        ("10.0.0.5", ("203.0.113.1, garbage",), "10.0.0.5"),  # a malformed hop: stop at the proxy
        ("10.0.0.5", (), "10.0.0.5"),
        ("2001:db8::1", (), "2001:db8::/64"),  # IPv6 by /64
        ("fd00::1", ("2001:db8:0:0:ffff::2",), "2001:db8::/64"),
        ("testclient", ("203.0.113.1",), "testclient"),  # not an address: never trusted
    ],
)
def test_client_key(peer: str, xff: tuple[str, ...], key: str) -> None:
    assert client_key(scope(peer, *xff), TRUSTED) == key


def test_token_bucket_refills_over_time_and_says_how_long_to_wait() -> None:
    now = [0.0]
    bucket = TokenBucket(capacity=2, refill=0.5, max_clients=10, clock=lambda: now[0])
    assert [bucket.take("a", 1), bucket.take("a", 1)] == [0, 0]
    assert bucket.take("a", 1) == pytest.approx(2.0)  # 1 token at 0.5/s
    now[0] = 2.0
    assert bucket.take("a", 1) == 0
    assert bucket.take("a", 2) == pytest.approx(4.0)
    now[0] = 100.0
    assert bucket.take("a", 2) == 0  # refilled to capacity, never beyond
    assert bucket.take("a", 1) > 0


def test_token_bucket_holds_at_most_max_clients() -> None:
    bucket = TokenBucket(capacity=1, refill=0.001, max_clients=2, clock=lambda: 0.0)
    for k in "abc":
        bucket.take(k, 1)
    assert len(bucket._buckets) == 2 and "a" not in bucket._buckets


def test_an_export_weight_above_capacity_is_refused() -> None:
    with pytest.raises(ValidationError):
        RateLimit(capacity=5, export_weight=6)


# --- CORS --------------------------------------------------------------------------------------------------
def test_cors_allows_exactly_the_configured_origins_without_credentials(store: Store) -> None:
    app = make_app(store.indexes.parent, cors_origins=("https://openproceedings.example",))
    with TestClient(app) as c:
        ok = c.get("/api/v1/healthz", headers={"Origin": "https://openproceedings.example"})
        assert ok.headers["access-control-allow-origin"] == "https://openproceedings.example"
        assert "access-control-allow-credentials" not in ok.headers
        assert "X-Total" in ok.headers["access-control-expose-headers"]
        other = c.get("/api/v1/healthz", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in other.headers
        pre = c.options(
            "/api/v1/healthz",
            headers={"Origin": "https://openproceedings.example", "Access-Control-Request-Method": "GET"},
        )
        assert pre.status_code == 200
        assert pre.headers["access-control-allow-origin"] == "https://openproceedings.example"


def test_no_origin_is_allowed_by_default(client: TestClient) -> None:
    r = client.get("/api/v1/healthz", headers={"Origin": "https://anywhere.example"})
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.org",
        "https://a.example/path",
        "a.example",
        "ftp://a.example",
        "https://a.example/",
    ],
)
def test_cors_origins_must_be_exact(origin: str, tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ApiConfig(data_dir=tmp_path, cors_origins=(origin,))


def test_trusted_proxies_must_be_addresses(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ApiConfig(data_dir=tmp_path, trusted_proxies=("proxy.local",))  # type: ignore[arg-type]
    assert ApiConfig(data_dir=tmp_path, trusted_proxies=("10.1.2.3",)).trusted_proxies  # type: ignore[arg-type]


# --- the query-length cap (spec 02 PARSE_TOO_LONG) -----------------------------------------------------------
@pytest.fixture
def no_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any lexing fail loudly: a refusal that still returns PARSE_TOO_LONG never parsed anything."""

    def refuse(q: str) -> Any:
        raise AssertionError(f"lexed a query of {len(q)} characters")

    monkeypatch.setattr(parser, "lex", refuse)


def test_a_40k_character_query_is_rejected_before_parsing(client: TestClient, no_parsing: None) -> None:
    q = "trust " * 6_667  # 40,002 characters
    r = client.get(SEARCH, params={"q": q})
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "PARSE_TOO_LONG"
    assert error["diagnostics"] == [
        {"code": "PARSE_TOO_LONG", "message": error["message"], "span": [MAX_QUERY_LENGTH, len(q)]}
    ]
    assert q[:50] not in r.text  # the refusal doesn't echo the query


def test_the_cap_is_code_points_and_exactly_the_parsers(client: TestClient) -> None:
    at_cap = "信" * MAX_QUERY_LENGTH  # 2,000 code points, 6,000 UTF-8 bytes: allowed
    assert checked_query(at_cap) == at_cap
    assert client.get(SEARCH, params={"q": at_cap}).status_code == 200
    with pytest.raises(ApiError) as e:
        checked_query(at_cap + "信")
    assert e.value.code == "PARSE_TOO_LONG" and e.value.diagnostics == parser.parse(at_cap + "信").errors
