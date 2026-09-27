---
id: TASK-079
title: 'Cap request bodies before they are read (POST /parse, POST /records)'
status: To Do
assignee: []
created_date: '2026-09-27 07:20'
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
- [ ] #1 Spec 04 §Error handling defines the status and code for an oversized body
- [ ] #2 A body over the configured bound is refused before it is fully read (Content-Length and chunked), in the one error envelope, with a contract test
<!-- AC:END -->
