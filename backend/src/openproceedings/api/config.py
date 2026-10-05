"""The API's configuration (spec 04 §Conventions, fastapi-conventions skill): one frozen model, built by
`op serve` from its flags and passed to `create_app`. Nothing reads the environment here.

The query-length cap is deliberately *not* configurable: it is the parser's `MAX_QUERY_LENGTH` (spec 02),
so the API refuses exactly what `op search` refuses (the API adds transport, not behaviour).
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, IPvAnyNetwork, field_validator, model_validator

from openproceedings.engine.index import VERSION_NAME

# An index to serve: the `current` symlink, or an index_version (hex; `-` allowed for hand-named copies).
# Nothing else — no `/`, no `..` — so a name can never leave `<data_dir>/indexes/` (task-034 notes).
INDEX_NAME = re.compile(rf"current|{VERSION_NAME.pattern}")
# An exact origin: scheme, host, optional port; no path, no wildcard (fastapi-conventions §Rate limit and CORS).
# the widest network a trusted proxy may be named by, per IP version: a proxy is a host or a small network
MIN_PROXY_PREFIX = {4: 8, 6: 32}
ORIGIN = re.compile(r"https?://(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)(:[0-9]{1,5})?")


class RateLimit(BaseModel):
    """A per-client token bucket: `capacity` tokens, refilled at `refill_per_second`. A request costs one
    token; an export or a record route costs `export_weight` (it touches the whole matched set), and a query
    with position-verified clauses (spec 03: a phrase with a wildcard, a NEAR the index can't answer) costs
    `verified_weight` per such clause (None: `ApiConfig.verified_cost`, the most that lets a query at
    `max_verified_clauses` be paid), the rest charged once the route has parsed it. `/healthz` is free. Every request is also charged to its client's network (IPv4 /24, IPv6 /48), a
    bucket of `network_capacity` (None: 4 × `capacity`) refilled at `network_refill_per_second` (None:
    4 × `refill_per_second`), so one host holding many addresses is bounded too."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = True
    capacity: float = Field(default=60.0, gt=0)
    refill_per_second: float = Field(default=1.0, gt=0)
    export_weight: float = Field(default=10.0, ge=1)
    verified_weight: float | None = Field(default=None, ge=0)  # per position-verified clause
    network_capacity: float | None = Field(default=None, gt=0)
    network_refill_per_second: float | None = Field(default=None, gt=0)
    # one token per this many ms of cold verification a request used, debited when it finishes (the bucket may
    # go below zero): a client's share of the verification slot is at most refill × this (round 4)
    verify_token_ms: float = Field(default=100.0, gt=0)
    # one token per this many ms a comparison (`POST /compare`, TASK-177) held its slot: the wall time its file
    # took to arrive plus the CPU time of the comparison, debited when it finishes like `verify_token_ms`. A
    # client's share of the comparison slot is at most refill × this (50% at the defaults), a network's 4 × that.
    # 500 ms, not 100: a comparison is seconds of work by design (about 10 s per 1,000 records), and at 100 one
    # run would lock a reviewer out of search for minutes
    compare_token_ms: float = Field(default=500.0, gt=0)
    # the wall time a comparison's file took to arrive counts this many times over, in that debit and in the
    # cooldown below: it is the part of a slot's time the client alone decides (a stalled upload holds the
    # slot and does no work), so it is the dearest
    compare_upload_weight: float = Field(default=4.0, ge=1)
    # what bounds a network's share of the comparison slots (the token debit can't: a network's bucket refills
    # 4 tokens/s, so several addresses of one network could hold a slot all the time). After a comparison, its
    # client's network (IPv4 /24, IPv6 /48) starts no other for this many times the slot time it used (the
    # upload weighted as above), and runs one at a time: a network's sustained share of a slot is at most
    # 1 / (1 + factor) however many addresses it holds, 25% at 3 (7.7% for uploads that stall), and a reviewer
    # waits under a minute after an 18 s comparison. 0 turns it off
    compare_cooldown_factor: float = Field(default=3.0, ge=0)
    max_clients: int = Field(default=100_000, ge=1)  # buckets held in memory; the least recent is dropped

    @property
    def smallest_capacity(self) -> float:
        """The smaller bucket's capacity: the most one request can ever be charged."""
        return min(self.capacity, self.network_bucket[0])

    @property
    def network_bucket(self) -> tuple[float, float]:
        """The network bucket's capacity and refill per second."""
        return (
            4 * self.capacity if self.network_capacity is None else self.network_capacity,
            4 * self.refill_per_second
            if self.network_refill_per_second is None
            else self.network_refill_per_second,
        )

    @model_validator(mode="after")
    def _export_fits(self) -> RateLimit:
        if self.export_weight > self.capacity:
            raise ValueError("export_weight must not exceed capacity, or no export could ever run")
        if max(self.export_weight, self.verified_weight or 0) > self.smallest_capacity:
            raise ValueError(
                "export_weight and verified_weight must fit in capacity and network_capacity, or no such "
                "request could ever run"
            )
        return self


class ApiConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    data_dir: Path
    index: str = "current"  # a name under <data_dir>/indexes (INDEX_NAME)
    rate_limit: RateLimit = RateLimit()
    cors_origins: tuple[str, ...] = ()  # exact origins; empty means no cross-origin access
    trusted_proxies: tuple[IPvAnyNetwork, ...] = ()  # peers whose X-Forwarded-For is believed
    # local dev only: lets the log formatter keep query-text fields (spec 04). No log call passes one today
    # (the access line never carries q), so it changes nothing until one does.
    log_query_text: bool = False
    # pinned index_versions (an export's `index_version`, a record's replay): engines held open besides the
    # served one, least recently used dropped first; size it to the versions the instance holds
    # (`op serve --pinned-indexes`)
    pinned_indexes: int = Field(default=4, ge=1)
    # a missing takedown list fails the load (TASK-067): `op serve` sets it off loopback, so a public instance
    # never serves every listed abstract because takedowns/ wasn't mounted; an empty list lists nothing
    takedown_list_required: bool = False
    # how long a refused pin (absent, unloadable, tampered) is remembered before it is checked again; a
    # SIGHUP reload forgets every refusal at once
    pinned_refusal_seconds: float = Field(default=300.0, gt=0)
    load_in_background: bool = True  # /healthz answers (index_loaded false) while the index loads
    handle_sighup: bool = True  # SIGHUP reloads `index` and swaps it in (main thread only)
    # the search-record store (<data_dir>/records/): a save is refused (503 API_RECORDS_STORE_FULL) once the
    # store holds `records_max_bytes` (None: no cap) or its disk has less than `records_min_free_bytes` free
    records_max_bytes: int | None = Field(default=1 << 30, ge=1)
    records_min_free_bytes: int = Field(default=256 << 20, ge=0)
    # every client together: at most `record_saves_burst` saves at once, refilled at `record_saves_per_hour`
    # (an append-only store can't be emptied, so its growth is bounded in time as well as in bytes)
    record_saves_burst: int = Field(default=60, ge=1)
    record_saves_per_hour: float = Field(default=600.0, gt=0)
    # a request body over this is 413 API_BODY_TOO_LARGE, before it is read (task-079). 64 KiB holds the
    # longest valid body: a 2,000-code-point `q` of astral characters as JSON escapes is ~24 KB
    max_body_bytes: int = Field(default=64 * 1024, ge=1024)
    # cold position verification (spec 03: seconds of pure Python per clause) runs at most this many at a
    # time; a query that would need another slot is 503 API_BUSY with `Retry-After: busy_retry_seconds`
    verification_slots: int = Field(default=1, ge=1)
    busy_retry_seconds: int = Field(default=5, ge=1)
    # how long a request waits for another version's pinned open to finish before its own (each re-hashes a
    # whole index): past it, 503 API_BUSY with `Retry-After: busy_retry_seconds` (TASK-067)
    pinned_open_wait_seconds: float = Field(default=2.0, gt=0)
    # a query with more position-verified clauses than this is 422 API_TOO_MANY_VERIFIED_CLAUSES, before anything
    # compiles it: a coarse backstop (16 admits every Trust-Evals string; main-2-pop has 10), the cost being
    # bounded by `max_verification_candidates` (decision-010)
    max_verified_clauses: int = Field(default=16, ge=1)
    # a query whose position-verified clauses would read more candidate documents than this, summed over each
    # clause's fields, is 422 API_QUERY_TOO_COSTLY before any is verified (decision-010): a cold verification
    # costs 37-56 µs per candidate by shape (wildcard-phrase NEARs the dearest), so the default bounds one
    # query's work near 11-17 s idle at 80k (more wall time under load, which `max_verification_seconds` caps),
    # above the heaviest real review query (Trust-Evals main-2-pop, Scholar mode: 247,793 candidates, 10.2 s)
    max_verification_candidates: int = Field(default=300_000, ge=1)
    # `/search` counts each concept group alone (spec 04 §SearchResponse, `groups`; TASK-176) for a query of at
    # most this many groups: one more collection a group, no position check of its own. A query with more gets
    # its result without them (`groups.not_counted`: `too_many_groups`); 10 is twice the widest Trust-Evals
    # string's groups
    max_counted_groups: int = Field(default=10, ge=1)
    # and only when counting them reads at most this many terms, summed over the trees counted (each group
    # alone and the query without each: `query.groups.Groups.terms_read`; a kept `NOT (… wildcards …)` is read
    # by every one). Over it: the result without counts, `too_costly`. 5,000 admits every Trust-Evals string
    # (the widest, main-2-pop, reads 243 on the real index) and refuses a query built to make 20 collections of thousands of terms
    max_counted_terms: int = Field(default=5_000, ge=1)
    # nor more than this many verified ids, summed the same way: a position-verified clause is an id set in
    # its tree's query, resolved id by id by every collection that reads it (a kept `NOT (model NEAR/10
    # model*)`: few terms, tens of thousands of ids, read by all 2 × N trees)
    max_counted_ids: int = Field(default=300_000, ge=1)
    # a request holding a verification slot longer than this logs `verification_slow` (WARNING)
    slow_verification_seconds: float = Field(default=5.0, gt=0)
    # a request's cold verifications together get this much wall time from its first slot; past it the verify
    # loop stops and the request is 503 API_BUSY (Retry-After), nothing stored (round 5). 30 s: main-2-pop, the
    # heaviest real query, needs 10.2 s idle at 80k and is served under paced load; under heavy load it can
    # pass 30 s and its retry finishes (finished clauses are kept). One query can't hold the slot for minutes.
    # The 503's Retry-After is the slot's; the CPU debit is applied after the response, so a retry may then
    # get a 429 with its own (longer) Retry-After
    max_verification_seconds: float = Field(default=30.0, gt=0)
    # one client network (IPv4 /24, IPv6 /48) at most `record_saves_network_burst` saves at once, refilled at
    # `record_saves_network_per_hour`, so one network can't spend the instance-wide ceiling for everyone
    record_saves_network_burst: int = Field(default=10, ge=1)
    record_saves_network_per_hour: float = Field(default=60.0, gt=0)
    # uvicorn's limit_concurrency: connections and tasks beyond it get a 503 from uvicorn itself. Behind the
    # reverse proxy (spec 08 §Deploy) these are the proxy's pooled upstream connections, not clients
    limit_concurrency: int | None = Field(default=256, ge=1)
    # uvicorn's timeout_keep_alive: an idle keep-alive connection is closed after this many seconds, so an
    # idle connection doesn't hold one of `limit_concurrency` for long
    keep_alive_seconds: int = Field(default=5, ge=1)
    # Swagger UI at /api/v1/docs (it loads its script and styles from a CDN). Off unless asked for: `op serve`
    # turns it on for a loopback --host only (a local instance), or with --docs. openapi.json is always served
    serve_docs: bool = False
    # `POST /compare` (TASK-177, decision pending): a reviewer's own RIS file against a query, parsed in memory
    # for the one request and never stored or logged. Off unless asked for: `op serve` turns it on for a
    # loopback --host without a trusted proxy (a local instance), or with --compare. While off, the route
    # answers 403 `API_COMPARE_DISABLED`, `/meta`'s `limits.compare` is null and no match table is built
    compare_enabled: bool = False
    # the file's caps, each refused with a typed error, never cut (`/meta` `limits.compare` states them).
    # 16 MiB: the Trust-Evals export is 3.7 MB for 1,834 records with abstracts (2 KB a record), so the record
    # cap's worth of such records is ~10 MB. A body over it is 413 `API_BODY_TOO_LARGE` before it is read
    compare_max_body_bytes: int = Field(default=16 * 1024 * 1024, ge=1024)
    # records one file may hold (413 `API_RIS_TOO_LARGE`). A comparison costs about 10 s of CPU per 1,000
    # records (the oracle decides every class), so 5,000 is what fits `compare_max_seconds` with room
    compare_max_records: int = Field(default=5_000, ge=1)
    # characters in one line of the file, tag included (413 `API_RIS_TOO_LARGE`): above the ingest cap on an
    # abstract (20,000, decision-026), so no line this corpus could hold is refused
    compare_max_line_chars: int = Field(default=32_768, ge=64)
    # papers of the query's result that the file doesn't hold (422 `API_COMPARE_TOO_COSTLY`): each is read from
    # the snapshot and judged by the oracle, so an unbounded result is unbounded work
    compare_max_results: int = Field(default=5_000, ge=1)
    # the largest answer, in bytes (422 `API_COMPARE_TOO_COSTLY`, checked as it is built): an answer echoes
    # the file's titles and venues and holds each list twice (rows and CSV), so its size follows the file's.
    # The body cap's value: an answer is never larger than the largest file (the review's 3.7 MB file: 1.4 MB)
    compare_max_response_bytes: int = Field(default=16 * 1024 * 1024, ge=1024)
    # comparisons running at once; one more is 503 `API_BUSY` with Retry-After, before its file is read (so at
    # most this many files are in memory)
    comparison_slots: int = Field(default=1, ge=1)
    # the wall time one comparison's work gets from the moment its file is read; past it, 503 `API_BUSY`
    compare_max_seconds: float = Field(default=60.0, gt=0)
    # the wall time a file gets to arrive once the slot is held; past it, 408 `API_UPLOAD_TIMEOUT`. Behind the
    # reverse proxy the body arrives whole (spec 08 §Deploy), so this bounds a direct client only
    compare_upload_seconds: float = Field(default=30.0, gt=0)

    @property
    def verified_cost(self) -> float:
        """What one position-verified clause costs: `rate_limit.verified_weight`, or by default the export
        weight, lowered so that a query at `max_verified_clauses` costs at most the smaller bucket (then every
        clause up to the cap costs something: none rides free past a capped charge)."""
        limit = self.rate_limit
        if limit.verified_weight is not None:
            return limit.verified_weight
        return min(limit.export_weight, limit.smallest_capacity / self.max_verified_clauses)

    def verified_charge(self, clauses: int) -> float:
        """What a query with `clauses` (at most `max_verified_clauses`) position-verified clauses costs."""
        return clauses * self.verified_cost

    @model_validator(mode="after")
    def _verified_fits(self) -> ApiConfig:
        limit = self.rate_limit
        if limit.enabled and self.max_verified_clauses * self.verified_cost > limit.smallest_capacity:
            raise ValueError(
                f"max_verified_clauses ({self.max_verified_clauses}) × verified_weight ({self.verified_cost:g}) "
                f"is more than the smaller rate-limit bucket ({limit.smallest_capacity:g}), so a query at the cap "
                "could never be paid; lower one of them or raise the capacity"
            )
        return self

    @field_validator("index")
    @classmethod
    def _index_name(cls, v: str) -> str:
        if not INDEX_NAME.fullmatch(v):
            raise ValueError("index must be `current` or an index_version (0-9, a-f, -)")
        return v

    @field_validator("trusted_proxies")
    @classmethod
    def _proxies(cls, v: tuple[IPvAnyNetwork, ...]) -> tuple[IPvAnyNetwork, ...]:
        for network in v:
            shortest = MIN_PROXY_PREFIX[network.version]
            if network.prefixlen < shortest:  # 0.0.0.0/0, ::/0, or near enough: clients could forge addresses
                raise ValueError(
                    f"trusted proxy {network} is wider than /{shortest}, so clients inside it could set their "
                    "own X-Forwarded-For; name the proxy's own address or network"
                )
        return v

    @field_validator("cors_origins")
    @classmethod
    def _origins(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for origin in v:
            if not ORIGIN.fullmatch(origin):
                raise ValueError(
                    f"CORS origin {origin!r} must be an exact scheme://host[:port], with no `*` and no path"
                )
        return v
