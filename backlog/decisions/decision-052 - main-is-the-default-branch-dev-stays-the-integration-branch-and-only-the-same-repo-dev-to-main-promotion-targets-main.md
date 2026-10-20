---
id: decision-052
title: >-
  main is the default branch; dev stays the integration branch, and only the
  same-repo dev to main promotion targets main
date: '2026-10-20 13:40'
status: accepted
---
## Context

The repo has been public since 2026-09-25 with `dev` as its default branch (spec 08 §Branch protection). Before
open-sourcing it more widely, the owner asked on 2026-10-20 for `main` to be the default: a visitor, a clone and a
fork should land on released code, not on the integration branch. `dev` stays where the org's writers integrate;
people outside the org may fork and open PRs, but never push. As checked that day, only three accounts have write
access (two maintainers and the lab account); the other collaborators are org members with read access, there are
no outside collaborators, and forking is on (a public repo can't turn it off). A public repo's branches are all
readable, so "dev for people with access" means merging into it, not seeing it: `dev`'s protection (a PR, the six
required checks, admins included) and its merge queue already limit that to writers.

Two GitHub behaviours tie to the default branch: Dependabot reads `.github/dependabot.yml` from it and opens its
version updates against it unless `target-branch` says otherwise, and a `schedule` trigger runs the default branch's
copy of a workflow on the default branch's head. Switched alone, Dependabot's PRs would target `main` past `dev`'s
queue, and the nightly would test `main`. A fork's PR also opens against the default branch unless its author picks
another.

Options: keep `dev` as the default (refused: the owner wants visitors on released code); switch at once and fix the
config at the next release (refused: until then Dependabot and the nightly point at `main`); land the config on
`dev` first and switch right after the next release puts it on `main` (chosen; v0.4.1, cut the same day, 2026-10-20). For
outsiders' PRs: allow them into `dev` (chosen, the usual open-source flow) or refuse every PR from a non-member
(refused by the owner).

## Decision

We make `main` the default branch right after v0.4.1 is tagged. Dependabot targets `dev` (`target-branch: dev` on
every ecosystem), the scheduled nightly checks out `dev`, and a `pr-base` check, required on `main`, fails every PR
into `main` except the same-repo `dev → main` promotion, telling its author to target `dev`.

## Consequences

- `.github/dependabot.yml`, `.github/workflows/nightly.yml` and `.github/workflows/pr-gates.yml` (`pr-base`) change;
  `.claude/scripts/tests/test-merge-group-gate.sh` checks `pr-base`'s wiring and runs its gate on the promotion, a
  fork's `dev`, a feature branch and `main` (TASK-271).
- The nightly's workflow file is `main`'s copy: an edit to it reaches the schedule only at the next release
  (`workflow_dispatch` on a branch runs that branch's copy, as a run dispatched on `dev` for §Release step 1's
  readiness does). A scheduled run is listed under `main` and its sha, so a first `resolve` job reads `dev`'s head once, writes it
  to the run's summary, and every job checks out that sha
  (`test-default-branch.sh`).
- Dependabot security updates always open against the default branch, whatever `target-branch` says (GitHub's
  Dependabot options reference, `target-branch`). They are off in this repo (`security_and_analysis`, checked
  2026-10-20); if they are turned on, such a PR fails `pr-base` and is retargeted to `dev` before review.
- `pr-base`, like `review-attested`, is a signpost, not an access control: a PR's own copy of `pr-gates.yml` runs.
  Branch protection and the maintainers who merge are the access control.
- After the switch, `gh pr create` without `--base` targets `main`; `/open-pr` and the promotion command already
  pass `--base`. Revisit if the release flow changes (a hotfix straight into `main` would need `pr-base` widened).
- No index, snapshot or search record is affected.

