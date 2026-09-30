---
id: TASK-066
title: 'Release process, versioning and changelog'
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-30 15:36'
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
1. Decide versioning (decision-023): one semver app version in backend/pyproject.toml and frontend/package.json, tagged vX.Y.Z on main; independent of index_version; tokenizer/schema/query version changes are at least MINOR.
2. Write .claude/scripts/changelog.py (make changelog): CHANGELOG.md from merged PRs (gh api REST), v* tags and docs/releases.toml, deterministic; case table test-changelog.sh and mutants/changelog.json.
3. Spec 08 §Release: what a release contains, versioning, the changelog rules and the release checklist (readiness, security gate/TASK-067, index verification, release branch, dev → main promotion with a second approval, tag and notes).
4. Generate and commit CHANGELOG.md up to now. Leave AC#1 (tagged release) for after TASK-065.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Done without a deployed instance or a hosting choice; nothing names a host.

- Versioning, decision-023: one MAJOR.MINOR.PATCH app version, equal in backend/pyproject.toml and frontend/package.json (still 0.0.0 and 0.1.0 today: the release branch sets both), tagged vX.Y.Z on the promotion's main commit; first tag v0.1.0, 1.0.0 is the owner's v1. The app version never enters index_version or canonical_hash. A TOKENIZER_VERSION, SCHEMA_VERSION, Tantivy or QUERY_VERSION change (what decides whether a saved record still replays as reproduced) is at least MINOR and is called out at the top of the release's section; a TOKENIZER/SCHEMA/Tantivy change deploys together with an index its own code built.
- CHANGELOG (AC#2): .claude/scripts/changelog.py, run by make changelog (RELEASE=X.Y.Z on a release branch; --check, --notes X.Y.Z, --prs <file>, --data-dir). Reads merged PRs via gh api REST, the v* tags and docs/releases.toml; places each PR by tag ancestry (HEAD for --release); leaves out this repo's promotions and release/* branches; groups Added/Changed/Fixed/Internal; no dates or authors, so it is reproducible; with --release checks the data table against the code constants, uv.lock and the index manifest; refuses AI attribution (whitespace collapsed), @-mentions, email addresses and URLs in titles and notes; a Tantivy upgrade must bump SCHEMA_VERSION. Case table .claude/scripts/tests/test-changelog.sh (120 rows, run by make tooling) and 37 mutants in .claude/scripts/mutants/changelog.json. CHANGELOG.md committed with PRs #1 to #52 under Unreleased.
- Process and checklist: spec 08 §Release, steps 1-9 (readiness, security gate with TASK-067 before the first public release, index verification with required replay outcomes, release branch, promotion via gh pr create --base main --head dev with a second approval, tag via gh release create since require-review.sh blocks an agent's git push of a tag, main → dev back-merge, retention, deploy). block-ai-attribution.sh now scans gh release create/edit notes.
- AC#1 (a tagged release from main) waits on TASK-065 (deploy), which waits on the hosting decision TASK-064; the task stays In Progress until then. No tag, GitHub release or promotion was made.

Left for the release itself (not tasks; the main session decides): the first release v0.1.0 after TASK-065; a maintainer adds the v* tag ruleset (spec 08 §Branch protection) before it.
<!-- SECTION:NOTES:END -->
