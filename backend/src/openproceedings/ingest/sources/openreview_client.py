"""The OpenReview HTTP client (openreview-api skill; spec 01 §Sources): authenticated, cached, paced.

- **Hosts.** Only `api2.openreview.net` and `api.openreview.net` (API v1, TASK-051) are ever called. URLs are
  built from a fixed base and a path, never taken from a response. Redirects are not followed (an API has
  no reason to send one, and following it would carry the bearer token to another host).
- **Auth.** `OPENREVIEW_USERNAME` / `OPENREVIEW_PASSWORD` from the environment or `.env`, nowhere else. Login
  (`POST <login_base>/login`; a v1 client logs in on api2, whose token api1 accepts) is lazy: a run served
  entirely from the cache needs no credentials and makes no network call. A 401, or an HTML page where JSON was asked for (the "Verifying your browser" challenge anonymous callers get with
  HTTP 200), logs in again once, then fails as `OpenReviewAuthError`: never read as an empty page.
- **Politeness.** At least `min_interval` seconds between requests. When `ratelimit-remaining` reaches 0,
  wait `ratelimit-reset` (seconds from now; never `x-ratelimit-reset`, an epoch), capped at about an hour.
  A 429 waits for `Retry-After` (seconds or an HTTP date), else `ratelimit-reset`, else the backoff. 5xx,
  network errors and a truncated JSON body back off exponentially with jitter. Any other 4xx fails at once:
  retrying a refusal spends budget. Every retry is bounded (`max_attempts`).
- **Cache.** Every successful GET is stored by `scholarmend.cache.Cache` (sha256 of the URL for the file
  name, atomic write) under `<cache>/openreview/<api>/http/`, with the time it was fetched, so a re-run
  never refetches it and a claim's `fetched_at` comes from the cache entry. `offline=True` never touches
  the network (`OpenReviewCacheMiss`); `refresh=True` refetches and overwrites.

Nothing here logs or raises with a credential, the token, a request body or response text.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit

from scholarmend.cache import Cache

from openproceedings import __version__

log = logging.getLogger(__name__)

API_V2 = "https://api2.openreview.net"
API_V1 = "https://api.openreview.net"
HOSTS = frozenset({"api2.openreview.net", "api.openreview.net"})
USER_AGENT = f"openproceedings/{__version__} (+https://github.com/uw-share-lab/openproceedings)"
# the widest window OpenReview advertises is an hour; a hostile header can't park a run longer
MAX_WAIT = 3700.0
MAX_BODY = 64 * 1024 * 1024  # a 1,000-note page is a few MB
KEPT_HEADERS = ("content-type", "ratelimit-policy", "ratelimit-remaining", "ratelimit-reset")


class OpenReviewError(Exception):
    """A crawl refused or failed. The message says why and what to do; it never holds a credential, the
    token or response text. `reason` is a short constant a log line may carry."""

    reason = "openreview_failed"

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        if reason is not None:
            self.reason = reason


class OpenReviewAuthError(OpenReviewError):
    reason = "auth_failed"


class OpenReviewHTTPError(OpenReviewError):
    """A 4xx other than 401/429: not retried."""

    reason = "http_refused"

    def __init__(self, message: str, *, status: int, name: str | None) -> None:
        super().__init__(message)
        self.status = status
        self.name = name


class OpenReviewRetriesExhausted(OpenReviewError):
    reason = "retries_exhausted"


class OpenReviewCacheMiss(OpenReviewError):
    """`offline` (or a dry run) needed a response the cache doesn't hold."""

    reason = "cache_miss"

    def __init__(self, url: str) -> None:
        super().__init__(f"{url} is not cached; run without --offline to fetch it")
        self.url = url


class TransportError(Exception):
    """The request never produced an HTTP response (DNS, connect, timeout, reset): transient."""


@dataclass(frozen=True)
class Credentials:
    username: str = field(repr=False)
    password: str = field(repr=False)


def read_dotenv(path: Path) -> dict[str, str]:
    """`KEY=VALUE` lines of a `.env` file (comments, blank lines and `export ` prefixes ignored; one pair of
    surrounding quotes stripped). A missing file is empty."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def credentials(environ: Mapping[str, str], dotenv: Path | None = None) -> Credentials | None:
    """`OPENREVIEW_USERNAME` / `OPENREVIEW_PASSWORD`: the environment first, then `.env`. None if either
    is missing or empty (scholarmend's `SCHOLARMEND_OPENREVIEW_*` names are not read)."""
    values = {**(read_dotenv(dotenv) if dotenv else {}), **environ}
    user, password = values.get("OPENREVIEW_USERNAME", ""), values.get("OPENREVIEW_PASSWORD", "")
    return Credentials(user, password) if user and password else None


@dataclass(frozen=True)
class Request:
    method: str
    url: str
    headers: Mapping[str, str] = field(repr=False)
    body: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]  # lower-case names
    body: bytes = field(repr=False)


