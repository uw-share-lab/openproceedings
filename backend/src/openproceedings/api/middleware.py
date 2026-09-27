"""Pure-ASGI middleware: the access line and the per-client rate limit (fastapi-conventions, logging-standards).

`AccessLog` is the outermost layer. It gives each request an id (bound into every log line of the
request) and writes exactly one `request` line when the response is done (streams and CORS preflights
included). `LastCatch`, just inside CORS, catches an unexpected exception: one ERROR line with the type and
frames (never the message), and a 500 `API_INTERNAL` envelope if nothing was sent yet (which CORS then
decorates like any response), or `aborted: true` on the access line if the response had started. Nothing
is re-raised, so the server never logs a traceback of its own (its last line would be the message, which
can quote the query). A response that started but never sent its final body message, with nothing having
failed, is a client that went away mid-stream: the line says `client_disconnected: true`.

`RateLimit` is a token bucket per client. The client is the TCP peer, unless the peer is a configured
trusted proxy: then it is the right-most `X-Forwarded-For` address that is not itself a trusted proxy.
IPv6 clients are bucketed by /64 (one host holds a whole /64).
"""

from __future__ import annotations

import ipaddress
import logging
import math
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Sequence

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from openproceedings.api.config import RateLimit as RateLimitConfig
from openproceedings.api.errors import ACCESS, error_response, internal_error
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.logs import bind

log = logging.getLogger(__name__)
API_PREFIX = "/api/v1"
HEALTH_PATH = f"{API_PREFIX}/healthz"
EXPORT_PATH = f"{API_PREFIX}/export"
RECORDS_PATH = f"{API_PREFIX}/records"  # POST /records, GET /records/{id}, /diff: each runs a whole query
# fields a route may add to the access line (api/deps.py); anything else in the dict is not logged
ANNOTATIONS = (
    "index_version",
    "canonical_hash",
    "total",
    "token_count",
    "n_errors",
    "error_codes",
    "warning_codes",
)

type Network = ipaddress.IPv4Network | ipaddress.IPv6Network


class AccessLog:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        rid = uuid.uuid4().hex
        fields: dict[str, object] = {"request_id": rid}
        scope[ACCESS] = fields
        status = 500
        sent = completed = False

        async def tracked(message: Message) -> None:
            nonlocal status, sent, completed
            if message["type"] == "http.response.start":
                status, sent = int(message["status"]), True
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True  # the final body message went out: the response is whole

        with bind(request_id=rid):
            try:
                await LastCatch.run(self.app, scope, receive, tracked, lambda: sent)
            finally:
                route = scope.get("route")
                template = getattr(route, "path", None)  # the route template, never the concrete path
                line: dict[str, object] = {
                    "request_id": rid,
                    "method": scope.get("method"),
                    "route": template,
                    "status": status,  # what the client was sent
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                    "index_version": fields.get("index_version"),
                }
                line.update({k: fields[k] for k in ANNOTATIONS if k in fields and k != "index_version"})
                if fields.get("aborted"):
                    line["aborted"] = True  # failed after the response started: the body is cut short
                elif sent and not completed:
                    # started, never finished, and nothing failed: the client went away mid-stream (the
                    # server cancelled the response), so the body it has is cut short
                    line["client_disconnected"] = True
                log.log(logging.DEBUG if template == HEALTH_PATH else logging.INFO, "request", extra=line)


