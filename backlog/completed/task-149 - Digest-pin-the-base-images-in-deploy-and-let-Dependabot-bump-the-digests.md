---
id: TASK-149
title: Digest-pin the base images in deploy/ and let Dependabot bump the digests
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 20:04'
updated_date: '2026-10-02 00:03'
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
- [x] #1 Every `FROM` in `deploy/` names its base image as `name:tag@sha256:<digest>` (today both stages of `web.Dockerfile`; any image TASK-065 has added by then), with the digest of the multi-arch index, not of a single platform
- [x] #2 `.github/dependabot.yml` has a `docker` entry for `/deploy` on the same weekly schedule, so Dependabot opens PRs that bump the digests (a `commit-message` prefix the changelog groups, e.g. `deps` or `build`), or the task records why Dependabot cannot and names what bumps them instead
- [x] #3 A check fails when a `FROM` in `deploy/` has no digest (a `make lint` step or a case in an existing tooling table), shown failing on an unpinned `FROM`
- [x] #4 Spec 08 §Deploy and the repo-conventions skill state the digest-pin rule
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Digest resolved 2026-10-01 two ways, which agree: `docker buildx imagetools inspect node:22-bookworm-slim` (no daemon needed; MediaType application/vnd.oci.image.index.v1+json, Digest sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c) and the Docker Hub registry API (anonymous pull token from auth.docker.io, then HEAD /v2/library/node/manifests/22-bookworm-slim with Accept: the OCI index and Docker manifest-list types; Docker-Content-Digest is the same sha256:43ac6c60…772c, content-type the OCI index). Both stages of deploy/web.Dockerfile now name node:22-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c. The unpinned `# syntax=docker/dockerfile:1` directive (a BuildKit frontend image pulled at build time) was dropped: the Dockerfile uses no syntax beyond the built-in frontend's, so nothing is pulled unpinned. Dependabot: a docker entry for /deploy, weekly, prefix build (changelog Internal). Its docker fetcher matches /dockerfile|containerfile/i (dependabot-core docker/file_fetcher.rb), so web.Dockerfile is found; Node semver-major updates are ignored there because the major moves with .nvmrc and CI. Check: .claude/scripts/check_digest_pins.py in make tooling (CI claude-tooling), 16 rows in .claude/scripts/tests/test-tooling-scripts.sh, 12 mutants in gates.json all killed (mutate.py --match 'pins:'). Shown failing on an unpinned FROM (a copy of the script over deploy/web.Dockerfile with both FROMs unpinned): 'digest pins: web.Dockerfile:1: node:22-bookworm-slim is not pinned as name:tag@sha256:<digest> (spec 08 §Deploy)', the same for line 2, '1 Dockerfile(s) under deploy/, 2 unpinned FROM', exit=1.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Both FROMs in deploy/web.Dockerfile pinned to node:22-bookworm-slim@sha256:43ac6c60… (the multi-arch OCI index digest, resolved with docker buildx imagetools inspect and the registry API); Dependabot docker entry for /deploy (weekly, prefix build, Node majors by hand); check_digest_pins.py in make tooling with case rows and killed mutants; spec 08 §Deploy and the repo-conventions skill state the rule.
<!-- SECTION:FINAL_SUMMARY:END -->
