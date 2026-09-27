"""The crawlers' cached, polite fetcher (`ingest/sources/http.py`), against a scripted transport."""

from __future__ import annotations

import json
from datetime import timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest
from openproceedings.ingest.sources.http import (
    CacheError,
    FetchError,
    Page,
    PageCache,
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


def test_offline_a_miss_is_an_error_never_a_fetch(tmp_path: Path) -> None:
    f, _ = fetcher(tmp_path, None, HOSTS)
    with pytest.raises(FetchError) as e:
        f.get(URL)
    assert e.value.reason == "not_cached"


def test_refresh_refetches_and_replaces_the_entry(tmp_path: Path) -> None:
    t = FakeTransport({URL: [response(PAGE), response("<html>new</html>")]})
    f, _ = fetcher(tmp_path, t, HOSTS)
    f.get(URL)
    assert f.get(URL, refresh=True).text == "<html>new</html>"
    assert f.get(URL).text == "<html>new</html>" and len(t.calls) == 2


def test_requests_are_paced(tmp_path: Path) -> None:
    urls = [f"https://proceedings.mlr.press/v28/p{i}.html" for i in range(3)]
    f, clock = fetcher(tmp_path, FakeTransport({u: response(PAGE) for u in urls}), HOSTS, min_interval=1.5)
    for u in urls:
        f.get(u)
    assert clock.sleeps == [1.5, 1.5]  # none before the first request


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


@pytest.mark.parametrize(
    "url",
    ["https://example.org/v28/", "ftp://proceedings.mlr.press/v28/", "https://proceedings.mlr.press.evil/x"],
)
def test_only_the_sources_hosts_are_fetched(tmp_path: Path, url: str) -> None:
    f, _ = fetcher(tmp_path, FakeTransport({}), HOSTS)
    with pytest.raises(FetchError) as e:
        f.get(url)
    assert e.value.reason == "off_host"


def test_a_redirect_off_the_hosts_is_refused(tmp_path: Path) -> None:
    f, _ = fetcher(tmp_path, FakeTransport({URL: response(PAGE, url="https://elsewhere.example/x")}), HOSTS)
    with pytest.raises(FetchError, match="not on"):
        f.get(URL)


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
