---
id: TASK-066
title: 'Release process, versioning and changelog'
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-30 14:31'
labels:
  - ops
milestone: m-6
dependencies:
  - TASK-065
ordinal: 65000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
release-manager; dev → main promotion with second approval.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Tagged release from main
- [x] #2 CHANGELOG from merged PRs
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Decide versioning (decision-022): one semver app version in backend/pyproject.toml and frontend/package.json, tagged vX.Y.Z on main; independent of index_version; tokenizer/schema/query version changes are at least MINOR.
2. Write .claude/scripts/changelog.py (make changelog): CHANGELOG.md from merged PRs (gh api REST), v* tags and docs/releases.toml, deterministic; case table test-changelog.sh and mutants/changelog.json.
3. Spec 08 §Release: what a release contains, versioning, the changelog rules and the release checklist (readiness, security gate/TASK-067, index verification, release branch, dev → main promotion with a second approval, tag and notes).
4. Generate and commit CHANGELOG.md up to now. Leave AC#1 (tagged release) for after TASK-065.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Done without a deployed instance or a hosting choice; nothing names a host.

- Versioning, decision-022: one MAJOR.MINOR.PATCH app version, equal in backend/pyproject.toml and frontend/package.json (still 0.0.0 and 0.1.0 today: the release branch sets both), tagged vX.Y.Z on the promotion's main commit; first tag v0.1.0, 1.0.0 is the owner's v1. The app version never enters index_version or canonical_hash. A TOKENIZER_VERSION, SCHEMA_VERSION or QUERY_VERSION change is at least MINOR and is called out at the top of the release's section.
- CHANGELOG (AC#2): .claude/scripts/changelog.py, run by make changelog (RELEASE=X.Y.Z on a release branch; --check, --notes X.Y.Z, --prs <file>). Reads merged PRs via gh api REST, the v* tags and docs/releases.toml (each release's index_version, snapshot hash and the three versions). Excludes dev → main promotions, release/* branches and PRs into other bases; groups Added/Changed/Fixed/Internal by title type, else branch prefix; no dates or authors, so it is reproducible; refuses any AI-attribution marker in its output. Case table .claude/scripts/tests/test-changelog.sh (59 rows, run by make tooling) and 14 mutants in .claude/scripts/mutants/changelog.json, all killed. CHANGELOG.md committed with PRs #1 to #52 under Unreleased.
- Process and checklist: spec 08 §Release (readiness, security gate with TASK-067 before the first public release, index verification, release branch, promotion with a second approval, tag via gh release create since require-review.sh blocks an agent's git push of a tag, notes from --notes).
- AC#1 (a tagged release from main) waits on TASK-065 (deploy), which waits on the hosting decision TASK-064; the task stays In Progress until then. No tag, GitHub release or promotion was made.

Deferred (not tasks yet): the first release itself (v0.1.0) after TASK-065; optionally reporting the app version in GET /api/v1/meta so step 3 of the checklist can read it from a running instance.
<!-- SECTION:NOTES:END -->
