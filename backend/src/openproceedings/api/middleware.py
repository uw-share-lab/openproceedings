"""Pure-ASGI middleware: the access line and the per-client rate limit (fastapi-conventions, logging-standards).

`AccessLog` is the outermost layer. It gives each request an id (bound into every log line of the
request) and writes exactly one `request` line when the response is done (streams and CORS preflights
included). `LastCatch`, just inside CORS, catches an unexpected exception: one ERROR line with the type and
frames (never the message), and a 500 `API_INTERNAL` envelope if nothing was sent yet (which CORS then
decorates like any response), or `aborted: true` on the access line if the response had started. Nothing
is re-raised, so the server never logs a traceback of its own (its last line would be the message, which
can quote the query). A response that started but never sent its final body message, with nothing having
failed, is a client that went away mid-stream: the line says `client_disconnected: true`.

`BodyLimit` refuses a request body over `ApiConfig.max_body_bytes` with 413 `API_BODY_TOO_LARGE` before
the app reads it: on its `Content-Length`, or, for a body without one (chunked), once the bytes received pass
the cap. It reads a body (at most the cap) before the app runs, so the refusal comes before routing and
before any other check (an index that isn't loaded yet included).

`RateLimit` is a token bucket per client, and a coarser one per client network (IPv4 /24, IPv6 /48), both
checked for every request. The client is the TCP peer, unless the peer is a configured trusted proxy: then it
is the right-most `X-Forwarded-For` address that is not itself a trusted proxy. IPv6 clients are bucketed by
/64 (one host holds a whole /64); the network bucket bounds a host holding a whole /48. A route can charge
more once it knows what the request costs (`charge`: a position-verified query, spec 04 §Rate limit).
"""

from __future__ import annotations

import ipaddress
import logging
import math
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Sequence
from urllib.parse import parse_qs

from pydantic import TypeAdapter, ValidationError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from openproceedings.api.config import RateLimit as RateLimitConfig
from openproceedings.api.errors import (
    ACCESS,
    ApiError,
    current_access,
    error_response,
    internal_error,
    refused,
)
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.logs import bind, elapsed_ms

log = logging.getLogger(__name__)
API_PREFIX = "/api/v1"
HEALTH_PATH = f"{API_PREFIX}/healthz"
EXPORT_PATH = f"{API_PREFIX}/export"
RECORDS_PATH = f"{API_PREFIX}/records"  # POST /records, GET /records/{id}, /diff: each runs a whole query
BUCKETS = "openproceedings.rate"  # scope key: the request's rate-limit buckets and keys, for `charge`
# fields a route may add to the access line (api/deps.py); anything else in the dict is not logged
ANNOTATIONS = (
    "index_version",
    "canonical_hash",
    "total",
    "abstract_source",  # an export's `X-Abstract-Source`: `unavailable` when it withheld abstracts (decision-021)
    "token_count",
    "n_errors",
    "error_codes",
    "warning_codes",
    "verified_clauses",  # the query's position-verified clauses (api/deps.py; replays too)
    "verification_candidates",  # the documents their position checks would read, summed (api/deps.py)
    "verify_ms",  # time this request held a verification slot (api/state.py::verification_slot)
    "verify_cpu_ms",  # the verifying thread's CPU time in those holds: what is debited (round 5)
    "verify_tokens",  # what that time was debited after the fact (RateLimit.debit_verification)
    "code",  # the error envelope's code, on every refusal and every 500 (api/errors.py::note_code)
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
        token = current_access.set(fields)
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
                    "ms": elapsed_ms(started),
                    "index_version": fields.get("index_version"),
                }
                line.update({k: fields[k] for k in ANNOTATIONS if k in fields and k != "index_version"})
                if fields.get("aborted"):
                    line["aborted"] = True  # failed after the response started: the body is cut short
                elif sent and not completed:
                    # started, never finished, and nothing failed: the client went away mid-stream (the
                    # server cancelled the response), so the body it has is cut short
                    line["client_disconnected"] = True
                try:
                    log.log(logging.DEBUG if template == HEALTH_PATH else logging.INFO, "request", extra=line)
                finally:  # a failing log call must not leave this request's fields in the context
                    current_access.reset(token)


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


