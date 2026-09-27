"""The shared HTTP layer's security properties, once for every source (TASK-103): the host allowlist, a
response that answers for another host, the body cap, and the error hierarchy; and that a cache written
before the layer was shared still replays. Scripted transports only; no network."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from openproceedings.ingest.sources import neurips, pmlr
from openproceedings.ingest.sources.common import CrawlError, MinerError
from openproceedings.ingest.sources.http import (
    CacheError,
    CacheMiss,
    FetchError,
    HttpClient,
    HTTPRefused,
    Request,
    Response,
    RetriesExhausted,
    SourceError,
)
from openproceedings.ingest.sources.openreview_client import (
    Credentials,
    OpenReviewAuthError,
    OpenReviewClient,
)
from scholarmend.cache import Cache

from tests.unit.ingest.openreview_fakes import PASSWORD, USERNAME, FakeClock, json_response
from tests.unit.ingest.proceedings_helpers import fetcher

HTML = b"<html><body>ok</body></html>"


class Script:
    """A transport that answers OpenReview's login with a token and every other request with `answer`, and
    records what was sent."""

    def __init__(self, answer: Callable[[Request], Response]) -> None:
        self.answer = answer
        self.sent: list[str] = []

    def __call__(self, request: Request, timeout: float) -> Response:
        self.sent.append(request.url)
        return json_response({"token": "t"}) if request.url.endswith("/login") else self.answer(request)

    def gets(self) -> int:
        return sum(not u.endswith("/login") for u in self.sent)


Make = Callable[[Path, Script], tuple[HttpClient[Any], Callable[[], Any]]]


def proceedings(hosts: frozenset[str], url: str) -> Make:
    def make(tmp_path: Path, transport: Script) -> tuple[HttpClient[Any], Callable[[], Any]]:
        f, _ = fetcher(tmp_path, transport, hosts, min_interval=0)  # type: ignore[arg-type]
        return f, lambda: f.get(url)

    return make


def openreview(tmp_path: Path, transport: Script) -> tuple[HttpClient[Any], Callable[[], Any]]:
    c = OpenReviewClient(tmp_path, credentials=Credentials(USERNAME, PASSWORD), transport=transport,
                         clock=FakeClock(), min_interval=0.0, jitter=lambda: 0.0)  # fmt: skip
    return c, lambda: c.get("/notes", {"id": "x"})


SOURCES = {
    "neurips": (
        proceedings(neurips.HOSTS, "https://proceedings.neurips.cc/paper_files/paper/2013"),
        "text/html",
    ),
    "pmlr": (proceedings(pmlr.HOSTS, "https://proceedings.mlr.press/v28/"), "text/html"),
    "openreview": (openreview, "application/json"),
}


def ok_body(content_type: str) -> bytes:
    return b'{"notes": []}' if content_type == "application/json" else HTML


@pytest.mark.parametrize("source", SOURCES)
def test_a_url_off_the_sources_hosts_is_never_sent(tmp_path: Path, source: str) -> None:
    make, _ = SOURCES[source]
    transport = Script(lambda r: Response(200, {}, b""))
    client, _ = make(tmp_path, transport)
    for url in (
        "https://example.org/x",
        "ftp://proceedings.mlr.press/v28/",
        "https://api2.openreview.net.evil/x",
    ):
        with pytest.raises(FetchError) as e:
            client.send(Request("GET", url, {}))
        assert e.value.reason == "off_host"
    assert transport.sent == []


@pytest.mark.parametrize("source", SOURCES)
def test_a_response_answering_for_another_host_is_refused_and_not_cached(tmp_path: Path, source: str) -> None:
    make, content_type = SOURCES[source]
    body = ok_body(content_type)
    _, get = make(tmp_path, Script(lambda r: Response(200, {"content-type": content_type}, body,
                                                          "https://elsewhere.example/x")))  # fmt: skip
    with pytest.raises(FetchError, match="not on") as e:
        get()
    assert e.value.reason == "off_host" and not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("source", SOURCES)
def test_a_body_over_the_cap_is_refused_at_once_and_not_cached(tmp_path: Path, source: str) -> None:
    make, content_type = SOURCES[source]
    transport = Script(lambda r: Response(200, {"content-type": content_type}, b" " * (cap + 1)))
    client, get = make(tmp_path, transport)
    cap = client.policy.max_body
    with pytest.raises(FetchError) as e:
        get()
    assert e.value.reason == "too_large" and not list(tmp_path.rglob("*.json"))
    assert transport.gets() == 1  # never retried


def test_every_crawler_error_is_one_source_error() -> None:
    for error in (FetchError, CacheMiss, RetriesExhausted, HTTPRefused, CacheError, CrawlError, MinerError,
                  OpenReviewAuthError):  # fmt: skip
        assert issubclass(error, SourceError)
    assert HTTPRefused("https://x/", 403).reason == "http_403" and CacheMiss("u").reason == "not_cached"


def test_an_openreview_cache_written_by_scholarmends_cache_still_replays(tmp_path: Path) -> None:
    """Before TASK-103 the OpenReview client stored entries with scholarmend's `Cache` (no trailing newline, its
    own temp names): the shared cache reads that layout unchanged."""
    url = "https://api2.openreview.net/notes?id=x"
    entry = {"url": url, "fetched_at": "2026-09-27T12:00:01+00:00", "headers": {}, "json": {"notes": []}}
    Cache(tmp_path).put(url, entry)
    client = OpenReviewClient(tmp_path, credentials=None, offline=True)
    assert client.get("/notes", {"id": "x"}) == entry and client.cached == 1
    [path] = tmp_path.rglob("*.json")
    assert json.loads(path.read_text()) == {"key": url, "payload": entry}
