# The first gates passed every test and still let `git status;git push` through

**Key lesson:** A gate's test table proves nothing until each row is shown to fail against a deliberately broken gate. Parse commands the way bash does (unspaced separators, newlines, heredocs, prefixes, redirects), not with `shlex.split`.

- **Date:** 2026-09-25 · **Task:** n/a (M0 tooling, first `/review-gate` round on `chore/claude-tooling`) · **Area:** tooling
- **Artifacts:** `.claude/hooks/lib/cmdparse.py`, `.claude/hooks/{require-review,block-ai-attribution,protect-data-dir}.sh`,
  `.claude/scripts/record-review.py`, `.claude/hooks/tests/test-openproceedings-gates.sh` (39 → 103 rows)

## What we set out to do
Run the new review gate on its own tooling: five routed reviewers (code, security, QA, docs, methodology).

## What we learned
- **`shlex.split` is not a shell parser.** It sees `;`/`&&` only when spaces surround them, and treats a
  newline as a space. So `git status;git push`, `git add -A⏎git push`, `FOO=1 git push`, `(git push)` and
  `git commit -am "…Co-Authored-By: Claude"` all got through. That was 29 of the 37 probes QA wrote. The
  fix is `shlex.shlex(punctuation_chars=";&|()\n<>")` with newline as a separator, plus stripping heredoc
  bodies, `VAR=`/`env`/`command`/`time` prefixes and redirects (`2>&1` made `2` and `1` look like refspecs
  and blocked legitimate pushes).
- **For content gates, scan the raw text, not the flags.** Pulling out `-m` values missed `-am`, `-qm`,
  `--trailer` and `-F - <<EOF`. Scanning the whole command whenever a message-writing command is present
  closes the whole class.
- **Every hand-parsed format needs a "strict or refuse" rule.** `record-review.py` counted `- [must]` only,
  so `- [Must]`, indented and `*` bullets were silently skipped, and APPROVE was recorded with three
  undispositioned must-fixes. Any line containing a severity tag must now parse, or the script refuses.
- **Mutation testing found holes the green table hid.** Breaking `cd` tracking, or `-C` resolution,
  changed *no* test result, because the rows named a branch that resolves from any directory. The rows now
  push `HEAD` from an approved checkout into an unapproved worktree. All 8 mutations are caught, and the old
  hooks fail 38 of the new rows.
- **The methodology review found real PRISMA flaws that no code review would.** Defaults are recognised
  by origin, so pasting a canonical string back in loses the exclusion counts. The methods text cited a
  string that doesn't reproduce "identified". Spec 02/03/04/05 now recognise defaults by content and
  define `identification_query`.

## Dead ends — don't repeat these
- Don't trust a gate table that has only been run against the implementation it was written for. Run it
  against mutants (`git archive` the hooks into a temp dir, break one line, run the table).
- Don't hand-keep a roster in a spec. Spec 08's "Commands (18)" listed 15. The list is now generated
  (`.claude/scripts/roster_index.py` → `.claude/README.md`) and CI checks it's current.

## Decisions (and what would change them)
- The attribution scan over-blocks a commit message that merely *mentions* "Co-Authored-By: Claude"
  (rejected nit: false positives are rare, and a missed trailer is the worse failure).
- `review-attested` is documented as an honesty check, not access control (spec 08 §CI).

## Follow-ups
- [ ] task-001 and the rest: open M1 semantic decisions remain tracked in Backlog.

## Propagated to
- `.claude/agents/qa-auditor.md` (mutation-test gate tables), `.claude/skills/review-gates/SKILL.md`
  (hooks, scripts and CI are now routed to `qa-auditor` too), `.claude/hooks/lib/cmdparse.py` docstring.
- Test rows: every finding from this round is a row in `test-openproceedings-gates.sh`.

## Addendum — 2026-09-25 (review round 2)

- **Git exports `GIT_DIR` into hooks run from a linked worktree.** The pre-push hook ran the case tables with
  it still set, so their throwaway `git init --bare` / `git -C` calls hit the *real* repo (`core.bare=true`,
  stray branches). Every hook and test script now clears repo-local git variables first
  (`unset $(git rev-parse --local-env-vars)`).
- **A row blocked by two barriers proves neither.** The `--base '--upload-pack=…'` injection row stayed
  green with validation deleted, because an unreviewed HEAD blocked first, and the explicit fetch refspec
  also neutralised it. Each row must isolate one barrier (here: approved HEAD + `--label no-learning`, so
  validation is the only thing left).
- **"Fails for the wrong reason" looks like coverage.** Tooling rows expected an error that a *stale index*
  produced anyway. The check they claimed to test could be deleted with no effect. These rows now regenerate
  the index first, so only the rule under test can fail.
- **Result:** 72 mutants across the four tables; 71 are killed. The survivor (redirect tokens left in the PR
  gate's token stream) is equivalent: redirect targets are never compared as refs, so no input tells the
  versions apart. Runner: parallel mutation script, one mutant per piece of logic, a baseline copy first.
- **Wrong-shaped command parsing kept recurring** (whitespace-only, then keywords, then wrappers, then
  process substitution). Parse like bash from the start: separators, reserved words, per-wrapper option
  tables, basenames, quote- and comment-aware heredocs.

## Addendum — 2026-09-25 (review round 3)

- **My round-2 fix introduced two regressions.** Comment stripping reset quote state on every line, so a
  commit message line `Closes #12` was "commented out". Quote blanking hid `<<'EOF'` delimiters. Both
  crashed the parser, and the gates then **failed open**. Fixes: one `preprocess` pass that carries quote
  state across lines and treats heredoc bodies as opaque, and every gate now **fails closed** on a parse
  error.
- **Fail-closed hides regressions from block rows.** Once a crash blocks, every "should block" row still
  passes when the parser breaks. Parser changes need **allow rows on approved work** (an approved push
  after a `#12` message line), which a crash would fail.
- **Delete code a mutant proves inert, rather than keeping it.** `glob_base` became redundant once globs
  are expanded (an unmatched glob deletes nothing), and the loop-header check never changed an outcome.
  Both were removed along with their mutants. Genuinely equivalent mutants stay, documented
  (`diff.renames` defaults to true).
- **Replace code by AST, not by slicing between function names.** A slice-based rewrite of `cmdparse.py`
  silently dropped `ParseError`, `read_payload` and `ASSIGNMENT`. An AST name diff against HEAD caught it.
- **Speed:** a hand-rolled serial mutation loop took about 40 minutes of review time. The committed parallel
  runner (`make mutate`, `mutate-changed`, `--match`) does the full set in minutes and a targeted re-check
  in seconds. `make tooling` now runs its tables in parallel (about 15 s). Reviews use `mutate-changed`;
  the nightly workflow runs everything.
