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
  logged its end), the interrupt rows wait up to 60 s for the table to start and time from the signal, the hung-once
  row runs in a copy of the fixture whose floor is 5 s with no explicit timeout to refuse, and the hang row runs in a
  copy whose floor is 120 s with `--table-timeout 30` (refused only past a 3 s baseline), bounded to [55 s, 200 s):
  about 60 s honoured, 240 s or more if the flag were ignored or raised to the floor, a margin load can't close
  (review rounds 1 and 2: `--table-timeout 15` with a 90 s bound was still refusable on a loaded machine, and the
  5 s-floor version no longer showed an explicit timeout under the floor being honoured).
- The xargs mutant survived because the only sh -c row pushed `"$@"`, an unresolved refspec that is refused with or
  without the flag. A commit on a feature branch is allowed unless `via_xargs` is set, so it isolates the flag
  (evidence: probe_hook.py on a mutant copy: enforce-pr-workflow allow; on the real hooks: block).
- `flock <file> -c '<cmd>'` is easiest to read as `sh -c '<cmd>'`: rewriting the argv lets the walk's child-shell
  branch handle separators, exports and xargs inside it, instead of splitting the string like `env -S`.
- Stripping a wrapper drops its words from what the gates read, and some of those words are paths the wrapper writes.
  flock creates its lock file, so skipping it hid `flock .git/op-reviews/<sha> true` from require-review's record
  check, which blocked it while `flock` was an unknown command word (security review, round 1: a regression). The walk
  now yields each such file as a `>>` redirect of an empty command of its own (`Argv.creates`), in the directory flock
  ran in, so every gate's redirect rules apply, and `flock data/snapshots/x.lock` and `flock backlog/…` are refused
  too. Attaching it to the command flock runs was not enough: the walk reads `eval` and `cd` itself and yields
  neither, so `flock .git/op-reviews/<sha> eval true` still passed (round 2). When adding a wrapper, ask what it
  opens, and yield that on its own.
- A wrapper's value-taking options need the tool's whole usage line: doas's `-a style` was missed at first, so
  `doas -a passwd git push` hid the push (code-reviewer and qa-auditor, round 1), and so was arch's `-e`: one
  `-e A=1` passed only because `A=1` looks like an assignment, and a second `-e` became the command word (round 2).
- enforce-pr-workflow already refused most wrapper-prefixed commits on main before the change (only the flock `-c`
  rows were red there); require-review, protect-data-dir and block-ai-attribution's `-F` file read all missed them.

## Dead ends — don't repeat these
- A mutant that deletes a block's only line (`out.creates.append(…)` under an `if`) doesn't compile; every hook
  then crashes and every table "kills" it for the wrong reason (round 3). Give such a mutant a `pass` body, and
  compile-check new mutants before running them.
- Measuring a "stopped early" bound from the start of a nested mutate.py run: under load the baseline alone can take
  longer than the bound. Measure from the event, or check the log for what didn't happen.

## Decisions (and what would change them)
- `arch -e NAME=value` takes a value, recorded as an assignment for what arch runs (as `env NAME=value` is), so
  `arch -e GIT_DIR=… git commit` is judged against that repository; `arch -d NAME` unsets it, as `env -u` does
  (round 3).
- `flock 9` (one numeric word, nothing after it) locks a file descriptor and creates nothing; with a command after
  it, util-linux reads the word as a file name, so it is a created file.
- `xcrun -f` and `doas -C` only find or check a tool; cmdparse still reads what follows as the command it runs. That is
  the conservative side for every gate.

## Follow-ups
- [ ] A short-option cluster that ends in a value-taking option (`flock -nw 5 <file>`, `doas -nu root`, the older
  `sudo -nu root`) is not split by `_strip_prefixes`, so its value is read as the command (pre-existing in the shared
  option loop; reported to the lead as a follow-up).
- [ ] Other tables that exercise one script (test-mutate-shard.sh: mutate.py; test-merge-group-gate.sh; test-changelog.sh)
  could declare `# mutate-scope:` too (reported to the lead; not filed from this branch).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/testing-standards/SKILL.md` §Mutation testing, spec 08 §Mutation testing and the cmdparse wrapper list
- Test or hook added? — `.claude/scripts/tests/test-mutate-run.sh` (scope rows), 5 mutants in `mutants/mutate.json`, 22 in `mutants/gates.json`
