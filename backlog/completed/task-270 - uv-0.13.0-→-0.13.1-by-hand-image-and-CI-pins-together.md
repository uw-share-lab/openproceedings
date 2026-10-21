---
id: TASK-270
title: uv 0.13.0 → 0.13.1 by hand (image and CI pins together)
status: Done
assignee: []
created_date: '2026-10-19 13:28'
updated_date: '2026-10-20 13:56'
labels:
  - deps
  - ci
dependencies: []
priority: medium
ordinal: 177000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Dependabot's #162 moves deploy/api.Dockerfile's ghcr.io/astral-sh/uv tag alone, which fails claude-tooling (check_uv_pin.py, TASK-252), so it is remade by hand with every setup-uv version (spec 08 §Dependabot). uv 0.13.1 was released 2026-10-14; the owner's 7-day hold would clear 2026-10-21. Owner chose (2026-10-19): prepare now, merge on or after 2026-10-21; then (2026-10-20) waived the remaining hold to ship it in v0.4.1 that day.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 deploy/api.Dockerfile pins uv 0.13.1 by the digest Dependabot proposed, and all 11 setup-uv steps say 0.13.1 (check_uv_pin.py: 0 problems)
- [x] #2 The api image builds with uv 0.13.1 (uv sync --locked) and uv lock --check passes under 0.13.1
- [x] #3 Merged on 2026-10-20 by the owner's waiver of the 7-day age (docker_digest.py that day: digest and astral-sh attestation verified, first attested 6.4 days ago); #162 closed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Digest verified (registry resolves 0.13.1 to it; GitHub attestation for astral-sh). docker build of api.Dockerfile green; uv stage reports uv 0.13.1 (aarch64 musl). uvx uv==0.13.1 uv lock --check: no change. docker_digest.py also flagged node:22-bookworm-slim's tag moving off the pinned digest: unrelated to this PR, left for Dependabot's digest bump.

2026-10-20: the owner waived the rest of the 7-day hold to ship uv 0.13.1 in v0.4.1 today. docker_digest.py on origin/build/uv-0.13.1: registry resolves 0.13.1 to the pinned digest; GitHub attestation verified for astral-sh; first attested 6.4 days ago (the only PROBLEM, accepted by the owner). #162 is closed once this merges.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
uv 0.13.0 → 0.13.1 in deploy/api.Dockerfile (pinned by digest, attestation verified) and all 11 CI setup-uv steps, remade by hand from Dependabot's #162. Merged 2026-10-20, at 6.4 days, by the owner's waiver of the 7-day hold, to ship in v0.4.1; #162 closed.
<!-- SECTION:FINAL_SUMMARY:END -->
