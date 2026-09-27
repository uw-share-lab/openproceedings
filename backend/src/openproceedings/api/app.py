"""The app factory (fastapi-conventions §App shape): `create_app(config) -> FastAPI`.

Layers, outermost first: `AccessLog` (request id, the one access line, the last catch for a failure) →
CORS (exact allowlist, no credentials) → `RateLimit` (per-client token bucket) → FastAPI (the error
envelope handlers, then the `/api/v1` routers). Nothing is served outside `/api/v1`, the OpenAPI document
included.

The lifespan loads the index (in the background by default, so `/healthz` answers meanwhile) and, on the
main thread, installs the SIGHUP reload. Logging is configured by the entry point (`op serve`,
`api/server.py`), never here.

A new resource (task-035 on) adds its `APIRouter` to `ROUTERS`; its handlers are `def` and take the engine
through `deps.EngineDep`.
"""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from openproceedings import __version__
from openproceedings.api import health
from openproceedings.api.config import ApiConfig
from openproceedings.api.errors import install_error_handlers
from openproceedings.api.middleware import API_PREFIX, AccessLog, RateLimit
from openproceedings.api.state import IndexState, Opener, install_sighup

ROUTERS: tuple[APIRouter, ...] = (health.router,)
EXPOSED_HEADERS = ("X-Total", "X-Index-Version", "Retry-After")  # spec 04 §Exports, §Error handling


def create_app(config: ApiConfig, *, opener: Opener | None = None) -> FastAPI:
    """The API over `config.index`. `opener` builds an engine from an index directory (default
    `TantivyEngine`; tests wrap it)."""
    if opener is None:
        from openproceedings.engine.tantivy_engine import TantivyEngine

        opener = TantivyEngine
    state = IndexState(config.data_dir, config.index, opener)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        restore = None
        if config.handle_sighup and threading.current_thread() is threading.main_thread():
            restore = install_sighup(state)
        if config.load_in_background:
            state.load_in_background()
        else:
            await anyio.to_thread.run_sync(state.load)
        try:
            yield
        finally:
            if restore is not None:
                restore()

    app = FastAPI(
        title="openproceedings",
        version=__version__,
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
    )
    app.state.index = state
    app.state.config = config
    install_error_handlers(app)
    v1 = APIRouter(prefix=API_PREFIX)
    for router in ROUTERS:
        v1.include_router(router)
    app.include_router(v1)
    # added innermost first: the last one added wraps everything
    app.add_middleware(RateLimit, config=config.rate_limit, trusted=config.trusted_proxies)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=list(EXPOSED_HEADERS),
    )
    app.add_middleware(AccessLog)
    return app