class BodyLimit:
    """413 `API_BODY_TOO_LARGE` for a body over `max_bytes` (module docstring). A body within the cap is
    read here, whole, and replayed to the app; after it, `receive` is the server's own (a disconnect)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = _content_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._refuse(scope, receive, send)
            return
        chunks: list[Message] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":  # the client went away: let the app see it
                # (an equivalent mutant drops this append: an ASGI server answers every `receive` after a
                # disconnect with `http.disconnect` again, so `replay`'s fall-through gives the app the same)
                chunks.append(message)
                break
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                await self._refuse(scope, receive, send)
                return
            chunks.append(message)
            if not message.get("more_body", False):
                break

        async def replay() -> Message:
            return chunks.pop(0) if chunks else await receive()

        await self.app(scope, replay, send)

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        refused(scope, DiagnosticCode.API_BODY_TOO_LARGE)
        response = error_response(
            DiagnosticCode.API_BODY_TOO_LARGE,
            f"The request body is over {self.max_bytes:,} bytes; a query fits in far less.",
            headers={"Connection": "close"},  # the rest of the body is never read
        )
        await response(scope, receive, send)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", ()):
        if name.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None  # the server refuses a malformed one before we see it
    return None


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


def network_key(client: str) -> str:
    """The coarser bucket of a client key: its IPv4 /24 or its IPv6 /48 (a /64 key included); a key that
    isn't an address (an in-process test client) is its own network."""
    try:
        network = ipaddress.ip_network(client, strict=False)
    except ValueError:
        return client
    prefix = 24 if network.version == 4 else 48
    return str(network.supernet(new_prefix=prefix)) if network.prefixlen > prefix else str(network)


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
    `max_clients` buckets are held; the least recently seen is dropped first. Thread-safe: the middleware
    takes on the event loop, a route charges more from its worker thread (`charge`)."""

    def __init__(
        self, capacity: float, refill: float, max_clients: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.capacity, self.refill, self.max_clients, self.clock = capacity, refill, max_clients, clock
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self.lock = threading.Lock()

    def wait(self, key: str, cost: float) -> float:
        """Seconds until `key` holds `cost` tokens (0: it does now), spending nothing. Under `lock`."""
        now = self.clock()
        tokens, last = self._buckets.pop(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill)
        self._buckets[key] = (tokens, now)
        self._evict(key)
        return 0.0 if tokens >= cost else (cost - tokens) / self.refill

    def _evict(self, keep: str) -> None:
        """Drop the least recently seen buckets beyond `max_clients`, skipping one in debt (below zero, from a
        slot-time debit): forgetting it would forgive the debt, and a new bucket starts full (round 5). The
        map stays bounded: if every other bucket were in debt, the oldest goes anyway. `keep`, the bucket just
        touched, is never dropped (its caller spends from it next). Under `lock`."""
        while len(self._buckets) > self.max_clients:
            victim = fallback = None  # a scan from the oldest that stops at the first bucket not in debt:
            now = self.clock()
            for k, (tokens, last) in self._buckets.items():  # O(1) unless debtors are the oldest
                if k == keep:
                    continue
                if fallback is None:
                    fallback = k
                # only debt still owed protects a bucket (round 6), not a debt the refill has repaid
                if tokens + (now - last) * self.refill >= 0:
                    victim = k
                    break
            del self._buckets[victim if victim is not None else fallback]  # type: ignore[arg-type]

    def spend(self, key: str, cost: float) -> None:
        """Spend `cost` of `key`'s tokens, which `wait` just found there. Under `lock`."""
        tokens, last = self._buckets[key]
        self._buckets[key] = (tokens - cost, last)

    def take(self, key: str, cost: float) -> float:
        """Spend `cost` tokens for `key`: 0 if allowed, else the seconds until it would be."""
        return take_all([(self, key)], cost)

    def debit(self, key: str, cost: float) -> None:
        """Take `cost` tokens `key` has already used, after the fact: the bucket may go below zero, and then
        `key` waits (429 with `Retry-After`) until the refill repays the debt. For a cost known only when the
        work is done (the verification time a request used, `RateLimit`)."""
        with self.lock:
            now = self.clock()
            tokens, last = self._buckets.pop(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill)
            self._buckets[key] = (tokens - cost, now)
            self._evict(key)

    def refund(self, key: str, cost: float) -> None:
        """Give back `cost` tokens `key` spent on work that then didn't happen (never above `capacity`)."""
        with self.lock:
            held = self._buckets.get(key)
            if held is not None:
                tokens, last = held
                self._buckets[key] = (min(self.capacity, tokens + cost), last)


