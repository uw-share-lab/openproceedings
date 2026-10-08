---
id: decision-048
title: >-
  A weekly Claude routine reviews and queues Dependabot PRs; the PR gates stay
  on for them
date: '2026-10-07 20:54'
status: accepted
---
## Context

Dependabot (`.github/dependabot.yml`, weekly; spec 08 §CI "Dependabot") opens about one grouped PR a week
per ecosystem into `dev` (github-actions, uv, npm, docker), plus one PR per docker digest bump. Every PR into
`dev` must pass the six required checks, two of which a bot's PR can't pass alone: `learnings` (an entry or the
`no-learning` label) and `review-attested` (the body attests an APPROVE record for the head, which only `record-review.py` writes
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
for the owner, a PR with a commit that isn't Dependabot's (signed and verified), a file outside its
ecosystem or a change beyond dependency versions and pins, an integrity or URL mismatch, a new publisher or lost
provenance, a new install script, a new package, a uv or npm release younger than 7 days, a digest that
doesn't resolve or a failed attestation, a red required check it can't fix, a Must it can't fix, any semver-major, anything
touching `tantivy`, or a new Python release (patch or minor). The gates stay on for Dependabot PRs.

The review gate of TASK-211 shaped three parts of this:
- **The routine runs untrusted code, so it trusts only `dev`.** It runs the checkers from `dev`'s copy, gates
  each PR with `prs.py check` before anything of the PR runs, rejects any change beyond versions and pins (a
  `package.json` script, a `[build-system]` requirement, a Dockerfile `RUN` line or a workflow `permissions:`
  would otherwise run in `make test` or merge unread), and queues with `--match-head-commit`.
- **A legitimate pipeline can still publish a bad release**, so Dependabot's `cooldown` holds every version
  update back 7 days (a compromised release is most often pulled within days), and the uv and npm checkers stop
  a younger one, which then can only be a security update: the owner decides. For actions and docker images
  the hold is the `cooldown` alone (no checker reads their age).
- **A new Python patch is the owner's.** Spec 08's "Python pin" says extracted text can depend on the release;
  TASK-208 proved 3.12.9 → 3.12.15 changed nothing by replaying the whole crawl cache, which needs `data/`, which
  the routine doesn't have. A new digest for the same tag carries no parser change and is merged like any other.

## Consequences

- Spec 08 §CI "Dependabot" states the routine, what it may merge and what it leaves open; `ci-engineer`
  points to the command. The procedure changes only by PR, reviewed like any other, so the routine runs
  what was reviewed (TASK-211).
- The checks that were judgement in the 2026-10-07 run are now scripts with a case table
  (`.claude/scripts/tests/test-dependabot.sh`, in `make tooling`) and mutants
  (`.claude/scripts/mutants/dependabot.json`), so a regression in a check fails CI.
- The routine needs, in its cloud environment: `gh` authenticated with a **fine-grained token for this
  repository only, with `contents`, `pull requests`, `issues` and `actions` read and write, and nothing
  else** (no `administration`, so it can't touch the rulesets; no `workflows`, because with it a leaked token
  could push a workflow that runs with the repository's secrets), held in `GH_TOKEN` only. So the routine
  reviews and attests a github-actions PR but doesn't queue it (queueing a change to `.github/workflows/` may
  need `workflows`): its summary asks the owner to run `gh pr merge <n> --auto`. It also needs Node 22, npm,
  uv 0.12.22 or later, Python 3.11 or later, shellcheck; Playwright's Chromium and Docker when available. Where `make e2e` or
  `deploy/smoke-test.sh` can't run, the PR names the CI check that stands in (`playwright`, `web-image`). The
  tests, the reviewers' runs, the pre-push hook's `make lint` and `make tooling`, and the autofix hook's ruff,
  prettier and eslint run without the token in their environment. What the cloud environment gives every process (a git credential helper, a proxy) stays
  reachable by dependency code; the shape checks (only registry-verified versions run) are what bound that.
  Its commits carry the git identity the environment
  configures, which must name a person (the command stops on an empty one or one naming an AI), and no AI
  attribution (the hooks and CI's `attribution` check refuse it).
- The attestation stays an honesty check, not an access control (spec 08 §CI): the token can edit any PR body.
  The fine-grained scope and the merge queue's required checks bound what a leaked token could do; the
  owner's review of `main` promotions stays the access control for releases.
- Review records are per clone (`.git/op-reviews/`), so the routine records, pushes and attests in one
  session; nothing it records survives to the next run.
- What would change this: the routine merging something a later review shows it shouldn't have (tighten
  the scripts or the hard stops, or go back to option 2), or GitHub offering a reviewed-bot path that keeps
  the attestation meaningful.
- The routine changes no rule about matching, `index_version` or search records. A dependency it merges can
  change behaviour exactly as a hand-merged one could; CI's golden, contract and differential suites guard
  that, and the Python release, the one bump known to change ingest output, stays with the owner.
