---
id: TASK-148
title: 'CI builds deploy/web.Dockerfile on PRs that touch it, the frontend or deploy/'
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 20:04'
updated_date: '2026-10-02 01:05'
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
- [x] #1 A GitHub Actions job runs `docker build -f deploy/web.Dockerfile .` from the repository root on pull requests into dev and main whose diff touches `deploy/**`, `frontend/**`, `package.json`, `package-lock.json`, `.dockerignore` or the workflow file itself, and does not run on a PR that touches none of them
- [x] #2 The job builds a private image (`OPENPROCEEDINGS_INSTANCE=private`) and a public image with a placeholder `NEXT_PUBLIC_TAKEDOWN_CONTACT`, and both builds succeed on the PR that adds the job (link the run in the PR)
- [x] #3 The job also runs a public build with no takedown contact and passes only when that build fails at `web-build-gate.sh`, so the gate is exercised in the real image
- [x] #4 The job pins its actions by commit sha like the other workflows, has `permissions: contents: read`, and pushes no image
- [x] #5 Spec 08 §CI (the workflow table, marked advisory or required) and §Deploy describe the job as built; if it is made required, §Branch protection lists it and a PR that touches none of the paths still reports the check (a workflow-level `paths` filter would leave a required check pending forever), shown on such a PR
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented as .github/workflows/web-image.yml (workflow and job web-image), advisory: a workflow-level paths filter (deploy/**, frontend/**, package.json, package-lock.json, .dockerignore, the workflow) on pull_request into dev/main and on push to them, so it does not run on a PR that touches none of them; it is not made required, because a skipped required check stays pending forever (making it required would need a changed-files step inside an always-running job; spec 08 §CI says so). Three docker builds from the repo root on ubuntu-24.04: OPENPROCEEDINGS_INSTANCE=private; public with NEXT_PUBLIC_TAKEDOWN_CONTACT=takedown@example.org; public with no contact, which passes only when docker build exits non-zero and the log shows the RUN sh deploy/web-build-gate.sh step and the gate's 'OPENPROCEEDINGS_INSTANCE=public needs NEXT_PUBLIC_TAKEDOWN_CONTACT' message. Checkout pinned by sha (v7.0.1, as the other workflows), persist-credentials false, permissions contents: read, nothing pushed (no login, no push). Spec 08 §CI (workflow table, advisory) and §Deploy describe it; §Branch protection is unchanged since it is not required. Docker isn't running on the owner's machine, so the PR's CI run is the only build.

PR #73's run (head e45597c): https://github.com/uw-share-lab/openproceedings/actions/runs/36948614343 (job web-image, success). Private build: gate prints 'web image: a private instance', next build compiles, image openproceedings-web:private named. Public with takedown@example.org: 'a public instance, takedown contact set', compiles, openproceedings-web:public named. Public with no contact: 'OPENPROCEEDINGS_INSTANCE=public needs NEXT_PUBLIC_TAKEDOWN_CONTACT …', 'ERROR: failed to build: … process "/bin/sh -c sh deploy/web-build-gate.sh" did not complete successfully', then the step's 'refused at web-build-gate.sh, as it should be'. Every other check on the PR also passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added the advisory web-image workflow: on PRs into and pushes to dev/main touching deploy/, frontend/, the npm manifests, .dockerignore or itself, it builds deploy/web.Dockerfile as a private image, a public image with a placeholder contact, and a public image with no contact that must fail at web-build-gate.sh. contents: read, sha-pinned checkout, nothing pushed. Kept advisory (a paths-filtered required check would stay pending); spec 08 §CI and §Deploy describe it. Verified by PR #73's run 36948614343, all three steps green.
<!-- SECTION:FINAL_SUMMARY:END -->
