---
id: TASK-184
title: 'op serve flags for the comparison caps, cooldown factor and upload weight'
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
labels:
  - ops
  - api
milestone: m-6
dependencies: []
ordinal: 128000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-177 exposes only --compare / --no-compare; the caps, compare_cooldown_factor, compare_upload_weight and compare_token_ms are ApiConfig values an operator cannot set from the command line.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each has a flag documented in spec 08 and deploy/README.md, validated at start, and shown in /meta where it is a limit
<!-- AC:END -->
