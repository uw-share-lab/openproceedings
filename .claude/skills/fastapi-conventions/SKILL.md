---
name: fastapi-conventions
description: How the openproceedings FastAPI service is built — /api/v1 base path, sync handlers for CPU-bound Tantivy, one index load at startup, the atomic hot-swap on SIGHUP, the single error shape, structured JSON logs that omit query text by default, the per-IP token bucket and the CORS allowlist. Use when writing or reviewing anything under backend/src/openproceedings/api/, adding a router or middleware, or changing app startup, logging or config.
---

# FastAPI conventions (spec 04 §Conventions, §Implementation notes)

## App shape
- One app factory, `create_app(config) -> FastAPI`, in `backend/src/openproceedings/api/`. Routers per
  resource (`search`, `parse`, `papers`, `export`, `records`, `coverage`, `meta`, `health`, and
  `near_misses` at M5), all mounted under **`/api/v1`**, `/healthz` included (spec 04 §Endpoints: liveness and whether the
  index is loaded). Nothing is served outside `/api/v1`.
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
3. **One engine per request.** A handler reads `engine = state.engine` **once** and uses that object for
   hits, `total`, facets and `excluded`. Reading it twice can mix two `index_version`s in one response,
   which breaks guarantee 4.
4. Older versions (for record replay) load on demand from `data/indexes/<v>/`, read-only.
   `data/indexes/` is immutable; the app never writes there.

## Errors: one shape everywhere
`{"error": {"code": "<CODE>", "message": "<human text>", "diagnostics": [Diagnostic]?}}`

Statuses and codes are **exactly** spec 04 §Error handling; this skill keeps no table of its own. In short:
422 `PARSE_*` (02 diagnostics, spans included), 422 `API_BAD_PARAM` (bad `sort`, `limit` > 200, unknown
`format`, malformed `record_id`: reject it, never clamp silently), 404 `API_PAPER_NOT_FOUND` /
`API_RECORD_NOT_FOUND`, 409 `API_INDEX_VERSION_UNAVAILABLE`, 409 `API_RECORD_MISMATCH` (export of a
`mismatch` record), 429 `API_RATE_LIMITED` + `Retry-After`, 503 `API_INDEX_NOT_LOADED`, 500 `API_INTERNAL`
(logged at ERROR with the request id; the message never echoes input). A replay `mismatch` is a `200`, not
an error. Codes come from the registry (`.claude/skills/error-diagnostics/SKILL.md`).

**Gotcha:** FastAPI's built-in `RequestValidationError` and `HTTPException` handlers emit `{"detail": …}`.
Override both, or the contract has two error shapes. See `.claude/skills/error-diagnostics/SKILL.md`.

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

## Rate limit and CORS
- An in-app token bucket per client IP, with capacity and refill set in config. Behind Caddy, take the
  client IP from `X-Forwarded-For` **only** when the peer is a configured trusted proxy. Otherwise every
  user shares Caddy's IP, or anyone can spoof theirs.
- An export costs more than one token (it touches the whole set). Pin the weight in config.
- CORS: an explicit origin allowlist from config. No `*`, no regex wildcards. v1 has no auth and no
  cookies, so `allow_credentials=False`.

## Checklist for an API change
- [ ] handler is `def`, reads the engine once
- [ ] errors go through the shared shape; no `{"detail"}` leaks (contract test)
- [ ] every response carries `index_version`, `tokenizer_version` and `query_version`
- [ ] no query text in logs (a test asserts it on a captured log line); one access line per request
- [ ] OpenAPI snapshot and `frontend/src/api/schema.ts` regenerated (`api-contract`)
