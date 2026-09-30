---
id: TASK-148
title: 'CI builds deploy/web.Dockerfile on PRs that touch it, the frontend or deploy/'
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 20:04'
updated_date: '2026-09-30 20:11'
labels:
  - ci
  - ops
milestone: m-6
dependencies: []
references:
  - deploy/web.Dockerfile
  - deploy/web-build-gate.sh
  - .dockerignore
  - .github/workflows/e2e.yml
  - docs/specs/08-ops-and-tooling.md
priority: medium
ordinal: 124000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: TASK-136 (PR #55) deferral. `deploy/web.Dockerfile` (the `web` image: the Next.js standalone server) and its build gate `deploy/web-build-gate.sh` landed in TASK-136, but the image was never built, locally or in CI: the Docker daemon was not running when TASK-136 was verified, so only the gate script was tested directly. Nothing today notices when a frontend or lockfile change breaks `docker build`, and TASK-065 (compose, TLS, the api image) will build on this image. The build fetches only the base image and npm packages, as CI's existing `npm ci` steps do; it reaches none of the data sources the "tests never call real APIs" rule covers. Whether the job becomes a required check is part of the work; spec 08 §Branch protection lists the required checks.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A GitHub Actions job runs `docker build -f deploy/web.Dockerfile .` from the repository root on pull requests into dev and main whose diff touches `deploy/**`, `frontend/**`, `package.json`, `package-lock.json`, `.dockerignore` or the workflow file itself, and does not run on a PR that touches none of them
- [ ] #2 The job builds a private image (`OPENPROCEEDINGS_INSTANCE=private`) and a public image with a placeholder `NEXT_PUBLIC_TAKEDOWN_CONTACT`, and both builds succeed on the PR that adds the job (link the run in the PR)
- [ ] #3 The job also runs a public build with no takedown contact and passes only when that build fails at `web-build-gate.sh`, so the gate is exercised in the real image
- [ ] #4 The job pins its actions by commit sha like the other workflows, has `permissions: contents: read`, and pushes no image
- [ ] #5 Spec 08 §CI (the workflow table, marked advisory or required) and §Deploy describe the job as built; if it is made required, §Branch protection lists it and a PR that touches none of the paths still reports the check (a workflow-level `paths` filter would leave a required check pending forever), shown on such a PR
<!-- AC:END -->
