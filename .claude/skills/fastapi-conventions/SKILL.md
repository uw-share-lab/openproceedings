---
name: fastapi-conventions
description: How the openproceedings FastAPI service is built — /api/v1 base path, sync handlers for CPU-bound Tantivy, one index load at startup, the atomic hot-swap on SIGHUP, the single error shape, structured JSON logs that omit query text by default, the per-IP token bucket and the CORS allowlist. Use when writing or reviewing anything under backend/src/openproceedings/api/, adding a router or middleware, or changing app startup, logging or config.
---

# FastAPI conventions (spec 04 §Conventions, §Implementation notes)

## App shape
- One app factory, `create_app(config) -> FastAPI`, in `backend/src/openproceedings/api/`. Routers per
  resource (`search`, `parse`, `papers`, `export`, `records`, `coverage`, `meta`, `health`, and
  `near_misses` at M5, deferred to phase 2 by decision-017), all mounted under **`/api/v1`**, `/healthz` included (spec 04 §Endpoints: liveness and whether the
  index is loaded). Nothing is served outside `/api/v1`. Declare each router with
  `APIRouter(prefix=API_PREFIX)` and include it directly. Don't nest routers: FastAPI 0.141 keeps
  `scope["route"].path` relative to the declaring router, so the access line would log `/search` instead
  of `/api/v1/search` (task-035). `/parse` and `/search` share `api/search.py`.
- The CLI (`op search`, `op export`, `op serve`) and the routers call **the same functions**. A router
  parses the request, calls the shared function, and shapes the response. No search logic lives in a router.
- Pydantic v2 models are the contract (`.claude/skills/api-contract/SKILL.md`). Every response model
  carries `index_version`, `tokenizer_version` and `query_version` (spec 04 §Conventions).

## Handlers are `def`, not `async def`
Tantivy search, `match_ids`, facets and exclusion accounting are CPU-bound and release no event loop.
Declare handlers as plain `def` so FastAPI runs them in its thread pool. An `async def` handler that calls
the engine blocks every other request. Exports use a **sync generator** in `StreamingResponse`.

## Index lifecycle
1. **Startup:** load `data/indexes/current` (a symlink to `data/indexes/<index_version>/`) once, in the
   lifespan handler. `/healthz` reports `index_loaded: false` until that finishes; search routes return
   `503` with code `API_INDEX_NOT_LOADED` meanwhile.
2. **Hot swap:** on SIGHUP, build the new `TantivyEngine` off to the side, then replace the single
   `state.engine` reference in one assignment. Never mutate the live engine.
3. **One served index per request.** The engine, its snapshot's records and its coverage are one bundle
   (`state.Served`), swapped as one reference. A handler takes it through `deps.ServedDep` (or just the
   engine through `deps.EngineDep`: the same read, cached per request) and uses that for hits, `total`,
   facets, `excluded`, a paper's record and coverage. Reading `state` twice, or looking records up by
   version, can mix two `index_version`s in one response (guarantee 4) or 500 after two swaps.
4. Older versions (for record replay) load on demand from `data/indexes/<v>/`, read-only.
   `data/indexes/` is immutable; the app never writes there.

## Errors: one shape everywhere
`{"error": {"code": "<CODE>", "message": "<human text>", "diagnostics": [Diagnostic]?}}`

Statuses and codes are **exactly** spec 04 §Error handling; this skill keeps no table of its own. In short:
422 `PARSE_*` (02 diagnostics, spans included) on endpoints that run the query (`POST /parse` reports them as a 200's `errors`), 422 `API_BAD_PARAM` (bad `sort`, `limit` > 200, unknown
`format`, malformed `record_id`: reject it, never clamp silently), 404 `API_PAPER_NOT_FOUND` /
`API_RECORD_NOT_FOUND`, 409 `API_INDEX_VERSION_UNAVAILABLE`, 409 `API_RECORD_MISMATCH` (export of a
`mismatch` record), 413 `API_BODY_TOO_LARGE` (a body over `max_body_bytes`, before it is read), 429 `API_RATE_LIMITED` + `Retry-After`, 503 `API_INDEX_NOT_LOADED`, 503 `API_RECORDS_STORE_FULL` (a record save into a full store), 503 `API_BUSY` + `Retry-After` (verification slots taken), 500 `API_INTERNAL`
(logged at ERROR with the request id; the message never echoes input), and for routing 404 `API_NOT_FOUND`
/ 405 `API_METHOD_NOT_ALLOWED` (task-034). A replay `mismatch` is a `200`, not an error. Codes come from the registry (`.claude/skills/error-diagnostics/SKILL.md`).

