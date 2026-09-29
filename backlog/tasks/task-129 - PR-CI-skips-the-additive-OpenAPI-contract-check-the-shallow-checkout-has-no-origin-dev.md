---
id: TASK-129
title: >-
  PR CI skips the additive OpenAPI contract check: the shallow checkout has no
  origin/dev
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 23:22'
updated_date: '2026-09-29 23:23'
labels:
  - ci
  - api
dependencies: []
ordinal: 113000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
test_openapi_additive compares the committed OpenAPI snapshot against origin/dev's (OPENAPI_BASELINE_REF). actions/checkout's default fetch-depth 1 fetches no origin/dev, so the test skips on every PR run (seen on the runs for PRs 23, 24 and 26), and a breaking API change would pass CI. Found 2026-09-29 while measuring TASK-127.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 CI fetches the PR's base branch so OPENAPI_BASELINE_REF resolves, comparing against the base the PR merges into
- [x] #2 In CI the test fails instead of skipping when the baseline can't be read; locally it still skips
- [ ] #3 The PR's own CI run shows the test ran (not in the skip list)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
test.yml's backend step fetches the base branch (github.base_ref, or the pushed branch) at depth 1 into refs/remotes/origin/<base>, exports OPENAPI_BASELINE_REF, and sets OPENAPI_BASELINE_REQUIRED=1; test_openapi_additive fails instead of skipping when that is set and the baseline can't be read. Verified locally: default run passes (17), OPENAPI_BASELINE_REQUIRED=1 with a missing ref fails. The api-contract skill says so.
<!-- SECTION:NOTES:END -->
