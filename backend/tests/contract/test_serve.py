"""`op serve` (spec 08 §CLI): its flags become the ApiConfig, and the real server (uvicorn over loopback, in
this process) writes exactly one access line per request, through our JSON handler, with uvicorn's own
access line off, and lets a valid 2,000-code-point query and an over-long one reach the app."""

from __future__ import annotations

import http.client
import io
import json
import logging
import threading
import time
import urllib.parse
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from openproceedings import cli
from openproceedings.api import ApiConfig
from openproceedings.api import server as api_server
from openproceedings.logs import QUIET_LOGGERS

from tests.contract.conftest import SECRET, Store, add_probes


def test_op_serve_builds_its_config_from_flags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def fake(config: ApiConfig, host: str, port: int, log_level: str, log_format: str) -> None:
        seen.update(config=config, host=host, port=port, log_level=log_level, log_format=log_format)

    monkeypatch.setattr(api_server, "serve", fake)
    argv = ["--data-dir", str(tmp_path), "--log-level", "debug", "serve", "--port", "9001", "--index", "abc123",
            "--cors-origin", "https://a.example", "--cors-origin", "http://localhost:3000",
            "--trusted-proxy", "10.0.0.0/8", "--rate-capacity", "30", "--rate-refill", "0.5",
            "--export-weight", "5"]  # fmt: skip
    assert cli.main(argv) == 0
    config: ApiConfig = seen["config"]
    assert (seen["host"], seen["port"], seen["log_level"]) == ("127.0.0.1", 9001, "DEBUG")
    assert config.data_dir == tmp_path and config.index == "abc123"
    assert config.cors_origins == ("https://a.example", "http://localhost:3000")
    assert [str(n) for n in config.trusted_proxies] == ["10.0.0.0/8"]
    assert (
        config.rate_limit.capacity,
        config.rate_limit.refill_per_second,
        config.rate_limit.export_weight,
    ) == (
        30,
        0.5,
        5,
    )
    assert config.log_query_text is False and config.load_in_background and config.handle_sighup


@pytest.mark.parametrize(
    "flags", [["--cors-origin", "*"], ["--index", "../elsewhere"], ["--trusted-proxy", "proxy.local"]]
)
def test_op_serve_refuses_bad_flags_as_usage(
    flags: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(api_server, "serve", lambda *a: pytest.fail("served with bad flags"))
    assert cli.main(["--data-dir", str(tmp_path), "serve", *flags]) == 1
    assert "invalid serve options" in capsys.readouterr().err


@pytest.fixture
def running(store: Store) -> Iterator[tuple[int, io.StringIO]]:
    """uvicorn serving the app on an ephemeral loopback port, configured as `serve` configures it."""
    names = ("uvicorn", "uvicorn.error", "uvicorn.access", *QUIET_LOGGERS)
    saved = {n: (logging.getLogger(n).handlers[:], logging.getLogger(n).level, logging.getLogger(n).propagate,
                 logging.getLogger(n).disabled) for n in names}  # fmt: skip
    stream = io.StringIO()
    api_server.configure_logging("DEBUG", "json", stream=stream, route_server_loggers=True)
    config = ApiConfig(data_dir=store.indexes.parent, load_in_background=False)
    uv = api_server.uvicorn_config(config, "127.0.0.1", 0)
    add_probes(uv.app)  # type: ignore[arg-type]
    server = uvicorn.Server(uv)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        assert time.monotonic() < deadline and thread.is_alive(), "server did not start"
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield port, stream
    finally:
        server.should_exit = True
        thread.join(10)
        for n, (handlers, level, propagate, disabled) in saved.items():
            lg = logging.getLogger(n)
            lg.handlers[:] = handlers
            lg.setLevel(level)
            lg.propagate, lg.disabled = propagate, disabled


def get(port: int, path: str) -> tuple[int, dict[str, Any]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", path)
        r = conn.getresponse()
        return r.status, json.loads(r.read() or b"{}")
    finally:
        conn.close()


def test_the_real_server_logs_one_access_line_per_request_and_nothing_else_of_uvicorns(
    running: tuple[int, io.StringIO], store: Store
) -> None:
    port, stream = running
    q = urllib.parse.quote
    assert get(port, "/api/v1/healthz")[1]["index_loaded"] is True
    status, body = get(port, f"/api/v1/_probe/search?q={q('trust ' + SECRET)}")
    assert status == 200 and body["index_version"] == store.big
    status, body = get(
        port, f"/api/v1/_probe/search?q={q('信' * 2_000)}"
    )  # 18 KB of URL: over uvicorn's default
    assert status == 200
    status, body = get(port, f"/api/v1/_probe/search?q={q(SECRET * 2_000)}")  # 40k characters
    assert status == 422 and body["error"]["code"] == "PARSE_TOO_LONG"
    status, body = get(port, "/api/v1/nope")
    assert status == 404 and body["error"]["code"] == "API_NOT_FOUND"
    time.sleep(0.1)  # the last access line is written after the response is sent
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    requests = [line for line in lines if line["event"] == "request"]
    assert [r["status"] for r in requests] == [200, 200, 200, 422, 404]
    assert not [line for line in lines if line["logger"] == "uvicorn.access"]
    assert any(line["logger"].startswith("uvicorn") for line in lines)  # uvicorn's own lines, as JSON
    assert SECRET not in stream.getvalue()
