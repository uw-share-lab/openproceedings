---
description: Review documentation, specs or .claude/ markdown for accuracy against the code, staleness, broken links, unsourced numbers, guarantee-wording drift and spec house format, via the docs-reviewer agent
argument-hint: "(optional) files or a directory, e.g. docs/specs/03-search-engine.md; default: docs changed on this branch"
allowed-tools: Read, Grep, Glob, Bash, Task
---

Spawn `.claude/agents/docs-reviewer.md` on `$ARGUMENTS` — or, if empty, on
`git diff --name-only origin/dev...HEAD -- '*.md' docs/ .claude/`.

If any target is under `docs/specs/`, also spawn `.claude/agents/review-methodologist.md` in the same
message: a spec change is a methods change for every review that cites it.

The docs-reviewer must verify against reality, not by reading alone: `ls` each path, `uv run op <cmd>
--help` for each documented command, grep the routers and pydantic models for each endpoint and field,
confirm each number appears in the dated `docs/results/` file it cites, and run
`python3 .claude/scripts/lint_tooling.py` when `.claude/` markdown changed.

Report consolidated findings in the `.claude/skills/review-gates/SKILL.md` contract — Must / Should /
Nit, `file:line — problem — fix`, with the command whose output disproved the doc — and one verdict per
reviewer (**APPROVE** / **REQUEST CHANGES**).
