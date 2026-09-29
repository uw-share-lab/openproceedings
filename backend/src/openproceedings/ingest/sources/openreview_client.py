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
- **Cache.** Before a successful GET is stored, it is reduced to world-readable notes/groups and the top-level
  fields the crawlers use; restricted v2 content fields are dropped, public content fields remain available
  to year-specific adapters, and a private row refuses the response. Entries
  live under `<cache>/openreview/<api>/http/` as `{"key": url, "payload": {url, fetched_at, headers, json,
  public_projection}}`, keyed by the canonical URL (parameters sorted). A pre-projection cache is rejected
  offline and replaced by a live run. `offline=True` never touches the network (`http.CacheMiss`);
  `refresh=True` refetches and overwrites. A live client also refetches an entry past its TTL (`ttl`, TASK-102;
  spec 01 §Pipeline): a listing that can still change expires sooner than one that has settled, and API v1
  (every venue-year on it is over) never expires. Offline, nothing expires.

Nothing here logs or raises with a credential, the token, a request body or response text.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import random
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from openproceedings.ingest.sources.http import (
    USER_AGENT,
    CacheError,
    Clock,
    FetchError,
    HttpClient,
    HTTPRefused,
    Policy,
    PolicyEvents,
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
PUBLIC_PROJECTION = 1

# --- expiry (TASK-102; spec 01 §Pipeline, Cache expiry) ----------------------------------------------------

DAY = 86400.0
# (listing kind) → (TTL while its venue-year is open, TTL once it is over), in seconds. A venue-year is open
# from its call until the end of its calendar year: its decisions may not be out, a withdrawal or an opted-in
# rejected paper can still appear. After that the accepted list has settled; a status list can still gain a
# late opt-in, so it is looked at again sooner.
TTL: dict[str, tuple[float, float]] = {
    "accepted": (7 * DAY, 365 * DAY),  # grows once, at decisions; camera-ready edits until the conference
    "status": (1 * DAY, 90 * DAY),  # submissions, rejected, withdrawn, desk-rejected: change until decisions
    "groups": (1 * DAY, 90 * DAY),  # a year's groups (a workshop added) and a venue's group (its venueids)
    "other": (1 * DAY, 1 * DAY),  # a request naming no venue-year: the shortest
}
_STATUS_LIST = ("/Submission", "/Rejected_Submission", "/Withdrawn_Submission", "/Desk_Rejected_Submission")
_YEAR = re.compile(r"\.cc/(\d{4})(?:/|$)")


def listing_kind(url: str) -> tuple[str, int | None]:
    """What a cached API v2 GET lists (a `TTL` key) and the venue-year it names (None if it names none)."""
    parts = urlsplit(url)
    params = {k: v[0] for k, v in parse_qs(parts.query).items()}
    if parts.path == "/notes" and (vid := params.get("content.venueid")):
        kind = "status" if vid.endswith(_STATUS_LIST) else "accepted"
        named = vid
    elif parts.path == "/groups" and (named := params.get("parent") or params.get("id") or ""):
        kind = "groups"
    else:
        return "other", None
    m = _YEAR.search(named)
    return (kind, int(m.group(1))) if m else ("other", None)


def ttl(url: str, now: datetime) -> float | None:
    """How long a cached OpenReview response stays fresh (`Policy.ttl`): API v1 never expires (its venue-years,
    ICLR ≤2023 and NeurIPS 2021–2022, are over and v1 is frozen); an API v2 listing by its kind, and by whether
    its venue-year is still open (its year is this calendar year or later) or over (`TTL`)."""
    if urlsplit(url).hostname == "api.openreview.net":
        return None
    kind, year = listing_kind(url)
    open_ttl, settled_ttl = TTL[kind]
    return open_ttl if year is None or year >= now.year else settled_ttl


EVENTS = PolicyEvents(
    retry_wait="openreview_retry_wait",
    budget_wait="openreview_budget_wait",
    cache_expired="openreview_cache_expired",
)
# the widest window OpenReview advertises is an hour; a hostile header can't park a run longer
POLICY = Policy(
    hosts=HOSTS, accept="application/json", expect="json", keep_query=True, attempts=6, backoff=(1.0, 60.0),
    jitter=random.random, hint_pad=1.0, max_wait=3700.0, cap_waits=True, wait_after_last=False,
    max_body=64 * 1024 * 1024, timeout=60.0, events=EVENTS, ttl=ttl,
)  # fmt: skip

Entry = dict[str, Any]  # {"url", "fetched_at", "headers", "json"}


class OpenReviewAuthError(SourceError):
    reason = "auth_failed"


class OpenReviewPublicDataError(SourceError):
    """An authenticated response contained an object that an anonymous reader cannot retrieve."""

    reason = "private_response"


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


def _world_readable(value: Mapping[str, Any]) -> bool:
    """Whether OpenReview's readers/nonreaders ACL makes an object available to `everyone`. A null `nonreaders`
    excludes no one, like `[]` or no key: API v1 writes it on public notes (ICLR 2017 workshop, TASK-119)."""
    readers = value.get("readers")
    nonreaders = value.get("nonreaders")
    if nonreaders is None:  # null or absent; any other non-list value (even "", {} or False) is refused below
        nonreaders = []
    if not isinstance(readers, list) or not all(isinstance(item, str) for item in readers):
        return False
    if not isinstance(nonreaders, list) or not all(isinstance(item, str) for item in nonreaders):
        return False
    return "everyone" in readers and "everyone" not in nonreaders


def _acl_shape(value: Mapping[str, Any], name: str) -> str:
    """An ACL's shape for an error message: its type, a list's length and whether it names `everyone`. Never
    its entries, which can be profile ids (personal data; logging-standards skill)."""
    if name not in value:
        return f"{name} absent"
    acl = value[name]
    if acl is None:
        return f"{name} null"
    if isinstance(acl, list):
        return f"{name} list of {len(acl)}{' naming everyone' if 'everyone' in acl else ' without everyone'}"
    return f"{name} {type(acl).__name__}"


def _public_content(value: Any) -> dict[str, Any]:
    """A public object's content, excluding v2 fields with their own restricted readers."""
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if (
            isinstance(item, Mapping)
            and ({"readers", "nonreaders"} & item.keys())
            and not _world_readable(item)
        ):
            continue
        out[key] = copy.deepcopy(item)
    return out


def _public_projection(url: str, data: Mapping[str, Any]) -> dict[str, Any]:
    """A public API projection with only crawler-used top-level fields; called before caching. `url` is the
    canonical request (the cache key: host, path and sorted parameters), which a refusal names so the
    listing can be found again; never the response's data, the token or a credential (TASK-116).

    A private top-level object makes the response unusable because silently dropping a row would corrupt
    offset/count pagination. Restricted v2 content fields can be dropped without changing that pagination.
    """
    path = urlsplit(url).path
    key = "notes" if path == "/notes" else "groups" if path == "/groups" else None
    if key is None:
        raise OpenReviewPublicDataError(
            f"OpenReview response to GET {url} has no public cache projection", reason="unexpected_shape"
        )
    out: dict[str, Any] = {}
    if isinstance(data.get("count"), int):
        out["count"] = data["count"]
    rows = data.get(key)
    if not isinstance(rows, list):
        return out  # preserve the malformed shape so the source adapter reports it consistently
    projected: list[Any] = []
    allowed = (
        {"id", "forum", "number", "invitation", "invitations", "replyto", "readers"}
        if key == "notes"
        else {"id", "domain", "parent", "readers"}
    )
    for row in rows:
        if not isinstance(row, Mapping):
            raise OpenReviewPublicDataError(
                f"OpenReview {key[:-1]} in the response to GET {url} is not an object",
                reason="unexpected_shape",
            )
        if not _world_readable(row):
            raise OpenReviewPublicDataError(
                f"OpenReview {key[:-1]} in the response to GET {url} is not world-readable "
                f"({_acl_shape(row, 'readers')}, "
                f"{_acl_shape(row, 'nonreaders')}): a malformed ACL is refused like a private one; a private "
                "one means the credentials see more than the public does (venue roles)"
            )
        item = {name: copy.deepcopy(row[name]) for name in allowed if name in row}
        item["content"] = _public_content(row.get("content"))
        projected.append(item)
    out[key] = projected
    return out


def _is_pre_projection_cache(path: Path, url: str) -> bool:
    """Whether a cache file is the old, otherwise-valid raw-response layout (and only that layout)."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        payload = document["payload"]
        fetched = datetime.fromisoformat(payload["fetched_at"])
        return (
            document["key"] == url
            and payload["url"] == url
            and isinstance(payload.get("json"), dict)
            and "public_projection" not in payload
            and fetched.tzinfo is not None
        )
    except (OSError, KeyError, TypeError, ValueError, AttributeError):
        return False


class EntryCodec:
    """`<cache>/openreview/<api>/http/<sha256[:2]>/<sha256>.json`: `{"key": url, "payload": entry}`."""

    subdir = ""

    def key(self, entry: Entry) -> str:
        return str(entry["url"])

    def encode(self, entry: Entry) -> dict[str, Any]:
        return {"key": entry["url"], "payload": entry}

    def decode(self, document: dict[str, Any]) -> tuple[str, Entry]:
        payload = document["payload"]
        if (
            payload.get("public_projection") != PUBLIC_PROJECTION
            or not isinstance(payload.get("json"), dict)
            or payload.get("url") != document["key"]
        ):
            raise ValueError("not an OpenReview response entry")
        if datetime.fromisoformat(payload["fetched_at"]).tzinfo is None:
            raise ValueError("naive fetched_at")
        return str(document["key"]), payload

    def fetched_at(self, entry: Entry) -> datetime:
        return datetime.fromisoformat(entry["fetched_at"])


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

    def get(self, path: str, params: Mapping[str, str | int], *, refresh: bool = False) -> Entry:
        """The cached entry for this GET, fetched (and cached) first if the cache lacks it, it has expired, or
        `refresh` (this call) or the client's `refresh` (every call) asks."""

        def fetch(url: str) -> tuple[Entry, bool]:
            response, data = self._authenticated_get(url)
            entry = {
                "url": url,
                "fetched_at": self.clock.now().astimezone(UTC).isoformat(),
                "headers": {k: response.headers[k] for k in KEPT_HEADERS if k in response.headers},
                "json": _public_projection(url, data),
                "public_projection": PUBLIC_PROJECTION,
            }
            return entry, True

        url = self.url(path, params)
        try:
            return self.through_cache(url, fetch, refresh=self.refresh or refresh)
        except CacheError:
            cache_path = self.cache.path(url)
            if self.offline or not _is_pre_projection_cache(cache_path, url):
                raise
            # Pre-projection caches may contain authenticated-only data. A live run removes the one exact
            # sha256-keyed entry and fetches a public projection; offline replay refuses it above.
            cache_path.unlink(missing_ok=True)
            log.warning("openreview_cache_incompatible", extra={"url": url})
            return self.through_cache(url, fetch, refresh=True)

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
