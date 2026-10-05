# Several agents on one machine need foreground test runs, their own scratch filenames, and one full suite at a time

**Key lesson:** When several agent sessions share a machine, run each long command in the foreground behind a loop that waits for the load to drop (a session that backgrounds its test run and waits to be told it finished can sit idle with its work uncommitted), name every scratch file after the task, never run two full suites at once (the load passed 100 and timed out Hypothesis and editor tests that were not broken), and when an automated scan's headline arrives without detail, audit the file it names instead of dismissing it.

- **Date:** 2026-10-05 · **Task:** n/a (the 2026-10-04/05 batch: TASK-056, TASK-175 to TASK-182) · **Area:** tooling
- **Artifacts:** `.claude/skills/pr-workflow/SKILL.md` §Several sessions on one machine, the batch branch `feat/review-comparison-tools`, commits af63f471 and 7d99504e (what the two scans led to)

## What we set out to do
Run a batch of tasks in parallel worktrees, one agent session per task, with a coordinating session merging
their branches.

## What we learned
- **A backgrounded run can end the work early.** One session started its full test run in the background
  behind a "wait until the load is under N, at most eight minutes" loop and stopped, expecting to be told when
  it finished. The load never dropped in the window, the loop wrote "skipped", and the fixes sat uncommitted
  for over an hour until the coordinator asked. In the foreground the same loop simply holds the session
  until the run has happened: `until [ "$(uptime | sed 's/.*load averages: \([0-9]*\).*/\1/')" -lt 30 ]; do sleep 20; done; make test > <scratch>/<task>-test.log 2>&1`.
- **Shared scratch names collide.** Two sessions wrote `test.log` in one scratch directory and one
  overwrote the other's. Name the file after the task (`t181-test.log`).
- **Two full suites at once fail tests that are not broken.** `make test` runs pytest under `-n auto` and
  Vitest with a worker per file; two of them together took the one-minute load past 100, and Hypothesis
  deadlines and the editor's tree tests failed
  ([the tree tests' own cause](2026-10-05-syntaxtree-reads-only-what-codemirror-parsed-within-its-time-budget.md);
  the `too_slow` one is [the cold Unicode cache](2026-10-01-hypothesis-too-slow-under-load-was-a-cold-unicode-cache.md)).
  The coordinator now gives the full suite to one session at a time; the others run the affected tests.
- **A fixed port reached the owner's running instance**: recorded in
  [the upload-refusal entry](2026-10-05-a-refusal-sent-before-an-upload-is-read-arrives-as-a-reset.md), not
  repeated here. The rule for sessions is the general one: nothing a session starts uses 8000 or 3000.
- **A scan's headline with no detail was right twice.** An automated scan named `search.py` and
  `api/compare.py` with one-line headlines and nothing to reproduce. Both pointed at a real class of issue:
  work in `search.py` that no bound charged (the group counts' verified ids, commit af63f471) and the order
  of checks on the disabled comparison route (commit 7d99504e pins the route's exceptions). Reading the whole
  file for that class of issue is what found them.
- **Agents in worktrees don't create Backlog ids** (already
  [recorded](2026-10-02-a-merge-queue-without-up-to-date-lets-two-prs-merge-one-backlog-id.md)): each reported
  its follow-ups and the coordinator filed them once, after the merges.

## Dead ends — don't repeat these
- Waiting on a notification for a command whose start depends on a condition that may never hold.
- Reading a failing property or editor test under load as a regression before rerunning it alone.
- Dismissing a finding because its report has no reproduction.

## Decisions (and what would change them)
- One full suite at a time, by the coordinator's word → the machine has one set of cores → would change with
  a second runner or a suite that bounds its own workers.

## Follow-ups
- Filed by the main session with the batch's follow-up tasks.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `pr-workflow` (§Several sessions on one machine).
- Test or hook added? — no: these are habits of a session, not of the code; the port rule is enforced by the
  e2e config's environment variables (the entry linked above).
