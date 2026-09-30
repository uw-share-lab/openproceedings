---
id: TASK-150
title: >-
  Stop Dependabot from bumping the exact tantivy pin without a SCHEMA_VERSION
  bump
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 20:05'
updated_date: '2026-09-30 20:10'
labels:
  - ci
  - ops
milestone: m-6
dependencies: []
references:
  - .github/dependabot.yml
  - backend/pyproject.toml
  - backend/src/openproceedings/engine/index.py
  - .claude/skills/index-versioning/SKILL.md
  - docs/specs/08-ops-and-tooling.md
priority: medium
ordinal: 126000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: the release-manager review of TASK-066 (PR #54), listed there as a deferral. `backend/pyproject.toml` pins `tantivy==0.26.2`, and the uv entry in `.github/dependabot.yml` will open a PR that bumps it like any other dependency. A Tantivy upgrade must bump `SCHEMA_VERSION` (`engine/index.py`) in the same change (decision-023; spec 08 §Release, versioning table; index-versioning skill): the engine refuses an index built with another Tantivy (`unservable`, `tantivy_version_mismatch`), so a Dependabot bump merged alone leaves `dev` unable to serve the current index and unable to build a new `index_version` for it. Today only `changelog.py --release` catches this, at release time, long after the merge. Either option closes the gap: `ignore: [{dependency-name: tantivy}]` on the uv entry (upgrades then happen by hand, with the bump), or a CI check that fails when `uv.lock`'s tantivy version changes and `SCHEMA_VERSION` does not.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A Dependabot PR that bumps tantivy on its own cannot reach dev: either Dependabot never opens one (an `ignore` for `tantivy` on the uv entry of `.github/dependabot.yml`), or a required CI check fails on any PR whose `uv.lock` tantivy version changes while `SCHEMA_VERSION` does not
- [ ] #2 If a CI check is chosen: it has a case table under `.claude/scripts/tests/` with rows for tantivy changed alone (fails), tantivy and SCHEMA_VERSION changed together (passes) and neither changed (passes), and its mutants are killed (`make mutate-changed`)
- [ ] #3 The chosen option and the reason for it are written in the index-versioning skill (the tantivy-py upgrade row) and spec 08 §Release, and the manual upgrade path (bump the pin, `uv lock`, bump SCHEMA_VERSION, rebuild) is stated there; if a CI check is chosen, spec 08 §CI (the workflow table) and §Branch protection (the required checks) list it
<!-- AC:END -->