Transport = Callable[[Request], Response]


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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # the 3xx surfaces as an HTTPError: a response, never a hop to another host


_OPENER = urllib.request.build_opener(_NoRedirect)


def urllib_transport(request: Request, timeout: float = 60.0, max_body: int = MAX_BODY) -> Response:
    """One HTTP exchange with the standard library: no redirects, a timeout, a bounded body."""
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
    except (urllib.error.URLError, OSError, HTTPException) as e:
        raise TransportError(type(e).__name__) from None
    if len(body) > max_body:
        raise TransportError("body_too_large")
    return Response(status, {k.lower(): v for k, v in (headers or {}).items()}, body)


def _number(raw: str | None) -> float | None:
    text = (raw or "").strip()
    return float(text) if text.replace(".", "", 1).isdigit() else None


def _capped(seconds: float) -> float:
    return min(max(seconds, 0.0), MAX_WAIT) + 1.0


def _is_json(response: Response) -> bool:
    return response.headers.get("content-type", "").split(";")[0].strip().lower() == "application/json"


def _error_name(response: Response) -> str | None:
    """OpenReview's error `name` (`ValidationError`, `NotFoundError`), never its message (it may quote input)."""
    try:
        name = json.loads(response.body).get("name")
    except (ValueError, AttributeError):
        return None
    return name if isinstance(name, str) and name.isidentifier() else None


