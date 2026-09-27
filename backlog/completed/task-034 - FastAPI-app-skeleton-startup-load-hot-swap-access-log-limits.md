---
id: TASK-034
title: 'FastAPI app skeleton: startup load, hot-swap, access log, limits'
status: Done
assignee:
  - '@api-engineer'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 07:23'
labels:
  - api
milestone: m-3
dependencies:
  - TASK-030
ordinal: 33000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 04 §Conventions and §Implementation notes (fastapi-conventions, logging-standards skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Index loaded once; atomic hot-swap on SIGHUP; exports in flight finish on their index
- [x] #2 One JSON access line per request with the logging-standards fields; no query text
- [x] #3 Per-IP rate limit and CORS allowlist from config; /healthz
- [x] #4 Route uvicorn.* loggers through the openproceedings JSON handler and pin httpx to WARNING (its INFO lines print full request URLs); a test asserts one access line per request
- [x] #5 Access log for /parse and /search: canonical_hash, token count, error/warning codes (capped), n_errors, total; never q, canonical, messages or spans; a parse failure is DEBUG at most
- [x] #6 A query-length cap (spec 02) is enforced before parsing; a 40k-character q is rejected cheaply (test)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. ApiConfig (config.py); 2. IndexState with restricted index_path, background load, SIGHUP reload + one-reference swap (state.py); 3. error envelope + handlers overriding RequestValidationError/HTTPException (errors.py); 4. AccessLog + RateLimit pure-ASGI middleware, CORS allowlist (middleware.py, app.py); 5. EngineDep, checked_query (parser.too_long), annotate/annotate_parse (deps.py); 6. /healthz; 7. op serve (server.py, cli.py) with uvicorn loggers routed via logs.configure_logging(route_server_loggers=True); 8. contract tests over the 5k fixture index with probe routes standing in for task-035.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From the M2 gate (observability): the CLI's cli_failed logs the traceback, whose last line is the exception message and can quote input; the API must log frames and type, not the message. resolve_snapshot accepts any path; don't reuse it for API index/snapshot selection (limit names to [0-9a-f-] under the data dir).

Built: backend/src/openproceedings/api/{__init__,app,config,state,deps,errors,middleware,health,server}.py; op serve in cli.py; parser.too_long shared by parse() and the API; logs.configure_logging(route_server_loggers=True). Tests: backend/tests/contract/{test_lifecycle,test_errors,test_access_log,test_limits,test_serve}.py (probe routes in contract/conftest.py stand in for task-035's /parse and /search, using EngineDep, checked_query, annotate_parse, annotate). AC1: test_sighup_swaps_atomically_and_a_request_in_flight_keeps_its_engine, test_a_stream_started_before_a_swap_finishes_on_its_index, test_the_index_is_loaded_once_at_startup, test_a_failed_swap_keeps_serving_the_old_index. AC2: test_one_access_line_per_request_whatever_the_outcome, test_no_query_text_reaches_any_log_line. AC3: test_limits.py (bucket, XFF only from trusted proxies, export weight, CORS exact origins, no credentials), test_healthz_*. AC4: test_server_loggers_go_through_the_json_handler, test_real_requests_through_the_routed_loggers_give_one_line_each, test_the_real_server_logs_one_access_line_per_request_and_nothing_else_of_uvicorns (real uvicorn on loopback). AC5: test_a_search_line_has_the_hash_count_and_total_and_no_query_text, test_a_parse_failure_logs_codes_only_and_nothing_above_info, test_parse_fields_cap_the_codes_listed. AC6: test_a_40k_character_query_is_rejected_before_parsing (lexer patched to fail), test_the_cap_is_code_points_and_exactly_the_parsers. Spec additions (need api-contract review): 404 API_NOT_FOUND and 405 API_METHOD_NOT_ALLOWED for routing, in the registry and spec 04's table. Decisions: the query-length cap is the parser's (not configurable) so API == CLI; a failed SIGHUP reload keeps the served engine (503 only before any load); uvicorn head limit raised to 64 KiB (16 KiB default refuses a valid 2,000-code-point CJK query). Dev dependency is httpx2 (Starlette 1.7 deprecates httpx for TestClient). Follow-ups: TASK-078 (engine cache races under concurrent requests), TASK-079 (request-body cap; needs a spec 04 code). uv run pytest: 2353 passed, 1 skipped before formatting; make lint clean.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
FastAPI skeleton in backend/src/openproceedings/api/: create_app(ApiConfig), background startup load, SIGHUP reload with a one-reference atomic swap (failed reload keeps the served engine), restricted index selection under data_dir/indexes, EngineDep (engine read once per request), the one error envelope (RequestValidationError and HTTPException overridden; 404 API_NOT_FOUND and 405 API_METHOD_NOT_ALLOWED added to the registry and spec 04), /api/v1/healthz, per-client token bucket (XFF only from trusted proxies, export weight), exact CORS allowlist without credentials, one JSON access line per request with no query text, uvicorn loggers routed through logs.py, httpx pinned to WARNING, PARSE_TOO_LONG via checked_query before parsing, and op serve. Verified by 64 contract tests in backend/tests/contract/ (incl. a real uvicorn on loopback); uv run pytest 2353 passed, 1 skipped; make lint and make tooling clean. Follow-ups TASK-078, TASK-079.
<!-- SECTION:FINAL_SUMMARY:END -->
