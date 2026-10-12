"""The shared HTTP layer's properties, once for every source (TASK-103, TASK-114): the host allowlist, a
response that answers for another host, the body cap, pacing, an offline miss, and the error hierarchy; and
that a cache written before the layer was shared still replays. Each source's own policy (retry waits,
back-off, what is cached and how) stays in `test_fetch.py` and `test_openreview_client.py`. Scripted transports only; no network."""

from __future__ import annotations

import gc
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from openproceedings.ingest.sources import iclr, neurips, pmlr
from openproceedings.ingest.sources.common import CrawlError, MinerError
from openproceedings.ingest.sources.http import (
    USER_AGENT,
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
    OpenReviewPublicDataError,
)
from scholarmend.cache import Cache

from tests.timing import growth
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
    """The whole body costs about 4x its first 1,024 bytes in CPU time, as the 4096-byte window and a linear walk
    give: never ~16x (quadratic in the window) or ~1,000x (the 1 MB tail read). Measured in a daemon thread, so a
    scan that never returns (a backtracking pattern) fails here by name instead of hanging the job until CI's
    timeout; 30 s is that guard, not the measure (tests/timing.py: wall-clock bounds flake on shared runners)."""
    found: list[bytes | None] = []
    ratios: list[tuple[float, list[tuple[float, float]]]] = []

    def measure() -> None:
        found.append(_xml_root(body))
        ratios.append(growth(lambda: _xml_root(body[:1024]), lambda: _xml_root(body), 5, 1e-6, calls=50))

    worker = threading.Thread(target=measure, daemon=True)
    worker.start()
    worker.join(timeout=30)
    if worker.is_alive():  # stuck inside a timed call, with the collector paused for the whole worker
        gc.enable()
    assert not worker.is_alive(), "_xml_root did not return within 30 s"
    assert found == [None]
    [(ratio, pairs)] = ratios
    assert ratio < 8, (ratio, pairs)


def test_xml_root_reads_only_the_first_4096_bytes() -> None:
    """A root after 4096 bytes of prolog is not found: the window is what bounds the scan."""
    assert _xml_root(b"<?a?>" * 800 + b"<OAI-PMH/>") == b"OAI-PMH"  # 4,000 bytes of prolog, then the root
    assert _xml_root(b"<?a?>" * 1000 + b"<OAI-PMH/>") is None


CROSSREF = "https://api.crossref.org/works/10.1145/3593013"
JSON = {"content-type": "application/json"}


def test_a_fetcher_sends_its_own_user_agent_and_never_stores_it(tmp_path: Path) -> None:
    sent: list[dict[str, str]] = []

    def transport(request: Request, timeout: float) -> Response:
        sent.append(dict(request.headers))
        return response('{"status": "ok"}', headers=JSON)

    ua = "openproceedings/test (mailto:reviewer@example.org)"
    f, _ = fetcher(tmp_path, transport, frozenset({"api.crossref.org"}), min_interval=0.0, accept="application/json",
                   expect="json", user_agent=ua)  # fmt: skip
    assert f.get(CROSSREF).ok
    assert sent[0]["User-Agent"] == ua
    assert all("reviewer@example.org" not in p.read_text() for p in tmp_path.rglob("*.json"))


def test_a_source_user_agent_reaches_no_log_line_or_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def transport(request: Request, timeout: float) -> Response:
        return response("busy", status=503, headers=JSON)

    ua = "openproceedings/test (mailto:reviewer@example.org)"
    f, _ = fetcher(tmp_path, transport, frozenset({"api.crossref.org"}), min_interval=0.0, attempts=2,
                   accept="application/json", expect="json", user_agent=ua)  # fmt: skip
    with caplog.at_level("DEBUG"), pytest.raises(RetriesExhausted) as caught:
        f.get(CROSSREF)
    assert "reviewer@example.org" not in str(caught.value)
    assert "reviewer@example.org" not in caplog.text
    assert all("reviewer@example.org" not in p.read_text() for p in tmp_path.rglob("*") if p.is_file())


def test_the_default_user_agent_is_unchanged(tmp_path: Path) -> None:
    sent: list[dict[str, str]] = []

    def transport(request: Request, timeout: float) -> Response:
        sent.append(dict(request.headers))
        return response("<html></html>")

    f, _ = fetcher(tmp_path, transport, frozenset({"proceedings.mlr.press"}), min_interval=0.0)
    f.get("https://proceedings.mlr.press/v81/")
    assert sent[0]["User-Agent"] == USER_AGENT


