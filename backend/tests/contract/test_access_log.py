"""The access line (task-034 AC2, AC4, AC5; logging-standards §API access line): exactly one `request` line
per request, with the standard fields and the route template; a parse's hash, term count and codes; never
the query, the canonical string, messages or spans; a parse failure never above INFO. Server loggers go
through our JSON handler; uvicorn's own access line is off; httpx is pinned to WARNING."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.api import RateLimit
from openproceedings.api.deps import MAX_LOGGED_CODES, parse_fields, token_count
from openproceedings.diagnostics import Diagnostic, DiagnosticCode
from openproceedings.logs import QUIET_LOGGERS, configure_logging
from openproceedings.query.parser import ParseResult, parse

from tests.contract.conftest import SECRET, Store, make_app

Logs = Callable[[], list[dict[str, Any]]]
FIELDS = {"request_id", "method", "route", "status", "ms", "index_version"}


def access(logs: Logs) -> list[dict[str, Any]]:
    return [line for line in logs() if line["event"] == "request"]


def test_one_access_line_per_request_whatever_the_outcome(store: Store, logs: Logs) -> None:
    app = make_app(
        store.indexes.parent, rate_limit=RateLimit(capacity=5, refill_per_second=0.001, export_weight=1)
    )
    requests = [
        ("GET", "/api/v1/_probe/search?q=trust", 200),
        ("GET", "/api/v1/_probe/search?q=(trust", 422),
        ("GET", "/api/v1/nope", 404),
        ("POST", "/api/v1/healthz", 405),  # /healthz costs no token, whatever the method
        ("GET", "/api/v1/_probe/boom/x", 500),
        ("GET", "/api/v1/_probe/search", 422),
        ("GET", "/api/v1/_probe/search?q=trust", 429),  # the 6th paid request: the bucket held 5
        ("GET", "/api/v1/healthz", 200),  # free, and logged at DEBUG
    ]
    with TestClient(app) as c:
        for method, url, status in requests:
            assert c.request(method, url).status_code == status
    lines = access(logs)
    assert [line["status"] for line in lines] == [s for _m, _u, s in requests]
    assert len({line["request_id"] for line in lines}) == len(requests)
    for line in lines:
        assert set(line) >= FIELDS
        assert isinstance(line["ms"], int | float)
        assert line["level"] == ("DEBUG" if line["route"] == "/api/v1/healthz" else "INFO")


def test_the_access_line_names_the_route_template_not_the_path(client: TestClient, logs: Logs) -> None:
    client.get(f"/api/v1/_probe/boom/{SECRET}")
    client.get("/api/v1/_probe/search", params={"q": "trust"})
    lines = access(logs)
    assert [line["route"] for line in lines] == ["/api/v1/_probe/boom/{item}", "/api/v1/_probe/search"]


def test_a_search_line_has_the_hash_count_and_total_and_no_query_text(
    client: TestClient, store: Store, logs: Logs
) -> None:
    q = f"trust AND ({SECRET} OR reliance*)"
    r = client.get("/api/v1/_probe/search", params={"q": q})
    assert r.status_code == 200
    (line,) = access(logs)
    result = parse(q)
    assert line["canonical_hash"] == result.canonical_hash
    assert line["token_count"] == 3
    assert line["total"] == r.json()["total"]
    assert line["index_version"] == store.big
    assert line["n_errors"] == 0 and line["error_codes"] == []
    for forbidden in ("q", "query", "input", "canonical", "identification_query", "diagnostics", "span"):
        assert forbidden not in line


def test_a_parse_failure_logs_codes_only_and_nothing_above_info(client: TestClient, logs: Logs) -> None:
    client.get("/api/v1/_probe/search", params={"q": f'"{SECRET} (trust'})
    (line,) = access(logs)
    assert line["status"] == 422 and line["n_errors"] >= 1
    assert "PARSE_UNTERMINATED_PHRASE" in line["error_codes"]
    assert "canonical_hash" not in line  # a query that doesn't parse has none
    assert all(entry["level"] in {"DEBUG", "INFO"} for entry in logs())


def test_no_query_text_reaches_any_log_line(store: Store, logs: Logs) -> None:
    """The query word appears in a good query, a parse error, a path segment, a 500's exception message, a
    bad parameter value and an over-long query: no captured line holds it, in any field."""
    with TestClient(make_app(store.indexes.parent)) as c:
        c.get("/api/v1/_probe/search", params={"q": f"trust {SECRET}"})
        c.get("/api/v1/_probe/search", params={"q": f"({SECRET}"})
        c.get("/api/v1/_probe/search", params={"q": "trust", "limit": SECRET})
        c.get(f"/api/v1/_probe/boom/{SECRET}", params={"q": SECRET})
        c.get("/api/v1/_probe/internal", params={"q": SECRET})
        c.get("/api/v1/_probe/too-many", params={"q": SECRET})
        c.get("/api/v1/_probe/search", params={"q": SECRET * 2_000})
    raw = logs.raw.getvalue()  # type: ignore[attr-defined]
    assert len(access(logs)) == 7
    assert SECRET not in raw
    assert "failed on" not in raw and "invariant broken" not in raw  # exception messages are never logged


def test_parse_fields_cap_the_codes_listed() -> None:
    codes = [c for c in DiagnosticCode if c.startswith(("PARSE_", "FIELD_"))][: MAX_LOGGED_CODES + 3]
    errors = [Diagnostic(code=c, message="m", span=(i, i + 1)) for i, c in enumerate(codes)]
    fields = parse_fields(ParseResult(ast=None, warnings=[], errors=errors))
    assert fields["n_errors"] == len(codes)
    assert len(fields["error_codes"]) == MAX_LOGGED_CODES + 1  # type: ignore[arg-type]
    assert fields["error_codes"][-1] == "+3"  # type: ignore[index]
    assert "canonical_hash" not in fields and fields["token_count"] == 0


@pytest.mark.parametrize(
    ("q", "n"),
    [('"large language model" NEAR/3 trust*', 4), ("NOT bias AND venue:ICLR", 1), ("a OR b OR c", 3)],
)
def test_token_count_counts_search_terms(q: str, n: int) -> None:
    assert token_count(parse(q).ast) == n


@pytest.fixture
def routed() -> Iterator[io.StringIO]:
    """Our JSON handler with the server loggers routed (what `op serve` sets up); undone afterwards."""
    names = ("uvicorn", "uvicorn.error", "uvicorn.access", *QUIET_LOGGERS)
    saved = {n: (logging.getLogger(n).handlers[:], logging.getLogger(n).level, logging.getLogger(n).propagate,
                 logging.getLogger(n).disabled) for n in names}  # fmt: skip
    stream = io.StringIO()
    configure_logging("INFO", "json", stream=stream, route_server_loggers=True)
    yield stream
    for n, (handlers, level, propagate, disabled) in saved.items():
        lg = logging.getLogger(n)
        lg.handlers[:] = handlers
        lg.setLevel(level)
        lg.propagate, lg.disabled = propagate, disabled


def test_server_loggers_go_through_the_json_handler(routed: io.StringIO) -> None:
    logging.getLogger("uvicorn.error").info("Started server process [%d]", 42)
    logging.getLogger("uvicorn.access").info('127.0.0.1 - "GET /api/v1/search?q=%s HTTP/1.1" 200', SECRET)
    logging.getLogger("httpx").info("HTTP Request: GET http://x/?q=%s", SECRET)
    logging.getLogger("httpx2").info("HTTP Request: GET http://x/?q=%s", SECRET)
    logging.getLogger("httpx").warning("httpx_warned")
    lines = [json.loads(line) for line in routed.getvalue().splitlines()]
    assert [(line["logger"], line["event"]) for line in lines] == [
        ("uvicorn.error", "Started server process [42]"),
        ("httpx", "httpx_warned"),
    ]
    assert SECRET not in routed.getvalue()
    for name in QUIET_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING


def test_real_requests_through_the_routed_loggers_give_one_line_each(
    store: Store, routed: io.StringIO, tmp_path: Path
) -> None:
    with TestClient(make_app(store.indexes.parent)) as c:
        for _ in range(3):
            c.get("/api/v1/_probe/search", params={"q": SECRET})
    lines = [json.loads(line) for line in routed.getvalue().splitlines()]
    assert [line["event"] for line in lines if line["event"] == "request"] == ["request"] * 3
    assert not [line for line in lines if line["logger"].startswith(("uvicorn.access", "httpx"))]
    assert SECRET not in routed.getvalue()
