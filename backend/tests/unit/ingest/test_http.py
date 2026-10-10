"""The shared HTTP layer's properties, once for every source (TASK-103, TASK-114): the host allowlist, a
response that answers for another host, the body cap, pacing, an offline miss, and the error hierarchy; and
that a cache written before the layer was shared still replays. Each source's own policy (retry waits,
back-off, what is cached and how) stays in `test_fetch.py` and `test_openreview_client.py`. Scripted transports only; no network."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from openproceedings.ingest.sources import iclr, neurips, pmlr
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
    _xml_root,
    canonical,
)
from openproceedings.ingest.sources.openreview_client import (
    Credentials,
    OpenReviewAuthError,
    OpenReviewClient,
)
from scholarmend.cache import Cache

from tests.unit.ingest.openreview_fakes import PASSWORD, USERNAME, FakeClock, json_response
from tests.unit.ingest.proceedings_helpers import FakeTransport, fetcher, response

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


Get = Callable[..., Any]  # get(n): the n-th distinct request of a source's kind
Made = tuple[HttpClient[Any], Get, Any]  # the client, get, and its fake clock
Make = Callable[..., Made]  # (cache, transport, *, offline, min_interval) → Made


def proceedings(hosts: frozenset[str], base: str) -> Make:
    def make(tmp_path: Path, transport: Script, *, offline: bool = False, min_interval: float = 0) -> Made:
        live = None if offline else transport
        f, clock = fetcher(tmp_path, live, hosts, min_interval=min_interval)  # type: ignore[arg-type]
        return f, lambda n=0: f.get(f"{base}p{n}.html"), clock

    return make


def openreview(tmp_path: Path, transport: Script, *, offline: bool = False, min_interval: float = 0) -> Made:
    clock = FakeClock()
    c = OpenReviewClient(tmp_path, credentials=Credentials(USERNAME, PASSWORD), transport=transport, clock=clock,
                         min_interval=min_interval, jitter=lambda: 0.0, offline=offline)  # fmt: skip
    return c, lambda n=0: c.get("/notes", {"id": f"x{n}"}), clock


SOURCES = {
    "iclr": (proceedings(iclr.HOSTS, iclr.LISTINGS[2014]), "text/html"),
    "neurips": (
        proceedings(neurips.HOSTS, "https://proceedings.neurips.cc/paper_files/paper/2013/"),
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
    client, _, _ = make(tmp_path, transport)
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
    _, get, _ = make(tmp_path, Script(lambda r: Response(200, {"content-type": content_type}, body,
                                                          "https://elsewhere.example/x")))  # fmt: skip
    with pytest.raises(FetchError, match="not on") as e:
        get()
    assert e.value.reason == "off_host" and not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("source", SOURCES)
def test_a_body_over_the_cap_is_refused_at_once_and_not_cached(tmp_path: Path, source: str) -> None:
    make, content_type = SOURCES[source]
    transport = Script(lambda r: Response(200, {"content-type": content_type}, b" " * (cap + 1)))
    client, get, _ = make(tmp_path, transport)
    cap = client.policy.max_body
    with pytest.raises(FetchError) as e:
        get()
    assert e.value.reason == "too_large" and not list(tmp_path.rglob("*.json"))
    assert transport.gets() == 1  # never retried


@pytest.mark.parametrize("source", SOURCES)
def test_requests_are_paced(tmp_path: Path, source: str) -> None:
    make, content_type = SOURCES[source]
    transport = Script(lambda r: Response(200, {"content-type": content_type}, ok_body(content_type)))
    _, get, clock = make(tmp_path, transport, min_interval=1.5)
    for n in range(3):
        get(n)
    assert clock.sleeps == [1.5] * (
        len(transport.sent) - 1
    )  # none before the first (OpenReview's: its login)


@pytest.mark.parametrize("source", SOURCES)
def test_offline_a_miss_is_an_error_never_a_request(tmp_path: Path, source: str) -> None:
    make, _ = SOURCES[source]
    transport = Script(lambda r: Response(200, {}, b""))
    _, get, _ = make(tmp_path, transport, offline=True)
    with pytest.raises(CacheMiss) as e:
        get()
    assert e.value.reason == "not_cached" and transport.sent == []


def test_every_crawler_error_is_one_source_error() -> None:
    for error in (FetchError, CacheMiss, RetriesExhausted, HTTPRefused, CacheError, CrawlError, MinerError,
                  OpenReviewAuthError):  # fmt: skip
        assert issubclass(error, SourceError)
    assert HTTPRefused("https://x/", 403).reason == "http_403" and CacheMiss("u").reason == "not_cached"


def test_an_openreview_cache_written_by_scholarmends_cache_still_replays(tmp_path: Path) -> None:
    """Before TASK-103 the OpenReview client stored entries with scholarmend's `Cache` (no trailing newline, its
    own temp names): the shared cache reads that layout unchanged."""
    url = "https://api2.openreview.net/notes?id=x"
    entry = {
        "url": url,
        "fetched_at": "2026-09-27T12:00:01+00:00",
        "headers": {},
        "json": {"notes": []},
        "public_projection": 1,
    }
    Cache(tmp_path).put(url, entry)
    client = OpenReviewClient(tmp_path, credentials=None, offline=True)
    assert client.get("/notes", {"id": "x"}) == entry and client.cached == 1
    [path] = tmp_path.rglob("*.json")
    assert json.loads(path.read_text()) == {"key": url, "payload": entry}


OAI = "https://ojs.aaai.org/index.php/AAAI/oai?verb=ListRecords&metadataPrefix=oai_dc"
OAI_BODY = '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords/></OAI-PMH>'
WHOLE = f'<?xml version="1.0"?>{OAI_BODY}\n'
CUT = WHOLE[:60]
XML_HEADERS = {"content-type": "text/xml; charset=utf-8"}


def _xml_fetcher(tmp_path: Path, body: str) -> tuple[Any, FakeTransport]:
    t = FakeTransport({})
    t.script[canonical(OAI, keep_query=True)] = [response(body, headers=XML_HEADERS)]  # the query names it
    f, _ = fetcher(tmp_path, t, frozenset({"ojs.aaai.org"}), min_interval=0.0, attempts=2,
                   accept="application/xml", expect="xml", keep_query=True)  # fmt: skip
    return f, t


def test_xml_page_is_kept_with_its_query(tmp_path: Path) -> None:
    f, t = _xml_fetcher(tmp_path, WHOLE)
    page = f.get(OAI)
    assert page.ok and page.url == OAI  # the query names the resource: kept in the URL and the cache key
    assert t.calls == [OAI]


def test_truncated_xml_is_retried_then_refused(tmp_path: Path) -> None:
    f, t = _xml_fetcher(tmp_path, CUT)
    with pytest.raises(RetriesExhausted):
        f.get(OAI)
    assert len(t.calls) == 2


@pytest.mark.parametrize(
    "body",
    [
        f'<?xml version="1.0"?><!-- c -->{OAI_BODY}',
        f'<?xml version="1.0"?>\n<?xml-stylesheet href="x.xsl"?>\n{OAI_BODY}  \n',
        f"  {OAI_BODY}",
    ],
)
def test_xml_prolog_is_skipped_to_find_the_root(tmp_path: Path, body: str) -> None:
    f, _ = _xml_fetcher(tmp_path, body)
    assert f.get(OAI).ok


def test_xml_with_another_closing_tag_is_not_whole(tmp_path: Path) -> None:
    f, _ = _xml_fetcher(tmp_path, '<?xml version="1.0"?><OAI-PMH><ListRecords></ListRecords>')
    with pytest.raises(RetriesExhausted):
        f.get(OAI)


def test_html_rule_unchanged_for_the_default_fetcher(tmp_path: Path) -> None:
    url = "https://ojs.aaai.org/index.php/AAAI/issue/archive"
    t = FakeTransport({url: response("<html><body>ok</body></html>")})
    f, _ = fetcher(tmp_path, t, frozenset({"ojs.aaai.org"}), min_interval=0.0)
    assert f.get(url).ok


@pytest.mark.parametrize(
    "body",
    [
        "\ufeff" + WHOLE,
        '<oai:OAI-PMH xmlns:oai="urn:x"><oai:ListRecords/></oai:OAI-PMH>',
        '<?xml version="1.0"?>' + "<?a b?>" * 50 + "<!-- c -->" * 50 + OAI_BODY,
    ],
)
def test_xml_bom_prefixed_and_namespaced_and_long_prolog_are_whole(tmp_path: Path, body: str) -> None:
    f, _ = _xml_fetcher(tmp_path, body)
    assert f.get(OAI).ok


@pytest.mark.parametrize("prolog", ["<?xml version='1.0'", "<!-- never closed"])
def test_xml_unterminated_prolog_is_truncated(tmp_path: Path, prolog: str) -> None:
    f, _ = _xml_fetcher(tmp_path, prolog + OAI_BODY)
    with pytest.raises(RetriesExhausted):
        f.get(OAI)


@pytest.mark.parametrize(
    "body",
    [
        b"<?a?>" * 800 + b"x",
        b"<!--a-->" * 500 + b"x",
        b"<?" + b"?" * 4000,
        b"<?a?>" * 200_000 + b"x",  # 1 MB, far past the 4096-byte window
    ],
)
def test_xml_root_scan_is_bounded_on_adversarial_prologs(body: bytes) -> None:
    """Run in a daemon thread, so a scan that never returns (a backtracking pattern) fails here by name, fast,
    instead of hanging the job until CI's timeout."""
    found: list[bytes | None] = []
    worker = threading.Thread(target=lambda: found.append(_xml_root(body)), daemon=True)
    start = time.perf_counter()
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive(), "_xml_root did not return within 2 s"
    assert found == [None] and time.perf_counter() - start < 0.5


def test_xml_root_reads_only_the_first_4096_bytes() -> None:
    """A root after 4096 bytes of prolog is not found: the window is what bounds the scan."""
    assert _xml_root(b"<?a?>" * 800 + b"<OAI-PMH/>") == b"OAI-PMH"  # 4,000 bytes of prolog, then the root
    assert _xml_root(b"<?a?>" * 1000 + b"<OAI-PMH/>") is None