class LastCatch:
    """The catch for an unexpected exception, just inside CORS (so a 500 carries the CORS headers too):
    one `request_failed` ERROR line (type and frames, never the message), then a 500 `API_INTERNAL`
    envelope, or, if the response had already started, `aborted: true` on the access line. Never re-raised,
    so the server never logs a traceback of its own. `AccessLog` runs the same catch around everything
    outside it (CORS itself), as a backstop."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        sent = False

        async def tracked(message: Message) -> None:
            nonlocal sent
            if message["type"] == "http.response.start":
                sent = True
            await send(message)

        await self.run(self.app, scope, receive, tracked, lambda: sent)

    @staticmethod
    async def run(
        app: ASGIApp, scope: Scope, receive: Receive, send: Send, started: Callable[[], bool]
    ) -> None:
        try:
            await app(scope, receive, send)
        except Exception as exc:  # the last catch: logged once here, never re-raised
            response = internal_error(scope, exc)
            if started():
                fields = scope.get(ACCESS)
                if isinstance(fields, dict):
                    fields["aborted"] = True
            else:
                await response(scope, receive, send)


def _address(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The address in `text`, an IPv4-mapped IPv6 one (`::ffff:a.b.c.d`, how a dual-stack bind reports an
    IPv4 peer) as the IPv4 address it is, so it keys and matches trusted proxies as IPv4."""
    try:
        address = ipaddress.ip_address(text.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def client_key(scope: Scope, trusted: Sequence[Network]) -> str:
    """The rate-limit key of a request's client (module docstring)."""
    client = scope.get("client")
    peer_text = str(client[0]) if client else ""
    peer = _address(peer_text)

    def is_trusted(a: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return any(a.version == n.version and a in n for n in trusted)

    chosen = peer
    if peer is not None and is_trusted(peer):
        hops = [
            h
            for name, value in scope.get("headers", ())
            if name.lower() == b"x-forwarded-for"
            for h in value.decode("latin-1").split(",")
        ]
        for hop in reversed(hops):
            address = _address(hop)
            if address is None:  # a malformed hop: stop at the last trusted one
                break
            chosen = address
            if not is_trusted(address):
                break
    if chosen is None:
        return peer_text  # not an IP address (an in-process test client): its name
    if chosen.version == 6:
        return str(ipaddress.ip_network(f"{chosen}/64", strict=False))
    return str(chosen)


class TokenBucket:
    """Buckets per key: `capacity` tokens, refilled continuously at `refill` per second. At most
    `max_clients` buckets are held; the least recently seen is dropped first."""

    def __init__(
        self, capacity: float, refill: float, max_clients: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.capacity, self.refill, self.max_clients, self.clock = capacity, refill, max_clients, clock
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()

    def take(self, key: str, cost: float) -> float:
        """Spend `cost` tokens for `key`: 0 if allowed, else the seconds until it would be."""
        now = self.clock()
        tokens, last = self._buckets.pop(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill)
        wait = 0.0
        if tokens >= cost:
            tokens -= cost
        else:
            wait = (cost - tokens) / self.refill
        self._buckets[key] = (tokens, now)
        while len(self._buckets) > self.max_clients:
            self._buckets.popitem(last=False)
        return wait


class RateLimit:
    """429 `API_RATE_LIMITED` with `Retry-After` once a client's bucket is empty. `/healthz` is free; an
    export and each record route cost `export_weight`. Runs on the event loop only, so the buckets need no lock."""

    def __init__(
        self,
        app: ASGIApp,
        config: RateLimitConfig,
        trusted: Sequence[Network],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.config = config
        self.trusted = tuple(trusted)
        self.buckets = TokenBucket(config.capacity, config.refill_per_second, config.max_clients, clock)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not self.config.enabled or path == HEALTH_PATH:
            await self.app(scope, receive, send)
            return
        heavy = path in (EXPORT_PATH, RECORDS_PATH) or path.startswith(RECORDS_PATH + "/")
        cost = self.config.export_weight if heavy else 1.0
        wait = self.buckets.take(client_key(scope, self.trusted), cost)
        if wait > 0:
            log.debug("request_refused", extra={"code": str(DiagnosticCode.API_RATE_LIMITED)})
            seconds = max(1, math.ceil(wait))
            response = error_response(
                DiagnosticCode.API_RATE_LIMITED,
                f"Too many requests from this address; try again in {seconds} s.",
                headers={"Retry-After": str(seconds)},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
