---
id: TASK-277
title: uv 0.13.1 → 0.13.4 by hand (image and CI pins together)
status: In Progress
assignee: []
created_date: '2026-10-21 02:44'
updated_date: '2026-10-21 02:50'
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
- [x] #1 deploy/api.Dockerfile pins uv 0.13.4 by the digest ghcr.io resolves the tag to, and all 11 setup-uv steps say 0.13.4 (check_uv_pin.py: 0 problems)
- [x] #2 The digest's GitHub attestation verifies for astral-sh's publish-docker-image workflow, the same publisher as 0.13.1's pin
- [x] #3 uv lock --check passes under 0.13.4, and the api image builds with it
- [x] #4 Spec 08 §Dependabot records the bump and the owner's waiver of the 7-day age
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-21: ghcr.io (anonymous token) resolves uv:0.13.4 to sha256:9f130421e930bfbdc563c00740466603f8723158e90297d07957c2294640262b; the same lookup returns 0.13.1's pinned digest, so the method matches. gh attestation verify: astral-sh/uv publish-docker-image.yml@refs/heads/main, the same signer as 0.13.1's pin, attested 2026-10-20 15:23Z. docker_digest.py --base origin/dev: registry and attestation ok; its one problem is the age (0.5 days), which the owner waived for this pin. uvx uv==0.13.4 uv lock --check: no change. check_uv_pin.py: 11 setup-uv steps, 0 problems. docker build of deploy/api.Dockerfile green; the uv stage reports uv 0.13.4 (aarch64-unknown-linux-musl).
<!-- SECTION:NOTES:END -->
