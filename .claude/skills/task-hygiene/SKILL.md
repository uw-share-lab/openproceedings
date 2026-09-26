---
name: task-hygiene
description: The standing rule that Backlog tasks, docs, specs, READMEs and every other .md are updated continuously as work happens — not at the end — and that a finished task is moved to backlog/completed/ with `backlog task complete`. Covers what "update" means per artifact, when in the session each update happens, and the CI checks that enforce it. Use at the start, during, and at the close of any task, and whenever a reviewer asks whether docs are as-built.
---

# Task and docs hygiene (project rule, 2026-09-25)

**Rule:** the repo describes itself truthfully *at every commit*. Tasks, docs, specs, READMEs and `.md`
files change **in the same commit** as the behaviour they describe. Nothing is batched up for "later". And
a task that is Done does not stay in `backlog/tasks/`.

## Tasks (Backlog.md, CLI only)
| When | Do |
|---|---|
| Starting work | `backlog task edit <id> -s "In Progress" -a @<you>`; add a plan (`--plan`) |
| As you go | Tick acceptance criteria as each is met (`--check-ac <n>`); add notes (`--append-notes`; `--notes` replaces them) when you learn something that changes the plan; create a new task for any follow-up **when you find it** |
| Scope changes | Edit the description/ACs so they match what you're actually doing; a stale AC is a lie |
| Done | All ACs checked → `backlog task edit <id> -s Done --final-summary "…"` → **`backlog task complete <id>`**, which moves it into `backlog/completed/` |

`backlog task complete` is the only way a task leaves `backlog/tasks/`. Never move files by hand: editor
writes under `backlog/` are blocked by `enforce-backlog-cli.sh`, Bash `mv`/`git mv`/`rm` of files under
`backlog/` are blocked by `protect-data-dir.sh`, and CI's `check_backlog.py` catches a Done task left
behind in `tasks/`. Archive (`backlog task archive`) is only for tasks that were dropped
unfinished. Give the reason in the notes first.

## Docs, specs, READMEs, every `.md`
| You changed… | Update in the same commit |
|---|---|
| Behaviour, a CLI flag, an endpoint, a file layout | The spec section that defines it (`docs/specs/`), plus any README or skill that describes it |
| A convention or gate | `CLAUDE.md`, `CONTRIBUTING.md`, the owning skill, and the hook's comment and case table |
| An agent, skill or command | Its frontmatter, then `python3 .claude/scripts/roster_index.py` (regenerates `.claude/README.md`) |
| Anything a new contributor would trip on | `README.md` / `CONTRIBUTING.md` |
| A lesson | `.claude/learnings/` via `/record-learnings` |

"As-built" means grep-verifiable: every path, command, flag and name a doc mentions exists and behaves as
described. `docs-reviewer` is routed on **every** diff (`.claude/skills/review-gates/SKILL.md`) to check
exactly this, and a stale doc is a **Should** at minimum (**Must** if it would send someone the wrong way).

## Enforcement
- **CI `claude-tooling`:**
  - fails if any task file in `backlog/tasks/` has `status: Done` (it should have been completed;
    `.claude/scripts/check_backlog.py`);
  - fails if `.claude/README.md` or `.claude/learnings/INDEX.md` is stale;
  - fails if the roster lint finds any reference to a missing agent, skill or command.
- **`/review-gate`:** `docs-reviewer` always runs.
- **Closing workflow** (`CLAUDE.md`): step 2 (Backlog) and step 3 (docs) come before the learning and the review.

## Anti-patterns
- "I'll update the docs in a follow-up PR." No. The PR that changes behaviour changes its docs.
- Leaving a task In Progress after the PR merges. Complete it before the PR is opened. Its final summary
  is part of what gets reviewed.
- A Done task left in `tasks/`. CI rejects it. Run `backlog task complete <id>`.
