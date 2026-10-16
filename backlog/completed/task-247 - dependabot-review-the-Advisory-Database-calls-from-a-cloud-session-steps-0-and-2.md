---
id: TASK-247
title: >-
  dependabot-review: the Advisory Database calls from a cloud session (steps 0
  and 2)
status: Done
assignee: []
created_date: '2026-10-14 01:13'
updated_date: '2026-10-16 18:00'
labels:
  - tooling
  - ci
dependencies: []
references:
  - decision-048
  - TASK-243
ordinal: 173000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The GitHub Advisory Database calls /dependabot-review makes (gh api advisories?ecosystem=...&affects=..., step 0's uv query and step 2's per-package queries) are a path outside repos/, so a Claude Code cloud session's proxy may refuse them with its HTTP 403 'sessions are bound to their configured repositories' (TASK-243 probe, 2026-10-13, session cse_01Q24cxnP5Nu3yXGC2FKjWqW, which did not try them). Until decided, the procedure fails closed: a refused step 2 query is a hard stop for that PR (check couldn't run), a refused step 0 uv query goes under 'for the owner' (decision-048, TASK-243 AC3/AC6 addendum). Can't be done yet: it needs a cloud session to probe the call.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A cloud session's answer to gh api 'advisories?ecosystem=npm&affects=next&per_page=1' is recorded (status and message)
- [x] #2 If refused: the owner decides whether step 2 keeps the hard stop, relies on npm audit --package-lock-only and the release notes, or another source; decision-048 and the procedure record it
- [x] #3 If it answers: the procedure's TASK-247 caveats are removed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16 (chore/dependabot-cloud-notify-only): AC1: the scheduled cloud run (session cse_014uvWwXsnPaQKx5UQf2fD6u, 15:02-15:05Z) called gh api 'advisories?ecosystem=pip&affects=uv&per_page=100' (step 0's query; the same advisories endpoint as AC1's npm/next probe) and was refused with HTTP 403 {"message":"This GitHub API path is not available: sessions are bound to their configured repositories"...}. AC2: the owner decided on 2026-10-16 that the cloud routine is notify-only (decision-048 addendum), so no cloud run merges: a refused per-package query keeps that PR off the cloud summary's 'ready for a local run' list ('advisories for <pkg>: not checked in the cloud'), a refused uv query goes under 'for the owner', and the local run that merges makes the queries itself; procedure steps 0 and 2 and spec 08 say so. AC3: not applicable (the call is refused); the 'not yet seen from a cloud session' caveats are replaced with the recorded refusal.

Review round 1: AC1's text names an npm/next probe; the recorded call is step 0's pip/uv query on the same advisories endpoint, which answers the question AC1 asks. AC3 is conditional ('if it answers') and is ticked as settled: the call is refused, and the 'not yet seen from a cloud session' caveats are gone. Correction to the note above: a refused per-package query does not keep a PR from 'ready for a local run' (that would make every cloud PR unready, since every cloud query is refused); it is listed as 'checked only locally' on the PR's line, and the local run makes the query (procedure step 2, spec 08, decision-048).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The cloud's Advisory Database call is refused (HTTP 403 'This GitHub API path is not available: sessions are bound to their configured repositories', 2026-10-16 run). Under the owner's notify-only decision a refused query is reported, not a stop: step 0's uv query goes under 'for the owner', a per-package query is listed as 'checked only locally' on the PR's line without keeping it from 'ready for a local run', and the local run that merges makes the queries. Procedure steps 0 and 2, spec 08 and decision-048 record it.
<!-- SECTION:FINAL_SUMMARY:END -->
