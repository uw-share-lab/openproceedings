---
id: TASK-183
title: Smoke-test the Caddy block that enables comparisons on a public instance
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
updated_date: '2026-10-05 13:21'
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
- [ ] #1 The enabled stack passes smoke-test.sh with a comparison upload, a stalled upload is cut by the proxy before it holds the slot, and the README's untested note is removed or the block corrected
- [ ] #2 N concurrent maximum-size uploads stay bounded in proxy memory (a memory limit on the caddy service is part of the enable steps), measured
- [ ] #3 The block scopes the site's 64KB request_body cap away from /api/v1/compare (the site-level cap otherwise still fires), uses 16MiB to match /meta's max_body_bytes, and the docs say read_body is a server-wide timeout
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Gate fix round 1 (2026-10-05, SEC-S1 and SEC-183): add to the acceptance criteria that N concurrent 16 MiB uploads stay bounded in the proxy's memory (request_buffers holds each in-flight upload before the API can refuse it; 200 at once is about 3.2 GB, and they cost no tokens), with a mem_limit on the caddy service as part of the enable steps. The block as written cannot work: the site-level request_body max_size 64KB (deploy/Caddyfile) wraps it first, so scope the 64KB cap with @rest not path /api/v1/compare and keep 16MiB under @compare; and Caddy's 16MB is 16,000,000 bytes, under the 16,777,216 the API advertises, so write 16MiB. read_body is a server-wide timeout (spec 08 now says so). deploy/README.md says all of this beside the block.
<!-- SECTION:NOTES:END -->
