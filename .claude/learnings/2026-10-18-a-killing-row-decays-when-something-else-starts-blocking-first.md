# A killing row decays when later work makes something else block first, or when its fixture differs by OS

**Key lesson:** When the nightly reports a survivor, apply that one mutant and run its table on the reporting OS before trusting the old row. Write each killing row so that only the check under test can block it: use a fallback name that can never become known, give it well-formed and present harmless inputs, and keep paths inside the table's own root.

- **Date:** 2026-10-18 · **Task:** task-261 · **Area:** tooling
- **Artifacts:** `.claude/hooks/enforce-pr-workflow.sh` (`git_calls`' docstring example), `.claude/hooks/tests/test-enforce-pr-workflow.sh` (the `unknown-wrapper` rows), `.claude/hooks/tests/test-openproceedings-gates.sh` (the TASK-261 rows), `.claude/skills/testing-standards/SKILL.md` §Mutation testing; nightly runs 38736208920, 38900169100, 39029318530

## What we set out to do
Make the scheduled nightly green for the v0.4.0 release. It had been red since 2026-10-15 in its `mutate` shards
only, with nine survivors in the hook gates.

## What we learned
- **A made-up case can become a real one.** Four PR-gate mutants in `git_calls` (the git word read behind a wrapper
  the walk doesn't know) survived from 2026-10-17. Their rows used `caffeinate`, and TASK-248 (#158) added
  `caffeinate` to `WRAPPER_VALUE_OPTS`, so the walk unwrapped it and the fallback was never reached. The evidence:
  all four survived locally on the unchanged table, and all four are killed by rows behind `unknown-wrapper`.
- **A newer fail-closed check can block a probe for its own reason.** Three survivors were rows that still blocked,
  but not because of the check they were written for:
  - `HOOK_INPUT='{}'`: TASK-244's `guard_payload` refuses `{}` as malformed, so a mutant that reads the
    environment variable blocks too. A well-formed harmless payload (`true`) in `HOOK_INPUT` tells the two
    readings apart.
  - `cd ~ && git commit -F op-msg.txt`: with the real HOME the first reading looks for the file in HOME, where it
    is missing, and since TASK-243 a missing message file is refused. That refusal comes first, so the row passed
    without the HOME '' reading. A HOME that holds a clean `op-msg.txt` leaves the trailer to the HOME '' reading
    alone.
  - Glob expansion: an unexpanded glob that matches a trailer file is unreadable, and refused either way. Only a
    glob that matches a clean file is allowed when expanded and refused when not.
- **A fixture can differ by OS.** `pdd: find checks only its first start` was killed on macOS and survived on CI.
  The row was `find /tmp . -delete` in a `mktemp -d` root, which is under `/var/folders` on macOS but under `/tmp`
  on Linux. On Linux the first start already covered the root. `find src .` uses a start inside the root on both
  systems. The same held for `ls | xargs mv -t /tmp`, now `mv -t frontend`, which was blocked on Linux by the
  immutable-ancestor check rather than the xargs check it was written for.
- **Two walks need a probe whose walks really differ.** `TASK-243: the two walks compared as one` needs a write
  that only the HOME '' walk makes. `cd ~; printf … > op-243w.md; gh … --body-file "$REPO/op-243w.md"` writes the
  file only where `cd ~` stays put. The first walk must still refuse the missing file; the mutant borrows the
  other walk's write and allows it.

## Dead ends — don't repeat these
- Re-running a red nightly. The same mutants survived every night (deterministic, no shard timeouts), as the
  2026-10-11 learning warned.
- Trusting that a row still kills a mutant because its label or comment names it. Most of the nine had a row written for them.

## Decisions (and what would change them)
- Keep the `caffeinate` rows as regression rows: they can't tell the walk's unwrapping from `git_calls`' fallback,
  and the known-wrapper mutants are killed by the TASK-248 rows. Add `unknown-wrapper` rows for the fallback. This
  would change only if `git_calls`' fallback were removed.
- Row verdicts (exit 2 or 0) are the assertion. The tables don't match stderr, and each new row's other inputs
  are made harmless so that only the check under test decides the verdict.

## Follow-ups
- [ ] none filed by this branch

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/testing-standards/SKILL.md` §Mutation testing (how a killing row decays, and three rules)
- Test or hook added? — the TASK-261 rows in `test-enforce-pr-workflow.sh` and `test-openproceedings-gates.sh`
