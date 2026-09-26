---
description: The pre-push review gate — route the branch diff to every required reviewer, disposition all findings, and record a per-commit approval (required before git push / gh pr create)
argument-hint: "(optional) extra reviewers to include, e.g. qa-auditor"
allowed-tools: Read, Grep, Glob, Bash, Task, Write
---

Run the review gate for the current branch, following `.claude/skills/review-gates/SKILL.md` exactly.
Extra reviewers requested: $ARGUMENTS

1. **Preconditions.** Working tree clean (commit first). `make test`, `make lint` and `make tooling` green.
   Tasks, docs, specs and READMEs updated in the same branch, and Done tasks moved with
   `backlog task complete <id>` (`.claude/skills/task-hygiene/SKILL.md`). The branch has its learnings entry
   (new, or an existing entry extended with a dated addendum) committed (`/record-learnings`) unless it will
   use `--label no-learning`. `git fetch origin dev`.
2. **Route.** `git diff --name-only origin/dev...HEAD` → apply the routing table. Always include
   `code-reviewer` and `docs-reviewer` (every diff). Add `observability-reviewer` for any `backend/src/**`
   change, and `security-reviewer` + `qa-auditor` for `.claude/hooks/**`, `.claude/scripts/**`,
   `.github/**`, `.githooks/**`, `Makefile`, `pyproject.toml` or lockfiles. For those, `qa-auditor` runs
   `make mutate-changed` (fast, parallel), not a hand-written mutation loop. Print the reviewer list and why
   each was chosen.
3. **Review in parallel.** Spawn all routed reviewers in one message. Give each: the diff range
   (`origin/dev...HEAD`), the relevant spec(s) under `docs/specs/`, and the reviewer output contract.
4. **Consolidate.** Merge duplicate findings; keep the highest severity. Show the user the table.
5. **Fix and re-review.** Fix **every Must and every Should** in this round (Nits too when cheap). Only work
   that genuinely can't be done yet becomes a `task-NNN`, with the reason stated. Commit, and re-run **only
   the reviewers whose paths the fixes touched** plus `code-reviewer` and `docs-reviewer`. Repeat until no Must or Should is open.
6. **Disposition everything.** Write the dispositions file (outside the repo, e.g. the scratchpad):
   every finding → `fixed <sha>` | `task-NNN` (create with `backlog task create`) | `rejected: <reason>`.
7. **Record.** `python3 .claude/scripts/record-review.py APPROVE <dispositions.md>` — add `--attest` if the
   PR already exists. If the script refuses, fix what it names; never hand-write a record.
8. Report: reviewers run, findings by severity with dispositions, the recorded sha, and the next command
   (`git push -u origin <branch>` then `/open-pr`).
