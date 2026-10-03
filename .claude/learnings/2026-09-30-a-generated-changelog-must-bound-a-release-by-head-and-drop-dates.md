# A generated changelog is reproducible only if a release is bounded by HEAD and nothing reads the clock

**Key lesson:** Place each merged PR in a release by commit ancestry (the oldest `v*` tag, or HEAD for a pending `--release`), leave dates and authors out, check release data against the code and the index manifest rather than trusting a hand-copied table, and plan the promotion around branch protection: `gh pr create --base main --head dev` (not `/open-pr`), the tag via `gh release create --target`, then a `main` → `dev` back-merge.

- **Date:** 2026-09-30 · **Task:** TASK-066 · **Area:** ops
- **Artifacts:** `.claude/scripts/changelog.py`, `.claude/scripts/tests/test-changelog.sh`,
  `.claude/scripts/mutants/changelog.json`, `.claude/hooks/block-ai-attribution.sh`,
  `docs/specs/08-ops-and-tooling.md` §Release, decision-023

## What we set out to do

Define the release process and generate `CHANGELOG.md` from merged PRs, before any deploy or tag exists.

## What we learned

- **"Untagged" is not "in this release".** The first version titled every untagged PR as the `--release`
  version. On `main` after a promotion, a PR merged into `dev` since would then be listed in a release that
  doesn't contain it. Bounding the pending release by `HEAD` (`git merge-base --is-ancestor <merge sha> HEAD`)
  fixes it (evidence: the "on a HEAD behind dev" row; the mutant "--release titles PRs outside HEAD", killed).
- **A release date breaks reproducibility.** The date is only known once the tag exists, so a file generated
  on the release branch would differ from one regenerated after tagging. With no dates (the tag carries the
  date), `--check` passes on both sides of the tag. The repository name must be compared without case too, or
  a clone whose remote is spelled `Owner/Repo` lists promotions (review round 1).
- **Escaping can hide what a later check looks for.** The attribution check ran on the rendered Markdown, where
  `Generated with [Claude` had become `Generated with \[Claude` and no longer matched. Check raw input before
  transforming it (review round 1, security-reviewer; row "a bracketed footer"), and make it plain
  first (drop format and other default-ignorable characters, collapse whitespace; NFKC for the check): a double, non-breaking or zero-width space slipped past
  a single-space pattern (rounds 2 and 3), and the renderer must show the same plain text that was checked. A refusal pattern over
  merged PR titles must not catch package names (`@types/node`, `next@15.1.0`): one Dependabot title would
  block every run until someone retitles it (round 2, code-reviewer).
- **Replay compatibility is more than the three named versions.** The engine refuses an index built with
  another Tantivy version as well as another tokenizer or schema (`engine/tantivy_engine.py` `unservable`), so
  a Tantivy upgrade makes every pinned index unservable: it is a MINOR release, and it can't ship without a new
  index. Tantivy is not an `index_version` input, so without a `SCHEMA_VERSION` bump the rebuild gets the old id
  and `op index build` keeps the old directory; the `index-versioning` skill now always requires the bump. A data table copied by hand from a running instance's `/meta` can also show the previous code's
  versions, so `--release` checks the table against the code constants, `uv.lock` and the index manifest.
- **The promotion path is shaped by the hooks and branch protection, not by `/open-pr`.** `/open-pr` pushes
  and attests, which a promotion from `dev` can't do; `require-review.sh` exempts exactly
  `gh pr create --base main --head dev`. It also blocks a `git push` of a tag (the merge commit on `main` has
  no per-sha record), so the tag is created server-side with `gh release create --target`. And `main` requires
  the branch to be up to date, so after a merge-commit promotion `dev` lacks `main`'s merge commit and the next
  promotion can't merge until `main` is merged back (release-manager review, round 1).
- `git merge-base --is-ancestor` exits 1 for "not an ancestor" and 128 for a commit the clone lacks; treating
  anything but 0 as "no" would silently file an unfetched PR as Unreleased.

## Dead ends — don't repeat these

- A mutant that swaps `!= 1` for `> 1` survives because both refuse 128; mutate to a condition that never
  fires to prove the refusal is tested.
