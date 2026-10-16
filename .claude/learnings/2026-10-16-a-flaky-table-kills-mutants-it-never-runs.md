# A flaky case table kills mutants of files it never runs

**Key lesson:** mutate.py counts any failing table as a kill, so a table that exercises only some files declares them with `# mutate-scope:` in its header, and its timing checks are bounded by the sleeps they tell apart, never by how fast a loaded machine starts a run.

- **Date:** 2026-10-16 · **Task:** task-238, task-248, task-249 · **Area:** tooling
- **Artifacts:** `.claude/scripts/mutate.py` (`table_scope`, `can_kill`), `.claude/scripts/tests/test-mutate-run.sh`,
  `.claude/hooks/lib/cmdparse.py` (`WRAPPER_VALUE_OPTS`, the flock branch of `_strip_prefixes`),
  `.claude/hooks/tests/test-enforce-pr-workflow.sh`, `.claude/hooks/tests/test-openproceedings-gates.sh` (TASK-248 rows)

## What we set out to do
Make `test-mutate-run.sh` pass under load and never credit itself with another file's mutant (TASK-238); strip six
more command wrappers in cmdparse (TASK-248); kill the surviving "xargs flag not carried into sh -c" mutant (TASK-249).

## What we learned
- A table that fails for a reason unrelated to the mutant is indistinguishable, to mutate.py, from a kill. The
  fixture `t-flaky.sh` (fails in every mutant's copy, passes in the baseline) reproduced the TASK-238 report at once:
  before the scope rule it was credited with m-survives, m-once, m-slow, m-unexercised and others (13 rows red).
  Declaring what a table exercises, and running it only for those files' mutants, makes such a credit impossible in
  the direction that matters: a wrong declaration can only leave a mutant SURVIVED, which the run reports as a problem.
- The scope must come from the table's header only. `test-mutate-run.sh` writes fixture tables with heredocs whose
  first line is `# mutate-scope: src/scoped.txt`; a whole-file scan would read that as the table's own declaration
  (row "this table declares mutate.py only").
- The load-sensitive checks were wall-clock bounds measured from the start of a run (`secs -lt 15` for "stopped",
  10 s to see a table start before an interrupt) and `--table-timeout 5`, which mutate.py refuses (exit 2) once a tiny
  table's baseline passes 0.5 s on a loaded machine. Now: the "stopped" check is the log (the slow table never
  logged its end), the interrupt rows wait up to 60 s for the table to start and time from the signal, the hang row
  uses `--table-timeout 15` with a 90 s bound (still far from the 60 s floor twice and from the 3017 s sleep), and the
  hung-once row runs in a copy of the fixture whose floor is 5 s, with no explicit timeout to refuse.
- The xargs mutant survived because the only sh -c row pushed `"$@"`, an unresolved refspec that is refused with or
  without the flag. A commit on a feature branch is allowed unless `via_xargs` is set, so it isolates the flag
  (evidence: probe_hook.py on a mutant copy: enforce-pr-workflow allow; on the real hooks: block).
- `flock <file> -c '<cmd>'` is easiest to read as `sh -c '<cmd>'`: rewriting the argv lets the walk's child-shell
  branch handle separators, exports and xargs inside it, instead of splitting the string like `env -S`.
- enforce-pr-workflow already refused most wrapper-prefixed commits on main before the change (only the flock `-c`
  rows were red there); require-review, protect-data-dir and block-ai-attribution's `-F` file read all missed them.

## Dead ends — don't repeat these
- Measuring a "stopped early" bound from the start of a nested mutate.py run: under load the baseline alone can take
  longer than the bound. Measure from the event, or check the log for what didn't happen.

## Decisions (and what would change them)
- `arch -e NAME=value` is not a value-taking option: the next word is an assignment, which `_strip_prefixes` already
  strips and records. If arch ever takes a value that isn't `NAME=value`, add `-e` to its set.
- `xcrun -f` and `doas -C` only find or check a tool; cmdparse still reads what follows as the command it runs. That is
  the conservative side for every gate.

## Follow-ups
- [ ] Other tables that exercise one script (test-mutate-shard.sh: mutate.py; test-merge-group-gate.sh; test-changelog.sh)
  could declare `# mutate-scope:` too (reported to the lead; not filed from this branch).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/testing-standards/SKILL.md` §Mutation testing, spec 08 §Mutation testing and the cmdparse wrapper list
- Test or hook added? — `.claude/scripts/tests/test-mutate-run.sh` (scope rows), 4 mutants in `mutants/mutate.json`, 14 in `mutants/gates.json`
