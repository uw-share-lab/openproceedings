---
id: TASK-121
title: >-
  Scale local test runs by risk: full suite for guarantee-bearing paths,
  affected tests for docs/tests/tooling
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 15:31'
updated_date: '2026-09-29 15:31'
labels:
  - tooling
  - docs
dependencies: []
priority: medium
ordinal: 113000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The closing workflow required a full local make test before every push, although CI's required test job runs the full backend and frontend suite on every PR. On docs-, tests- or tooling-only changes the local run cost ~6 min per review round and caught nothing CI would not. The owner chose (2026-09-29) to scale the local run by risk, and to remove a PR's worktree once it merges (ten stale worktrees had piled up).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 pr-workflow §Local test runs defines the rule once, as a table keyed by what the diff touches that fails safe (anything no row names runs the full make test): the full make test for backend/src/** or dependency files, for shared test code (any conftest, helper, fixture or test module other tests import) and for docs/specs, docs/results and backlog files (tests on both sides read them); the whole backend suite for frontend files backend tests read and the API contract; narrower runs for other frontend code and config, e2e, other tests (and the tests that read a changed data file) and hook/CI changes; nothing extra for other docs; make lint and make tooling always; CI's test job is the full-suite gate
- [x] #2 CLAUDE.md, CONTRIBUTING.md, /review-gate, /open-pr, code-reviewer and senior-engineer point to the table without restating its triggers, instead of requiring make test unconditionally
- [x] #3 A PR's Tests section says what ran locally and that CI runs the rest; no full-suite pass is claimed that wasn't run
- [x] #4 pr-workflow's and CLAUDE.md's closing order end with removing the PR's worktree and local branch once it merges, archiving uncommitted work as a patch first
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Local test runs scale by risk (owner's decision, 2026-09-29). pr-workflow §Local test runs defines it once, keyed by what the diff touches, and fails safe: anything no row names runs the full make test. The full make test also runs for backend/src/** or dependency files, for shared test code (any conftest.py, strategies, corpus, fixtures, or a test module other tests import; a frontend test reads backend/tests/fixtures/queries/) and for docs/specs, docs/results and backlog files (backend and frontend tests read them). The whole backend suite runs for frontend files backend tests read (frontend/src/**/*.json, schema.ts) and for backend/tests/contract/openapi.json; frontend Vitest for other frontend code and root config (a test imports next.config.ts); make e2e for e2e specs (CI's e2e job is advisory); the changed test files, or the tests that read a changed data file, for other tests; make tooling and mutate-changed for hooks and CI; nothing extra for other docs (README, CONTRIBUTING, CLAUDE.md, docs/design|research|plans|usability, .claude markdown, which make tooling's case tables cover). make lint and make tooling always run; CI's required test job is the full-suite gate. CLAUDE.md, CONTRIBUTING.md, /review-gate, /open-pr, code-reviewer and senior-engineer point to the table without restating it, and a PR's Tests section says what ran locally. The closing order in pr-workflow and CLAUDE.md now ends with removing a merged PR's worktree and local branch, archiving uncommitted work as a patch first.
<!-- SECTION:FINAL_SUMMARY:END -->
