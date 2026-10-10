# A property that fails only in one checkout is a stored falsifying example: extract it before judging it pre-existing

**Key lesson:** When a Hypothesis test fails in only one worktree, the `.hypothesis` database holds an input no explicit `@example` covers: extract that input and pin it as an `@example` before bisecting or calling the failure pre-existing, because copying the database between checkouts stores choice sequences, not examples, and gives inconclusive results; verify "pre-existing" in a detached temporary worktree, never with `git stash`.

- **Date:** 2026-10-10 · **Task:** TASK-214 (follow-ups TASK-224, TASK-225) · **Area:** ingest
- **Artifacts:** `.superpowers/sdd/2026-10-10-new-venues-milestone-b/progress.md` (Task 6 and Debug lines), `debug-reconcile-report.md`, `review-dedup-fix.md`, `task-6-report.md`, `task-7-report.md`, `task-8-report.md`, `task-9-report.md`; commits 3bd090cb, 955d15b1 (dedup), 4dd4a651, 0006f9bd (Crossref), c65a7e60, 6e41f6d2

## What we set out to do
Milestone B: AAAI 1980-2008, FAccT 2018-2026 and AIES 2018-2023 as new sources.

## What we learned
- **A local database can hold a failing example nothing else covers.** `test_reconcile.py::test_dedup_and_reconcile_again_change_nothing` failed in one worktree only; with its `.hypothesis` removed HEAD passed (evidence: progress.md, Task 6). The controller's bisect with the database copied between checkouts was inconclusive: merged `dev` plus the database failed, the older commit plus the database passed, yet the database stores choice sequences that decode to different inputs on different code.
- **The extracted example was a real bug.** Dedup was not idempotent since TASK-179 (06e029bc): step 2 refuses an import-ambiguous title group, step 3 merges the import by abstract into a newer RIS row with another title, and one claim per source drops the import's title, so a second run merges more. Fix: steps 2 and 3 (and the forum link) repeat until a pass merges nothing (3bd090cb, 955d15b1); the cases are `@example`s on `test_idempotent` (evidence: debug-reconcile-report.md, review-dedup-fix.md).
- **"Pre-existing" claims need a clean check.** The Task 6 implementer reported the failure as pre-existing and unrelated, verified "via a tagged stash" (task-6-report.md). The stash stack is shared across worktrees, so that check was unsafe and its result misleading: the failure was real and reachable.
- **Desk research is a hypothesis; the census decides.** AAAI was also not held in 1995 (found from the pinned dblp release: 23 held years, not 24); the brief's 1,341 FAccT DOIs could not be reproduced (1,239 ACM DOIs, 1,230 records); the ISBN cross-check is unbuildable because papers carry no ISBN (evidence: task-8-report.md, task-9-report.md, progress.md).
- **Crossref `next-cursor` encodes position and differs per page**, checked live (2 requests, 2026-10-10), so URL-keyed cache chains are safe (progress.md, Task 7).
- **New sources stop; legacy paths keep their behaviour.** AAAI `invalid_record`, Crossref `unexpected_type` and count mismatches, and PMLR's non-ICML count check all stop the crawl or replay (e5749e04, caebc9c5, 02d7c050), while ICML's old paths and extract bytes are unchanged unless deliberately changed (hash `c2086904...0168` held).
- **A personal contact address leaked into the plan's rulings** (commit c0ff8929) and was caught before push by the Task 9 reviewer's grep; the unpushed branch was rewritten with `filter-branch` over `origin/dev..HEAD` and `git log -p` then had 0 hits (progress.md).

## Dead ends — don't repeat these
- Bisecting with the Hypothesis database copied between checkouts; it replays choice sequences, not inputs, so pass/fail flips with the code.
- Using `git stash` to test a base commit from a worktree.
- Quoting a count from the desk note; every figure comes from the census.

## Decisions (and what would change them)
- Pin the extracted input as an explicit `@example` first, then bisect → deterministic on every checkout → none.
- Refer to secrets and personal contacts as "the address in `.env`" in plans, rulings and briefs → tracked files never carry them → none.
- Accept 1995 as not held → the pinned release has no 1995 volume → a later release that adds one.

## Follow-ups
- [ ] TASK-224 — milestone B follow-up (filed by the controller)
- [ ] TASK-225 — milestone B follow-up (filed by the controller)

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/testing-standards/SKILL.md` (falsifying examples; temporary worktrees, not stash) and `.claude/skills/pr-workflow/SKILL.md` (grep for personal contact data before push)
- Test or hook added? — the dedup regression `@example`s on `test_idempotent` (`backend/tests/unit/ingest/test_dedup_props.py`); no hook for the contact grep (a reviewer step, and the address is not stored in the repo to grep for by script)
