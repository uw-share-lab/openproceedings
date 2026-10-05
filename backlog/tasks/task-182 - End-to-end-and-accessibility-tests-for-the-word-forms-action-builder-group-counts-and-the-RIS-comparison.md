---
id: TASK-182
title: >-
  End-to-end and accessibility tests for the word-forms action, builder group
  counts and the RIS comparison
status: In Progress
assignee: []
created_date: '2026-10-05 05:12'
updated_date: '2026-10-05 08:11'
labels:
  - frontend
  - e2e
  - a11y
milestone: m-3
dependencies:
  - TASK-175
  - TASK-176
  - TASK-177
references:
  - docs/specs/05-frontend.md
ordinal: 126000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-175, TASK-176 and TASK-177 each shipped with unit and contract tests only: Playwright binds ports 3000 and 8000, which the owner's running instance held while they were built. Three new UI surfaces would otherwise release without browser, axe or visual coverage.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 frontend/e2e covers: Scholar string, Add $ (all and chosen terms), Search, URL carries the $, expansions shown, Back restores the typed query
- [x] #2 frontend/e2e covers: builder group counts and without-counts after a search, hidden when the draft differs, the too-many and too-costly notes, the live announcement
- [x] #3 frontend/e2e covers: the RIS comparison from upload to the kept, dropped, added and not-in-index lists and their exports, the disabled state, and an over-cap file
- [ ] #4 axe passes WCAG 2.2 AA on each new state and the 320 px reflow check passes; visual snapshots are added through the suite's own update command
- [x] #5 make e2e passes locally and the run's counts are recorded in the task
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Branch task-182-e2e (off feat/review-comparison-tools).

Added to frontend/e2e: word-forms.spec.ts (9 tests), group-counts.spec.ts (11), compare.spec.ts (9), 6 element visual tests in visual.spec.ts, helpers.ts and instances.ts. The fixture server now serves three configurations of the one index (API port: default; +1 tight: 2 groups and 5 terms counted, rate limit on with a comparison cooldown factor of 200, a 2,048-byte comparison file cap; +2 plain: comparisons off); a spec re-addresses a page's API calls to one of them, so the too-many, too-costly, over-cap, cooldown and not-offered states are the server's own answers.

Run on 2026-10-05 with OP_E2E_API_PORT=8018 OP_E2E_WEB_PORT=3018 (ports 8000/3000 were in use): Playwright 55 passed, twice in a row (20 before this task). Vitest 4,824 passed in 46 files (one run before it had 1 failure in src/editor/lang/grammar.test.ts, a different case from an earlier one-off, passing on rerun: a load-dependent flake outside this task). make lint and make tooling exit 0.

AC#4 is ticked only in part, so it is left open: axe (WCAG 2.2 AA, both themes, 1280 and 320 px) and the 320 px reflow check pass on every new state, and the visual snapshots were added through npm run e2e:update, but only the darwin baselines exist. The six Linux baselines (word-forms, group-counts, comparison x light, dark) must be written on an amd64 ubuntu-24.04 host or runner; until then CI's e2e job fails on those six tests.

Product change made: lib/compare.ts megabytes() showed a cap under 0.05 MB as 0.0 MB; it now shows kilobytes under a tenth of a megabyte.
<!-- SECTION:NOTES:END -->
