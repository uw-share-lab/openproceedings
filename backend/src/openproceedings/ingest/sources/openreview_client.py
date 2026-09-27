"""The OpenReview client (openreview-api skill; spec 01 §Sources): the shared HTTP layer (`http.HttpClient`) with
OpenReview's policy, its login and its JSON cache entries on top.

- **Hosts.** Only `api2.openreview.net` and `api.openreview.net` (API v1) are ever called. URLs are built from a
  fixed base and a path, never taken from a response; the transport follows no redirect (following one would
  carry the bearer token to another host).
- **Auth.** `OPENREVIEW_USERNAME` / `OPENREVIEW_PASSWORD` from the environment or `.env`, nowhere else. Login
  (`POST <login_base>/login`; a v1 client logs in on api2, whose token api1 accepts) is lazy: a run served
  entirely from the cache needs no credentials and makes no network call. A 401, or an HTML page where JSON
  was asked for (the "Verifying your browser" challenge anonymous callers get with HTTP 200), logs in again
  once, then fails as `OpenReviewAuthError`: never read as an empty page, never cached.
- **Politeness** is `POLICY` (`http` module docstring): one request a second, a spent budget waits for
  `ratelimit-reset`, 429 → `Retry-After` → `ratelimit-reset` → `min(2^n, 60) s + jitter`, every wait capped at
  3,701 s, at most `max_attempts` tries; any other 4xx fails at once (`http.HTTPRefused`).
- **Cache.** Every successful GET is stored under `<cache>/openreview/<api>/http/` as `{"key": url, "payload":
  {url, fetched_at, headers, json}}` (the layout scholarmend's `Cache` wrote, so an older cache replays), keyed
  by the canonical URL (parameters sorted). `offline=True` never touches the network (`http.CacheMiss`);
  `refresh=True` refetches and overwrites.

Nothing here logs or raises with a credential, the token, a request body or response text.
"""

from __future__ import annotations

import json
import logging
import os
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

from openproceedings.ingest.sources.http import (
    USER_AGENT,
    Clock,
    FetchError,
    HttpClient,
    HTTPRefused,
    Policy,
    Request,
    Response,
    ResponseCache,
    SourceError,
    Transport,
    error_name,
    is_json,
    urllib_transport,
)

log = logging.getLogger(__name__)

API_V2 = "https://api2.openreview.net"
API_V1 = "https://api.openreview.net"
HOSTS = frozenset({"api2.openreview.net", "api.openreview.net"})
KEPT_HEADERS = ("content-type", "ratelimit-policy", "ratelimit-remaining", "ratelimit-reset")
# the widest window OpenReview advertises is an hour; a hostile header can't park a run longer
POLICY = Policy(
    hosts=HOSTS, accept="application/json", expect="json", keep_query=True, attempts=6, backoff=(1.0, 60.0),
    jitter=random.random, hint_pad=1.0, max_wait=3700.0, cap_waits=True, wait_after_last=False,
    max_body=64 * 1024 * 1024, timeout=60.0, log_prefix="openreview",
)  # fmt: skip

Entry = dict[str, Any]  # {"url", "fetched_at", "headers", "json"}


class OpenReviewAuthError(SourceError):
    reason = "auth_failed"


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


class EntryCodec:
    """`<cache>/openreview/<api>/http/<sha256[:2]>/<sha256>.json`: `{"key": url, "payload": entry}`."""

    subdir = ""

    def key(self, entry: Entry) -> str:
        return str(entry["url"])

    def encode(self, entry: Entry) -> dict[str, Any]:
        return {"key": entry["url"], "payload": entry}

    def decode(self, document: dict[str, Any]) -> tuple[str, Entry]:
        payload = document["payload"]
        if not isinstance(payload.get("json"), dict) or payload.get("url") != document["key"]:
            raise ValueError("not an OpenReview response entry")
        return str(document["key"]), payload


class OpenReviewClient(HttpClient[Entry]):
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
        policy = replace(POLICY, min_interval=min_interval, attempts=max_attempts, jitter=jitter)
        super().__init__(
            ResponseCache(cache_dir, EntryCodec()), None if offline else transport, policy, clock
        )
        self.base = base
        self.login_base = login_base or base
        self.refresh = refresh
        self._credentials = credentials
        self._token: str | None = None

    @property
    def requests(self) -> int:
        """HTTP exchanges made (login included), for reports and tests."""
        return self.stats.network

    @property
    def cached(self) -> int:
        """GETs answered from the cache."""
        return self.stats.cached

    def url(self, path: str, params: Mapping[str, str | int]) -> str:
        """The canonical URL (and cache key): parameters sorted, `/` left readable."""
        query = urlencode(sorted((k, str(v)) for k, v in params.items()), safe="/")
        return f"{self.base}{path}" + (f"?{query}" if query else "")

    def get(self, path: str, params: Mapping[str, str | int]) -> Entry:
        """The cached entry for this GET, fetched (and cached) first if the cache lacks it."""

        def fetch(url: str) -> tuple[Entry, bool]:
            response, data = self._authenticated_get(url)
            entry = {
                "url": url,
                "fetched_at": self.clock.now().astimezone(UTC).isoformat(),
                "headers": {k: response.headers[k] for k in KEPT_HEADERS if k in response.headers},
                "json": data,
            }
            return entry, True

        return self.through_cache(self.url(path, params), fetch, refresh=self.refresh)

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
        response = self.send(request)
        token = None
        if response.status == 200 and is_json(response):
            data = json.loads(response.body)
            token = data.get("token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise OpenReviewAuthError(
                f"OpenReview refused the login (HTTP {response.status}"
                f"{', ' + name if (name := error_name(response)) else ''}); "
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
                                           "Accept": self.policy.accept, "User-Agent": USER_AGENT})  # fmt: skip
            response = self.send(request)
            if response.status == 401 or (response.status == 200 and not is_json(response)):
                log.warning("openreview_auth_refused",
                            extra={"what": what, "status": response.status, "relogin": not fresh_login})  # fmt: skip
                continue
            if response.status != 200:
                raise HTTPRefused(url, response.status, error_name(response))
            data = json.loads(response.body)
            if not isinstance(data, dict):
                raise FetchError(f"OpenReview answered {url} with JSON that is not an object",
                                 reason="unexpected_shape")  # fmt: skip
            return response, data
        raise OpenReviewAuthError(
            "OpenReview did not accept the session: it answered with a login refusal or an HTML page "
            "(its browser check) instead of JSON, after a fresh login; check OPENREVIEW_USERNAME and "
            "OPENREVIEW_PASSWORD"
        )


def repo_dotenv() -> Path | None:
    """The repository's `.env` (found from this package's location), if the package runs from a checkout."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "backend").is_dir() and (parent / "pyproject.toml").is_file():
            return parent / ".env"
    return None


def env_credentials() -> Credentials | None:
    """Credentials from the process environment, else the repository's `.env`."""
    return credentials(os.environ, repo_dotenv())
