"""The crawlers' one HTTP layer (spec 01 §Pipeline; TASK-103): every source (OpenReview API v2 and v1, the
ICLR archive, NeurIPS proceedings and PMLR) fetches through `HttpClient`, and only the source's own rules
(`Policy`) differ.

- **Transport.** `transport(Request, timeout) -> Response`, swappable (tests script one; conftest blocks the
  network). The live one (`urllib_transport`) never follows a redirect (a 3xx is a response, never a hop to
  another host carrying a bearer token) and reads at most `max_body + 1` bytes.
- **Scope.** Only `http(s)` URLs on the source's hosts are ever sent (`Policy.hosts`, one allowlist); a
  response naming another URL off them is refused. `canonical` is the one URL form fetched and cached: https,
  a lower-case host, no fragment, and no query string unless the source keys on it (OpenReview's sorted
  parameters; the proceedings drop `?utm_source=…`).
- **Politeness.** At least `min_interval` seconds between requests. 429 and 5xx wait for `Retry-After`
  (seconds or an HTTP date), else `ratelimit-reset` (seconds from now; never `x-ratelimit-reset`, an epoch),
  else an exponential back-off (`backoff[0] · 2^n`, capped at `backoff[1]`, plus jitter); so do a network
  error and a truncated 200 (an HTML page without `</html>`, or JSON that doesn't parse). A spent budget
  (`ratelimit-remaining: 0` on a 200) waits for its reset. A wait past `max_wait` is capped or aborts the
  crawl (`cap_waits`). Any other response is returned for the source to judge; retries are bounded.
- **Cache.** `ResponseCache`: one JSON file per canonical URL under `<root>/[<subdir>/]<sha256[:2]>/<sha256>.json`,
  naming its URL, written atomically (`storage.write_json`), so a crash never leaves half an entry and a crawl
  resumes where it stopped. A codec shapes the entry, so each source's on-disk layout is unchanged: the
  proceedings' fixture-shaped pages (`PageCodec`), OpenReview's `{key, payload}` documents. A client without a
  transport reads the cache only; a miss is `CacheMiss`, never a network call. The entry's fetch time is what
  every claim built from it carries.
- **Expiry** (TASK-102). `Policy.ttl(url, now)` is how long an entry for `url` stays fresh (seconds; None: never
  expires). A live client re-fetches an entry older than that, logs its policy's `cache_expired` event
  (`crawl_cache_expired`, `openreview_cache_expired`) and overwrites it;
  a client without a transport never expires anything, so an offline replay (`op snapshot build`) reads the
  same bytes whenever it runs. The proceedings never expire; OpenReview's TTLs are `openreview_client.ttl`.
- **Log events.** A policy's event names are fixed constants (`PolicyEvents`: `CRAWL_EVENTS` here,
  `openreview_client.EVENTS`), never built from a prefix, so every name is greppable (TASK-116).
- **Errors.** One hierarchy under `SourceError` (each with a `reason` constant for the log), handled once in
  `cli.main` and in `snapshot.load_sources`. No message holds a credential, a token or response text.

The proceedings' page fetcher (`Fetcher`, `Page`, `PageCache`) is here too; OpenReview's login and JSON
entries are layered on top in `openreview_client`. So is `fetch_file`, for a file too large to hold in memory
that is named by its bytes (`PinnedFile`: URL, size, sha256; the dblp release, TASK-205): streamed to a `.tmp-`
file through the same host check, no-redirect rule and retry waits, kept only when it hashes to the pin, and
read from disk afterwards (a sidecar `<name>.json` records the download time every claim from it carries).
"""

from __future__ import annotations

import email.utils
import functools
import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urlparse, urlunparse

from openproceedings import __version__, storage
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)

USER_AGENT = (
    f"openproceedings/{__version__} (+https://github.com/uw-share-lab/openproceedings; systematic-review search "
    "index; one request per second)"
)
_ABSENT = frozenset({404, 410})
_CHARSET = re.compile(r"charset=([A-Za-z0-9._-]+)", re.IGNORECASE)
_TOO_LARGE = "body_too_large"


