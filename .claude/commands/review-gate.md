---
description: The pre-push review gate — route the branch diff to every required reviewer, disposition all findings, and record a per-commit approval (required before git push / gh pr create)
argument-hint: "(optional) extra reviewers to include, e.g. qa-auditor"
allowed-tools: Read, Grep, Glob, Bash, Task, Write
---

Run the review gate for the current branch, following `.claude/skills/review-gates/SKILL.md` exactly.
Extra reviewers requested: $ARGUMENTS

1. **Preconditions.** Working tree clean (commit first). The branch has its learnings entry committed
   (`/record-learnings`) unless it will use `--label no-learning`. `git fetch origin dev`.
2. **Route.** `git diff --name-only origin/dev...HEAD` → apply the routing table. Always include
   `code-reviewer`. Print the reviewer list and why each was chosen.
3. **Review in parallel.** Spawn all routed reviewers in one message. Give each: the diff range
   (`origin/dev...HEAD`), the relevant spec(s) under `docs/specs/`, and the reviewer output contract.
4. **Consolidate.** Merge duplicate findings; keep the highest severity. Show the user the table.
5. **Fix and re-review.** Fix every Must (and whatever Should/Nit you choose), commit, and re-run **only
   the reviewers whose paths the fixes touched** plus `code-reviewer`. Repeat until no Must is open.
6. **Disposition everything.** Write the dispositions file (outside the repo, e.g. the scratchpad):
   every finding → `fixed <sha>` | `task-NNN` (create with `backlog task create`) | `rejected: <reason>`.
7. **Record.** `python3 .claude/scripts/record-review.py APPROVE <dispositions.md>` — add `--attest` if the
   PR already exists. If the script refuses, fix what it names; never hand-write a record.
8. Report: reviewers run, findings by severity with dispositions, the recorded sha, and the next command
   (`git push -u origin <branch>` then `/open-pr`).
