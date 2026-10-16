---
id: TASK-183
title: Smoke-test the Caddy block that enables comparisons on a public instance
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-05 08:39'
updated_date: '2026-10-16 18:37'
labels:
  - ops
  - security
milestone: m-6
dependencies: []
ordinal: 127000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-035 makes this a precondition: deploy/README.md's Caddy snippet for an instance run with --compare has never been through deploy/smoke-test.sh (its image builds need network, which TASK-177's sessions lacked). That block is what keeps a slow upload off the single comparison slot.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The enabled stack passes smoke-test.sh with a comparison upload, a stalled upload is cut by the proxy before it holds the slot, and the README's untested note is removed or the block corrected
- [x] #2 N concurrent maximum-size uploads stay bounded in proxy memory (a memory limit on the caddy service is part of the enable steps), measured
- [x] #3 The block scopes the site's 64KB request_body cap away from /api/v1/compare (the site-level cap otherwise still fires), uses 16MiB to match /meta's max_body_bytes, and the docs say read_body is a server-wide timeout
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Gate fix round 1 (2026-10-05, SEC-S1 and SEC-183): add to the acceptance criteria that N concurrent 16 MiB uploads stay bounded in the proxy's memory (request_buffers holds each in-flight upload before the API can refuse it; 200 at once is about 3.2 GB, and they cost no tokens), with a mem_limit on the caddy service as part of the enable steps. The block as written cannot work: the site-level request_body max_size 64KB (deploy/Caddyfile) wraps it first, so scope the 64KB cap with @rest not path /api/v1/compare and keep 16MiB under @compare; and Caddy's 16MB is 16,000,000 bytes, under the 16,777,216 the API advertises, so write 16MiB. read_body is a server-wide timeout (spec 08 now says so). deploy/README.md says all of this beside the block.

Done (2026-10-16, fix/compare-proxy-block): comparisons are turned on by the overlay deploy/compare.yml (api: op serve --compare; caddy: OP_COMPARE=on, OP_READ_BODY 60s, mem_limit 1g with no swap, GOMEMLIMIT 800MiB). The Caddyfile imports compare-{$OP_COMPARE:off}: compare-on scopes the 64KiB cap to @rest (not path /api/v1/compare) and gives the path request_body and request_buffers of 16MiB, plus 411 for a POST with no Content-Length. Found on the stack: past request_buffers Caddy streams the rest of a body (bufferedBody returns MultiReader once the limit is read or a read fails), so a chunked upload over 16 MiB that stalled held the API slot until its 30 s upload timeout; the 411 closes it (Chromium sends a Content-Length for a Blob over HTTP/2). 64KB/16MB were 64,000/16,000,000 bytes: now 64KiB/16MiB everywhere. smoke-test.sh --compare passed (168 s; plain 110 s, also passed): 8 uploads stalled a byte short of 16 MiB were held in the proxy (446 MiB, peak 482 MiB of 1 GiB, no OOM kill), a 16 MiB comparison ran meanwhile (200), the API logged only it, each stall cut 58.4 s after its last byte (read_body 60s), 16 MiB+1 -> 413 (API, from the header), chunked and unsized HTTP/2 -> 411, 64KiB+1 elsewhere -> 413. Measured separately with compare_probe.py: 16 uploads 793 MiB, 24 uploads 912 MiB (no OOM), 32 uploads OOM-killed (docker oom event, exit 137) and restarted. Follow-ups reported to the lead: the 64 KiB stream-through on the other API routes; a per-client connection or upload cap in front of the proxy.

Gate round 1 (2026-10-16): no Must. Fixed: HTTP/3 off with comparisons on (protocols-on snippet; Caddy's HTTP/3 server isn't given read_body); the smoke test now checks the proxy's adapted body caps and protocols (the 64 KiB 413 is the API's own, from the declared length), Alt-Svc only with comparisons off, caddy restarts 0, each stall timed from its request's start (60.02 s with read_body 60s), memory.peak with a sampled fallback; the probe can't hang (connect errors caught, barrier timeout, killed on failure) and has unit tests (backend/tests/deploy/test_compare_probe.py); decision-035 got an as-built note; measurements in docs/results/2026-10-16-compare-proxy.md. Rerun: smoke-test.sh PASS 97 s, --compare PASS 160 s (8 stalls held 412 MiB, peak 448 MiB of 1 GiB).
<!-- SECTION:NOTES:END -->