CSV_URL = "https://facctconference.org/static/docs/facct2026-final.csv"


@pytest.mark.parametrize(
    ("headers", "whole"),
    [({"content-type": "text/csv"}, True), ({"content-type": "text/csv", "content-length": "9"}, True),
     ({"content-type": "text/csv", "content-length": "99"}, False)],
)  # fmt: skip
def test_a_text_page_is_judged_by_its_stated_length(
    tmp_path: Path, headers: dict[str, str], whole: bool
) -> None:
    t = FakeTransport({CSV_URL: response("a,b\n1,2\n\n", headers=headers)})  # 9 bytes
    f, _ = fetcher(tmp_path, t, frozenset({"facctconference.org"}), min_interval=0.0, attempts=2,
                   accept="text/csv", expect="text")  # fmt: skip
    if whole:
        assert f.get(CSV_URL).text.startswith("a,b")
    else:
        with pytest.raises(RetriesExhausted):
            f.get(CSV_URL)


OPENALEX = "https://api.openalex.org/works?filter=doi:10.1145/3593013.3594011&per-page=50"
SECRET = "Bearer sk-test-secret"


def test_secret_headers_are_sent_and_never_stored_or_logged(tmp_path: Path, caplog) -> None:
    sent: list[dict[str, str]] = []

    def transport(request: Request, timeout: float) -> Response:
        sent.append(dict(request.headers))
        return response('{"meta": {"count": 0}, "results": []}', headers={"content-type": "application/json"})

    caplog.set_level(logging.DEBUG)
    f, _ = fetcher(tmp_path, transport, frozenset({"api.openalex.org"}), min_interval=0.0,
                   accept="application/json", expect="json", keep_query=True,
                   headers={"Authorization": SECRET})  # fmt: skip
    assert f.get(OPENALEX).ok
    assert sent[0]["Authorization"] == SECRET
    assert "sk-test-secret" not in caplog.text
    assert all("sk-test-secret" not in p.read_text() for p in tmp_path.rglob("*.json"))


def test_a_refused_request_never_names_a_secret_header(tmp_path: Path) -> None:
    # a plain transport: `FakeTransport` keys its script without the query, which OpenAlex's URL needs
    f, _ = fetcher(tmp_path, lambda request, timeout: response("", status=403), frozenset({"api.openalex.org"}), min_interval=0.0, attempts=1,
                   accept="application/json", expect="json", keep_query=True,
                   headers={"Authorization": SECRET})  # fmt: skip
    with pytest.raises(HTTPRefused) as e:
        f.get(OPENALEX)
    assert "sk-test-secret" not in str(e.value)


def test_secret_headers_ride_every_retry_and_stay_out_of_logs_and_errors(tmp_path: Path, caplog) -> None:
    sent: list[str | None] = []

    def transport(request: Request, timeout: float) -> Response:
        sent.append(request.headers.get("Authorization"))
        return response("", status=503)

    caplog.set_level(logging.DEBUG)
    f, _ = fetcher(tmp_path, transport, frozenset({"api.openalex.org"}), min_interval=0.0, attempts=3,
                   accept="application/json", expect="json", keep_query=True,
                   headers={"Authorization": SECRET})  # fmt: skip
    with pytest.raises(RetriesExhausted) as e:
        f.get(OPENALEX)
    assert sent == [SECRET] * 3
    assert "sk-test-secret" not in str(e.value) + repr(e.value) + caplog.text
    assert not list(tmp_path.rglob("*.json"))


def test_a_request_never_echoes_its_headers(tmp_path: Path) -> None:
    r = Request("GET", OPENALEX, {"Authorization": SECRET})
    assert "sk-test-secret" not in repr(r) + str(r)


def test_a_transport_error_quoting_the_header_stays_out_of_the_error(tmp_path: Path, caplog) -> None:
    def transport(request: Request, timeout: float) -> Response:
        raise OSError(f"bad header {request.headers['Authorization']}")

    caplog.set_level(logging.DEBUG)
    f, _ = fetcher(tmp_path, transport, frozenset({"api.openalex.org"}), min_interval=0.0, attempts=2,
                   accept="application/json", expect="json", keep_query=True,
                   headers={"Authorization": SECRET})  # fmt: skip
    with pytest.raises(RetriesExhausted) as e:
        f.get(OPENALEX)
    assert "sk-test-secret" not in str(e.value) + caplog.text