**Gotcha:** FastAPI's built-in `RequestValidationError` and `HTTPException` handlers emit `{"detail": …}`.
Override both, or the contract has two error shapes. See `.claude/skills/error-diagnostics/SKILL.md`.

**Parameters are exact** (spec 04 §Conventions): the app-wide `deps.strict_query` dependency refuses a
query parameter the route doesn't declare, or one given twice (422 `API_BAD_PARAM`), so declare every
parameter the route reads in its signature (a `Query(...)` with a `description`), never read
`request.query_params` for a value (only to tell whether a defaulted one was sent, as `/export`'s `mode`).
`redirect_slashes=False`: a trailing slash is a 404, never a redirect. A path id takes a `Path(pattern=…)`.
A Starlette `RuntimeError("Caught handled exception, but response already started")` wraps a typed error
raised mid-stream: `errors.internal_error` logs the cause's frames and reason, so keep `raise … from e`.

## Logging
- Logging is configured **only** in `backend/src/openproceedings/logs.py` (`configure_logging`, called
  from the API's startup). The app factory, routers and middleware never call `basicConfig`, add handlers
  or set levels.
- Exactly one access line per request, with the fields defined in
  `.claude/skills/logging-standards/SKILL.md` §API access line (the `request` event: `request_id`,
  `method`, route template, `status`, `ms`, `index_version`, `canonical_hash` for search/export, `total`;
  health checks at DEBUG). Don't define a second field list here.
- **Neither `q` nor the canonical or identification strings are logged by default** (spec 04
  §Implementation notes). All three reveal an unpublished review
  design. Config `log_query_text` (default `false`) is the only switch. Also keep query text out of
  exception messages and tracebacks that reach the log.

## Rate limit, body cap and CORS
- An in-app token bucket per client IP, and one per client network (IPv4 /24, IPv6 /48) checked with it,
  with capacity and refill set in config. Behind Caddy, take the client IP from `X-Forwarded-For` **only**
  when the peer is a configured trusted proxy (no network wider than /8 IPv4 or /32 IPv6: refused). Otherwise every user
  shares Caddy's IP, or anyone can spoof theirs.
- An export or a record route costs `export_weight` (it touches the whole set). A query's
  position-verified clauses are counted from the AST (`engine.compile.verified_clauses`): over
  `ApiConfig.max_verified_clauses` is 422 `API_TOO_MANY_VERIFIED_CLAUSES` (decision-010), else each costs
  `ApiConfig.verified_cost` (the cap × it fits the smaller bucket, checked by the config): a cost known only
  after the parse is charged with `middleware.charge(request.scope, total)` (`deps.charge_verified`, from
  `deps.searchable`). Then, on the route's engine, `deps.check_candidates` refuses a query whose position
  checks would read more than `max_verification_candidates` documents (422 `API_QUERY_TOO_COSTLY`); every
  route that runs the client's query calls both. A replay calls `deps.admit_replay` instead, which withholds
  (200, `refused`) rather than refusing. `API_BUSY` and `API_QUERY_TOO_COSTLY` give the verified charge back
  (`middleware.refund_charged`, from `RateLimit` by the access line's `code`).
  Cold verification is bounded by `ApiConfig.verification_slots` through `TantivyEngine.verification_gate`
  (set by `IndexState` on every engine it opens) and refused with 503 `API_BUSY`, never queued.
- Record saves are held to a per-network ceiling (`record_saves_network_burst`,
  `record_saves_network_per_hour`) and an instance-wide one (`record_saves_burst`, `record_saves_per_hour`),
  taken together (`api/records.py::SaveCeiling`); a save that then saves nothing is refunded.
- `BodyLimit` refuses a body over `ApiConfig.max_body_bytes` (64 KiB) before anything reads it, on
  `Content-Length` and on a chunked body's bytes. uvicorn runs with `limit_concurrency` and
  `timeout_keep_alive`; `op serve` sits behind the proxy, whose timeouts and request buffering spec 08 §Deploy
  requires. Swagger UI (CDN scripts) is off unless `ApiConfig.serve_docs` (`op serve`: loopback only).
- CORS: an explicit origin allowlist from config. No `*`, no regex wildcards. v1 has no auth and no
  cookies, so `allow_credentials=False`.

## Checklist for an API change
- [ ] handler is `def`, reads the served index once (`ServedDep` / `EngineDep`)
- [ ] every query parameter declared and described; ids carry a `pattern`; response fields always sent
- [ ] errors go through the shared shape; no `{"detail"}` leaks (contract test)
- [ ] every response carries `index_version`, `tokenizer_version` and `query_version`
- [ ] no query text in logs (a test asserts it on a captured log line); one access line per request
- [ ] OpenAPI snapshot and `frontend/src/api/schema.ts` regenerated (`api-contract`)
