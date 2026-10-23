"""The proceedings fetcher's own policy (`ingest/sources/http.py`: its cache, retry waits and back-off),
against a scripted transport. What every source shares (the allowlist, off-host answers, pacing, an offline
miss) is tested once in `test_http.py`."""

from __future__ import annotations

import ast
import json
import logging
from datetime import timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest
from openproceedings.ingest import sources
from openproceedings.ingest.sources.http import (
    CRAWL_EVENTS,
    PROCEEDINGS,
    CacheError,
    FetchError,
    Page,
    PageCache,
    Response,
    RetriesExhausted,
    canonical,
    entry_from_fixture,
)

from tests.unit.ingest.proceedings_helpers import T0, T1, FakeTransport, fetcher, fixture, response

HOSTS = frozenset({"proceedings.mlr.press"})
URL = "https://proceedings.mlr.press/v28/"
PAGE = "<html><body>ok</body></html>"


def test_a_page_is_fetched_once_then_served_from_the_cache(tmp_path: Path) -> None:
    t = FakeTransport({URL: response(PAGE)})
    f, _ = fetcher(tmp_path, t, HOSTS)
    first, again = f.get(URL), f.get(URL)
    assert first == again == Page(URL, 200, PAGE, T1, "text/html; charset=utf-8")
    assert t.calls == [URL] and (f.stats.network, f.stats.cached) == (1, 1)
    offline, _ = fetcher(tmp_path, None, HOSTS)
    assert offline.get(URL).fetched_at == T1  # the cache entry's time, never the reader's clock


def test_refresh_refetches_and_replaces_the_entry(tmp_path: Path) -> None:
    t = FakeTransport({URL: [response(PAGE), response("<html>new</html>")]})
    f, _ = fetcher(tmp_path, t, HOSTS)
    f.get(URL)
    assert f.get(URL, refresh=True).text == "<html>new</html>"
    assert f.get(URL).text == "<html>new</html>" and len(t.calls) == 2


@pytest.mark.parametrize(
    ("headers", "wait"),
    [
        ({"retry-after": "7"}, 7.0),
        ({"retry-after": format_datetime(T1 + timedelta(seconds=42), usegmt=True)}, 42.0),
        ({"ratelimit-reset": "12"}, 12.0),
        ({}, 5.0),  # no hint: the first back-off step
    ],
)
def test_429_honours_retry_after(tmp_path: Path, headers: dict[str, str], wait: float) -> None:
    t = FakeTransport({URL: [response("", 429, headers), response(PAGE)]})
    f, clock = fetcher(tmp_path, t, HOSTS, min_interval=0)
    assert f.get(URL).ok
    assert clock.sleeps == [wait] and f.stats.retries == 1


# TASK-282: urllib decodes headers as latin-1, so a byte 0xB2 arrives as '²', a digit to `isdigit()` that
# `float()` refuses. It is no hint, never an exception that aborts the crawl.
LATIN1_TWO = b"\xb2".decode("latin-1")


@pytest.mark.parametrize("value", [LATIN1_TWO, f"1{LATIN1_TWO}", "١٢", "1.²"])
def test_a_non_ascii_retry_after_on_a_429_is_no_hint(tmp_path: Path, value: str) -> None:
    t = FakeTransport({URL: [response("", 429, {"retry-after": value}), response(PAGE)]})
    f, clock = fetcher(tmp_path, t, HOSTS, min_interval=0)
    assert f.get(URL).ok
    assert clock.sleeps == [5.0]  # the first back-off step, as with no header


