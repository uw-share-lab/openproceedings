---
id: TASK-277
title: uv 0.13.1 → 0.13.4 by hand (image and CI pins together)
status: To Do
assignee: []
created_date: '2026-10-21 02:44'
labels:
  - deps
  - ci
dependencies: []
priority: medium
ordinal: 184000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No Dependabot PR is open for uv 0.13.4: #162 had been rebased to 0.13.4 but closed when #175 (TASK-270, 0.13.1) merged. Dependabot's docker update moves deploy/api.Dockerfile's ghcr.io/astral-sh/uv tag alone, which fails claude-tooling (check_uv_pin.py, TASK-252), so the bump is made by hand with every setup-uv version (spec 08 §Dependabot). uv 0.13.4 was released 2026-10-20 15:25Z (0.13.2 and 0.13.3 the same day); on 2026-10-21 the owner asked for it now, waiving the 7-day age for this pin.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 deploy/api.Dockerfile pins uv 0.13.4 by the digest ghcr.io resolves the tag to, and all 11 setup-uv steps say 0.13.4 (check_uv_pin.py: 0 problems)
- [ ] #2 The digest's GitHub attestation verifies for astral-sh's publish-docker-image workflow, the same publisher as 0.13.1's pin
- [ ] #3 uv lock --check passes under 0.13.4, and the api image builds with it
- [ ] #4 Spec 08 §Dependabot records the bump and the owner's waiver of the 7-day age
<!-- AC:END -->
