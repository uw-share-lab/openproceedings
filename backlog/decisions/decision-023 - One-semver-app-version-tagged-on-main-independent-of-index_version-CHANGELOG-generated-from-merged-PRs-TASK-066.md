---
id: decision-023
title: >-
  One semver app version, tagged on main, independent of index_version;
  CHANGELOG generated from merged PRs (TASK-066)
date: '2026-09-30 15:16'
status: accepted
---
## Context

TASK-066 defines the release process before the first release. Until now the code carried no release
version: `backend/pyproject.toml` said `0.0.0` and `frontend/package.json` `0.1.0`, and nothing tagged `main`.
The results a review cites are pinned by data, not code: guarantee 4 keys reproducibility to the canonical
query and `index_version` (spec 03 §Versioning), and a search record also stores `tokenizer_version` and
`query_version` (spec 04 §Search records). A reader of a release needs to know two things apart: what the code
changed, and whether their saved searches still replay. Options considered:

1. **Fold the data into the version** (e.g. `0.3.0+<index_version>`, or a release per index). Rejected: an
   index promotion would then need a code release, and spec 08 §Deploy and the `release-manager` agent keep
   code and data separate (a code release never silently changes the served `index_version`).
2. **Separate versions for the backend and the frontend.** Rejected: they ship together from one commit, the
   frontend's types are generated from the backend's OpenAPI document, and two numbers invite the question of
   which pairs are compatible.
3. **Calendar versions** (`2026.10.0`). Rejected: a date tells a reviewer nothing about whether their search
   records drift; semver's MINOR/PATCH split can carry that.
4. **One semver version for the app, with the replay-relevant versions stated beside it.** Chosen.

For the changelog: a hand-written file drifts, and the repo already records every change as a PR whose title
follows `<type>: <summary>` (`repo-conventions`), so the file can be generated. Options: from commit messages
(merge commits and review fixes make that noisy), or from merged PRs (one line per reviewed change). Chosen:
merged PRs, read from the REST API (`gh pr edit` fails here on the retired Projects API, so the repo's
scripts use REST).

## Decision

The app has one `MAJOR.MINOR.PATCH` version, equal in `backend/pyproject.toml` and `frontend/package.json`,
tagged `vX.Y.Z` on the `main` commit a `dev → main` promotion creates; the first tag is `v0.1.0`, and `1.0.0`
is the owner's v1 release. A change of `TOKENIZER_VERSION`, `SCHEMA_VERSION`, Tantivy or `QUERY_VERSION`
(the inputs that decide whether a saved search record can still replay as `reproduced`) is at least a MINOR
release and is called out at the top of its notes. `CHANGELOG.md` is generated from merged PRs by
`.claude/scripts/changelog.py` (`make changelog`), with each release's data (the `index_version` it was
verified on, its snapshot hash and those four versions) read from `docs/releases.toml` and checked against the
code and the index's manifest. The process and checklist are spec 08 §Release.

## Consequences

- The app version never enters `index_version` or `canonical_hash`, so this decision changes no index id and
  makes no search record drift. Whether a record replays as `reproduced` still depends only on its pinned
  `index_version` and `query_version`, on that index being kept, and on the running code being able to serve
  it (same `TOKENIZER_VERSION`, `SCHEMA_VERSION` and Tantivy); each release's Data section states which
  releases' records still reproduce, and a record from an earlier release with other versions reproduces
  under that release's tag, on the index it pins.
- Code and data ship separately, except a release that changes `TOKENIZER_VERSION`, `SCHEMA_VERSION` or
  Tantivy: its code can't serve the old index, so it deploys together with an index it built. Tantivy is not
  an `index_version` input, so a Tantivy upgrade always bumps `SCHEMA_VERSION` (the `index-versioning` skill
  no longer allows an exception), or the new build would reuse the old id; `changelog.py --release` refuses a
  Tantivy change alone.
- A release bumps two manifests and both lockfiles; `changelog.py --release` refuses when the manifests
  disagree with the version, when a release lacks its data table or the table disagrees with the code or the
  index manifest, and when a PATCH changes one of the four versions.
- `CHANGELOG.md` is not checked in CI (it reads GitHub, and each merge would make it stale), so between
  releases its Unreleased section lags `dev`; a release branch regenerates it. PR titles become release notes,
  which makes the `<type>: <summary>` convention matter more; titles without a type fall back to the head
  branch's prefix.
- `require-review.sh` blocks an agent session's `git push` of a tag (the promotion's merge commit has no
  per-sha record), so the tag is created with `gh release create --target`, not pushed, and
  `block-ai-attribution.sh` now scans `gh release create`/`edit` notes. `main`'s branch protection requires
  the promotion branch to be up to date, so each promotion is followed by a back-merge of `main` into `dev`
  (a `release/X.Y.Z-back-merge` PR, left out of the changelog). A tag ruleset on `v*` (a maintainer's
  setting) keeps tags from moving.
- Revisit if a second deployable (e.g. a separately released client) appears, or if the API ever versions
  independently of the app (`/api/v2` alongside `/api/v1`).
- Specs and tooling changed with it: spec 08 §Release (new) and §Branch protection, the `release-manager`
  agent, `/open-pr` (a promotion doesn't use it), the `pr-workflow`, `repo-conventions` and
  `no-ai-attribution` skills, the Makefile's `changelog` target, `.claude/hooks/block-ai-attribution.sh`,
  `.claude/scripts/tests/test-changelog.sh` and `.claude/scripts/mutants/changelog.json`.

## Compatibility clarification — 2026-10-03

Decisions 030 and 033 subsequently added compatibility readers for independently supported schema 2/3
and tokenizer 2/3 indexes. The original same-version assumption above is historical: supported retained
pins can reproduce on the current reader when `QUERY_VERSION` matches, while unsupported versions or
incompatible Tantivy require the matching historical release. Replay against changed inputs reports
`drifted`; release tables alone cannot classify an individual older record.

The MINOR-bump rule and fresh current-index verification/deployment requirement remain unchanged.
Spec 08, the release-manager guidance and generated changelog now distinguish those operational release
requirements from the reader's support for retained pins. The first tagged release also makes no claim
that development search records do not exist.
