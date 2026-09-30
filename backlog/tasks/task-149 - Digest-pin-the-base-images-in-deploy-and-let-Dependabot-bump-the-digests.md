---
id: TASK-149
title: Digest-pin the base images in deploy/ and let Dependabot bump the digests
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 20:04'
labels:
  - ops
  - ci
milestone: m-6
dependencies: []
references:
  - deploy/web.Dockerfile
  - .github/dependabot.yml
  - docs/specs/08-ops-and-tooling.md
  - .claude/skills/repo-conventions/SKILL.md
priority: medium
ordinal: 125000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: a TASK-136 (PR #55) review nit, rejected there as deploy-time work (PR #55 lists it as "Base-image digest pin: deferred to TASK-065"; this task carries it). `deploy/web.Dockerfile` names `node:22-bookworm-slim` by tag in both stages, so the same Dockerfile can build on different base images from one day to the next, and a rebuilt image is not the one that was reviewed. The workflows already pin every action by commit sha (spec 08 §CI); the base images should follow the same rule, with the tag kept for readers. `.github/dependabot.yml` has `github-actions` and `uv` entries and no `docker` one today, so a digest pin would go stale with nothing to bump it. The api image TASK-065 adds is a base image in `deploy/` too.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every `FROM` in `deploy/` names its base image as `name:tag@sha256:<digest>` (today both stages of `web.Dockerfile`; any image TASK-065 has added by then), with the digest of the multi-arch index, not of a single platform
- [ ] #2 `.github/dependabot.yml` has a `docker` entry for `/deploy` on the same weekly schedule, so Dependabot opens PRs that bump the digests (a `commit-message` prefix the changelog groups, e.g. `deps` or `build`), or the task records why Dependabot cannot and names what bumps them instead
- [ ] #3 A check fails when a `FROM` in `deploy/` has no digest (a `make lint` step or a case in an existing tooling table), shown failing on an unpinned `FROM`
- [ ] #4 Spec 08 §Deploy and the repo-conventions skill state the digest-pin rule
<!-- AC:END -->