# --- errors ------------------------------------------------------------------------------------------------


class SourceError(Exception):
    """A crawl or replay refused or failed. The message says why and what to do (never a credential, a token
    or response text); `reason` is a short constant a log line may carry."""

    reason = "source_failed"

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        if reason is not None:
            self.reason = reason


class FetchError(SourceError):
    """A response could not be had: off the hosts, too large, a wait too long, a refusal, retries spent."""

    reason = "fetch_failed"


class CacheMiss(FetchError):
    """A client without a transport (`--offline`, a dry run, a snapshot build) needed an uncached URL."""

    reason = "not_cached"

    def __init__(self, url: str) -> None:
        super().__init__(
            f"{url} is not in the cache (offline): not cached yet; run without --offline to fetch it"
        )
        self.url = url


class RetriesExhausted(FetchError):
    reason = "retries_exhausted"


class HTTPRefused(FetchError):
    """A status the source doesn't retry (a 4xx other than 429, a 3xx): raised at once, since retrying a
    refusal spends the host's patience. `name` is an API's error name (`NotFoundError`), never its message."""

    def __init__(self, url: str, status: int, name: str | None = None) -> None:
        super().__init__(f"{url}: HTTP {status}{' ' + name if name else ''}", reason=f"http_{status}")
        self.status = status
        self.name = name


class CacheError(SourceError):
    """A cache entry is unreadable or names another URL: the message says which file to delete."""

    reason = "cache_invalid"


class TransportError(Exception):
    """The request never produced a usable HTTP response (DNS, connect, timeout, reset, a body over the cap)."""


# --- transport ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Request:
    method: str
    url: str
    headers: Mapping[str, str] = field(repr=False)
    body: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Response:
    """What a transport returns: status, lower-case headers, the raw body, and the URL it answered for (empty
    when it is the request's)."""

    status: int
    headers: Mapping[str, str]  # lower-case names
    body: bytes = field(repr=False)
    url: str = ""


Transport = Callable[[Request, float], Response]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # the 3xx surfaces as an HTTPError: a response, never a hop to another host


_OPENER = urllib.request.build_opener(_NoRedirect)


def urllib_transport(request: Request, timeout: float = 60.0, max_body: int = 64 * 1024 * 1024) -> Response:
    """One HTTP exchange with the standard library: no redirects, a timeout, a bounded body. The live
    transport; tests never use it against a real host (conftest blocks the network)."""
    req = urllib.request.Request(request.url, data=request.body, headers=dict(request.headers),
                                 method=request.method)  # fmt: skip
    try:
        try:
            with _OPENER.open(req, timeout=timeout) as resp:
                status, headers, body = resp.status, resp.headers, resp.read(max_body + 1)
        except urllib.error.HTTPError as e:
            status, headers = e.code, e.headers
            try:
                body = e.read(max_body + 1)
            except (OSError, HTTPException):
                body = b""
    except (urllib.error.URLError, OSError, HTTPException, ValueError) as e:
        # a ValueError is a header http.client won't send; its message quotes the value (a bearer token), so
        # only the type goes on (TASK-067)
        raise TransportError(type(e).__name__) from None
    if len(body) > max_body:
        raise TransportError(_TOO_LARGE)
    return Response(status, {k.lower(): v for k, v in (headers or {}).items()}, body)


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...
    def now(self) -> datetime: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def now(self) -> datetime:
        return datetime.now(UTC)


# --- URLs, waits, the policy -------------------------------------------------------------------------------


def canonical(url: str, *, keep_query: bool = False) -> str:
    """https, lower-case host, no fragment, and no query string unless `keep_query`: the form fetched and
    cached."""
    p = urlparse(url)
    return urlunparse(("https", p.netloc.lower(), p.path or "/", "", p.query if keep_query else "", ""))


def _seconds(raw: str | None) -> float | None:
    text = (raw or "").strip()
    return float(text) if text.replace(".", "", 1).isdigit() else None


