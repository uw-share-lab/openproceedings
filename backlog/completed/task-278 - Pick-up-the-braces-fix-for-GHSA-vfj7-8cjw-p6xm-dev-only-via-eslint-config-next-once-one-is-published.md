---
id: TASK-278
title: >-
  Pick up the braces fix for GHSA-vfj7-8cjw-p6xm (dev-only, via
  eslint-config-next) once one is published
status: Done
assignee: []
created_date: '2026-10-21 15:42'
updated_date: '2026-10-28 03:55'
labels:
  - deps
  - security
  - frontend
dependencies: []
priority: low
ordinal: 184000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
npm audit on dev (2026-10-21, after #178) reports 5 high findings that are one advisory, GHSA-vfj7-8cjw-p6xm (CVE-2026-93687, published 2026-09-18: braces stack-exhaustion denial of service through deeply nested patterns, braces <= 3.0.3). The chain is eslint-config-next 16.4.0 -> @next/eslint-plugin-next 16.4.0 (pins fast-glob 3.3.1) -> micromatch 4.0.8 (braces ^3.0.3) -> braces 3.0.3; every entry is dev: true in package-lock.json. It predates #178. The exposure is lint only, in dev and CI: the glob patterns braces expands come from the repo's own ESLint config, not from users, and npm audit --omit=dev finds 0 (nothing that ships). As of 2026-10-21 there is no patch upstream: the advisory's first_patched_version is null, braces 3.0.3 is npm's latest, and @next/eslint-plugin-next 16.4.2 (latest) and 16.5.0-canary.21 still pin fast-glob 3.3.1 (fast-glob 3.3.3 still takes micromatch 4.0.8). npm audit's suggested fix, eslint-config-next 14.2.35, is a major downgrade to Next 14's config and not an option. Evidence and the dead ends: .claude/learnings/2026-10-21-npm-audit-fix-available-can-be-a-downgrade-with-no-patch-upstream.md.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A braces release that fixes GHSA-vfj7-8cjw-p6xm, or an upstream change to the eslint-config-next chain that npm audit no longer flags, is taken into dev through a normal deps PR or Dependabot's (a major of eslint-config-next by hand, since dependabot.yml ignores npm majors; spec 08 §CI "Dependabot")
- [x] #2 npm audit on dev shows no braces advisory, and npm audit --omit=dev stays at 0
- [x] #3 make lint passes with the resulting lock, and npm_specs.py (make tooling) still finds the manifests and the lock's workspace entries equal
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-28: GitHub withdrew GHSA-vfj7-8cjw-p6xm on 2026-10-23, so npm audit no longer flags braces 3.0.3 and no braces release is needed. npm audit on dev then showed two other dev-only highs, undici 7.30.0 (via jsdom) and zod 4.6.5 (via eslint-plugin-react-hooks); npm audit fix took undici 7.30.1 and zod 4.6.7 (lock only). npm audit and npm audit --omit=dev both report 0; make lint, the frontend vitest suite and npm_specs.py pass.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed: the braces advisory was withdrawn upstream on 2026-10-23, so npm audit no longer flags it. The same PR takes the dev-only undici 7.30.1 and zod 4.6.7 fixes; npm audit is 0 with and without dev.
<!-- SECTION:FINAL_SUMMARY:END -->
