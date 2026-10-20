---
id: TASK-275
title: logs.scrub's URL-userinfo pattern is quadratic on a long alphanumeric run
status: To Do
assignee: []
created_date: '2026-10-20 15:18'
labels:
  - logging
  - security
dependencies: []
ordinal: 182000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-272's security sweep (2026-10-20), pre-existing: logs.py _URL_USERINFO.sub in scrub() takes 317 ms on a 20k alphanumeric run and 11.1 s on 100k; every log message and exception passes through it, so long crawled text reaching a log line pays it. Reviewer's candidate (identical sub output on 6.7M short strings, ~2 ms at 100k): (?<![a-zA-Z0-9+.-])(?P<pre>[0-9+.-]*+)(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*+://)[^/\s@]+@ replaced with \g<pre>\g<scheme>…@ (a plain lookbehind would stop redacting '1a://user@').
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scrub's userinfo redaction is linear with identical output (exhaustive short-string comparison), with a CPU-growth test
<!-- AC:END -->