@pytest.mark.parametrize("header", ["ratelimit-remaining", "ratelimit-reset"])
def test_a_non_ascii_ratelimit_header_on_a_200_is_no_hint(tmp_path: Path, header: str) -> None:
    """`_respect_budget` reads both on every 200, outside the transport's try: a '²' there is no hint too."""
    spent = {"content-type": "text/html; charset=utf-8", "ratelimit-remaining": "0", "ratelimit-reset": "3"}
    t = FakeTransport({URL: response(PAGE, headers=spent | {header: LATIN1_TWO})})
    f, clock = fetcher(tmp_path, t, HOSTS, min_interval=0)
    assert f.get(URL).text == PAGE
    # no remaining count: no budget wait; a spent budget with no reset: the 60s default (+ the pad)
    assert clock.sleeps == ([] if header == "ratelimit-remaining" else [60.0 + f.policy.hint_pad])


def test_5xx_backs_off_exponentially_then_gives_up(tmp_path: Path) -> None:
    t = FakeTransport({URL: response("", 503)})
    f, clock = fetcher(tmp_path, t, HOSTS, min_interval=0, attempts=3)
    with pytest.raises(FetchError) as e:
        f.get(URL)
    assert e.value.reason == "retries_exhausted" and clock.sleeps == [5.0, 10.0, 20.0] and len(t.calls) == 3
    assert PageCache(tmp_path).get(URL) is None


def test_a_wait_past_max_wait_aborts(tmp_path: Path) -> None:
    f, clock = fetcher(tmp_path, FakeTransport({URL: response("", 429, {"retry-after": "7200"})}), HOSTS)
    with pytest.raises(FetchError) as e:
        f.get(URL)
    assert e.value.reason == "wait_too_long" and clock.sleeps == []


@pytest.mark.parametrize("status", [400, 401, 403, 451])
def test_other_4xx_raise_at_once(tmp_path: Path, status: int) -> None:
    t = FakeTransport({URL: response("", status)})
    f, _ = fetcher(tmp_path, t, HOSTS)
    with pytest.raises(FetchError) as e:
        f.get(URL)
    assert e.value.reason == f"http_{status}" and len(t.calls) == 1


def test_a_404_is_cached_only_when_asked(tmp_path: Path) -> None:
    t = FakeTransport({URL: response("", 404)})
    f, _ = fetcher(tmp_path, t, HOSTS)
    assert (
        f.get(URL).status == 404 and PageCache(tmp_path).get(URL) is None
    )  # an index page: re-asked next time
    assert f.get(URL, keep_absent=True).status == 404
    assert PageCache(tmp_path).get(URL) == Page(URL, 404, "", T1, "text/html; charset=utf-8")


def test_a_truncated_body_and_a_network_error_are_retried(tmp_path: Path) -> None:
    class Flaky(FakeTransport):
        def __call__(self, url: str, timeout: float):  # type: ignore[no-untyped-def]
            if not self.calls:
                self.calls.append(url)
                raise TimeoutError("timed out")
            return super().__call__(url, timeout)

    t = Flaky({URL: [response("<html><body>cut"), response(PAGE)]})
    f, clock = fetcher(tmp_path, t, HOSTS, min_interval=0)
    assert f.get(URL).text == PAGE
    assert len(t.calls) == 3 and clock.sleeps == [5.0, 10.0]


