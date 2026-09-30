# A generated changelog is reproducible only if a release is bounded by HEAD and nothing reads the clock

**Key lesson:** Place each merged PR in a release by commit ancestry (the oldest `v*` tag, or HEAD for a pending `--release`), never by "untagged", and leave dates and authors out, so the file regenerates byte for byte before and after the tag; create the tag with `gh release create --target`, since `require-review.sh` blocks a `git push` of it.

- **Date:** 2026-09-30 · **Task:** TASK-066 · **Area:** ops
- **Artifacts:** `.claude/scripts/changelog.py`, `.claude/scripts/tests/test-changelog.sh`,
  `.claude/scripts/mutants/changelog.json`, `docs/specs/08-ops-and-tooling.md` §Release, decision-022

## What we set out to do
Define the release process and generate `CHANGELOG.md` from merged PRs, before any deploy or tag exists.

## What we learned
- **"Untagged" is not "in this release".** The first version titled every untagged PR as the `--release`
  version. On `main` after a promotion, a PR merged into `dev` since would then be listed in a release that
  doesn't contain it. Bounding the pending release by `HEAD` (`git merge-base --is-ancestor <merge sha> HEAD`)
  fixes it (evidence: the "on a HEAD behind dev" row, and the mutant "--release titles PRs outside HEAD",
  killed).
- **A release date breaks reproducibility.** The date is only known once the tag exists, so a file generated on
  the release branch would differ from one regenerated after tagging. With no dates (the tag carries the date),
  `--check` passes on both sides of the tag.
- **The release's own PR has to be excluded.** A `release/*` PR merges after the file is generated; listing it
  would make the file stale the moment it merges. The same goes for the `dev → main` promotion, which repeats
  what `dev` lists. A fork PR whose head is also named `dev` is not a promotion (the head repo is compared).
- **A tag can't be pushed from an agent session.** `require-review.sh` resolves each pushed ref to a commit and
  demands a per-sha review record; `main`'s promotion merge commit has none (its review is the second
  approval). `gh release create vX.Y.Z --target <sha>` creates the tag server-side instead
  (`.claude/hooks/require-review.sh`, the `for src in pushed` loop).
- `git merge-base --is-ancestor` exits 1 for "not an ancestor" and 128 for a commit the clone lacks; treating
  anything but 0 as "no" would silently file an unfetched PR as Unreleased (the mutant `r.returncode == -1`
  survives until a row feeds an unknown sha; a first mutant, `> 1`, was equivalent to `!= 1`).

## Dead ends — don't repeat these
- A mutant that swaps `!= 1` for `> 1` survives because both refuse 128; mutate to a condition that never
  fires to prove the refusal is tested.

## Decisions (and what would change them)
- One semver app version, independent of `index_version` (decision-022) → data and code ship separately and
  search records pin data versions, not the app → revisit if a second deployable or `/api/v2` appears.
- No CI check of `CHANGELOG.md` → it reads GitHub and every merge would stale it → revisit if releases become
  frequent enough that a stale Unreleased section misleads.

## Follow-ups
- [ ] The first release (v0.1.0) and TASK-066 AC#1 wait on TASK-065 (deploy), which waits on TASK-064 (hosting).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `docs/specs/08-ops-and-tooling.md` §Release (checklist step 6: tag with
  `gh release create`), `.claude/agents/release-manager.md` (steps 2 and 3), `CLAUDE.md` (Makefile list),
  `.claude/skills/repo-conventions/SKILL.md` (CHANGELOG.md and docs/releases.toml rows).
- Test or hook added? — `.claude/scripts/tests/test-changelog.sh` (59 rows) and 14 mutants in
  `.claude/scripts/mutants/changelog.json`.