def retry_after(headers: Mapping[str, str], now: datetime) -> float | None:
    """Seconds to wait from `Retry-After` (seconds or an HTTP date), else `ratelimit-reset` (seconds from
    now); never `x-ratelimit-reset` (an epoch). None when neither says."""
    raw = headers.get("retry-after", "").strip()
    if (seconds := _seconds(raw)) is not None:
        return seconds
    if raw:
        try:
            when = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            when = None
        if when is not None:
            return max(0.0, (when if when.tzinfo else when.replace(tzinfo=UTC)).timestamp() - now.timestamp())
    return _seconds(headers.get("ratelimit-reset"))


def _no_jitter() -> float:
    return 0.0


def never_expires(url: str, now: datetime) -> float | None:
    """The default `Policy.ttl`: a cached response stays fresh for good (only `--refresh` re-fetches it)."""
    return None


@dataclass(frozen=True)
class PolicyEvents:
    """One policy's log event names, each a fixed constant (logging-standards: `event` is a constant)."""

    retry_wait: str  # WARNING: a 429, a 5xx, a network error or a truncated 200, waited out
    budget_wait: str  # INFO: a spent rate-limit budget, waited out
    cache_expired: str  # INFO: a cached entry past its TTL, re-fetched


CRAWL_EVENTS = PolicyEvents(
    retry_wait="crawl_retry_wait", budget_wait="crawl_budget_wait", cache_expired="crawl_cache_expired"
)


@dataclass(frozen=True)
class Policy:
    """One source's rules for the shared client. The defaults are the proceedings crawlers';
    `openreview_client.POLICY` is OpenReview's."""

    hosts: frozenset[str]
    accept: str = "text/html"
    expect: Literal["html", "json"] = "html"  # how a truncated 200 is recognised (and retried)
    keep_query: bool = False  # does the query string name the resource (and the cache entry)?
    min_interval: float = 1.0
    attempts: int = 5
    backoff: tuple[float, float] = (5.0, 300.0)  # the first step and the cap, in seconds
    jitter: Callable[[], float] = _no_jitter
    hint_pad: float = 0.0  # added to a server-named wait (Retry-After, ratelimit-reset)
    max_wait: float = 3600.0
    cap_waits: bool = False  # a wait past max_wait: True waits max_wait, False aborts the crawl
    wait_after_last: bool = True  # back off after the last attempt too (a resumed run starts rested)
    max_body: int = 20 * 1024 * 1024
    timeout: float = 30.0
    events: PolicyEvents = CRAWL_EVENTS  # its log event names (fixed constants)
    # how long a cached response to `url` stays fresh at `now` (seconds; None: for good); only a live client
    # expires anything (module docstring, Expiry)
    ttl: Callable[[str, datetime], float | None] = never_expires


@dataclass
class FetchStats:
    network: int = 0  # requests sent (every attempt, login included)
    cached: int = 0  # answered from the cache
    retries: int = 0
    expired: int = 0  # cache entries past their TTL, re-fetched


# --- the cache ---------------------------------------------------------------------------------------------


class Codec[T](Protocol):
    """How one source's entries sit on disk (its layout predates the shared cache, so it is kept)."""

    subdir: str  # under the cache root ("" for none)

    def key(self, entry: T) -> str: ...
    def encode(self, entry: T) -> dict[str, Any]: ...
    def decode(self, document: dict[str, Any]) -> tuple[str, T]: ...  # (the URL it names, the entry)
    def fetched_at(self, entry: T) -> datetime: ...  # when the entry was fetched (its age, for expiry)


def cache_name(url: str) -> str:
    """A cache entry's name under its codec's directory: `<sha256[:2]>/<sha256>.json` of the canonical URL."""
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"{key[:2]}/{key}.json"


