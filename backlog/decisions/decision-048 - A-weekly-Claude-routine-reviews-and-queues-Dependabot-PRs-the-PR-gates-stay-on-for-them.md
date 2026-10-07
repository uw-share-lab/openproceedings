---
id: decision-048
title: >-
  A weekly Claude routine reviews and queues Dependabot PRs; the PR gates stay
  on for them
date: '2026-10-07 20:54'
status: accepted
---
## Context

Dependabot (`.github/dependabot.yml`, weekly; spec 08 §CI "Dependabot") opens up to four grouped PRs a week
into `dev`: github-actions, uv, npm and the docker base-image digests. Every PR into `dev` must pass the six
required checks, two of which a bot's PR can't pass alone: `learnings` (an entry or the `no-learning` label)
and `review-attested` (the body attests an APPROVE record for the head, which only `record-review.py` writes
after a review). Until 2026-10-07 the owner's session reviewed each PR by hand. The run that merged #123–#125
on 2026-10-07 found real work in them: a caret Dependabot wrote into the lock's workspace entry (#124), `libc`
fields an older local npm dropped, seven Next.js advisories `npm audit` didn't show, two older high advisories
with lockfile-only fixes, and a docs version to move.

Options considered:
1. **Exempt `dependabot[bot]` from `learnings` and `review-attested`**, and let a green PR merge unreviewed.
   Rejected by the owner (2026-10-07): CI would pass every finding above, because none of them fails a test
   (`npm ci` accepts the caret; a dropped `libc` installs on the runner; advisories are not test failures). It
   would also be the first author-based exemption in the gates, which the attestation's honesty check
   (spec 08 §CI) was built not to have.
2. **The owner reviews each PR by hand** (the practice so far). It works, but takes a session a week and
   depends on the procedure being remembered.
3. **A weekly scheduled Claude routine runs a committed procedure** (`/dependabot-review`): a cloud Claude
   Code session on a fresh clone, with no access to the owner's machine, reviews each open Dependabot PR
   through the same gates as any PR, fixes what is needed, attests and queues it, and leaves anything
   suspicious open with a comment.

## Decision

We adopt option 3 (owner's decision, 2026-10-07). A weekly routine runs `/dependabot-review`
(`.claude/commands/dependabot-review.md`) with the scripted checks in `.claude/scripts/dependabot/`. It may
merge, through the merge queue only, a Dependabot PR that passes the supply-chain scripts, the release-note
review, the tests, the reviewers and every required check. It never merges, and leaves open with a comment
for the owner, a PR with an integrity or URL mismatch, a new publisher or lost provenance, a new install
script, a new package, a digest that doesn't resolve or a failed attestation, a red required check it can't
fix, a Must it can't fix, any semver-major, or anything touching `tantivy` or the Python minor. The gates
stay on for Dependabot PRs.

## Consequences

- Spec 08 §CI "Dependabot" states the routine, what it may merge and what it leaves open; `ci-engineer`
  points to the command. The procedure changes only by PR, reviewed like any other, so the routine runs
  what was reviewed (TASK-211).
- The checks that were judgement in the 2026-10-07 run are now scripts with a case table
  (`.claude/scripts/tests/test-dependabot.sh`, in `make tooling`) and mutants
  (`.claude/scripts/mutants/dependabot.json`), so a regression in a check fails CI.
- The routine needs, in its cloud environment: `gh` authenticated with push, PR, label and merge rights on
  the repo, Node 22, npm, uv and Python 3.12; Playwright and Docker when available. Where `make e2e` or
  `deploy/smoke-test.sh` can't run, the PR names the CI check that stands in (`playwright`, `web-image`).
  Its commits carry the git identity the environment configures, and no AI attribution (the hooks and CI's
  `attribution` check refuse it).
- Review records are per clone (`.git/op-reviews/`), so the routine records, pushes and attests in one
  session; nothing it records survives to the next run.
- What would change this: the routine merging something a later review shows it shouldn't have (tighten
  the scripts or the hard stops, or go back to option 2), or GitHub offering a reviewed-bot path that keeps
  the attestation meaningful.
- No effect on matching, `index_version` or search records.
