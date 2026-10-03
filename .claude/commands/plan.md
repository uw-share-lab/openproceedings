---
description: Turn a goal, epic, milestone or spec into a tracked Backlog.md plan — epics → child tasks with acceptance criteria mapped to spec sections, dependencies, milestones M0–M6, design docs and decisions — via the project-manager agent, using the backlog CLI only
argument-hint: "the goal, milestone or spec, e.g. 'M1', 'docs/specs/02-query-language.md', or 'add BibTeX export'"
allowed-tools: Read, Grep, Glob, Bash, Edit, Task
---

Plan **$ARGUMENTS** with `.claude/agents/project-manager.md`.

Give it: the goal as stated; the owning spec(s) under `docs/specs/` (resolve a milestone to its specs via
`docs/specs/00-overview.md` §Milestones); and the current board (`backlog task list --plain`,
`backlog milestone list`).

It must:
1. Read `backlog instructions overview` and `backlog instructions task-creation` first.
2. Search for existing tasks before creating any (`backlog search "<topic>" --plain`).
3. Create one epic per spec area and child tasks of ½–1 day with `backlog task create … -p <epic> -m <M>
   --ac "… (NN §Section)" --dep … --ref docs/specs/NN-….md`; guarantee-bearing criteria written out.
4. Record design detail with `backlog doc create`, and irreversible choices with
   `backlog decision create "<title>"` followed by editing only that decision's body
   (`.claude/skills/decision-records/SKILL.md`).
5. Never Write or Edit any other file under `backlog/` (`enforce-backlog-cli.sh` blocks it).

If the goal needs a spec that does not exist yet, stop and recommend `/new-spec <name>` first. Report
the created ids as epic → children with milestone and dependencies, spec sections left uncovered,
decisions opened, and the first task to start.