class OpenReviewClient:
    """GETs against one OpenReview API, through the disk cache. See the module docstring for the rules."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        credentials: Credentials | None,
        base: str = API_V2,
        login_base: str | None = None,
        transport: Transport = urllib_transport,
        clock: Clock | None = None,
        offline: bool = False,
        refresh: bool = False,
        min_interval: float = 1.0,
        max_attempts: int = 6,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        for url in (base, login_base or base):
            if urlsplit(url).scheme != "https" or urlsplit(url).hostname not in HOSTS or urlsplit(url).path:
                raise ValueError(
                    "the OpenReview base URL must be https://api2.openreview.net or api.openreview.net"
                )
        self.cache = Cache(cache_dir)
        self.base = base
        self.login_base = login_base or base
        self._credentials = credentials
        self._transport = transport
        self._clock: Clock = clock or SystemClock()
        self.offline = offline
        self.refresh = refresh
        self.min_interval = min_interval
        self.max_attempts = max_attempts
        self._jitter = jitter
        self._token: str | None = None
        self._last: float | None = None
        self.requests = 0  # HTTP exchanges made (login included), for reports and tests
        self.cached = 0  # GETs answered from the cache

    def url(self, path: str, params: Mapping[str, str | int]) -> str:
        """The canonical URL (and cache key): parameters sorted, `/` left readable."""
        query = urlencode(sorted((k, str(v)) for k, v in params.items()), safe="/")
        return f"{self.base}{path}" + (f"?{query}" if query else "")

    def cached_get(self, url: str) -> dict[str, Any] | None:
        """The cache entry for `url` (`{"url", "fetched_at", "headers", "json"}`), or None."""
        entry = self.cache.get(url)
        return entry if isinstance(entry, dict) and isinstance(entry.get("json"), dict) else None

    def get(self, path: str, params: Mapping[str, str | int]) -> dict[str, Any]:
        """The cached entry for this GET, fetched (and cached) first if the cache lacks it."""
        url = self.url(path, params)
        if not self.refresh and (hit := self.cached_get(url)) is not None:
            self.cached += 1
            return hit
        if self.offline:
            raise OpenReviewCacheMiss(url)
        response, data = self._authenticated_get(url)
        entry = {
            "url": url,
            "fetched_at": self._clock.now().astimezone(UTC).isoformat(),
            "headers": {k: response.headers[k] for k in KEPT_HEADERS if k in response.headers},
            "json": data,
        }
        self.cache.put(url, entry)
        return entry

    # --- the exchange --------------------------------------------------------------------------------------

    def _pace(self) -> None:
        if self._last is not None:
            wait = self.min_interval - (self._clock.monotonic() - self._last)
            if wait > 0:
                self._clock.sleep(wait)

    def _backoff(self, attempt: int) -> float:
        return float(min(2**attempt, 60)) + self._jitter()

    def _retry_wait(self, response: Response, attempt: int) -> float:
        """A 429's wait: `Retry-After` (seconds or an HTTP date), else `ratelimit-reset`, else the backoff."""
        raw = response.headers.get("retry-after")
        if (seconds := _number(raw)) is not None:
            return _capped(seconds)
        if raw:
            try:
                return _capped((parsedate_to_datetime(raw) - self._clock.now()).total_seconds())
            except (TypeError, ValueError):
                pass
        if (reset := _number(response.headers.get("ratelimit-reset"))) is not None:
            return _capped(reset)
        return self._backoff(attempt)

    def _send(self, request: Request, what: str) -> Response:
        """One request, retried on 429, 5xx, network errors and a truncated JSON body; any other response
        (2xx, 3xx, other 4xx) is returned for the caller to judge. Paces every attempt."""
        for attempt in range(self.max_attempts):
            self._pace()
            try:
                response = self._transport(request)
            except TransportError as e:
                response, wait, why = None, self._backoff(attempt), str(e)
            finally:
                self._last = self._clock.monotonic()
                self.requests += 1
            if response is not None:
                if response.status == 429:
                    wait, why = self._retry_wait(response, attempt), "429"
                elif response.status >= 500:
                    wait, why = self._backoff(attempt), str(response.status)
                elif response.status == 200 and _is_json(response) and not _parses(response.body):
                    wait, why = self._backoff(attempt), "truncated_json"
                else:
                    return response
            if attempt + 1 < self.max_attempts:
                log.warning("openreview_retry_wait",
                            extra={"what": what, "why": why, "attempt": attempt + 1, "wait_s": round(wait, 1)})  # fmt: skip
                self._clock.sleep(wait)
        raise OpenReviewRetriesExhausted(
            f"OpenReview kept failing ({what}) after {self.max_attempts} attempts; re-run later: "
            "cached pages are not fetched again"
        )

    def _login(self) -> str:
        if self._credentials is None:
            raise OpenReviewAuthError(
                "OpenReview needs OPENREVIEW_USERNAME and OPENREVIEW_PASSWORD (in .env or the environment) "
                "to fetch; a run served from the cache (--offline) needs none",
                reason="credentials_missing",
            )
        body = json.dumps({"id": self._credentials.username, "password": self._credentials.password})
        request = Request("POST", f"{self.login_base}/login",
                          {"Content-Type": "application/json", "Accept": "application/json",
                           "User-Agent": USER_AGENT}, body.encode("utf-8"))  # fmt: skip
        response = self._send(request, "login")
        token = None
        if response.status == 200 and _is_json(response):
            data = json.loads(response.body)
            token = data.get("token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise OpenReviewAuthError(
                f"OpenReview refused the login (HTTP {response.status}"
                f"{', ' + name if (name := _error_name(response)) else ''}); "
                "check OPENREVIEW_USERNAME and OPENREVIEW_PASSWORD"
            )
        log.info("openreview_logged_in", extra={"host": urlsplit(self.login_base).hostname})
        return token

    def _authenticated_get(self, url: str) -> tuple[Response, dict[str, Any]]:
        what = urlsplit(url).path
        for fresh_login in (False, True):
            if self._token is None or fresh_login:
                self._token = self._login()
            request = Request("GET", url, {"Authorization": f"Bearer {self._token}",
                                           "Accept": "application/json", "User-Agent": USER_AGENT})  # fmt: skip
            response = self._send(request, what)
            refused = response.status == 401 or (response.status == 200 and not _is_json(response))
            if refused:
                log.warning("openreview_auth_refused",
                            extra={"what": what, "status": response.status, "relogin": not fresh_login})  # fmt: skip
                continue
            if response.status != 200:
                name = _error_name(response)
                raise OpenReviewHTTPError(
                    f"OpenReview answered {response.status}{' ' + name if name else ''} for {url}",
                    status=response.status,
                    name=name,
                )
            data = json.loads(response.body)
            if not isinstance(data, dict):
                raise OpenReviewError(f"OpenReview answered {url} with JSON that is not an object",
                                      reason="unexpected_shape")  # fmt: skip
            self._respect_budget(response, what)
            return response, data
        raise OpenReviewAuthError(
            "OpenReview did not accept the session: it answered with a login refusal or an HTML page "
            "(its browser check) instead of JSON, after a fresh login; check OPENREVIEW_USERNAME and "
            "OPENREVIEW_PASSWORD"
        )

    def _respect_budget(self, response: Response, what: str) -> None:
        """When the window's budget is spent, wait for it to reset (`ratelimit-reset`, seconds from now)."""
        remaining = _number(response.headers.get("ratelimit-remaining"))
        if remaining is None or remaining > 0:
            return
        reset = _number(response.headers.get("ratelimit-reset"))
        wait = _capped(60.0 if reset is None else reset)
        log.info("openreview_budget_wait", extra={"what": what, "wait_s": round(wait, 1)})
        self._clock.sleep(wait)


def _parses(body: bytes) -> bool:
    try:
        json.loads(body)
    except ValueError:
        return False
    return True


def repo_dotenv() -> Path | None:
    """The repository's `.env` (found from this package's location), if the package runs from a checkout."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "backend").is_dir() and (parent / "pyproject.toml").is_file():
            return parent / ".env"
    return None


def env_credentials() -> Credentials | None:
    """Credentials from the process environment, else the repository's `.env`."""
    return credentials(os.environ, repo_dotenv())