class ResponseCache[T]:
    """One source's response cache: sha256-named files (never a path from URL text), atomic writes."""

    def __init__(self, root: Path, codec: Codec[T]) -> None:
        self.root, self.codec = root, codec

    def path(self, url: str) -> Path:
        return self.root / self.codec.subdir / cache_name(url)

    def get(self, url: str) -> T | None:
        path = self.path(url)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            raise CacheError(f"cache entry {path.name} is unreadable ({type(e).__name__}); delete it") from e
        try:
            named, entry = self.codec.decode(document)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise CacheError(f"cache entry {path.name} is malformed ({type(e).__name__}); delete it") from e
        if named != url:
            raise CacheError(f"cache entry {path.name} names another URL; delete it")
        return entry

    def put(self, entry: T) -> None:
        storage.write_json(self.path(self.codec.key(entry)), self.codec.encode(entry))


# --- the client --------------------------------------------------------------------------------------------


class HttpClient[T]:
    """Cache first; then, with a transport, a paced, retrying exchange (the module docstring's rules)."""

    def __init__(self, cache: ResponseCache[T], transport: Transport | None, policy: Policy,
                 clock: Clock | None = None) -> None:  # fmt: skip
        if transport is urllib_transport:  # the live transport reads no more than this policy's body bound
            transport = functools.partial(urllib_transport, max_body=policy.max_body)
        self.cache, self.transport, self.policy = cache, transport, policy
        self.clock: Clock = clock or SystemClock()
        self.stats = FetchStats()
        self._last: float | None = None

    @property
    def offline(self) -> bool:
        return self.transport is None

    def check(self, url: str) -> str:
        """The canonical form of `url`, or a FetchError if it is off this source's hosts."""
        p = urlparse(url)
        if p.scheme not in ("http", "https") or p.netloc.lower() not in self.policy.hosts:
            raise FetchError(f"{url!r} is not on {sorted(self.policy.hosts)}", reason="off_host")
        return canonical(url, keep_query=self.policy.keep_query)

    def is_cached(self, url: str) -> bool:
        return self.cache.get(self.check(url)) is not None

    def through_cache(self, url: str, fetch: Callable[[str], tuple[T, bool]], *, refresh: bool = False) -> T:
        """The cached entry for `url` unless `refresh`; else `fetch(url)` → (entry, keep?), stored when kept.
        A live client re-fetches an entry past its TTL (`Policy.ttl`); offline, nothing expires and a miss
        raises instead of fetching."""
        url = self.check(url)
        hit = None if refresh else self.cache.get(url)
        if hit is not None and (self.transport is None or not self._expired(url, hit)):
            self.stats.cached += 1
            return hit
        if self.transport is None:
            raise CacheMiss(url)
        entry, keep = fetch(url)
        if keep:
            self.cache.put(entry)
        return entry

    def _expired(self, url: str, entry: T) -> bool:
        """Whether `entry` (cached for `url`) is past the policy's TTL; an expiry is counted and logged."""
        now = self.clock.now()
        if (ttl := self.policy.ttl(url, now)) is None:
            return False
        age = (now - self.cache.codec.fetched_at(entry)).total_seconds()
        if age <= ttl:
            return False
        self.stats.expired += 1
        log.info(self.policy.events.cache_expired,
                 extra={"url": url, "age_s": round(age), "ttl_s": round(ttl)})  # fmt: skip
        return True

    def send(self, request: Request) -> Response:
        """One request, paced, retried on 429, 5xx, a network error and a truncated 200; any other response
        is returned for the source to judge."""
        assert self.transport is not None
        policy, url = self.policy, self.check(request.url)
        request = replace(request, url=url)  # only the canonical form is ever sent
        for attempt in range(policy.attempts):
            self._pace()
            started = time.monotonic()
            response, hint = None, None
            try:
                response = self.transport(request, policy.timeout)
            except TransportError as e:
                if str(e) == _TOO_LARGE:
                    raise FetchError(
                        f"{url}: body over {policy.max_body} bytes", reason="too_large"
                    ) from None
                why = str(e)
            except (OSError, HTTPException) as e:  # a scripted transport's timeout, a reset
                why = type(e).__name__
            finally:
                self._last = self.clock.monotonic()
                self.stats.network += 1
            if response is not None:
                if response.url and canonical(response.url, keep_query=policy.keep_query) != url:
                    self.check(response.url)  # it answered for another URL: that must be on the hosts too
                log.debug("crawl_page_fetched", extra={"url": url, "status": response.status,
                                                       "ms": elapsed_ms(started, time.monotonic)})  # fmt: skip
                if len(response.body) > policy.max_body:
                    raise FetchError(f"{url}: body over {policy.max_body} bytes", reason="too_large")
                if response.status == 429 or response.status >= 500:
                    why, hint = f"http_{response.status}", retry_after(response.headers, self.clock.now())
                elif response.status == 200 and self._truncated(response):
                    why = "truncated"
                else:
                    if response.status == 200:
                        self._respect_budget(response, url)
                    return response
            if attempt + 1 < policy.attempts or policy.wait_after_last:
                wait = self._backoff(attempt) if hint is None else hint
                self._wait(self._bounded(wait, url, why) + (0.0 if hint is None else policy.hint_pad), url, why,
                           attempt + 1)  # fmt: skip
        raise RetriesExhausted(
            f"{url}: gave up after {policy.attempts} attempts; re-run later (cached responses are not fetched again)"
        )

    def _truncated(self, response: Response) -> bool:
        if self.policy.expect == "html":
            return b"</html>" not in response.body[-4096:].lower()
        if not is_json(response):
            return False  # not JSON at all (a challenge page): the source judges it
        try:
            json.loads(response.body)
        except ValueError:
            return True
        return False

    def _pace(self) -> None:
        if (
            self._last is not None
            and (wait := self.policy.min_interval - (self.clock.monotonic() - self._last)) > 0
        ):
            self.clock.sleep(wait)

    def _backoff(self, attempt: int) -> float:
        first, cap = self.policy.backoff
        return float(min(first * 2**attempt, cap)) + self.policy.jitter()

    def _bounded(self, seconds: float, url: str, why: str) -> float:
        """`seconds`, unless past `max_wait`: then `max_wait` (`cap_waits`), or the crawl aborts."""
        if seconds <= self.policy.max_wait:
            return max(seconds, 0.0)
        if self.policy.cap_waits:
            return self.policy.max_wait
        raise FetchError(f"{url}: asked to wait {seconds:.0f}s ({why})", reason="wait_too_long")

    def _wait(self, seconds: float, url: str, why: str, attempt: int) -> None:
        self.stats.retries += 1
        log.warning(self.policy.events.retry_wait, extra={
            "host": urlparse(url).netloc, "why": why, "attempt": attempt, "wait_s": round(seconds, 1)})  # fmt: skip
        self.clock.sleep(seconds)

    def _respect_budget(self, response: Response, url: str) -> None:
        """When the window's budget is spent, wait for it to reset (`ratelimit-reset`, seconds from now)."""
        remaining = _seconds(response.headers.get("ratelimit-remaining"))
        if remaining is None or remaining > 0:
            return
        reset = _seconds(response.headers.get("ratelimit-reset"))
        wait = min(60.0 if reset is None else reset, self.policy.max_wait) + self.policy.hint_pad
        log.info(self.policy.events.budget_wait,
                 extra={"host": urlparse(url).netloc, "wait_s": round(wait, 1)})  # fmt: skip
        self.clock.sleep(wait)


