"""`op serve`: the API under uvicorn, one process (the index lives in its memory; SIGHUP swaps it).

uvicorn is told not to configure logging (`log_config=None`) nor to write its own access line
(`access_log=False`); `configure_logging(route_server_loggers=True)` sends its loggers through our JSON
handler. `proxy_headers=False`: the client address for the rate limit comes from `X-Forwarded-For` only
through `ApiConfig.trusted_proxies` (api/middleware.py), never uvicorn's own allowlist.
"""

from __future__ import annotations

import uvicorn

from openproceedings.api.app import create_app
from openproceedings.api.config import ApiConfig
from openproceedings.logs import configure_logging

# The largest request head h11 buffers (request line + headers). uvicorn's default, 16 KiB, would refuse a
# valid 2,000-code-point query (up to 4 UTF-8 bytes each, 3 URL-encoded characters per byte: 24 KB) with a
# bare 400 before the app could answer; 64 KiB lets it through, and an over-long `q` reaches the app, whose
# PARSE_TOO_LONG check is a length comparison.
MAX_REQUEST_HEAD = 64 * 1024


def uvicorn_config(config: ApiConfig, host: str, port: int) -> uvicorn.Config:
    return uvicorn.Config(
        create_app(config),
        host=host,
        port=port,
        workers=1,
        log_config=None,
        access_log=False,
        proxy_headers=False,
        server_header=False,
        date_header=True,
        h11_max_incomplete_event_size=MAX_REQUEST_HEAD,
        # connections and tasks beyond this get uvicorn's own 503 before the app: a bound on what one
        # process holds open (header and body timeouts are the reverse proxy's job; spec 08 §Deploy)
        limit_concurrency=config.limit_concurrency,
        # an idle keep-alive connection is closed after this, so it doesn't hold a concurrency slot
        timeout_keep_alive=config.keep_alive_seconds,
        http="h11",
        lifespan="on",
    )


def serve(config: ApiConfig, host: str, port: int, log_level: str = "INFO", log_format: str = "json") -> None:
    configure_logging(log_level, log_format, log_query_text=config.log_query_text, route_server_loggers=True)
    uvicorn.Server(uvicorn_config(config, host, port)).run()
