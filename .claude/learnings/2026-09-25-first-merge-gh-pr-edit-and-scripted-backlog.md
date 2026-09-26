# `gh pr edit` fails on this GitHub, so the review attestation goes through the REST API

**Key lesson:** Use `gh api -X PATCH repos/{owner}/{repo}/pulls/<n>` to change a PR body, because `gh pr edit` fails on the retired Projects (classic) API. Merge PRs whose learnings or dispositions cite commit SHAs with a merge commit, not a squash. Build a large backlog from a script that checks dependency order before it creates anything.

- **Date:** 2026-09-25 · **Task:** task-008 (M0 exit) · **Area:** tooling
- **Artifacts:** PR #1 (merged as `1377b9d`), `.claude/scripts/record-review.py` (`--attest`), backlog milestones m-0…m-6

## What we set out to do
Merge the M0 tooling PR into `dev`, close M0, and create the M0–M6 backlog.

## What we learned
- **`gh pr edit` is unusable here.** Every call fails with `GraphQL: Projects (classic) is being deprecated … (repository.pullRequest.projectCards)`,
  so `record-review.py --attest` crashed after `gh pr create` on PR #1. The REST endpoint works:
  `gh api -X PATCH repos/{owner}/{repo}/pulls/<n> -f body=<text>` (`-f` sends a raw string; `-F` would
  coerce types and read `@file`). `--attest` now uses it and prints gh's error if the call fails. The
  `review-attested` check then re-ran on the `edited` event and passed within about 20 s.
- **A check that runs before its input exists fails once, and that's fine.** `review-attested` ran at PR
  creation, before the attestation existed, and failed. Editing the body re-triggered it. `/open-pr` already
  attests straight after `gh pr create`; the attestation has to follow creation.
- **Merge, don't squash, when records cite SHAs.** 196 dispositions and two learnings entries cite branch
  commits (`2585bc5`, `82f10f9` …). A squash merge would leave every one of those references pointing at a
  commit that isn't on `dev`.
- **Scripted backlog:** 7 milestones and 62 tasks were created through the CLI in 13 s. The script checks
  dependency order statically first (two forward dependencies were caught and reordered before anything
  ran). Every task's acceptance criteria cite the spec section they implement.

## Dead ends — don't repeat these
- Don't retry `gh pr edit`; it fails the same way every time. Go straight to `gh api`.
- **`backlog task edit --dep` replaces the dependency list; it doesn't append.** Adding the Q2/Q3 decisions to
  task-050 silently dropped its dependency on task-002 and task-022. Pass the full list (old plus new) every time.

## Decisions (and what would change them)
- Merge commits into `dev`, for the traceability above. If history gets noisy, squash only the PRs whose
  records cite no SHAs.

## Follow-ups
- [ ] task-009 onward: the M1–M6 plan (`backlog milestone list`).

## Propagated to
- `.claude/scripts/record-review.py` (`--attest` via REST).
- `.claude/skills/pr-workflow/SKILL.md` (merge method): see the note added below.