def is_json(response: Response) -> bool:
    return response.headers.get("content-type", "").split(";")[0].strip().lower() == "application/json"


def error_name(response: Response) -> str | None:
    """An API's error `name` (`ValidationError`, `NotFoundError`), never its message (it may quote input)."""
    try:
        name = json.loads(response.body).get("name")
    except (ValueError, AttributeError):
        return None
    return name if isinstance(name, str) and name.isidentifier() else None


# --- the proceedings' pages ---------------------------------------------------------------------------------


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


class PageCodec:
    """`<cache>/<source>/pages/…`: shaped like a recorded fixture (`request`, `response`) plus `fetched_at`."""

    subdir = "pages"

    def key(self, entry: Page) -> str:
        return entry.url

    def encode(self, entry: Page) -> dict[str, Any]:
        return {
            "fetched_at": entry.fetched_at.astimezone(UTC).isoformat(),
            "request": {"method": "GET", "url": entry.url},
            "response": {"status": entry.status, "headers": {"content-type": entry.content_type},
                         "text": entry.text},
        }  # fmt: skip

    def fetched_at(self, entry: Page) -> datetime:
        return entry.fetched_at

    def decode(self, document: dict[str, Any]) -> tuple[str, Page]:
        url, response = document["request"]["url"], document["response"]
        fetched_at = datetime.fromisoformat(document["fetched_at"])
        if fetched_at.tzinfo is None:
            raise ValueError("naive fetched_at")
        return url, Page(
            url=url, status=int(response["status"]), text=str(response.get("text", "")),
            fetched_at=fetched_at.astimezone(UTC), content_type=str(response.get("headers", {}).get("content-type", "")),
        )  # fmt: skip


