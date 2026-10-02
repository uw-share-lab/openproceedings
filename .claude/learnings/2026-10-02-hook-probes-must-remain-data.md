# A hook probe can execute before the hook sees it

**Key lesson:** Feed hostile hook probes from a file or one safely quoted argument to probe_hook.py, and lint the case tables so shell expansions cannot execute the probe before the hook checks it.

- **Date:** 2026-10-02 · **Task:** TASK-169, TASK-164, TASK-170, TASK-172, TASK-173 · **Area:** tooling
- **Artifacts:** [TASK-169](../../backlog/completed/task-169%20-%20Hook-test-harness-hostile-probes-stay-data-never-reach-an-executed-shell-2026-10-02-incident.md), [probe helper](../scripts/probe_hook.py), [probe lint](../scripts/lint_probes.py), [boundary tests](../hooks/tests/test-parser-boundaries.sh)

## What we set out to do

Recover the interrupted gate hardening and finish the follow-ups from TASK-156 without executing any hostile probe.

## What we learned

- TASK-169 records the 2026-10-02 incident: a reviewer's probe heredoc closed early and its `rm -rf data` ran in the home directory. A guard's correct verdict cannot protect a probe that the test harness executes first. The helper reads probe data and feeds hook JSON or cmdparse directly. Its explicit sandbox mode gives intentional execution a temporary HOME and working directory.
- Double-quoted or unquoted command substitutions and backquotes can run while constructing a case-table argument. The lint checks both payload calls and row labels/commands; its fixtures include nested wrappers, escaped quotes and ANSI-C quoting. Safe payload wrappers remain allowed.
- Scanning sed's input files alone misses script files that print attribution. Five recovery regression rows failed before `reader_files` scanned separate and attached `-f`/`--file` values, including an unresolved value. A later safe JSON probe found `-nfFILE` still skipped the script; the reader now follows bundled short flags through their first `e`/`f`, whose value consumes the rest of the bundle, and refuses unfamiliar bundles. Round1 review found `--` termination also matters: leading-dash input filenames must be scanned literally after options end, while sed still consumes its implicit expression when no `-e`/`-f` supplied one.
- A fail-closed fallback can mask a broken parser branch. Exact joined-text checks distinguish two heredoc delimiter mutants that the older block/allow rows did not kill. The same boundary table exercises the production case-folded root comparison independently of whether the host filesystem folds case.

## Dead ends — don't repeat these

- Never put a hostile probe into an executable shell heredoc or interpolate it into shell command text. Use the helper's file input or a single quoted argument.
- Do not infer that a parser branch is covered solely because a gate still blocks its probe. Mutate it and check a distinguishing output.

## Decisions (and what would change them)

- Keep shell case tables but require their probes to remain data, with a lint in `make tooling`. Existing table conventions and the helper make this enforceable without executing probes.
- Keep the filesystem APFS coverage and add a deterministic production-function boundary check so Linux also kills the worktree comparison mutant.

## Follow-ups

None identified within these five tasks. Independent review of the exact committed version follows the recovery handoff.

## Propagated to

- [security-reviewer](../agents/security-reviewer.md), [qa-auditor](../agents/qa-auditor.md), [review-gates](../skills/review-gates/SKILL.md), [CLAUDE.md](../../CLAUDE.md), and [spec 08](../../docs/specs/08-ops-and-tooling.md).
- `make tooling` runs the probe lint and boundary table; `.claude/scripts/mutants/gates.json` breaks their guarded branches.
