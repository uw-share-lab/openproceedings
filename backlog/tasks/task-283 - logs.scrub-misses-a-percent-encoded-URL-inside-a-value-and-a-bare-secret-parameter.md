---
id: TASK-283
title: >-
  logs.scrub misses a percent-encoded URL inside a value and a bare secret
  parameter
status: To Do
assignee: []
created_date: '2026-10-23 15:06'
labels:
  - logging
  - security
dependencies: []
priority: low
ordinal: 185000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-275's round-2 security review (2026-10-23), pre-existing: scrub matches a secret parameter only after ?, &, # or ;, on the text as written. So ?next=https%3A%2F%2Fh%2F%3Ftoken%3Dabc (a redirect target, percent-encoded) and a bare access_token=abc with nothing before it are logged in clear. Neither is on a current path: OpenReview's bearer token travels in a header, and httpx error text carries only the request URL. Options: decode percent-escapes in a value before matching (bounded, linear), and/or start a parameter at any non-name character; either must stay linear and only add redaction.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scrub redacts a secret parameter inside a percent-encoded URL value, or the limit is documented in logging-standards with the owner's decision
- [ ] #2 scrub redacts a bare secret=value at the start of the text or after a non-name character, with an over-redaction check on ordinary prose, or the limit is documented
- [ ] #3 linear on hostile input (CPU-growth test), and every string scrub redacted before is still redacted (old-vs-new comparison)
<!-- AC:END -->