def PageCache(root: Path) -> ResponseCache[Page]:
    """The raw page cache for one proceedings source (`<data>/cache/<source>`)."""
    return ResponseCache(root, PageCodec())


PROCEEDINGS = Policy(hosts=frozenset())


class Fetcher(HttpClient[Page]):
    """The proceedings crawlers' page fetcher: `HttpClient` with the proceedings' policy, keeping 200s (and,
    when asked, a stable absence) as `Page`s."""

    def __init__(
        self, cache: ResponseCache[Page], transport: Transport | None, *, hosts: frozenset[str],
        min_interval: float = 1.0, attempts: int = 5, max_wait: float = 3600.0, timeout: float = 30.0,
        clock: Clock | None = None,
    ) -> None:  # fmt: skip
        policy = replace(PROCEEDINGS, hosts=hosts, min_interval=min_interval, attempts=attempts,
                         max_wait=max_wait, timeout=timeout)  # fmt: skip
        super().__init__(cache, transport, policy, clock)

    def get(
        self, url: str, *, refresh: bool = False, keep_absent: bool = False, charset: str = "utf-8"
    ) -> Page:
        """The page at `url`: from the cache unless `refresh`, else fetched (and cached when it is a 200, or a
        404/410 with `keep_absent`). Offline, a miss raises instead of fetching. `charset` decodes a body whose
        `Content-Type` names none (a 1990s-2000s page served as bare `text/html`, TASK-206); one the response
        names always wins."""

        def fetch(canonical_url: str) -> tuple[Page, bool]:
            page = self._page(canonical_url, charset)
            return page, page.ok or (keep_absent and page.status in _ABSENT)

        return self.through_cache(url, fetch, refresh=refresh)

    def _page(self, url: str, default_charset: str = "utf-8") -> Page:
        request = Request("GET", url, {"User-Agent": USER_AGENT, "Accept": self.policy.accept})
        resp = self.send(request)
        if resp.status == 200:
            content_type = resp.headers.get("content-type", "text/html; charset=utf-8")
            charset = m.group(1) if (m := _CHARSET.search(content_type)) else default_charset
            try:
                text = resp.body.decode(charset)
            except (LookupError, UnicodeDecodeError) as e:
                raise FetchError(f"{url}: body is not {charset}", reason="undecodable") from e
            return Page(url, 200, text, self.clock.now(), content_type)
        if resp.status in _ABSENT:
            return Page(url, resp.status, "", self.clock.now(), resp.headers.get("content-type", ""))
        raise HTTPRefused(url, resp.status)


# --- a pinned file (the dblp release, TASK-205) ----------------------------------------------------------------


@dataclass(frozen=True)
class StreamResponse:
    """A response whose body is read in chunks, never held whole: status, lower-case headers, the chunks, and
    how to release the connection."""

    status: int
    headers: Mapping[str, str]
    chunks: Iterable[bytes] = field(repr=False)
    close: Callable[[], None] = field(default=lambda: None, repr=False)


