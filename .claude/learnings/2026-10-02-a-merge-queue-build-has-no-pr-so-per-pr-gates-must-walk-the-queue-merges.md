# A merge-queue build has no PR, so a per-PR gate must find each PR from the queue's merge commits

**Key lesson:** When a workflow that produces a required check gets a `merge_group` trigger, rewrite every step that reads `github.event.pull_request` (it is absent there), and resolve each queued PR from the queue's two-parent merges in `base_sha..head_sha` (parent 2 is the PR's head), because the `gh-readonly-queue/<base>/pr-N-<sha>` ref names only the newest PR in the group and a gate that skips or passes on `merge_group` is a silent no-op.

- **Date:** 2026-10-02 · **Task:** task-161 · **Area:** tooling
- **Artifacts:** `.claude/scripts/merge_group_gate.py`, `.claude/scripts/tests/test-merge-group-gate.sh`, `.claude/scripts/mutants/merge-group.json`, `.github/workflows/pr-gates.yml`, decision record "Merge queue for dev"

## What we set out to do
Replace `dev`'s "require branches to be up to date" setting with a merge queue. Every merge was forcing each
open PR to rebase, re-review and re-attest by hand. The review gate, which is keyed to the head sha, had to
keep working.

## What we learned
- Classic branch protection has no merge-queue field in its REST API. The queue is a `merge_queue` rule in a
  repository ruleset, and rulesets stack with classic protection, so the six required checks can stay where
  they are (evidence: `gh api repos/uw-share-lab/openproceedings/branches/dev/protection` shows `strict: true`
  and no queue setting).
- A required check whose workflow lacks `merge_group` never starts on a queue build, so the queue waits
  until its check timeout. Every workflow that produces a required check needs the trigger, including
  `lint`, `test` and `claude-tooling`, which have no PR-specific logic.
- Under `merge_group`, `github.head_ref`, `github.base_ref` and `github.event.pull_request.*` are all empty.
  The `pr-gates` job-level `if:` therefore still runs, but its step reading `pull_request.body` would compare
  against an empty string. A step guarded by `contains(pull_request.labels…)` would run for every group.
- With the MERGE method, each queued PR is one two-parent merge on the first-parent chain from `base_sha`.
  `git diff parent1...parent2` is that PR's own diff, so the `pull_request` learnings rule carries over as it
  is. Reading the PR's current body through the API, not an event snapshot, also avoids the stale-body race
  that the `pull_request` `review-attested` job has.
- `gh pr merge <n> --auto` queues a PR by enabling auto-merge, so it needs the repository's "Allow auto-merge"
  setting, which was off here (`gh api repos/uw-share-lab/openproceedings --jq .allow_auto_merge` → `false`).
  Enabling a merge queue is therefore three settings, not two. GraphQL `enqueuePullRequest` works without it.
- A per-PR gate that requires every PR in the range to be open can eject good entries. GitHub merges an entry
  ahead as soon as its own build is green, so a later entry's jobs (or a re-run of them) may find that PR
  closed. Accept exactly "merged by this group's own queue commit" (`merged` and `merge_commit_sha`).
- A case table that checks only the exit status lets mutants survive behind incidental failures. A removed
  type check still fails, just later, on an `AttributeError` that `main` catches. Every err row now names the
  `::error::` text it expects. Before that change, 9 of 33 mutants survived.
- A row that compares two separately built merge commits passes only when both land in the same second.
  Take the commit from the chain under test (`$Q2^1`), not from a sibling branch.
- The repo's `fake gh on PATH` pattern (from `test-changelog.sh`) plus real `git merge --no-ff` commits gives a
  table that covers the GitHub shape without network access.

## Dead ends — don't repeat these
- YAML anchors (`&env` / `*env`) to share the `merge_group` env block: GitHub accepts them now, but they are
  new enough that the pinned actionlint and readers may not. Repeat the five lines instead.
- `run: { echo …; exit 1; }` in a workflow is a YAML flow mapping, not a shell group. Write it as a plain
  string.

## Decisions (and what would change them)
- The gate walks the queue's merges and does not trust the head ref alone, because the ref names only the
  newest PR. If GitHub stops using two-parent merges (the MERGE method), the gate fails closed, and the
  decision record's rollback restores the strict flow.

## Follow-ups
- [ ] none: applying the ruleset is a settings step for the lead, with the commands in the decision record and TASK-161's notes.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/pr-workflow/SKILL.md` §Merge method, `.claude/agents/ci-engineer.md` (a required check's workflow must trigger on `merge_group`), spec 08 §Merge queue
- Test or hook added? — `.claude/scripts/tests/test-merge-group-gate.sh` with mutants in `.claude/scripts/mutants/merge-group.json`
