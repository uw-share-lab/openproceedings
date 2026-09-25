---
name: fastapi-conventions
description: How the openproceedings FastAPI service is built — /api/v1 base path, sync handlers for CPU-bound Tantivy, one index load at startup, the atomic hot-swap on SIGHUP, the single error shape, structured JSON logs that omit query text by default, the per-IP token bucket and the CORS allowlist. Use when writing or reviewing anything under backend/src/openproceedings/api/, adding a router or middleware, or changing app startup, logging or config.
---

# FastAPI conventions (spec 04 §Conventions, §Implementation notes)

## App shape
- One app factory, `create_app(config) -> FastAPI`, in `backend/src/openproceedings/api/`. Routers per
  resource (`search`, `parse`, `papers`, `export`, `records`, `coverage`, `meta`, `health`, and
  `near_misses` at M5), all mounted under **`/api/v1`**. Nothing is served outside it except `/healthz`
  if the deploy probe needs it; verify against `deploy/compose.yml` at implementation time.
- The CLI (`op search`, `op export`, `op serve`) and the routers call **the same functions**. A router
  parses the request, calls the shared function, and shapes the response. No search logic lives in a router.
- Pydantic v2 models are the contract (`.claude/skills/api-contract/SKILL.md`). Every response model
  carries `index_version` and `tokenizer_version`.

## Handlers are `def`, not `async def`
Tantivy search, `match_ids`, facets and exclusion accounting are CPU-bound and release no event loop.
Declare handlers as plain `def` so FastAPI runs them in its thread pool. An `async def` handler that calls
the engine blocks every other request. Exports use a **sync generator** in `StreamingResponse`.

## Index lifecycle
1. **Startup:** load `data/indexes/current` (a symlink to `data/indexes/<index_version>/`) once, in the
   lifespan handler. `/healthz` reports `index_loaded: false` until that finishes; search routes return
   `503` with code `index_not_loaded` meanwhile.
2. **Hot swap:** on SIGHUP, build the new `TantivyEngine` off to the side, then replace the single
   `state.engine` reference in one assignment. Never mutate the live engine.
3. **One engine per request.** A handler reads `engine = state.engine` **once** and uses that object for
   hits, `total`, facets and `excluded`. Reading it twice can mix two `index_version`s in one response,
   which breaks guarantee 4.
4. Older versions (for record replay) load on demand from `data/indexes/<v>/`, read-only.
   `data/indexes/` is immutable; the app never writes there.

## Errors: one shape everywhere
`{"error": {"code": "<snake_case>", "message": "<human text>", "diagnostics": [Diagnostic]?}}`
| Situation | Status | code |
|---|---|---|
| Query parse error (02 diagnostics, spans included) | 422 | `parse_error` |
| Bad parameter (`limit` > 200, unknown `sort`/`format`) | 422 | `invalid_parameter` (reject it, never clamp silently) |
| Unknown paper or record | 404 | `not_found` |
| Rate limited | 429 + `Retry-After` | `rate_limited` |
| Index not loaded / requested `index_version` absent | 503 | `index_not_loaded` / `index_unavailable` |

**Gotcha:** FastAPI's built-in `RequestValidationError` and `HTTPException` handlers emit `{"detail": …}`.
Override both, or the contract has two error shapes. See `.claude/skills/error-diagnostics/SKILL.md`.

## Logging
One structured JSON line per request: `request_id`, route, status, `latency_ms`, `canonical_hash`,
`total`, `index_version`. **Neither the raw `q` nor the canonical string is logged by default.** Both
reveal an unpublished review design. Config `log_query_text` (default `false`) is the only switch.
Also keep query text out of exception messages and tracebacks that reach the log.

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
- [ ] no query text in logs (a test asserts it on a captured log line)
- [ ] OpenAPI snapshot and `frontend/src/api/schema.ts` regenerated (`api-contract`)
