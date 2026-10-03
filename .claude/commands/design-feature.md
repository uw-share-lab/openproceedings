---
description: Design a frontend feature before it is built — ux-designer writes the design doc (flow, every state, wireframes, interaction spec), then hci-researcher checks it against verified evidence and usability-auditor runs a pre-implementation heuristic pass; outputs the design doc path
argument-hint: "the feature or Backlog task, e.g. 'task-031 drift diff view on /record/[id]' or 'zero-results state for /search'"
allowed-tools: Read, Grep, Glob, Bash, Task
---

Design the feature **$ARGUMENTS** before any implementation. If the argument is empty, ask which feature
or Backlog task. Don't guess.

1. **Context.** If a Backlog id is given, `backlog task view <id> --plain`. List existing designs
   (`ls docs/design/`), research (`docs/research/`) and usability reports (`docs/usability/`) that touch the
   same flow. Pass their paths on.
2. **Design.** Spawn `.claude/agents/ux-designer.md` with the feature, the Backlog task, the related docs and
   `docs/specs/05-frontend.md`. It writes `docs/design/<YYYY-MM-DD>-<feature>.md` from the template in
   `.claude/skills/ux-design/SKILL.md`, with every row of the states table designed and the API fields
   listed.
3. **Check, in parallel (one message)**, both given the design doc path:
   - `.claude/agents/hci-researcher.md`: extract the claims the design rests on and check each against
     sources it actually opens (`.claude/skills/hci-methods/SKILL.md` verified-citation rule). It fills
     the doc's Evidence section and proposes a study where evidence is missing (with the ethics status).
   - `.claude/agents/usability-auditor.md`: heuristic pass and cognitive walkthrough of the wireframes
     per `.claude/skills/heuristic-evaluation/SKILL.md`, with reviewer output contract. It is read-only,
     so it returns findings for you to fold into the doc's Heuristic pass section.
4. **Revise.** Send severity 3–4 findings and "unsupported" evidence verdicts back to `ux-designer` for a
   revision. Re-run only the checker whose concern was touched. Stop when no severity 3–4 finding is open.
   Record every other finding in the doc as fixed, a Backlog task, or rejected with a reason.
5. **Report:** the design doc path, the states covered, the evidence verdicts, the heuristic findings with
   dispositions, API gaps (as Backlog ids for `.claude/agents/api-engineer.md`), open questions, and the
   handoff to `.claude/agents/frontend-engineer.md`.

This command writes a design doc only. It doesn't implement, and it doesn't record a review approval. The
doc is committed on a branch and goes through `/review-gate` (`docs-reviewer`) like any `docs/**` change,
with `/record-learnings` first.
