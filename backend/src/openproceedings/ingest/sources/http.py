"""The crawlers' one HTTP path (spec 01 §Pipeline 1): a disk cache in front of a polite, retrying fetcher.

- **Cache.** One JSON file per URL under `<cache>/<source>/pages/<sha256[:2]>/<sha256>.json`, shaped like a
  recorded fixture (`request`, `response`) plus the fetch time, written atomically (a `.tmp-` file, fsync,
  rename), so a crash never leaves half an entry and a crawl resumes where it stopped. The entry's
  `fetched_at` is what every claim built from the page carries (never the build clock). A stable absence
  (404/410) is cached too when the caller asks, so an offline rebuild sees exactly what the crawl saw.
- **Offline.** A fetcher without a transport reads the cache only; a miss is a `FetchError`, never a
  network call. `op snapshot build` mines through one.
- **Politeness.** At most one request per `min_interval` seconds; 429 and 5xx are retried, honouring
  `Retry-After` (seconds or an HTTP date) or `ratelimit-reset`, else an exponential back-off; any other 4xx
  raises at once (retrying a refusal spends the host's patience). A truncated body (no `</html>`) is retried
  inside the loop. A wait longer than `max_wait` aborts the crawl instead of sleeping for hours.
- **Scope.** Only https URLs on the source's hosts are fetched, a redirect off them is refused, and the
  query string and fragment are dropped (real links carry `?utm_source=…`).
"""

from __future__ import annotations

import email.utils
import hashlib
import http.client
import json
import logging
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse, urlunparse

from openproceedings import __version__, storage
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)

USER_AGENT = f"openproceedings/{__version__} (systematic-review search index; one request per second)"
MAX_BODY = 20 * 1024 * 1024  # a proceedings page is well under 1 MB; anything this big is not one
_KEEP_HEADERS = ("content-type",)
_ABSENT = frozenset({404, 410})
_CHARSET = re.compile(r"charset=([A-Za-z0-9._-]+)", re.IGNORECASE)


class FetchError(Exception):
    """A page could not be had: the message names the URL, `reason` is a constant for the log."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Response:
    """What a transport returns: the final URL (after redirects), status, lower-cased headers, raw body."""

    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes


class Transport(Protocol):
    def __call__(self, url: str, timeout: float) -> Response: ...


def urllib_transport(url: str, timeout: float) -> Response:
    """The live transport (stdlib only). Tests never use it: conftest blocks the network."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return Response(resp.geturl(), resp.status, headers, resp.read(MAX_BODY + 1))
    except urllib.error.HTTPError as e:
        headers = {k.lower(): v for k, v in (e.headers or {}).items()}
        return Response(e.geturl() or url, e.code, headers, e.read(MAX_BODY + 1) if e.fp else b"")


@dataclass(frozen=True, slots=True)
class Page:
    """A fetched page: `text` is empty unless `status` is 200; `fetched_at` is the cache entry's time."""

    url: str
    status: int
    text: str
    fetched_at: datetime
    content_type: str = "text/html; charset=utf-8"

    @property
    def ok(self) -> bool:
        return self.status == 200


def canonical(url: str) -> str:
    """https, lower-case host, no query string or fragment: the form fetched and cached."""
    p = urlparse(url)
    return urlunparse(("https", p.netloc.lower(), p.path or "/", "", "", ""))


class CacheError(Exception):
    """A cache entry is unreadable or names another URL: the message says which file to delete."""


