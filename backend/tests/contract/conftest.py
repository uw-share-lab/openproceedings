"""Contract-test fixtures (spec 07; decision-004): the app in-process over the synthetic 5k fixture index.

Two indexes are built once per session into a read-only store: the 5k corpus (`big`) and its first 300
records (`small`), so a hot swap has a different index_version to move to. A test that repoints `current`
gets its own data directory holding copies of both (the store's `current` is never touched).

Probe routes stand in for the task-035 endpoints: they use exactly the shared pieces those endpoints will
(`EngineDep`, `checked_query`, `annotate_parse`, `annotate`).
"""

from __future__ import annotations

import io
import json
import shutil
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from openproceedings.api import ApiConfig, RateLimit, create_app
from openproceedings.api.deps import EngineDep, annotate, annotate_parse, checked_query
from openproceedings.api.state import Opener
from openproceedings.diagnostics import DiagnosticCode, InternalError
from openproceedings.engine.protocol import EngineInputError
from openproceedings.logs import configure_logging
from openproceedings.query.parser import parse

from tests.fixtures.corpus.synthetic_5k import records
from tests.unit.engine.test_exclusions import tantivy_of

SECRET = "zzsecretreviewdesign"  # a query word no log line may ever hold


@dataclass(frozen=True)
class Store:
    indexes: Path  # <store>/indexes, holding both built indexes
    big: str  # the 5k index's version
    small: str


@pytest.fixture(scope="session")
def store(tmp_path_factory: pytest.TempPathFactory) -> Store:
    root = tmp_path_factory.mktemp("api-store")
    corpus = list(records())
    big = tantivy_of(corpus, root / "big").index_version
    small = tantivy_of(corpus[:300], root / "small").index_version
    indexes = root / "indexes"
    indexes.mkdir()
    for name, version in (("big", big), ("small", small)):
        shutil.copytree(root / name / "indexes" / version, indexes / version)
    (indexes / "current").symlink_to(big)
    return Store(indexes, big, small)


@pytest.fixture
def data_dir(store: Store, tmp_path: Path) -> Path:
    """A private data directory: copies of both indexes, `current` → the 5k one."""
    shutil.copytree(store.indexes, tmp_path / "data" / "indexes", symlinks=True)
    return tmp_path / "data"


def point_current(data_dir: Path, version: str) -> None:
    """Repoint `current` atomically, as the deploy runbook does (a new link renamed over the old)."""
    tmp = data_dir / "indexes" / ".current.tmp"
    tmp.symlink_to(version)
    tmp.replace(data_dir / "indexes" / "current")


def add_probes(
    app: FastAPI, hold: threading.Event | None = None, entered: threading.Event | None = None
) -> None:
    """Stand-ins for the task-035 routes, built from the shared request helpers."""

    @app.get("/api/v1/_probe/search")
    def probe_search(request: Request, engine: EngineDep, q: str, limit: int = 10) -> dict[str, Any]:
        result = parse(checked_query(q))
        annotate_parse(request, result)
        if result.effective_ast is None:
            from openproceedings.api.errors import ApiError

            first = result.errors[0]
            raise ApiError(first.code, first.message, diagnostics=result.errors)
        total = len(engine.match_ids(result.effective_ast))
        annotate(request, total=total)
        return {"index_version": engine.index_version, "total": total, "limit": limit}

    @app.get("/api/v1/_probe/hold")
    def probe_hold(engine: EngineDep) -> dict[str, Any]:
        """Takes its engine, then waits: a request in flight across a swap."""
        assert hold is not None and entered is not None
        entered.set()
        hold.wait(10)
        return {"index_version": engine.index_version, "total": len(engine.ids)}

    @app.get("/api/v1/_probe/stream")
    def probe_stream(engine: EngineDep) -> StreamingResponse:
        """A streamed body (an export's shape): each chunk names the engine the generator holds."""
        assert hold is not None and entered is not None

        def chunks() -> Iterator[str]:
            yield engine.index_version + "\n"
            entered.set()
            hold.wait(10)
            yield engine.index_version + "\n"

        return StreamingResponse(chunks(), media_type="text/plain")

    @app.get("/api/v1/_probe/boom/{item}")
    def probe_boom(item: str, q: str = "") -> None:
        raise RuntimeError(f"failed on {q} {item}")  # the message quotes the query

    @app.get("/api/v1/_probe/internal")
    def probe_internal(q: str = "") -> None:
        raise InternalError(DiagnosticCode.API_INTERNAL, f"invariant broken for {q}")

    @app.get("/api/v1/_probe/too-many")
    def probe_too_many(q: str = "") -> None:
        raise EngineInputError(DiagnosticCode.WILDCARD_TOO_MANY_EXPANSIONS, f"`{q}` expands to 900 terms")


@pytest.fixture
def logs() -> Callable[[], list[dict[str, Any]]]:
    """Capture every `openproceedings` log line (DEBUG and up) as parsed JSON."""
    stream = io.StringIO()
    configure_logging("DEBUG", "json", stream=stream)

    def lines() -> list[dict[str, Any]]:
        return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]

    lines.raw = stream  # type: ignore[attr-defined]
    return lines


def config(data_dir: Path, **overrides: Any) -> ApiConfig:
    base: dict[str, Any] = {
        "data_dir": data_dir,
        "load_in_background": False,
        "handle_sighup": False,
        "rate_limit": RateLimit(capacity=10_000),  # rate-limit tests set their own
    }
    return ApiConfig(**{**base, **overrides})


def make_app(
    data_dir: Path,
    *,
    opener: Opener | None = None,
    hold: threading.Event | None = None,
    entered: threading.Event | None = None,
    **overrides: Any,
) -> FastAPI:
    app = create_app(config(data_dir, **overrides), opener=opener)
    add_probes(app, hold, entered)
    return app


@pytest.fixture
def client(store: Store) -> Iterator[TestClient]:
    """The app over the store's `current` (the 5k index), loaded before the first request."""
    with TestClient(make_app(store.indexes.parent)) as c:
        yield c