def take_each(buckets: Sequence[tuple[TokenBucket, str]], cost: float) -> list[float]:
    """Spend `cost` from every (bucket, key) if each holds it. Returns each one's wait (all 0: spent); if any
    is over 0, nothing is spent, so a refusal by one bucket never drains another."""
    locks = sorted({id(b): b.lock for b, _key in buckets}.items())
    for _id, lock in locks:
        lock.acquire()
    try:
        waits = [bucket.wait(key, cost) for bucket, key in buckets]
        if max(waits) == 0:
            for bucket, key in buckets:
                bucket.spend(key, cost)
        return waits
    finally:
        for _id, lock in reversed(locks):
            lock.release()


def wait_all(buckets: Sequence[tuple[TokenBucket, str]], cost: float) -> float:
    """Seconds until every (bucket, key) holds `cost` tokens, spending nothing."""
    locks = sorted({id(b): b.lock for b, _key in buckets}.items())
    for _id, lock in locks:
        lock.acquire()
    try:
        return max(bucket.wait(key, cost) for bucket, key in buckets)
    finally:
        for _id, lock in reversed(locks):
            lock.release()


def take_all(buckets: Sequence[tuple[TokenBucket, str]], cost: float) -> float:
    """`take_each`, as the longest wait (0: spent)."""
    return max(take_each(buckets, cost))


def rate_limited(wait: float, who: str = "Too many requests from this address") -> ApiError:
    """429 `API_RATE_LIMITED` with `Retry-After` in whole seconds; the message is `who`, then when to retry."""
    seconds = max(1, math.ceil(wait))
    return ApiError(
        DiagnosticCode.API_RATE_LIMITED,
        f"{who}; try again in {seconds} s.",
        headers={"Retry-After": str(seconds)},
    )


def charge(scope: Scope, total: float) -> None:
    """Bring what this request costs its client (both buckets) up to `total` tokens, or raise 429
    `API_RATE_LIMITED`: for a cost a route learns after routing (a position-verified query). What the
    middleware already took counts toward it. A no-op when the rate limit is off or the request didn't
    pass through it (a unit test)."""
    held = scope.get(BUCKETS)
    if not isinstance(held, tuple):
        return
    buckets, paid, base = held
    if total <= paid:
        return
    if take_all(buckets, total - paid) > 0:
        # the wait is for the whole `total`, not the shortfall: a retry pays the middleware's weight again
        # before this charge, so a client that honours Retry-After is admitted then (round 6: with the
        # shortfall alone it spent the one refilled token on each retry and was never served)
        raise rate_limited(wait_all(buckets, total))
    scope[BUCKETS] = (buckets, total, base)


# a refusal after `charge` took a query's up-front verified charge (its admission cost, per clause): that
# charge is given back and the route's own weight is kept, as a refused save's is (`records.SaveCeiling.
# refund`). A 422 `API_QUERY_TOO_COSTLY` verified nothing (its candidates were counted from the index, 4-8 ms
# of work the base token pays for); a 503 `API_BUSY` may have verified some clauses before it met a taken slot,
# and that time is still debited like any request's (`RateLimit`: the charge for time used is separate)
REFUNDED = frozenset({str(DiagnosticCode.API_BUSY), str(DiagnosticCode.API_QUERY_TOO_COSTLY)})