class PageCache:
    """The raw page cache for one source (`<data>/cache/<source>`)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.root / "pages" / key[:2] / f"{key}.json"

    def get(self, url: str) -> Page | None:
        path = self.path(url)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            raise CacheError(f"cache entry {path.name} is unreadable ({type(e).__name__}); delete it") from e
        try:
            if data["request"]["url"] != url:
                raise CacheError(f"cache entry {path.name} names another URL; delete it")
            response = data["response"]
            fetched_at = datetime.fromisoformat(data["fetched_at"])
            if fetched_at.tzinfo is None:
                raise ValueError("naive fetched_at")
            return Page(
                url=url, status=int(response["status"]), text=str(response.get("text", "")),
                fetched_at=fetched_at.astimezone(UTC),
                content_type=str(response.get("headers", {}).get("content-type", "")),
            )  # fmt: skip
        except (KeyError, TypeError, ValueError) as e:
            raise CacheError(f"cache entry {path.name} is malformed ({type(e).__name__}); delete it") from e

    def put(self, page: Page) -> None:
        """Write one entry atomically (temp file in the same directory, fsync, rename)."""
        path = self.path(page.url)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "fetched_at": page.fetched_at.astimezone(UTC).isoformat(),
            "request": {"method": "GET", "url": page.url},
            "response": {
                "status": page.status,
                "headers": {"content-type": page.content_type},
                "text": page.text,
            },
        }
        data = (json.dumps(entry, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=storage.TMP, suffix=".json")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                storage.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def _retry_after(headers: Mapping[str, str], now: datetime) -> float | None:
    """Seconds to wait from `Retry-After` (seconds or an HTTP date) or `ratelimit-reset` (seconds)."""
    for name in ("retry-after", "ratelimit-reset"):
        value = headers.get(name, "").strip()
        if not value:
            continue
        if value.isdigit():
            return float(value)
        try:
            when = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return max(0.0, (when - now).total_seconds())
    return None


@dataclass
class FetchStats:
    network: int = 0  # requests sent
    cached: int = 0  # pages served from the cache
    retries: int = 0


class Fetcher:
    """Cache first; then, with a transport, a paced, retrying fetch that fills the cache."""

    def __init__(
        self,
        cache: PageCache,
        transport: Transport | None,
        *,
        hosts: frozenset[str],
        min_interval: float = 1.0,
        attempts: int = 5,
        max_wait: float = 3600.0,
        timeout: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.cache, self.transport, self.hosts = cache, transport, hosts
        self.min_interval, self.attempts, self.max_wait, self.timeout = (
            min_interval,
            attempts,
            max_wait,
            timeout,
        )
        self._sleep, self._clock, self._now = sleep, clock, now
        self._last: float | None = None
        self.stats = FetchStats()

    @property
    def offline(self) -> bool:
        return self.transport is None

    def check(self, url: str) -> str:
        """The canonical form of `url`, or a FetchError if it is off this source's hosts."""
        host = urlparse(url).netloc.lower()
        if urlparse(url).scheme not in ("http", "https") or host not in self.hosts:
            raise FetchError(f"{url!r} is not on {sorted(self.hosts)}", reason="off_host")
        return canonical(url)

    def cached(self, url: str) -> bool:
        return self.cache.get(self.check(url)) is not None

    def get(self, url: str, *, refresh: bool = False, keep_absent: bool = False) -> Page:
        """The page at `url`: from the cache unless `refresh`, else fetched (and cached when it is a 200,
        or a 404/410 with `keep_absent`). Offline, a miss raises instead of fetching."""
        url = self.check(url)
        if not refresh and (page := self.cache.get(url)) is not None:
            self.stats.cached += 1
            return page
        if self.transport is None:
            raise FetchError(f"{url} is not in the cache (offline)", reason="not_cached")
        page = self._fetch(url)
        if page.ok or (keep_absent and page.status in _ABSENT):
            self.cache.put(page)
        return page

    def _pace(self) -> None:
        if self._last is not None and (wait := self.min_interval - (self._clock() - self._last)) > 0:
            self._sleep(wait)
        self._last = self._clock()

    def _backoff(self, attempt: int) -> float:
        return float(min(5 * 2 ** (attempt - 1), 300))

    def _wait(self, seconds: float, url: str, why: str, attempt: int) -> None:
        if seconds > self.max_wait:
            raise FetchError(f"{url}: asked to wait {seconds:.0f}s ({why})", reason="wait_too_long")
        self.stats.retries += 1
        log.warning(
            "crawl_fetch_backoff",
            extra={"host": urlparse(url).netloc, "why": why, "attempt": attempt, "wait_s": round(seconds, 1)},
        )
        self._sleep(seconds)

    def _fetch(self, url: str) -> Page:
        assert self.transport is not None
        for attempt in range(1, self.attempts + 1):
            self._pace()
            started = time.monotonic()
            try:
                resp = self.transport(url, self.timeout)
            except (OSError, http.client.HTTPException) as e:  # URLError and timeouts are OSErrors
                self.stats.network += 1
                self._wait(self._backoff(attempt), url, type(e).__name__, attempt)
                continue
            self.stats.network += 1
            if canonical(resp.url) != url:
                self.check(resp.url)  # a redirect: it must stay on this source's hosts
            log.debug(
                "crawl_page_fetched",
                extra={"url": url, "status": resp.status, "ms": elapsed_ms(started, time.monotonic)},
            )
            if resp.status == 200:
                if len(resp.body) > MAX_BODY:
                    raise FetchError(f"{url}: body over {MAX_BODY} bytes", reason="too_large")
                if b"</html>" not in resp.body[-4096:].lower():
                    self._wait(self._backoff(attempt), url, "truncated", attempt)
                    continue
                content_type = resp.headers.get("content-type", "text/html; charset=utf-8")
                charset = m.group(1) if (m := _CHARSET.search(content_type)) else "utf-8"
                try:
                    text = resp.body.decode(charset)
                except (LookupError, UnicodeDecodeError) as e:
                    raise FetchError(f"{url}: body is not {charset}", reason="undecodable") from e
                return Page(url, 200, text, self._now(), content_type)
            if resp.status in _ABSENT:
                return Page(url, resp.status, "", self._now(), resp.headers.get("content-type", ""))
            if resp.status == 429 or resp.status >= 500:
                wait = _retry_after(resp.headers, self._now())
                self._wait(
                    self._backoff(attempt) if wait is None else wait, url, f"http_{resp.status}", attempt
                )
                continue
            raise FetchError(f"{url}: HTTP {resp.status}", reason=f"http_{resp.status}")
        raise FetchError(f"{url}: gave up after {self.attempts} attempts", reason="retries_exhausted")


def entry_from_fixture(fixture: Mapping[str, Any], fetched_at: datetime) -> Page:
    """A cache page from a recorded fixture (`request`, `response`): how tests and a person seed a cache."""
    response = fixture["response"]
    return Page(
        url=canonical(fixture["request"]["url"]), status=int(response["status"]),
        text=str(response.get("text", "")), fetched_at=fetched_at,
        content_type=str(response.get("headers", {}).get("content-type", "")),
    )  # fmt: skip
