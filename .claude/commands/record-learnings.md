---
description: Write (or extend) the .claude/learnings/ entry for the task just completed — required before a PR
argument-hint: "(optional) the task topic or Backlog id, e.g. task-012 wildcard expansion"
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, Task
---

Spawn the **learning-recorder** agent (`.claude/agents/learning-recorder.md`) to record what this task
taught us. Topic (if given): $ARGUMENTS — otherwise the current branch's work.

It must:
1. Check `.claude/learnings/INDEX.md` first and **extend** an existing entry with a dated
   `## Addendum — YYYY-MM-DD` if the lesson is already there. That satisfies the PR gate: the hook and
   CI accept a modified entry as well as a new one.
2. Otherwise write `.claude/learnings/YYYY-MM-DD-<slug>.md` (directly in that folder; only that name counts)
   from `_TEMPLATE.md`, with every `<placeholder>` replaced, a standalone `**Key lesson:**` line and
   evidence for every lesson.
3. Fold behaviour-changing lessons into the owning skill/agent/CLAUDE.md and note it under "Propagated to".
4. Create Backlog tasks for follow-ups.
5. Regenerate the index (`python3 .claude/scripts/learnings_index.py`) and verify `--check` passes (it
   also rejects non-dates, leftover template `<placeholders>` and entries in subfolders).

Then commit the entry + INDEX.md (no AI attribution in the message) **before** running `/review-gate`.
Report the entry path and the key-lesson line.