def refund_charged(scope: Scope) -> None:
    """Give back what `charge` took beyond the middleware's own weight (a no-op if it took nothing)."""
    held = scope.get(BUCKETS)
    if not isinstance(held, tuple):
        return
    buckets, paid, base = held
    if paid > base:
        for bucket, key in buckets:
            bucket.refund(key, paid - base)
        scope[BUCKETS] = (buckets, base, base)


_BOOL = TypeAdapter(bool)


def stored_read(scope: Scope) -> bool:
    """Whether the request is `GET /records/{id}?replay=false` (TASK-091): the stored record read alone, which
    runs no query and returns no membership ids, so it costs one token, not the export weight. `replay` is
    read with the route's own bool rule (pydantic's); every parameter must be one the route takes (`replay`,
    `include`), each given once. `include=ids` and anything else (a repeat, an unknown parameter, a value the
    route refuses) are charged in full."""
    path = scope.get("path", "")
    rest = path[len(RECORDS_PATH) + 1 :] if path.startswith(RECORDS_PATH + "/") else ""
    if scope.get("method") != "GET" or not rest or "/" in rest:
        return False
    try:
        params = parse_qs(scope.get("query_string", b"").decode("latin-1"), keep_blank_values=True)
        if not set(params) <= {"replay", "include"} or any(len(v) != 1 for v in params.values()):
            return False
        if "include" in params:
            return False
        return "replay" in params and _BOOL.validate_python(params["replay"][0]) is False
    except (ValidationError, UnicodeDecodeError, ValueError):
        return False


class RateLimit:
    """429 `API_RATE_LIMITED` with `Retry-After` once a client's bucket is empty. `/healthz` is free; an
    export and each record route cost `export_weight` (a `GET /records/{id}?replay=false` without ids reads
    one, `stored_read`). Runs on the event loop only, so the buckets need no lock."""

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
        self.networks = TokenBucket(*config.network_bucket, config.max_clients, clock)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not self.config.enabled or path == HEALTH_PATH:
            await self.app(scope, receive, send)
            return
        heavy = (path in (EXPORT_PATH, RECORDS_PATH) or path.startswith(RECORDS_PATH + "/")) and not (
            stored_read(scope)
        )
        cost = self.config.export_weight if heavy else 1.0
        client = client_key(scope, self.trusted)
        held = [(self.buckets, client), (self.networks, network_key(client))]
        wait = take_all(held, cost)
        if wait > 0:
            error = rate_limited(wait)
            refused(scope, error.code)
            response = error_response(error.code, error.message, headers=error.headers)
            await response(scope, receive, send)
            return
        scope[BUCKETS] = (held, cost, cost)
        try:
            await self.app(scope, receive, send)
        finally:
            fields = scope.get(ACCESS)
            if isinstance(fields, dict):
                if fields.get("code") in REFUNDED:
                    refund_charged(scope)
                self.debit_verification(held, fields)

    def debit_verification(self, held: Sequence[tuple[TokenBucket, str]], fields: dict[str, object]) -> None:
        """Charge the cold verification time this request used, after the fact, to its client's and network's
        buckets: one token per `verify_token_ms` of the verifying thread's CPU time in the slot
        (`verify_cpu_ms`, round 5: not the wall time `verify_ms`, which other requests' load on the GIL inflates,
        and a reviewer shouldn't be billed for; a main-2-pop query was debited 155 tokens idle and 1,090 under
        contention by wall time). The buckets
        may go below zero, so a client that keeps the one slot busy (cold queries back to back: vary a NEAR
        distance and each is cold) then waits until its debt is repaid, and its share of the slot is at most
        refill × `verify_token_ms` (10% a client, 40% a network at the defaults): the rest is everyone
        else's (M3a review gate round 4, decision-010). The up-front per-clause charge stays, as the
        admission cost."""
        used = fields.get("verify_cpu_ms")
        if isinstance(used, int | float) and used > 0:
            tokens = used / self.config.verify_token_ms
            for bucket, key in held:
                bucket.debit(key, tokens)
            fields["verify_tokens"] = round(tokens, 2)
