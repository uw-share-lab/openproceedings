---
id: decision-027
title: >-
  Merge queue for dev: queue builds re-run the required checks and pr-gates
  checks every queued PR from the queue's merge commits, failing closed
  (TASK-161)
date: '2026-10-02 05:15'
status: accepted
---
## Context

`dev`'s classic branch protection requires a PR to be up to date with `dev` (`strict: true`), and the
`review-attested` check is keyed to the exact head sha. Every merge into `dev` left every other open PR
behind. Each one then needed a rebase, a patch-id comparison, a new review record with its `fixed <sha>`
dispositions remapped, a force-push, a new attestation, and often a close and reopen to beat the stale-body
race. The PRs had to be merged one at a time, by hand. With several agents' PRs open at once, this became
the slowest step in the project.

A GitHub merge queue removes the rebase. A PR is added to the queue. GitHub builds a temporary branch,
`gh-readonly-queue/dev/pr-<N>-<sha>`, holding `dev` plus the queued PRs. It runs the required checks on that
branch under the `merge_group` event and fast-forwards `dev` when they pass. The queue is configured through
a repository ruleset. Classic branch protection has no merge-queue setting in its API. Rulesets and classic
protection stack, so the six required checks stay where they are.

The three `pr-gates` jobs read `github.event.pull_request`, and a `merge_group` event doesn't have it. Taught
nothing, those jobs would never start, and the queue would wait for the checks forever. Made to pass on
`merge_group`, they would become no-ops. The owner asked for neither. The queue's builds must still prove
that each PR in the group was reviewed (an APPROVE attested for that PR's head), has a learnings entry, and
carries no AI attribution.

Options considered:
1. **Resolve the PRs from the head ref alone** (`pr-<N>` in `gh-readonly-queue/dev/pr-<N>-<sha>`), then check
   PR N. Rejected as the whole answer: the ref names only the newest PR in the group. When PRs are grouped,
   the ones ahead of it would go unchecked.
2. **Trust the PR-level checks**, since a PR can't be queued until its own checks pass, and make the
   `merge_group` jobs pass. Rejected: the owner ruled out a no-op, and the PR-level `review-attested` reads a
   body snapshot that may predate a later push.
3. **Walk the queue's merge commits** (chosen). With the MERGE method, `base_sha..head_sha` along first
   parents is one two-parent merge per queued PR, oldest first. Parent 2 of each merge is the PR's head as
   queued. Each PR can then be checked exactly as the `pull_request` job checks it.
4. **Drop strict up-to-date without a queue.** Rejected: two green PRs could then merge into a red `dev`, and
   no check would ever have run on their combination.

## Decision

`lint`, `test`, `claude-tooling` and `pr-gates` trigger on `merge_group` (`checks_requested`), so the queue's
builds report all six required checks under their existing names. `test` takes its OpenAPI baseline from
`merge_group.base_sha`.

In a `merge_group` run, the three `pr-gates` jobs run `.claude/scripts/merge_group_gate.py
review|learnings|attribution` with the event's `base_sha`, `head_sha` and `head_ref`:

- **The group.** The head ref must match `refs/heads/gh-readonly-queue/dev/pr-<N>-<40 hex>`. Every commit in
  `git rev-list --first-parent base..head` must have exactly two parents. The first commit's parent 1 must be
  `base`, and each later commit's parent 1 must be the commit before it. Each merge's PR comes from GitHub's
  subject, `Merge pull request #N from …`. A merge with a different subject falls back to the one open PR
  into `dev` whose head is parent 2 (`GET commits/<sha>/pulls`). No PR may appear twice, and the newest
  merge's PR must be the head ref's `N`.
- **review-attested.** For each PR, the API copy must be `open`, have base `dev` and head sha = parent 2, and
  the current body must contain `<!-- op-review: <parent 2> APPROVE -->`. The body is read when the queue
  build runs, so the stale-snapshot race of the `pull_request` job doesn't apply.
- **learnings.** For each PR: the `no-learning` label (an exact name), or an added or extended
  `.claude/learnings/YYYY-MM-DD-<slug>.md` in `git diff parent1...parent2`. That diff starts at the merge base
  of the PR and the queue commit before it, so it is the PR's own change. The rule is the `pull_request` job's,
  renames included.
- **attribution.** No commit message in `base..head` (the queue's merge commits included), and no PR title or
  body, may match the attribution pattern.

Everything fails closed: a malformed sha or ref, an empty range, a non-merge or octopus commit, a chain that
doesn't start at `base`, an unresolvable or duplicated PR, a failed `gh` call, and JSON of the wrong shape.
Each `pr-gates` job also starts with a step that fails on any event other than `pull_request` and
`merge_group`, so a job whose gate steps all skip can't pass. The three jobs get `pull-requests: read`.

The queue settings: merge method MERGE, because dispositions and learnings cite branch SHAs (the existing
merge-commit rule), and the gate depends on two-parent merges. ALLGREEN grouping, so every entry's own
checks must pass and no PR merges only on the strength of a later entry's build. Up to 5 entries built and
merged at once, minimum 1, no wait, and a 60-minute check timeout (the `test` job's limit is 30 minutes).
`strict` is turned off on `dev`'s classic required checks, because the queue provides the up-to-date
guarantee. `main` is unchanged.

Commands, for a maintainer to run after TASK-161's PR merges. Run the ruleset first, so there is no window
with neither the queue nor the strict check:

```sh
gh api -X POST repos/uw-share-lab/openproceedings/rulesets --input - <<'JSON'
{
  "name": "dev: merge queue",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["refs/heads/dev"], "exclude": [] } },
  "rules": [
    {
      "type": "merge_queue",
      "parameters": {
        "merge_method": "MERGE",
        "grouping_strategy": "ALLGREEN",
        "max_entries_to_build": 5,
        "min_entries_to_merge": 1,
        "max_entries_to_merge": 5,
        "min_entries_to_merge_wait_minutes": 0,
        "check_response_timeout_minutes": 60
      }
    }
  ]
}
JSON
gh api -X PATCH repos/uw-share-lab/openproceedings/branches/dev/protection/required_status_checks -F strict=false
# verify: prints merge_queue, then false and the six contexts
gh api repos/uw-share-lab/openproceedings/rules/branches/dev --jq '.[].type'
gh api repos/uw-share-lab/openproceedings/branches/dev/protection/required_status_checks --jq '.strict, .contexts'
```

Rollback, if the queue's builds misbehave:

```sh
id=$(gh api repos/uw-share-lab/openproceedings/rulesets --jq '.[] | select(.name == "dev: merge queue") | .id')
gh api -X PATCH repos/uw-share-lab/openproceedings/branches/dev/protection/required_status_checks -F strict=true
gh api -X DELETE "repos/uw-share-lab/openproceedings/rulesets/$id"
```

## Consequences

- A green PR is queued with `gh pr merge <n> --auto`. A PR that falls behind `dev` needs no rebase, review
  record or attestation. A rebase is needed only for a real conflict or a red queue build, and then the new
  head is re-reviewed and re-attested as before. A push to a queued PR removes it from the queue.
- The trust model is unchanged. As with the `pull_request` jobs, this is an honesty check, not an access
  control. A queued PR's own commits can change `merge_group_gate.py` and the workflow, since GitHub runs
  the workflow from the queue's head, just as a PR can change `pr-gates.yml` today. The access control is
  still branch protection plus human review on `main`.
- The gate depends on GitHub's queue shape: two-parent merges with the MERGE method, and the
  `gh-readonly-queue/dev/pr-N-<sha>` ref. If GitHub changes that shape, the jobs fail closed and the queue
  stops merging. It does not wave PRs through. The rollback above then restores the old flow while the
  script is updated. The table `.claude/scripts/tests/test-merge-group-gate.sh` builds the expected shape with
  real merges. The first queued PR after the ruleset is applied is the live check of that shape.
- Every queue entry runs the full `test` job again on the combined result. That doubles CI minutes per PR,
  which is the price of never merging an untested combination.
- Release promotions (`dev → main`) and back-merges keep their existing procedure (spec 08 §Release). The
  back-merge PR into `dev` goes through the queue like any other PR, under the same `no-learning` label rule.