def test_a_capture_judged_by_length_is_whole_without_a_closing_html_tag(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A 1990s page that never had `</html>` (ICML 1997/1998 captures, TASK-207): with `by_length`, its stated
    `Content-Length` decides; a body shorter than stated is retried, and with no length the `</html>` rule holds."""
    old = "<body><pre>An old page.</pre>"

    def sized(body: str, length: int | None) -> Response:
        headers = {"content-type": "text/html"} | (
            {"content-length": str(length)} if length is not None else {}
        )
        return response(body, headers=headers)

    t = FakeTransport({URL: [sized(old[:10], len(old)), sized(old, len(old))]})
    f, clock = fetcher(tmp_path / "a", t, HOSTS, min_interval=0)
    assert f.get(URL, by_length=True).text == old
    assert len(t.calls) == 2 and clock.sleeps == [5.0]  # the short body was retried once
    # without `by_length`, or with no stated length, the same page is truncated: retried until given up
    # a stated length that isn't 1-19 ASCII digits (`²`, or 5,000 digits, past int()'s limit) is no length: never a
    # crash, the closing-tag rule, and the retry lines say so
    for odd in ("²", "9" * 5_000):
        t = FakeTransport({URL: response(old, headers={"content-type": "text/html", "content-length": odd})})
        f, _ = fetcher(tmp_path / f"odd{len(odd)}", t, HOSTS, min_interval=0)
        caplog.clear()
        with caplog.at_level(logging.WARNING), pytest.raises(RetriesExhausted):
            f.get(URL, by_length=True)
        assert {getattr(r, "why", None) for r in caplog.records if r.getMessage() == "crawl_retry_wait"} == {
            "truncated_no_length"
        }
    for by_length, length, why in ((False, len(old), "truncated"), (True, None, "truncated_no_length")):
        t = FakeTransport({URL: sized(old, length)})
        f, _ = fetcher(tmp_path / f"{by_length}{length}", t, HOSTS, min_interval=0)
        caplog.clear()
        with caplog.at_level(logging.WARNING), pytest.raises(RetriesExhausted):
            f.get(URL, by_length=by_length)
        # a capture that states no length is told apart from a short body in the retry lines
        assert {getattr(r, "why", None) for r in caplog.records if r.getMessage() == "crawl_retry_wait"} == {
            why
        }


def test_a_capture_with_no_length_is_whole_when_its_source_vouches_for_its_bytes(
    tmp_path: Path, caplog
) -> None:
    """An archived page served with no Content-Length and no closing </html> (aaai07-001, TASK-232) is whole when
    `whole` vouches for its exact bytes (a pinned digest); otherwise it is still `truncated_no_length`."""
    body = "<html><body><p>an old page that never closed its tags"
    t = FakeTransport({URL: response(body, headers={"content-type": "text/html"})})
    f, _ = fetcher(tmp_path / "ok", t, HOSTS, min_interval=0)
    assert f.get(URL, by_length=True, whole=lambda b: b == body.encode()).text == body
    assert len(t.calls) == 1
    t = FakeTransport({URL: response(body, headers={"content-type": "text/html"})})
    f, _ = fetcher(tmp_path / "no", t, HOSTS, min_interval=0)
    caplog.clear()
    with caplog.at_level(logging.WARNING), pytest.raises(RetriesExhausted):
        f.get(URL, by_length=True, whole=lambda b: False)
    assert {getattr(r, "why", None) for r in caplog.records if r.getMessage() == "crawl_retry_wait"} == {
        "truncated_no_length"
    }


def test_query_strings_and_fragments_are_dropped() -> None:
    assert canonical("http://PROCEEDINGS.mlr.press/v28/x.html?utm_source=chatgpt.com#abs") == (
        "https://proceedings.mlr.press/v28/x.html"
    )


def test_cache_entries_are_fixture_shaped_and_checked(tmp_path: Path) -> None:
    cache = PageCache(tmp_path)
    page = entry_from_fixture(fixture("pmlr/v28/volume-index.json"), T0)
    cache.put(page)
    path = cache.path(page.url)
    entry = json.loads(path.read_text(encoding="utf-8"))
    assert set(entry) == {"fetched_at", "request", "response"} and entry["request"]["url"] == page.url
    assert cache.get(page.url) == page
    assert not [p for p in path.parent.iterdir() if p.name.startswith(".tmp-")]  # the write left no temp file
    entry["request"]["url"] = "https://proceedings.mlr.press/v32/"
    path.write_text(json.dumps(entry), encoding="utf-8")
    with pytest.raises(CacheError, match="another URL"):
        cache.get(page.url)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CacheError, match="unreadable"):
        cache.get(page.url)


# --- log event names (TASK-116) ---------------------------------------------------------------------------


def test_the_proceedings_policy_logs_fixed_event_names(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert PROCEEDINGS.events is CRAWL_EVENTS
    spent = {"content-type": "text/html; charset=utf-8", "ratelimit-remaining": "0", "ratelimit-reset": "3"}
    t = FakeTransport({URL: [response("", 503), response(PAGE, headers=spent)]})
    f, _ = fetcher(tmp_path, t, HOSTS, min_interval=0)
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.sources.http"):
        assert f.get(URL).ok
    assert [r.getMessage() for r in caplog.records] == ["crawl_retry_wait", "crawl_budget_wait"]


LOG_METHODS = frozenset({"debug", "info", "warning", "error", "exception", "critical", "log"})


def _is_logger(receiver: ast.expr) -> bool:
    """`log`, `logger`, `self._log`, `x.log`: a receiver whose own name ends in `log` or `logger`."""
    name = receiver.id if isinstance(receiver, ast.Name) else getattr(receiver, "attr", "")
    return name.lower().endswith(("log", "logger"))


def test_every_crawler_log_event_is_a_constant_never_built() -> None:
    """logging-standards: `event` is a constant. A crawler's first log argument is a string literal or a
    named constant (`self.policy.events.retry_wait`), never an f-string, a concatenation or a call."""
    checked, receivers = 0, set()
    for path in sorted(Path(sources.__file__).parent.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in LOG_METHODS and _is_logger(node.func.value)):  # fmt: skip
                continue
            event = node.args[1 if node.func.attr == "log" else 0]
            assert isinstance(event, ast.Constant | ast.Name | ast.Attribute), f"{path.name}:{node.lineno}"
            assert not isinstance(event, ast.Constant) or isinstance(event.value, str), (
                f"{path.name}:{node.lineno}"
            )
            checked += 1
            receivers.add(ast.unparse(node.func.value))
    assert checked >= 30  # the walk found the crawlers' log calls
    assert {"log", "logger", "self._log"} <= receivers  # every receiver form the crawlers use was checked


def test_a_body_with_no_charset_decodes_with_the_one_asked_for_and_a_named_one_wins(tmp_path: Path) -> None:
    """TASK-206: old conference pages are served as bare `text/html` in cp1252. `get(charset=)` decodes such a
    body; a charset the response names still wins; utf-8 stays the default, so a cp1252 body is refused."""
    url = "https://icml.cc/Conferences/2010/abstracts.html"
    page = "<html>Naïve “quoted”</html>"
    bare = Response(200, {"content-type": "text/html"}, page.encode("cp1252"))
    f, _ = fetcher(tmp_path / "a", FakeTransport({url: bare}), frozenset({"icml.cc"}), min_interval=0)
    assert f.get(url, charset="cp1252").text == page
    f, _ = fetcher(tmp_path / "b", FakeTransport({url: bare}), frozenset({"icml.cc"}), min_interval=0)
    with pytest.raises(FetchError, match="not utf-8") as e:
        f.get(url)
    assert e.value.reason == "undecodable"
    named = Response(200, {"content-type": "text/html; charset=utf-8"}, "café</html>".encode())
    f, _ = fetcher(tmp_path / "c", FakeTransport({url: named}), frozenset({"icml.cc"}), min_interval=0)
    assert f.get(url, charset="cp1252").text == "café</html>"


def test_exact_bytes_keeps_the_body_one_to_one_whatever_charset_the_response_names(tmp_path: Path) -> None:
    """TASK-232: a source that checks a digest of the captured bytes (aaai_library) reads the body as ISO-8859-1,
    whatever the response names, so `text.encode("latin-1")` is the body exactly, and a body the named charset
    can't decode is still kept, never refused."""
    url = "https://web.archive.org/web/20081121081132id_/http://www.aaai.org/Library/AAAI/1980/aaai80-001.php"
    body = "<html>café ’ </html>".encode() + b"\xe9\xff</html>"  # UTF-8, then two bytes UTF-8 refuses
    named = Response(200, {"content-type": "text/html; charset=utf-8"}, body)
    f, _ = fetcher(
        tmp_path / "a", FakeTransport({url: named}), frozenset({"web.archive.org"}), min_interval=0
    )
    page = f.get(url, exact_bytes=True)
    assert page.text.encode("latin-1") == body
    assert page.content_type == "text/html; charset=utf-8"  # the response's own, kept for the record
    assert PageCache(tmp_path / "a").get(canonical(url)) == page  # cached as read
    f, _ = fetcher(
        tmp_path / "b", FakeTransport({url: named}), frozenset({"web.archive.org"}), min_interval=0
    )
    with pytest.raises(FetchError, match="not utf-8"):
        f.get(url)  # without it, the named charset still decides


def test_a_verify_callback_that_refuses_keeps_the_page_out_of_the_cache(tmp_path: Path) -> None:
    """TASK-232: `get(verify=)` judges a fetched 200 before it is stored; a refused page is returned, never cached."""
    url = "https://web.archive.org/web/20081121081132id_/http://www.aaai.org/Library/AAAI/1980/aaai80-001.php"
    ok = Response(200, {"content-type": "text/html"}, b"<html>x</html>")
    f, _ = fetcher(tmp_path, FakeTransport({url: ok}), frozenset({"web.archive.org"}), min_interval=0)
    page = f.get(url, verify=lambda p: False)
    assert page.ok and PageCache(tmp_path).get(canonical(url)) is None
    assert f.get(url, verify=lambda p: True).ok and PageCache(tmp_path).get(canonical(url)) == page


def test_a_redirect_callback_judges_a_3xx_and_fetch_never_hops_or_caches(tmp_path: Path) -> None:
    """`get(redirect=)` hands a 3xx (with its Location) to the source, which returns the page to keep: a 200 it
    vouches for, or the 3xx as a stable answer; both are cached. Without it a 3xx is still `HTTPRefused`.
    `fetch` is one live request, never cached, and a 3xx there is refused, never followed."""
    from openproceedings.ingest.sources.http import HTTPRefused

    hosts = frozenset({"web.archive.org"})
    url, there = "https://web.archive.org/web/1/x", "https://web.archive.org/web/2/x"
    moved = Response(302, {"location": there}, b"")
    script = {url: moved, there: Response(200, {"content-type": "text/html"}, b"<html>x</html>")}
    f, _ = fetcher(tmp_path, FakeTransport(script), hosts, min_interval=0)
    with pytest.raises(HTTPRefused):
        f.get(url)
    seen: list[str] = []

    def follow(at: str, resp: Response) -> Page:
        seen.append(resp.headers["location"])
        return Page(at, resp.status, "", T1)

    page = f.get(url, redirect=follow)
    assert seen == [there] and page.status == 302 and PageCache(tmp_path).get(canonical(url)) == page
    assert f.fetch(there).ok and PageCache(tmp_path).get(canonical(there)) is None
    with pytest.raises(HTTPRefused):
        f.fetch(url)
    with pytest.raises(FetchError, match="not on"):
        f.fetch("https://www.aaai.org/x")


@pytest.mark.parametrize(
    "url", ["https://www.aaai.org/x", "http://web.archive.org.evil/x", "ftp://web.archive.org/x"]
)
def test_fetch_refuses_a_url_off_its_hosts_before_any_request(tmp_path: Path, url: str) -> None:
    """`Fetcher.fetch` is a general API (gate C round 1): a URL off the fetcher's hosts, or not http(s), is a
    `FetchError` (`off_host`) and the transport is never called."""
    transport = FakeTransport({})
    f, _ = fetcher(tmp_path, transport, frozenset({"web.archive.org"}), min_interval=0)
    with pytest.raises(FetchError) as e:
        f.fetch(url)
    assert e.value.reason == "off_host" and transport.calls == []
