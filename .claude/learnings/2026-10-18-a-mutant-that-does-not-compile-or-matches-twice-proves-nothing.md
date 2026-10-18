# A mutant that doesn't compile, or whose old text matches twice, proves nothing

**Key lesson:** Vet a mutant before crediting a kill: its `old` text must occur exactly once in each file and its edit must leave the file compiling (`mutate.py --check`, in `make tooling`); and read a wrapper's options as its getopt does (groups, attached values, unique long prefixes) or refuse the command, since one misplaced value word becomes the command.

- **Date:** 2026-10-18 · **Task:** task-253, task-254 · **Area:** tooling
- **Artifacts:** `.claude/scripts/mutate.py` (`vet`, `breaks_compile`, `check_scopes`, `--check`), `.claude/hooks/lib/cmdparse.py` (`GETOPT_WRAPPERS`, `_getopt`, `Argv.chdir`, `_anchor`), `.claude/hooks/protect-data-dir.sh` (`mv_operands`), `.claude/scripts/tests/test-mutate-run.sh`, `.claude/hooks/tests/test-openproceedings-gates.sh` and `test-enforce-pr-workflow.sh` (TASK-253 sections)

## What we set out to do
Close three older cmdparse gaps (grouped wrapper options, `env -C` moving every later command, `sh -c`/`eval` dropping their redirects) and the mv `-t` misread, and make mutate.py refuse mutants that can't be run as written.

## What we learned
- Compiling every mutant found five uncompilable ones, not the two TASK-254 listed: `PR gate: xargs verdict dropped` (`pass, branch` left behind), `pdd: perl read like sed` and `ruby -i not in place` (a stray `    ` indented the next `if`), plus the two known. Each had been "killed" by any table that ran the hook, on the compile error alone (evidence: the branch's `mutate.py --check` run on origin/dev's `mutants/*.json`: 18 FAIL, 12 AMBIGUOUS, 5 UNCOMPILABLE and 1 STALE, the one this branch's own mutate.py edit made).
- An ambiguous mutant's first occurrence is not always the one its label meant; `git log -S'<label>' -- .claude/scripts/mutants/gates.json` and the hook at that commit show which line it was written for (`dd branch removed` was the immutable `of=` check, now the second of three matches).
- Compiling 1,650 mutants serially took 14 s, half of it recompiling the unmutated files; caching the originals and a process pool brought `--check` to about 2-3 s, cheap enough for `make tooling`.
- A table's scope must list everything it reads, not only the script it is named for: `test-merge-group-gate.sh`'s wiring row reads four workflows, and the `pr-gates.yml`, `lint.yml` and `test.yml` mutants are killed only there.
- `env -C dir cmd > f` writes `./f`, not `dir/f`: the shell opens the redirect before env changes directory, so moving the command's directory has to leave its redirects where the shell is (`_anchor`), or a write to `backlog/` reads as one to `/tmp/backlog/`.
- Getopt reading has to stop where getopt stops: in GNU mv's `-St DIR`, the `t` is `-S`'s suffix and `DIR` is still
  a source (review round 1 found `mv -St ../repo ../moved` allowed), every word after `--` is an operand, `nice --5`
  and `nice -+5` are nice's old adjustment form, and `env -a ARG` exists in coreutils 9: an option missing from a
  table is a ParseError, which block-ai-attribution answers with a text-only scan.
- A short group ending in a value letter (`sudo -nu root git push`) read `root` as the command and hid the push from every gate; so did `flock --wai 5` (an unknown long option, so `5` was the lock file and the lock file the command).

## Dead ends — don't repeat these
- A python heredoc whose body contains its own delimiter (`<<'EOF'` inside a `<<'EOF'` script) ends early; zsh refused the whole call at parse time here, but bash would have run the rest. Write edit scripts with the Write tool and run them by path.
- `compile(..., flags=ast.PyCF_ONLY_AST)` is no faster than a full compile (9.5 ms against 7.4 ms on cmdparse.py), so it is no shortcut for `--check`; caching the originals is.

## Decisions (and what would change them)
- Unknown or ambiguous wrapper options, and any option after flock's lock file but `-c`/`--command`, are a ParseError (refused), not a guess → the hooks are guardrails and a wrong guess hides a command → reversed only if a common real command trips it.
- Interpreter programs (`python3 -c`, heredocs) writing under `backlog/` stay outside protect-data-dir's model → refusing every interpreter call naming a backlog path would refuse reads too → a second such edit in review would justify a narrow rule.

## Follow-ups
None filed. The nightly mutation shards rerun every mutant against the new cmdparse loop; this branch ran its own
TASK-253/254 mutants and the rewritten ones by `--match`.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/testing-standards/SKILL.md` (unique old text, compiling new text), `.claude/skills/pr-workflow/SKILL.md` (claude-tooling runs `--check`), `docs/specs/08-ops-and-tooling.md` (§Mutation testing, the cmdparse list, `make tooling`)
- Test or hook added? — `mutate.py --check` in `make tooling` and the nightly; rows in `test-mutate-run.sh` and the gate tables' TASK-253 sections