# --- a deeply nested JSON body (json.loads raises RecursionError, not ValueError) ----------------------------------

NESTED = ("[" * 100_000 + "]" * 100_000).encode()
NESTED_JSON = {"content-type": "application/json"}


def test_a_deeply_nested_json_body_is_whole_to_the_transport_layer_and_crossref_refuses_it(
    tmp_path: Path,
) -> None:
    from openproceedings.ingest.sources import crawl, crossref

    url = "https://api.crossref.org/works"
    t = FakeTransport({url: Response(200, NESTED_JSON, NESTED, "")})
    f = crawl.crossref_fetcher(tmp_path, offline=False, transport=t, min_interval=0, mailto=None)
    page = f.get(url)  # never a raw RecursionError out of send(), and never retried
    assert page.ok and len(t.calls) == 1
    with pytest.raises(CrawlError) as e:
        crossref.parse_works(page.text)
    assert e.value.reason == "crossref_unreadable"


def test_a_deeply_nested_json_body_reaches_openalex_whose_parser_refuses_it(tmp_path: Path) -> None:
    from openproceedings.ingest.sources import crawl, openalex

    url = "https://api.openalex.org/works"
    t = FakeTransport({url: Response(200, NESTED_JSON, NESTED, "")})
    f = crawl.openalex_fetcher(tmp_path, offline=False, transport=t, min_interval=0)
    page = f.get(url)
    assert page.ok and len(t.calls) == 1
    with pytest.raises(CrawlError) as e:
        openalex.parse_works(page.text)
    assert e.value.reason == "openalex_unreadable"


def test_a_deeply_nested_openreview_answer_is_an_unexpected_shape(tmp_path: Path) -> None:
    def transport(request: Request, timeout: float) -> Response:
        if request.method == "POST":
            return json_response({"token": "tok"}, headers={"content-type": "application/json"})
        return Response(200, NESTED_JSON, NESTED, "")

    _, get, _ = openreview(tmp_path, transport)
    with pytest.raises(FetchError) as e:
        get()
    assert e.value.reason == "unexpected_shape"


@pytest.mark.parametrize("field", ["content", "top"])
def test_a_public_note_nested_under_the_decoders_depth_is_an_unexpected_shape(
    tmp_path: Path, field: str
) -> None:
    """600 deep parses (`json.loads` allows it) but the public projection's deepcopy recurses deeper per level: a
    typed refusal, never a raw RecursionError, and nothing cached."""
    deep = "[" * 600 + "1" + "]" * 600
    inner = f'"content": {{"title": {{"value": {deep}}}}}' if field == "content" else f'"replyto": {deep}'
    body = f'{{"notes": [{{"id": "n1", "readers": ["everyone"], {inner}}}]}}'.encode()
    assert json.loads(body)  # under the decoder's depth: only the projection can fail

    def transport(request: Request, timeout: float) -> Response:
        if request.method == "POST":
            return json_response({"token": "tok"}, headers={"content-type": "application/json"})
        return Response(200, NESTED_JSON, body, "")

    _, get, _ = openreview(tmp_path, transport)
    with pytest.raises(OpenReviewPublicDataError) as e:
        get()
    assert e.value.reason == "unexpected_shape"
    assert not list(tmp_path.rglob("*.json"))  # never cached


def test_a_deeply_nested_openreview_login_answer_is_a_refused_login(tmp_path: Path) -> None:
    def transport(request: Request, timeout: float) -> Response:
        return Response(200, NESTED_JSON, NESTED, "")

    _, get, _ = openreview(tmp_path, transport)
    with pytest.raises(OpenReviewAuthError):
        get()


@pytest.mark.parametrize("status", [400, 404])
def test_a_deeply_nested_error_body_has_no_error_name(tmp_path: Path, status: int) -> None:
    from openproceedings.ingest.sources.http import error_name

    assert error_name(Response(status, NESTED_JSON, NESTED, "")) is None

    def transport(request: Request, timeout: float) -> Response:
        if request.method == "POST":
            return json_response({"token": "tok"}, headers={"content-type": "application/json"})
        return Response(status, NESTED_JSON, NESTED, "")

    _, get, _ = openreview(tmp_path, transport)
    with pytest.raises(HTTPRefused) as e:
        get()
    assert e.value.status == status
