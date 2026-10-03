---
description: Bring documentation to as-built after a behaviour change — README, CONTRIBUTING, CLI/API usage, plans, as-built spec notes — verified by running the commands, via the docs-writer agent
argument-hint: "(optional) the files or topic to document; default: whatever the current branch changed"
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, Task
---

Spawn `.claude/agents/docs-writer.md` for: $ARGUMENTS — or, if empty, the user-visible changes on this
branch (`git diff --name-only origin/dev...HEAD`).

It must:
1. List the behaviour that changed (CLI flags, endpoints, defaults, response fields, setup steps).
2. Run every command it documents (`uv run op <cmd> --help`, fixture-index searches, `uv sync`,
   `npm run dev`) and check every path with `ls`; anything it cannot run is written as
   "verify at implementation time: …".
3. Take every number from a dated `docs/results/` file, with a link.
4. Keep guarantee wording identical to `docs/specs/00-overview.md`; touch `docs/specs/` only as part of a
   spec PR, keeping the status line and depends-on/consumed-by accurate
   (`.claude/skills/spec-writing/SKILL.md`).
5. Use roles, not names; `.env.example`, never real credentials; no AI-attribution text.

Then spawn `.claude/agents/docs-reviewer.md` on the files it changed and fix every Must before
reporting. Report the files changed with a one-line why, the verification commands run, the reviewer
verdict, and the reminder that `/record-learnings` and `/review-gate` still close the task.
