"""Contract-test fixtures (spec 07; decision-004): the app in-process over the synthetic 5k fixture index.

Two indexes are built once per session into a read-only store: the 5k corpus (`big`) and its first 300
records (`small`), so a hot swap has a different index_version to move to. A test that repoints `current`
gets its own data directory holding copies of both (the store's `current` is never touched).

The real routes (task-035) are exercised as they are. Probe routes remain only for what no real route can
be made to do on demand: hold a request or a stream across a swap, and fail in each way a handler can.
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
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from openproceedings.api import ApiConfig, RateLimit, create_app
from openproceedings.api.deps import EngineDep
from openproceedings.api.state import Opener
from openproceedings.diagnostics import DiagnosticCode, InternalError
from openproceedings.engine.index import build_index
from openproceedings.engine.protocol import EngineInputError
from openproceedings.ingest.dedup import DedupResult
from openproceedings.ingest.record import Claim, PaperRecord, Urls
from openproceedings.ingest.snapshot import render
from openproceedings.logs import configure_logging

from tests.corpus import Rec
from tests.fixtures.corpus.synthetic_5k import records
from tests.golden.test_tantivy_200 import as_paper
from tests.unit.engine.test_exclusions import BUILT

SECRET = "zzsecretreviewdesign"  # a query word no log line may ever hold


@dataclass(frozen=True)
class Store:
    indexes: Path  # <store>/indexes, holding both built indexes (<store>/snapshots holds their snapshots)
    big: str  # the 5k index's version
    small: str


# `attributed`'s authors: a record gets 1 to 6 of them, so both a short list and one cut to "et al." occur
AUTHORS = ("Ada Okafor", "Bo Lindqvist", "Chen Wei", "Dana Haddad", "Emil Novak", "Farah Iqbal")


def attributed(r: Rec) -> PaperRecord:
    """`as_paper(r)` as a crawled record looks to the results list (TASK-134, decision-018): authors, and its
    abstract claimed by the source that supplies that venue's abstracts (spec 01 §Sources), with the urls that
    source gives. ICML: `pmlr` (the claim's url is the paper's PMLR page); ICLR: `openreview_v2` (the claim's
    url is the API listing, the forum is `urls.forum`); NeurIPS: `neurips_proceedings`. Every 11th record also
    carries an `ris` claim for its abstract, which precedence ranks last. The browser fixture serves these."""
    paper = as_paper(r)
    n = int(paper.native.removeprefix("Fx"))
    authors = tuple(AUTHORS[(n + i) % len(AUTHORS)] for i in range(n % len(AUTHORS) + 1))
    claims = [*paper.provenance, Claim(field="authors", value=authors, source="ris", fetched_at=BUILT)]
    urls = Urls()
    if paper.abstract is not None:
        if paper.venue == "ICML":
            page = f"https://proceedings.mlr.press/fixture/{paper.native}.html"
            source, claim_url, urls = "pmlr", page, Urls(proceedings=page)
        elif paper.venue == "ICLR":
            forum = f"https://openreview.net/forum?id={paper.native}"
            source, claim_url, urls = (
                "openreview_v2",
                "https://api2.openreview.net/notes?offset=0",
                Urls(forum=forum),
            )
        else:
            page = f"https://proceedings.neurips.cc/fixture/{paper.native}-Abstract.html"
            source, claim_url, urls = "neurips_proceedings", page, Urls(proceedings=page)
        claims.append(
            Claim(field="abstract", value=paper.abstract, source=source, url=claim_url, fetched_at=BUILT)
        )
        if n % 11 == 0:
            claims.append(Claim(field="abstract", value=paper.abstract, source="ris", fetched_at=BUILT))
    return paper.model_copy(update={"authors": authors, "urls": urls, "provenance": tuple(claims)})


def build(
    corpus: list[Rec],
    snapshots: Path,
    name: str,
    indexes: Path,
    paper: Callable[[Rec], PaperRecord] = as_paper,
) -> str:
    """A snapshot `<snapshots>/<name>` of `corpus` (each record made a snapshot record by `paper`) and its index
    under `indexes`; the index_version."""
    snap = snapshots / name
    snap.mkdir(parents=True)
    papers = tuple(sorted((paper(r) for r in corpus), key=lambda p: p.id))
    for file, data in render(DedupResult(papers, (), ()), [], BUILT).items():
        (snap / file).write_bytes(data)
    return build_index(snap, indexes, BUILT).index_version


@pytest.fixture(scope="session")
def store(tmp_path_factory: pytest.TempPathFactory) -> Store:
    root = tmp_path_factory.mktemp("api-store")
    corpus = list(records())
    big = build(corpus, root / "snapshots", "big", root / "indexes")
    small = build(corpus[:300], root / "snapshots", "small", root / "indexes")
    (root / "indexes" / "current").symlink_to(big)
    return Store(root / "indexes", big, small)


@pytest.fixture
def data_dir(store: Store, tmp_path: Path) -> Path:
    """A private data directory: copies of both indexes and snapshots, `current` → the 5k one."""
    for part in ("indexes", "snapshots"):
        shutil.copytree(store.indexes.parent / part, tmp_path / "data" / part, symlinks=True)
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

    @app.get("/api/v1/_probe/stream-fail")
    def probe_stream_fail(q: str = "") -> StreamingResponse:
        """A stream that fails after its first chunk: the response has started when it raises."""

        def chunks() -> Iterator[str]:
            yield "first\n"
            raise RuntimeError(f"failed mid-stream on {q}")

        return StreamingResponse(chunks(), media_type="text/plain")

    @app.get("/api/v1/_probe/http/{status}")
    def probe_http(status: int) -> None:
        from starlette.exceptions import HTTPException

        raise HTTPException(status_code=status)

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
