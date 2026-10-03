---
id: TASK-066
title: 'Release process, versioning and changelog'
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-10-03 17:23'
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

2026-10-03 code-only promotion: verify dev readiness, perform the full main...dev security review, build and validate a tokenizer-3/schema-3 index on copied local data, prepare release/0.1.0 bookkeeping and its reviewed PR into dev, then promote dev into main with a second-person approval. No tag or public deployment is included; AC#1 remains unchecked.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Done without a deployed instance or a hosting choice; nothing names a host.

- Versioning, decision-023: one MAJOR.MINOR.PATCH app version, equal in backend/pyproject.toml and frontend/package.json (still 0.0.0 and 0.1.0 today: the release branch sets both), tagged vX.Y.Z on the promotion's main commit; first tag v0.1.0, 1.0.0 is the owner's v1. The app version never enters index_version or canonical_hash. A TOKENIZER_VERSION, SCHEMA_VERSION, Tantivy or QUERY_VERSION change (what decides whether a saved record still replays as reproduced) is at least MINOR and is called out at the top of the release's section; a TOKENIZER/SCHEMA/Tantivy change deploys together with an index its own code built.
- CHANGELOG (AC#2): .claude/scripts/changelog.py, run by make changelog (RELEASE=X.Y.Z on a release branch; --check, --notes X.Y.Z, --prs <file>, --data-dir). Reads merged PRs via gh api REST, the v* tags and docs/releases.toml; places each PR by tag ancestry (HEAD for --release); leaves out this repo's promotions and release/* branches; groups Added/Changed/Fixed/Internal; no dates or authors, so it is reproducible; with --release checks the data table against the code constants, uv.lock and the index manifest; refuses AI attribution (on plain text: format and default-ignorable characters dropped, whitespace collapsed, NFKC), @-mentions, email addresses and URLs in titles and notes; a Tantivy upgrade must bump SCHEMA_VERSION. Case table .claude/scripts/tests/test-changelog.sh (131 rows, run by make tooling) and 43 mutants in .claude/scripts/mutants/changelog.json. CHANGELOG.md committed with PRs #1 to #52 under Unreleased.
- Process and checklist: spec 08 §Release, steps 1-9 (readiness, security gate with TASK-067 before the first public release, index verification with required replay outcomes, release branch, promotion via gh pr create --base main --head dev with a second approval, tag via gh release create since require-review.sh blocks an agent's git push of a tag, main → dev back-merge, retention, deploy). block-ai-attribution.sh now scans gh release create/edit notes.
- AC#1 (a tagged release from main) waits on TASK-065 (deploy), which waits on the hosting decision TASK-064; the task stays In Progress until then. No tag, GitHub release or promotion was made.

Left for the release itself (not tasks; the main session decides): the first release v0.1.0 after TASK-065; a maintainer adds the v* tag ruleset (spec 08 §Branch protection) before it.

2026-10-02 (TASK-065, host-agnostic part built): §Release step 9 now runs through deploy/README.md. Its §Deploying a release covers: checking out the tag and running docker compose up --build; a TOKENIZER/SCHEMA/Tantivy release built and verified first, then deployed together with its index; rollback. AC#1 (the first tag) still waits on TASK-065 being Done, which now waits only on the host items TASK-065's notes list (TASK-064 and the checks on the host).

2026-10-03: Preparing the first 0.1.0 release candidate for code-only promotion. The candidate index was built outside the repository from copied snapshot d552baa07aed6bd754720c7ef17bc7d9ef7a645531fb95d6bc4174c2eacf91b8: index 5cc8e14c2f9a, 95,877 documents, tokenizer 3, schema 3, Tantivy 0.26.2. Parity, coverage, and replay verification are in progress; no live current pointer or original records database has been modified. The citation date is the planned tag date and must be rechecked on main before any later tag. No tag or hosting action has occurred.

2026-10-03 verification: current copied index 5cc8e14c2f9a passed parity over 95,877 records, 133,865 terms and 191,123 phrases with zero differences; coverage --check passed M4 (43/44 plus the existing accepted ICLR 2013 exception). The copied snapshot diff is empty. Local source data has no saved-search store/current pointer and hosting is not configured, so this is first-instance code preparation. Supplementary development-store replay preserved 14 actual records: all reproduced with retained pins; all drifted on the new-only index naming exactly tokenizer 2-to-3 and schema 2-to-3 with zero membership changes. This is explicitly not a target-instance backup. The first full suite exposed only the app-version metadata golden: reverting that one manifest value in memory restored its prior exact files hash. Updated the deliberate 0.1.0 golden, preserved strict byte checks, and the targeted test passed; fresh full suite is running.

2026-10-03 local closure: full backend suite passed 6,757 tests with three optional skips (205.46s), including golden/contract suites. Vitest startup in that aggregate make run failed because the temporary local lockfile regeneration had omitted native optional bindings; the tracked npm lockfile is restored unchanged. A fresh npm ci --ignore-scripts --include=optional repaired the installation and all 4,724 frontend tests in 41 files then passed (7.22s, exit 0). Both full suites are green; the aggregate failed command is retained honestly in the release report. Final local lint/tooling and changelog --check --release 0.1.0 passed. No tag, deployment, target-store backup claim or second-person approval is implied; final exact-head review and PR CI precede promotion.

Pre-merge compatibility audit: fixed spec03 unsupported-version summary, spec08 older-pin/replay statements, release-manager guidance and changelog universal drift/first-tag claims. Decision023 has a dated clarification referencing decisions030/033; accepted history and MINOR/fresh-index requirements retained. Changelog real case table RED 10 expected failures, GREEN 133/0; five mutants added. Final checks and exact-head review pending; no tag or deployment claimed.

2026-10-03 compatibility verification completed: official make mutate-changed killed all 48 expected changelog mutants, including five new regression cases, with zero survivors/stale patterns and exit 0. Complete post-correction make test exited 0: backend 6,757 passed/three optional skips in 192.77s; frontend 4,724 passed/41 files in 6.35s. Lint and generated changelog --check --release 0.1.0 exited 0. Current definitions total 778; the earlier 773-mutant nightly proof remains tied to its original source. Final tooling, verification of evidence/task edits, exact-head review and protected PR checks remain closing gates; no tag, hosting or target-store backup is claimed.

2026-10-03: Owner requested solo-maintainer main promotion (zero mandatory approving reviews). GitHub protection before/after comparison proved only the review count changed; all CI and other guards remain. PR101 merged normally as 87b7dea321df3ad73045d6214158a284d7b797e2. Workflow/spec/agent guidance and decision023 receive dated clarification with the protected back-merge. No tag or deployment; those acceptance criteria remain open.
<!-- SECTION:NOTES:END -->
