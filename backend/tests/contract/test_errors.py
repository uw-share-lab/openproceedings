"""The one error envelope (spec 04 §Error handling): every refusal is `{"error": {code, message,
diagnostics?}}` with the registry's status, and FastAPI's `{"detail": …}` never leaks."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.api import RateLimit
from openproceedings.diagnostics import DiagnosticCode, http_status

from tests.contract.conftest import SECRET, Store, make_app


def envelope(r: Any, code: str) -> dict[str, Any]:
    """Assert `r` is the envelope for `code` at the registry's status; return its error body."""
    body = r.json()
    assert set(body) == {"error"}, body
    assert "detail" not in r.text
    error = body["error"]
    assert error["code"] == code
    assert set(error) <= {"code", "message", "diagnostics"}
    assert isinstance(error["message"], str) and error["message"].strip()
    assert r.status_code == http_status(DiagnosticCode(code))
    assert r.headers["content-type"] == "application/json"
    return dict(error)


def test_404_unknown_route(client: TestClient) -> None:
    envelope(client.get("/api/v1/nope"), "API_NOT_FOUND")
    envelope(client.get("/"), "API_NOT_FOUND")  # nothing is served outside /api/v1


def test_405_wrong_method_names_the_allowed_one(client: TestClient) -> None:
    r = client.post("/api/v1/healthz")
    envelope(r, "API_METHOD_NOT_ALLOWED")
    assert set(r.headers["allow"].split(", ")) == {"GET", "HEAD"}


def test_healthz_answers_head_for_uptime_monitors(client: TestClient) -> None:
    r = client.head("/api/v1/healthz")
    assert r.status_code == 200 and r.content == b""


@pytest.mark.parametrize("status", [400, 413, 418])
def test_any_other_4xx_is_the_clients_not_a_500(
    client: TestClient, status: int, logs: Callable[[], list[dict[str, Any]]]
) -> None:
    envelope(client.get(f"/api/v1/_probe/http/{status}"), "API_BAD_PARAM")
    assert not [line for line in logs() if line["level"] == "ERROR"]


@pytest.mark.parametrize(
    "params",
    [
        {},  # `q` missing
        {"q": "trust", "limit": "many"},  # not an int
    ],
)
def test_422_bad_parameter_is_api_bad_param_not_detail(client: TestClient, params: dict[str, str]) -> None:
    error = envelope(client.get("/api/v1/search", params=params), "API_BAD_PARAM")
    assert "diagnostics" not in error
    assert "query." in error["message"]  # names the location


def test_422_bad_parameter_message_does_not_echo_the_value(client: TestClient) -> None:
    error = envelope(client.get("/api/v1/search", params={"q": "x", "limit": SECRET}), "API_BAD_PARAM")
    assert SECRET not in error["message"]


def test_422_parse_error_carries_diagnostics_with_spans(client: TestClient) -> None:
    error = envelope(client.get("/api/v1/search", params={"q": "(trust"}), "PARSE_UNBALANCED_PAREN")
    assert error["diagnostics"][0]["code"] == "PARSE_UNBALANCED_PAREN"
    assert error["diagnostics"][0]["span"] == [0, 1]


def test_422_an_engine_refusal_keeps_its_own_code(client: TestClient) -> None:
    error = envelope(
        client.get("/api/v1/_probe/too-many", params={"q": "re*"}), "WILDCARD_TOO_MANY_EXPANSIONS"
    )
    # spec 04 row 1: a PARSE_/FIELD_/WILDCARD_ refusal carries diagnostics (no span when none is known)
    assert error["diagnostics"] == [
        {"code": "WILDCARD_TOO_MANY_EXPANSIONS", "message": error["message"], "span": None, "reading": None}
    ]


def test_a_500_carries_the_cors_headers(store: Store) -> None:
    app = make_app(store.indexes.parent, cors_origins=("https://openproceedings.example",))
    with TestClient(app) as c:
        r = c.get("/api/v1/_probe/boom/x", headers={"Origin": "https://openproceedings.example"})
    envelope(r, "API_INTERNAL")
    assert r.headers["access-control-allow-origin"] == "https://openproceedings.example"


