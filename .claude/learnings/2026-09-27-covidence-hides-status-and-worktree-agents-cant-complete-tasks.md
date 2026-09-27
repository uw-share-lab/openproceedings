# Covidence hides a paper's status from screeners, and worktree agents can't close Backlog tasks

**Key lesson:** A screener in Covidence sees neither RIS `KW` nor `N1`, so a paper's review status must be
enforced before import (the default `status:accepted` filter), never left to the screener. In this repo's
agent worktrees `backlog task complete` is refused, so the agent sets the task Done back to In Progress and
the main session completes it after the merge.

- **Date:** 2026-09-27 · **Task:** task-004, task-036, task-081, task-078, task-083, task-087, task-089 · **Area:** exports, tooling
- **Artifacts:** `docs/results/2026-09-27-covidence-check.md`, `docs/specs/04-backend-api.md` §Exports,
  `.claude/skills/ris-format/SKILL.md`, decision-011

## What we set out to do
Close the M3a export tasks with the hand Covidence import (a throwaway practice review, never the live
Trust-Evals one), then land the M3 follow-ups: `/parse` filter clauses (078), paper-page highlights (087),
`op record` (083) and `/meta` limits (089).

## What we learned
- **Covidence's screening card shows title, authors, a journal-style source line (`<T2> <year>;():`), year,
  DOI, the RIS `ID` as "Ref ID" and the abstract; no keywords, no imported notes, no URL.** The Note box holds
  only the team's own notes. So record 1 of the fixture (rejected) looked exactly like an accepted paper.
- **Covidence's duplicate check tolerated an empty vs present volume, `CPAPER` vs `CONF`/`JOUR`, another
  source string and initials-only authors, but not a year one off** (dedup probes 1–5): different-year
  copies are merged by hand. So the export needs no `VL` (task-081 closed without a change).
- **Uploading two files in a row through Covidence's import widget with browser automation silently did
  nothing** after the first import; the owner's manual drag-and-drop worked. Don't retry the widget: hand the
  second import to a person.
- **Worktree agents can't run `backlog task complete`** (the sandbox reads `complete` as the shell builtin),
  and a Done task left in `backlog/tasks/` fails `check_backlog`. Every agent this session hit it; the main
  session ran `backlog task complete` after each merge.

## Dead ends — don't repeat these
- Re-uploading the same file (or a renamed identical copy) via automation to test "import twice": use a person.

## Decisions (and what would change them)
- `TY  - CPAPER` stays (verified in Covidence). Revisit only if a reference manager a reviewer uses mangles it.
- Status is enforced before import, not shown during screening; if Covidence ever shows keywords on the
  screening card, the RIS `KW  - status:` line would reach screeners with no export change.

## Follow-ups
- [ ] The owner deletes the throwaway Covidence review "TEST - openproceedings RIS import check" (#830022).

## Propagated to
- `docs/specs/04-backend-api.md` §Exports; `.claude/skills/ris-format/SKILL.md`;
  `docs/results/2026-09-27-covidence-check.md`.