StreamTransport = Callable[[Request, float], StreamResponse]
CHUNK = 1024 * 1024


def urllib_stream(request: Request, timeout: float = 60.0) -> StreamResponse:
    """The live streaming transport: no redirects (a 3xx is a response), the body read in `CHUNK`s. Tests never
    use it against a real host (conftest blocks the network)."""
    req = urllib.request.Request(request.url, headers=dict(request.headers), method=request.method)
    try:
        try:
            resp = _OPENER.open(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            e.close()
            return StreamResponse(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, ())
    except (urllib.error.URLError, OSError, HTTPException, ValueError) as e:
        raise TransportError(type(e).__name__) from None

    def chunks() -> Iterator[bytes]:
        try:
            while block := resp.read(CHUNK):
                yield block
        except (OSError, HTTPException) as e:
            raise TransportError(type(e).__name__) from None

    return StreamResponse(resp.status, {k.lower(): v for k, v in resp.headers.items()}, chunks(), resp.close)


@dataclass(frozen=True)
class PinnedFile:
    """A file named by its exact bytes: where it is published, its size and its sha256 (guarantee 4: the same
    pin is the same input). A download that doesn't hash to the pin is refused and never kept."""

    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class FileEntry:
    path: Path
    fetched_at: datetime  # when the pinned bytes were downloaded (every claim built from them carries it)
    cached: bool  # True: already on disk and verified, nothing fetched


def _sidecar(path: Path) -> Path:
    return path.with_name(f"{path.name}.json")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def fetch_file(
    pinned: PinnedFile, path: Path, transport: StreamTransport | None, *, hosts: frozenset[str],
    attempts: int = 3, backoff: tuple[float, float] = (5.0, 300.0), timeout: float = 60.0, max_wait: float = 3600.0,
    clock: Clock | None = None, verify: Callable[[Path], str] = file_sha256,
) -> FileEntry:  # fmt: skip
    """The pinned file at `path`: the copy on disk when it hashes to the pin (its sidecar `<name>.json` names the
    URL, the sha256 and the download time), else downloaded once through `transport` (only `hosts`, no
    redirect, 429/5xx and network errors retried with `Retry-After` or back-off, any other status refused),
    streamed to a `.tmp-` file while hashing, checked against the pin's size and sha256, and renamed into place
    with its sidecar. Without a transport (offline) a missing or mismatched copy is a `CacheMiss`."""
    clock = clock or SystemClock()
    p = urlparse(pinned.url)
    if p.scheme != "https" or p.netloc.lower() not in hosts:
        raise FetchError(f"{pinned.url!r} is not on {sorted(hosts)}", reason="off_host")
    side = _sidecar(path)
    if path.exists() and side.exists():
        try:
            meta = json.loads(side.read_text(encoding="utf-8"))
            fetched = datetime.fromisoformat(meta["fetched_at"])
            named = (meta["url"], meta["sha256"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise CacheError(
                f"{side.name} is unreadable ({type(e).__name__}); delete it and {path.name}"
            ) from e
        if fetched.tzinfo is None:
            raise CacheError(f"{side.name} has a naive fetched_at; delete it and {path.name}")
        if named != (pinned.url, pinned.sha256):
            reason = "sidecar_mismatch"
        elif path.stat().st_size != pinned.size:
            reason = "size_mismatch"
        else:
            log.info("pinned_file_verify_started", extra={"file": path.name, "bytes": pinned.size})
            reason = "hash_mismatch" if verify(path) != pinned.sha256 else ""
        if not reason:
            return FileEntry(path, fetched.astimezone(UTC), cached=True)
        log.warning("pinned_file_mismatch", extra={"file": path.name, "reason": reason})
    if transport is None:
        raise CacheMiss(pinned.url)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{storage.TMP}{path.name}")
    request = Request("GET", pinned.url, {"User-Agent": USER_AGENT, "Accept": "*/*"})
    log.info("pinned_file_fetch_started", extra={"file": path.name, "bytes_expected": pinned.size})
    for attempt in range(attempts):
        started = time.monotonic()
        hint: float | None = None
        try:
            response = transport(request, timeout)
        except TransportError as e:
            why = str(e)
        else:
            try:
                if response.status == 200:
                    digest, size = _stream_to(tmp, response.chunks, pinned.size, clock, path.name)
                    if (size, digest) != (pinned.size, pinned.sha256):
                        tmp.unlink(missing_ok=True)
                        raise FetchError(
                            f"{pinned.url}: {size} bytes with sha256 {digest[:12]}…, not the pinned "
                            f"{pinned.size} bytes / {pinned.sha256[:12]}…; the release changed or the pin is wrong",
                            reason="pin_mismatch",
                        )
                    now = clock.now()
                    os.replace(tmp, path)
                    storage.write_json(side, {"url": pinned.url, "sha256": pinned.sha256, "size": pinned.size,
                                              "fetched_at": now.astimezone(UTC).isoformat()})  # fmt: skip
                    log.info("pinned_file_fetched", extra={"file": path.name, "bytes": size,
                                                           "ms": elapsed_ms(started, time.monotonic)})  # fmt: skip
                    return FileEntry(path, now.astimezone(UTC), cached=False)
                if response.status != 429 and response.status < 500:
                    raise HTTPRefused(pinned.url, response.status)
                why, hint = f"http_{response.status}", retry_after(response.headers, clock.now())
            except TransportError as e:
                tmp.unlink(missing_ok=True)
                why = str(e)
            finally:
                response.close()
        if attempt + 1 < attempts:
            if hint is not None and hint > max_wait:  # as HttpClient without cap_waits: never wait that long
                raise FetchError(f"{pinned.url}: asked to wait {hint:.0f}s ({why})", reason="wait_too_long")
            wait = min(backoff[0] * 2**attempt, backoff[1]) if hint is None else hint
            log.warning(CRAWL_EVENTS.retry_wait, extra={"host": p.netloc, "why": why, "attempt": attempt + 1,
                                                         "wait_s": round(wait, 1)})  # fmt: skip
            clock.sleep(wait)
    raise RetriesExhausted(f"{pinned.url}: gave up after {attempts} attempts; re-run later")


PROGRESS_SECONDS = (
    30.0  # a long download: one progress line at most this often (logging-standards §Crawl lines)
)


def _stream_to(tmp: Path, chunks: Iterable[bytes], limit: int, clock: Clock, name: str) -> tuple[str, int]:
    """Write `chunks` to `tmp`, returning (sha256, size); more than `limit` bytes is refused at once
    (`pin_mismatch`). A `pinned_file_progress` line at most every `PROGRESS_SECONDS` of `clock`."""
    digest, size = hashlib.sha256(), 0
    last = clock.monotonic()
    with tmp.open("wb") as fh:
        for block in chunks:
            size += len(block)
            if clock.monotonic() - last >= PROGRESS_SECONDS:
                last = clock.monotonic()
                log.info("pinned_file_progress", extra={"file": name, "bytes": size, "of": limit})
            if size > limit:  # not the pinned file: refused at once, never fetched again in full
                fh.close()
                tmp.unlink(missing_ok=True)
                raise FetchError(f"{tmp.name}: over the pinned {limit} bytes; the release changed or the pin is wrong",
                                 reason="pin_mismatch")  # fmt: skip
            digest.update(block)
            fh.write(block)
        fh.flush()
        os.fsync(fh.fileno())
    return digest.hexdigest(), size


def entry_from_fixture(fixture: Mapping[str, Any], fetched_at: datetime) -> Page:
    """A cache page from a recorded fixture (`request`, `response`): how tests and a person seed a cache."""
    response = fixture["response"]
    return Page(
        url=canonical(fixture["request"]["url"]), status=int(response["status"]),
        text=str(response.get("text", "")), fetched_at=fetched_at,
        content_type=str(response.get("headers", {}).get("content-type", "")),
    )  # fmt: skip
