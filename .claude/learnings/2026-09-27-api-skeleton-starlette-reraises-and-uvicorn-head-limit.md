# Starlette re-raises every 500 to the server, and uvicorn's default head limit refuses valid long queries

**Key lesson:** In the API, catch unexpected exceptions in our own outermost ASGI middleware and never re-raise (Starlette's `ServerErrorMiddleware` always re-raises, so uvicorn logs a traceback whose last line quotes the query), and run uvicorn with `h11_max_incomplete_event_size` ≥ 64 KiB (the 16 KiB default answers a valid 2,000-code-point CJK query with a bare 400 before the app sees it).

- **Date:** 2026-09-27 · **Task:** task-034 · **Area:** api
- **Artifacts:** `backend/src/openproceedings/api/{app,middleware,errors,state,deps,server}.py`, `backend/src/openproceedings/logs.py` (`route_server_loggers`), `backend/tests/contract/`

## What we set out to do
The FastAPI skeleton: startup index load and SIGHUP hot swap, one error envelope, one JSON access line per
request with no query text, per-client rate limit, CORS allowlist, and the query-length cap before parsing.

## What we learned
- **A registered `Exception` handler doesn't stop the re-raise.** Starlette 1.7
  `middleware/errors.py` sends the handler's response and then `raise exc` ("allows servers to log the
  error"); uvicorn then logs "Exception in ASGI application" with the traceback, message included. The fix
  is the `AccessLog` middleware (added last, so outermost inside `ServerErrorMiddleware`) catching,
  logging type + frames, and answering the 500 itself. Evidence: `test_500_does_not_reach_the_test_client_as_an_exception`
  passes with `TestClient`'s default `raise_server_exceptions=True`.
- **uvicorn's request-head limit is below the query cap.** 2,000 × `信` URL-encodes to 18 KB; uvicorn's h11
  default (16 KiB) refuses it with a plain-text 400, outside the error envelope. `api/server.py`
  sets 64 KiB; `test_the_real_server_logs_one_access_line_per_request_and_nothing_else_of_uvicorns` sends
  both the 2,000-code-point query (200) and a 40k-character one (422 `PARSE_TOO_LONG`) through a real
  uvicorn on loopback.
- **`uvicorn.access` must be off, not just routed.** Its line holds the path *with the query string*, i.e.
  `q`; our own `request` line replaces it (`access_log=False` plus `configure_logging(route_server_loggers=True)`
  disabling the logger).
- **Starlette 1.7 deprecates `httpx` for `TestClient`; the dev dependency is `httpx2`**, whose loggers are
  `httpx2`/`httpcore2`, so those are pinned to WARNING alongside `httpx`/`httpcore`.
- **FastAPI 0.141 keeps included routers as `_IncludedRouter` objects**, so `app.routes` no longer lists
  the flattened paths; `scope["route"].path` after routing is still the full template, which is what the
  access line logs.
- **The route template is only known after routing**, so a request refused by the rate limit (before
  routing) logs `route: null`.
- **`TantivyEngine`'s caches have check-then-read races** under concurrent handlers (a `clear()` between
  `key in cache` and `cache[key]`): task-080.

## Dead ends — don't repeat these
- Registering `app.add_exception_handler(Exception, …)` to hide tracebacks: it answers the client but the
  exception still reaches uvicorn's logger.
- Making the query-length cap an API config value: a lower API cap would refuse queries `op search`
  accepts. The cap is the parser's (`parser.too_long`), shared by both.

## Decisions (and what would change them)
- Routing 404/405 get their own codes (`API_NOT_FOUND`, `API_METHOD_NOT_ALLOWED`), added to spec 04's
  table, since spec 04 had none and the envelope needs a code → reverse only by a spec 04 decision.
- A failed SIGHUP reload keeps the engine being served (ERROR `index_load_failed`); 503 only before any
  load succeeded → would change if spec 04 intends "failed swap" to mean "stop serving".
- The index loads in a background thread at startup so `/healthz` can report `index_loaded: false`.

## Follow-ups
- [ ] task-080 — TantivyEngine caches must be safe under concurrent API requests
- [ ] task-079 — cap request bodies before they are read (needs a spec 04 status/code)

## Propagated to
- Skill / agent / CLAUDE.md updated? — `docs/specs/04-backend-api.md` (as built, error table),
  `.claude/skills/fastapi-conventions/SKILL.md`, `.claude/skills/error-diagnostics/SKILL.md`, `CLAUDE.md` layout
- Test or hook added? — `backend/tests/contract/test_errors.py`, `test_serve.py`, `test_access_log.py`
