---
description: Plan a usability study of a named openproceedings flow — usability-tester writes the study plan and task script from real review tasks (with metrics, success criteria and the ethics-clearance status), optionally with user-researcher for the recruitment screener
argument-hint: "the flow to study, optionally '+recruit', e.g. 'exclusion banner and export' or 'search-record replay +recruit'"
allowed-tools: Read, Grep, Glob, Bash, Task
---

Plan a usability study of: **$ARGUMENTS**. If empty, ask which flow. Don't guess.

**Ethics reminder, printed first in the report:** no session with any participant (lab members outside
the core team included) runs until the University of Waterloo Office of Research Ethics has cleared the
protocol. Whether an activity is exempt is the Office's decision, not ours. Participant data (recordings,
notes, screener answers, the code-to-identity key) never goes into this public repo. It stays in lab
storage or `data/research/` (gitignored). See `.claude/skills/hci-methods/SKILL.md`.

1. **Scope.** Map the flow to spec 05 sections and existing material: designs in `docs/design/`, past
   studies in `docs/usability/`, research in `docs/research/`.
2. **Plan.** Spawn `.claude/agents/usability-tester.md` with the flow and those paths. It writes
   `docs/usability/<YYYY-MM-DD>-<flow>/plan.md` from `.claude/skills/usability-testing/SKILL.md`: the
   decision the study informs, personas, tasks drawn from the task bank and the real Trust-Evals strings in
   `backend/tests/fixtures/`, a success criterion per task checkable against the API, metrics (success,
   time, errors, SEQ, SUS or UMUX-Lite), the fixture environment, the pilot step, the data-handling plan, and
   `Ethics: not submitted`.
3. **Recruitment (only if `+recruit` is in the arguments).** In parallel, spawn
   `.claude/agents/user-researcher.md` to write the screener and recruitment text per
   `.claude/skills/user-research/SKILL.md`: persona quotas, role and experience questions, no names in any
   committed file. It appends them to the same plan.
4. **Check** the plan before reporting. Every task is a goal, not an instruction. No task names the
   control or the syntax that solves it. Every criterion is measurable. The sample size follows the
   skill's guidance per persona, with its caveats stated.
5. **Report:** the plan path, the ethics reminder, the task table (goal → success criterion), the metrics, the
   participants per persona, and the next steps (submit to the Office of Research Ethics, pilot, run, and then
   `usability-tester` writes `report.md` and files Backlog tasks for severity ≥2 findings).

This command plans only. It runs no sessions. The plan is committed on a branch and goes through
`/review-gate` (`docs-reviewer`) after `/record-learnings`.