def test_a_disallowed_cors_preflight_is_a_plain_400_and_is_logged(
    store: Store, logs: Callable[[], list[dict[str, Any]]]
) -> None:
    """Starlette's CORS middleware answers it before our routes (spec 04 as built): plain text, not the
    envelope; the access line still records it."""
    app = make_app(store.indexes.parent, cors_origins=("https://openproceedings.example",))
    with TestClient(app) as c:
        r = c.options(
            "/api/v1/search",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
        )
    assert r.status_code == 400 and r.headers["content-type"].startswith("text/plain")
    assert "access-control-allow-origin" not in r.headers
    (line,) = [entry for entry in logs() if entry["event"] == "request"]
    assert (line["method"], line["status"]) == ("OPTIONS", 400)


def test_429_rate_limited_with_retry_after(store: Store) -> None:
    app = make_app(
        store.indexes.parent, rate_limit=RateLimit(capacity=1, refill_per_second=0.1, export_weight=1)
    )
    with TestClient(app) as c:
        assert c.get("/api/v1/search", params={"q": "trust"}).status_code == 200
        r = c.get("/api/v1/search", params={"q": "trust"})
        envelope(r, "API_RATE_LIMITED")
        assert r.headers["retry-after"] == "10"


def test_503_no_index_loaded(tmp_path: Path) -> None:
    (tmp_path / "indexes").mkdir()
    with TestClient(make_app(tmp_path)) as c:
        envelope(c.get("/api/v1/search", params={"q": "trust"}), "API_INDEX_NOT_LOADED")


@pytest.mark.parametrize("path", ["/api/v1/_probe/boom/item-1", "/api/v1/_probe/internal"])
def test_500_is_api_internal_names_the_request_and_never_echoes_input(
    store: Store, path: str, logs: Callable[[], list[dict[str, Any]]]
) -> None:
    with TestClient(make_app(store.indexes.parent), raise_server_exceptions=False) as c:
        r = c.get(path, params={"q": SECRET})
    error = envelope(r, "API_INTERNAL")
    assert SECRET not in r.text
    failed = [line for line in logs() if line["event"] == "request_failed"]
    assert len(failed) == 1 and failed[0]["level"] == "ERROR"
    assert failed[0]["request_id"] in error["message"]  # a report can be matched to the log line
    assert failed[0]["error"] in {"RuntimeError", "InternalError"}
    assert any("probe_" in frame for frame in failed[0]["frames"])  # where, not what


def test_a_typed_failure_mid_stream_logs_where_it_happened(
    store: Store, logs: Callable[[], list[dict[str, Any]]]
) -> None:
    """Starlette wraps an OpenProceedingsError its handler catches after the response started in a
    RuntimeError whose frames stop at the handler; the line carries the cause's frames (M3a review)."""
    from collections.abc import Iterator

    from fastapi.responses import StreamingResponse
    from openproceedings.engine.protocol import EngineInternalError

    app = make_app(store.indexes.parent)

    @app.get("/api/v1/_probe/typed-stream-fail")
    def probe_typed_stream_fail() -> StreamingResponse:
        def failing_generator() -> Iterator[str]:
            yield "first\n"
            raise EngineInternalError(DiagnosticCode.API_INTERNAL, f"broke on {SECRET}")

        return StreamingResponse(failing_generator(), media_type="text/plain")

    with TestClient(app) as c:
        assert c.get("/api/v1/_probe/typed-stream-fail").status_code == 200  # it had started
    (failed,) = [line for line in logs() if line["event"] == "request_failed"]
    assert (failed["error"], failed["cause"]) == ("RuntimeError", "EngineInternalError")
    assert not any("failing_generator" in f for f in failed["frames"])  # the wrapper's frames stop short
    assert any("failing_generator" in f for f in failed["cause_frames"])  # the cause's say where
    assert SECRET not in str(logs())


def test_500_does_not_reach_the_test_client_as_an_exception(store: Store) -> None:
    # the access middleware is the last catch: nothing is re-raised for the server to log with a traceback
    with TestClient(make_app(store.indexes.parent)) as c:  # raise_server_exceptions defaults to True
        envelope(c.get("/api/v1/_probe/boom/x"), "API_INTERNAL")
