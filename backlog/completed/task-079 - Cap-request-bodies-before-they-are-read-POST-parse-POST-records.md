---
id: TASK-079
title: 'Cap request bodies before they are read (POST /parse, POST /records)'
status: Done
assignee: []
created_date: '2026-09-27 07:20'
updated_date: '2026-09-27 11:25'
labels:
  - api
milestone: m-3
dependencies:
  - TASK-034
ordinal: 77000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-034. checked_query() refuses a q over 2,000 code points in O(1), but for a JSON body (POST /parse, POST /records) FastAPI reads and decodes the whole body first, so a multi-megabyte body costs memory and CPU before the cap applies. Spec 04 has no status/code for an oversized body (413 is not in §Error handling), so this needs a spec 04 row first (e.g. 413 with a new API_ code, or 422 PARSE_TOO_LONG when Content-Length exceeds a bound), then an ASGI check on Content-Length and on the streamed byte count. GET query strings are already bounded by op serve's 64 KiB request-head limit (api/server.py MAX_REQUEST_HEAD).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Spec 04 §Error handling defines the status and code for an oversized body
- [x] #2 A body over the configured bound is refused before it is fully read (Content-Length and chunked), in the one error envelope, with a contract test
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
M3a gate (security review Must 1): api/middleware.py BodyLimit, a pure-ASGI layer inside LastCatch and outside RateLimit, refuses a body over ApiConfig.max_body_bytes (64 KiB) with 413 API_BODY_TOO_LARGE (new registry code; spec 04 §Error handling row) on Content-Length without reading a byte, or once a chunked body's bytes pass the cap; a body within the cap is read here and replayed to the app. Verified by backend/tests/contract/test_abuse_limits.py: Content-Length and chunked refusals, the refusal before 503 API_INDEX_NOT_LOADED, a direct ASGI call whose receive() must never run, and a 2,000-astral-code-point q as JSON escapes (~24 KB) still admitted.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Request bodies are capped before they are read: 413 API_BODY_TOO_LARGE over ApiConfig.max_body_bytes (64 KiB), by Content-Length or streamed bytes, ahead of every other check. Spec 04 §Error handling has the row; contract tests in test_abuse_limits.py; full pytest, make lint and make tooling green.
<!-- SECTION:FINAL_SUMMARY:END -->
