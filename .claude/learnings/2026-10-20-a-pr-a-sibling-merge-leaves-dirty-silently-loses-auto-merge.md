# A PR that a sibling's merge leaves in conflict silently loses its auto-merge

**Key lesson:** After each merge into `dev`, read every other waiting PR's `mergeStateStatus`: a `DIRTY` one has lost its auto-merge with no notice and runs no CI, even after a close and reopen, so rebase it (regenerating `.claude/learnings/INDEX.md` with `learnings_index.py` at each stop), re-record its approval on the new shas, and queue it again.

- **Date:** 2026-10-20 · **Task:** v0.4.1 release (TASK-270, TASK-271, TASK-272) · **Area:** tooling
- **Artifacts:** PRs #175, #176, #177; `.claude/skills/pr-workflow/SKILL.md` §Merge method

## What we set out to do
Merge #176 (TASK-272), then let #175 (TASK-270) and #177 (TASK-271), both already approved and set to
auto-merge, follow it through `dev`'s merge queue before cutting `release/0.4.1`.

## What we learned
- **Two learnings make two PRs conflict.** Every PR adds a learning, and `learnings_index.py` writes each new entry
  at the top of the generated `INDEX.md`, newest first. Once #176 merged, #175 and #177 both conflicted with `dev`
  on that file alone (evidence: `git merge-tree --write-tree --name-only origin/dev HEAD` named only
  `.claude/learnings/INDEX.md` for each).
- **`DIRTY` drops the PR from the queue without a word.** #177 had been set to merge. After #176 merged,
  `gh pr view 177` showed `mergeStateStatus: DIRTY` and `autoMergeRequest: null`, and the queue was empty. Nothing
  notified us, and the PR sat for about two hours.
- **Closing and reopening a conflicted PR runs no CI.** #175 was closed and reopened to rerun its checks on the
  fixed `dev`. Its latest `test` run was still the one from before #176, because a conflicted PR has no merge ref
  for `pull_request` workflows to build.
- **Regenerating the index resolves the conflict exactly.** At each stop in the rebase,
  `python3 .claude/scripts/learnings_index.py` followed by `git add` and `git rebase --continue` rebuilt the file
  from the entries on disk. The rebased diff then added exactly one index line, and `git patch-id --stable` matched
  the old branch on every other file. So the old review record still covered the change; only its `fixed <sha>`
  references needed remapping to the rebased commits.
- **#175 then conflicted with #177 the same way, but the queue serialized them.** Both were queued after the
  rebase; #177 merged first and #175 merged right after it with no further rebase.

## Dead ends — don't repeat these
- Closing and reopening a `DIRTY` PR to get fresh checks. Rebase it instead.
- `git push … | tail -2 && record-review.py … --attest` in one chained command: `tail` exits 0, so the attestation
  ran while the push was still stuck in the pre-push hook (`make tooling` took more than 100 minutes at a load
  average of 80). The record and the PR body named a head that wasn't on GitHub yet. Run the push alone and check
  its exit status before recording.

## Decisions (and what would change them)
- Resolve the index conflict by regenerating it, never by picking hunks: the file says "do not edit by hand", and
  regeneration can't drop an entry. Generating the index at merge time instead of committing it would remove the
  conflict altogether. That is worth doing if it happens again.

## Follow-ups
- None filed. Committing `INDEX.md` is the existing design (`load-learnings.sh` reads it at session start); the
  skill now says how to resolve the conflict.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/pr-workflow/SKILL.md` §Merge method (watch for `DIRTY` after
  each merge; regenerate `INDEX.md` when rebasing)
- Test or hook added? — no: what changes is how a person watches the queue, and no check in this repo can see it
