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
