# npm audit's `fixAvailable` can be a major downgrade when the advisory has no patched version

**Key lesson:** Before filing "bump X to clear advisory Y", read the advisory's `first_patched_version` (`gh api /advisories/<GHSA>`) and npm audit's `fixAvailable.version` against the version in the lock: a null patch with a `fixAvailable` older than what is installed means npm is proposing a downgrade away from the chain, and no upgrade clears it yet.

- **Date:** 2026-10-21 · **Task:** TASK-271 (close-out PR) · **Area:** tooling
- **Artifacts:** `package-lock.json` (`node_modules/braces`, `micromatch`, `fast-glob`, `@next/eslint-plugin-next`, `eslint-config-next`), GHSA-vfj7-8cjw-p6xm, `.claude/commands/dependabot-review.md` §10

## What we set out to do
File a task for the five high `npm audit` findings on `dev` after #178, assumed to be cleared by an eslint-config-next major.

## What we learned
- **The five findings are one advisory.** `npm audit --json` lists `eslint-config-next`, `@next/eslint-plugin-next`,
  `fast-glob`, `micromatch` and `braces`, each high, each `via` the next: eslint-config-next 16.4.0 →
  @next/eslint-plugin-next 16.4.0 (pins `fast-glob` 3.3.1) → micromatch 4.0.8 → braces 3.0.3, all `dev: true` in the
  lock. `npm audit --omit=dev` finds 0.
- **There is no patched braces.** `gh api /advisories/GHSA-vfj7-8cjw-p6xm` gives `braces <= 3.0.3` with
  `first_patched_version: null`, and `npm view braces version` is 3.0.3.
- **npm's "fix" is a downgrade.** `fixAvailable` is `eslint-config-next@14.2.35, isSemVerMajor: true`: Next 14's
  config, whose plugin uses `glob` instead of `fast-glob`. "Semver-major" here means a major *away*, not up, and it
  doesn't fit Next 16.
- **An upgrade doesn't help either.** @next/eslint-plugin-next 16.4.2 (latest) and 16.5.0-canary.21 still pin
  `fast-glob` 3.3.1, and fast-glob 3.3.3 still takes micromatch 4.0.8.

## Dead ends — don't repeat these
- Reading "5 high" and `isSemVerMajor` as "a major bump fixes it". Check the direction of the version.
- An `overrides` entry for fast-glob: its newest release still reaches braces 3.0.3.

## Decisions (and what would change them)
- Wait for upstream, tracked as a low-priority task: the exposure is lint over the repo's own glob patterns, in dev
  and CI only. A braces release that fixes the advisory, or a Next plugin that drops this chain, reverses it.

## Follow-ups
- [ ] task-278 — pick up the braces fix once one is published

## Propagated to
- Skill / agent / CLAUDE.md updated? — no: `/dependabot-review` already runs `npm audit --omit=dev` for what ships;
  this is a filing check, recorded here.
- Test or hook added? — no (nothing to enforce until a fix exists).

## Addendum (2026-10-28)
GitHub withdrew GHSA-vfj7-8cjw-p6xm on 2026-10-23 without a braces release, so `npm audit` stopped
flagging braces 3.0.3 and TASK-278 closed with no dependency change for it. A task that waits on an upstream
fix should also check `gh api /advisories/<id> -q .withdrawn_at`: a withdrawal ends the wait as surely as
a patch.
