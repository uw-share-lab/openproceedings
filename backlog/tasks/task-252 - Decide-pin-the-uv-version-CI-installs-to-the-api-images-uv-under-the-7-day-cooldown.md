---
id: TASK-252
title: >-
  Decide: pin the uv version CI installs to the api image's uv, under the 7-day
  cooldown
status: In Progress
assignee: []
created_date: '2026-10-16 22:50'
updated_date: '2026-10-17 08:35'
labels:
  - ci
  - decision
dependencies: []
ordinal: 165000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the #154 review (2026-10-16): CI's setup-uv steps have no version, so CI installs the newest uv with no 7-day hold (decision-048's cooldown); on 2026-10-16 CI already ran uv 0.13.1 (2 days old) while deploy/api.Dockerfile pins 0.13.0. Pinning keeps CI, local and the image on one reviewed uv, at the cost of a hand bump alongside each image bump.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The owner decides; if yes, every setup-uv step pins the version deploy/api.Dockerfile pins, a make tooling check fails when they differ, and the Dependabot procedure and spec 08 say the two move together
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner decision 2026-10-17: yes. All 11 setup-uv steps (bench, claude-tooling, e2e, lint, test, nightly x6) now have with: { version: "0.13.0" }, the uv deploy/api.Dockerfile pins. New .claude/scripts/check_uv_pin.py in make tooling (so claude-tooling): reads the image's one ghcr.io/astral-sh/uv:X.Y.Z stage and every setup-uv step under .github/ (workflows and composite actions, matched case-blind), and fails on a different version, no version, a version-file or manifest-file, two with: or two version inputs (input names case-blind), uv installed another way (pip/pipx, the astral.sh installer, docker://, uv self update), a job running uv before its setup-uv step, or a form it can't read (flow-style step, multi-line flow mapping, anchors, aliases, block scalars, expressions), on no uv stage or two, a tag that isn't X.Y.Z, and no setup-uv step at all. 51 rows in test-tooling-scripts.sh, 37 mutants in gates.json (label prefix uvpin:). Mutation: one mutate.py run (--match uvpin: --jobs 2) killed 19 of the first 21; the two survivors got rows, and every mutant added or changed after it (21) was then applied by hand, one at a time, and confirmed killed by the table. Spec 08 (Python pin, Testing, claude-tooling row, Dependabot), .claude/commands/dependabot-review.md (step 0 and the stop list), .github/dependabot.yml, the pr-workflow skill and ci-engineer say the two move together: a uv bump is a hand PR moving the Dockerfile and every workflow's version; a Dependabot docker PR moving the tag fails claude-tooling and is remade by hand; a digest-only bump passes.
<!-- SECTION:NOTES:END -->
