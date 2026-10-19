---
id: TASK-270
title: uv 0.13.0 → 0.13.1 by hand (image and CI pins together)
status: In Progress
assignee: []
created_date: '2026-10-19 13:28'
updated_date: '2026-10-19 13:28'
labels:
  - deps
  - ci
dependencies: []
priority: medium
ordinal: 177000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Dependabot's #162 moves deploy/api.Dockerfile's ghcr.io/astral-sh/uv tag alone, which fails claude-tooling (check_uv_pin.py, TASK-252), so it is remade by hand with every setup-uv version (spec 08 §Dependabot). uv 0.13.1 was released 2026-10-14; the owner's 7-day hold clears 2026-10-21 (docker_digest.py: first attested 5.3 days ago on 2026-10-19). Owner chose (2026-10-19): prepare now, merge on or after 2026-10-21.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 deploy/api.Dockerfile pins uv 0.13.1 by the digest Dependabot proposed, and all 11 setup-uv steps say 0.13.1 (check_uv_pin.py: 0 problems)
- [x] #2 The api image builds with uv 0.13.1 (uv sync --locked) and uv lock --check passes under 0.13.1
- [ ] #3 docker_digest.py passes the uv pin's 7-day age on the merge day; merged on or after 2026-10-21; #162 closed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Digest verified (registry resolves 0.13.1 to it; GitHub attestation for astral-sh). docker build of api.Dockerfile green; uv stage reports uv 0.13.1 (aarch64 musl). uvx uv==0.13.1 uv lock --check: no change. docker_digest.py also flagged node:22-bookworm-slim's tag moving off the pinned digest: unrelated to this PR, left for Dependabot's digest bump.
<!-- SECTION:NOTES:END -->