- A "missing keys" row whose table also had a malformed value passed for the wrong reason (the hex check
  refused first); give a refusal row exactly one fault (qa-auditor, round 1).

## Decisions (and what would change them)

- One semver app version, independent of `index_version` (decision-023) → data and code ship separately and
  search records pin data versions, not the app → revisit if a second deployable or `/api/v2` appears.
- No CI check of `CHANGELOG.md` → it reads GitHub and every merge would stale it → revisit if releases become
  frequent enough that a stale Unreleased section misleads.

## Follow-ups

- [ ] The first release (v0.1.0) and TASK-066 AC#1 wait on TASK-065 (deploy), which waits on TASK-064 (hosting).
- [ ] A maintainer adds the `v*` tag ruleset (spec 08 §Branch protection) before the first tag.

## Propagated to

- Skill / agent / CLAUDE.md updated? — `docs/specs/08-ops-and-tooling.md` §Release and §Branch protection,
  `.claude/agents/release-manager.md`, `.claude/commands/open-pr.md`, the `pr-workflow`, `repo-conventions`
  and `no-ai-attribution` skills, `CLAUDE.md`.
- Test or hook added? — `.claude/scripts/tests/test-changelog.sh` (131 rows) and 43 mutants in
  `.claude/scripts/mutants/changelog.json`; `block-ai-attribution.sh` scans `gh release create`/`edit` notes
  (5 rows in `test-openproceedings-gates.sh`, 2 mutants in `gates.json`).

## Addendum — 2026-10-03: name the candidate and compatible artifacts before promotion

For a first promotion, record the candidate code SHA, copied snapshot identity, compatible index manifest and each verification's exact source separately. Old real indexes are evidence of their original tokenizer/schema combination, not substitutes for an index built with the candidate's current combination. Here candidate `07fe70f0fb6b18202f819149088cfcc54b75ef00` requires tokenizer 3 and schema 3 together. The copied, unchanged snapshot `2026-09-29-d552baa07aed` (hash `d552baa07aed6bd754720c7ef17bc7d9ef7a645531fb95d6bc4174c2eacf91b8`) was used to build candidate index `5cc8e14c2f9a`, whose manifest records that compatible 3/3 combination and Tantivy 0.26.2. Copy provenance is recorded in `/tmp/openproceedings-main-promotion-data/source-copy.json`; build output in `/tmp/main-promotion-index-build.log`; release metadata uses that manifest in `docs/releases.toml`. Building this artifact does not deploy it, promote an index or create a target production database.

Compare failed CI by pinned code, not creation order. The later-created nightly `37123261384` tested old `5ff69202` and hit the known Unicode property-fixture seed crash. Corrected source `8d273d61` passed all 27 jobs in run `37115476175` and is an ancestor of the candidate; relevant backend/test/workflow paths are unchanged. That is proof for the corrected source, not a claim the remote run tested the later candidate SHA. Evidence: `/tmp/main-promotion-nightly-ingest-analysis.md` and the complete nightly artifacts referenced by the mutation recovery results.

Next time, build an evidence table before release: candidate SHA; snapshot hash and copy provenance; compatible index/version manifest; then exact commands, source identities and actual statuses for parity, replay, full-tree security and publication. A finished index build alone proves none of those later gates. At this recording step parity, replay and security verification remain pending; no replay result, clean security verdict, deployment or target-database existence is claimed. Existing TASK-066 release work owns the remaining gates; no new follow-up task is created. Propagated to this release lesson and candidate artifact/metadata selection only; no skill or production changes were authorized for this recording.

The first release-version bump also exposed the combined snapshot's whole-directory golden: its manifest
records the app version, although that value enters neither the corpus hash nor the index ID. The first
full suite failed only that golden at `0.1.0`. Replacing only the manifest's `openproceedings_version`
with `0.0.0` in memory restored the exact prior file hash; all corpus bytes remained unchanged. Update
this golden deliberately when release metadata changes, recording the one-field reversal evidence;
do not drop the manifest from its strict byte check or refresh hashes without diagnosing the difference.
Evidence: `backend/tests/unit/ingest/test_combined_snapshot.py` and the release-preparation report.
Propagated to `.claude/agents/release-manager.md` §Versions so the next release diagnoses this metadata
change before updating the golden.
