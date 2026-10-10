"""Shared helpers for the proceedings-miner tests: recorded fixtures into a page cache, and a scripted
transport. Nothing here opens a socket (conftest blocks the network anyway)."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openproceedings.ingest.sources.http import Fetcher, Page, PageCache, Request, Response, canonical

HTTP = Path(__file__).parents[2] / "fixtures" / "http"
T0 = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 9, 27, 12, 5, tzinfo=UTC)
MAIN = "proceedings.neurips.cc"
DB = "datasets-benchmarks-proceedings.neurips.cc"


def fixture(rel: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((HTTP / rel).read_text(encoding="utf-8"))
    return data


def fixture_text(rel: str) -> str:
    return str(fixture(rel)["response"]["text"])


def fixture_url(rel: str) -> str:
    return str(fixture(rel)["request"]["url"])


def seed(
    cache: Path,
    source_dir: str,
    url: str,
    text: str,
    *,
    status: int = 200,
    at: datetime = T0,
    keep_query: bool = False,
) -> None:
    PageCache(cache / source_dir).put(Page(canonical(url, keep_query=keep_query), status, text, at))


def seed_fixture(
    cache: Path, source_dir: str, rel: str, *, url: str | None = None, edit: Callable[[str], str] | None = None,
    at: datetime = T0,
) -> None:  # fmt: skip
    """A recorded page into the cache, optionally at another URL or with its text edited (a derived case)."""
    text = fixture_text(rel)
    seed(cache, source_dir, url or fixture_url(rel), edit(text) if edit else text, at=at)


def neurips_abs(year: int, sha: str, token: str | None = None, host: str = MAIN) -> str:
    suffix = f"-{token}" if token else ""
    return f"https://{host}/paper_files/paper/{year}/hash/{sha}-Abstract{suffix}.html"


def response(text: str = "<html></html>", status: int = 200, headers: Mapping[str, str] | None = None,
             url: str = "") -> Response:  # fmt: skip
    return Response(status, dict(headers or {"content-type": "text/html; charset=utf-8"}), text.encode(), url)


class FakeTransport:
    """Serves scripted responses per URL (a list is served in order; the last one repeats). An unscripted
    URL is a test bug."""

    def __init__(self, script: Mapping[str, Response | list[Response]]) -> None:
        self.script = {canonical(k): v if isinstance(v, list) else [v] for k, v in script.items()}
        self.calls: list[str] = []

    def __call__(self, request: Request, timeout: float) -> Response:
        self.calls.append(request.url)
        queue = self.script[request.url]
        r = queue.pop(0) if len(queue) > 1 else queue[0]
        return Response(r.status, r.headers, r.body, r.url or request.url)


class Clock:
    """A fake clock (`http.Clock`): monotonic time moves only when something sleeps (each sleep is recorded),
    and the wall clock always says T1."""

    def __init__(self) -> None:
        self.t = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def now(self) -> datetime:
        return T1

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def fetcher(
    cache: Path, transport: FakeTransport | None, hosts: frozenset[str], **kw: Any
) -> tuple[Fetcher, Clock]:
    clock = Clock()
    f = Fetcher(PageCache(cache), transport, hosts=hosts, clock=clock, **kw)
    return f, clock
