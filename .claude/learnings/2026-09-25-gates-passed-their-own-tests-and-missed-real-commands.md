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

## Addendum — 2026-09-25 (review rounds 4–5)

- **A partial bash parser never converges edge case by edge case.** Rounds 4–5 found `$((1<<n))`,
  `$((cmd) | …)`, `<<E"OF"`, a heredoc body ending in `\`, and clustered `-fdxe…`, each one another place
  where the scan's model of the command diverged from bash's. The fix that ends that class is structural: if the
  scan ends inside arithmetic or a heredoc, or meets a delimiter it can't fully read, `preprocess` raises,
  and every gate treats the error as **block**. The specific fixes stay, but the net is what makes future
  misreads fail safe.
- **Advice in an error message is code.** The hook told users to "add -e data", and `git clean -X -e data`
  is exactly what deletes `data/`. Every suggestion a gate prints needs its own test row.
- **Layered defences need one isolating row per layer.** With paren tracking, delimiter checks and the
  end-of-input net all present, each mutant survived, because the other layers caught it. Each layer now has
  a row where it is the only barrier.
- **Test inputs with trailing whitespace must be built with `printf`.** Files lose trailing spaces, and the
  `'EOF '` row silently tested nothing until it was rebuilt that way.

## Addendum — 2026-10-03 (learning rename equivalence review)

- An equivalence claim must describe the actual mutant. The learning gate mutant's label claimed that it
  dropped `--find-renames`, but its replacement explicitly set `--no-renames`. Independent evidence showed
  that a byte-for-byte rename changes from 0/0 with rename detection to an added-file count without it.
  The latter falsely satisfies the learning gate. The production gate was correct; the equivalence claim
  concealed missing regression coverage.
- Pair a negative unchanged rename with a positive rename plus new content, both with approved fixture
  commits. The previous positive row alone could not distinguish the mutant. The paired rows now live in
  `.claude/hooks/tests/test-openproceedings-gates.sh`; the renamed mutant in
  `.claude/scripts/mutants/gates.json` is required to die and no longer carries `equivalent: true`.
- Propagated to `.claude/skills/testing-standards/SKILL.md`: prove the replacement's semantics with an
  isolating negative case and positive control before claiming equivalence. Interrupted official runs
  remain diagnostics, never pass evidence.

## Addendum — 2026-10-03 (case-position equivalence review)

- Supported ordinary case forms were insufficient evidence for a case-position mutant's exemption.
  Independent QA compared the production protect-data-dir verdicts: benign case-shaped argument data
  and a comment before `in` are refused by the documented conservative shape policy, but the mutant
  allows them. This is a mutation-proof defect, with no demonstrated security bypass. The production
  parser remains unchanged; spec 08 already documents its shape-based refusal policy.
- Added paired data-only case-table controls: both unsupported shapes BLOCK, while an ordinary benign
  case substitution ALLOWs. Injecting the replacement produced exactly those two failures
  (`868 passed, 2 failed`); the positive control stayed allowed. Removed the false equivalent marker
  and named its actual effect. The previous 47-kill official run was interrupted with exit 137 and is
  preserved only as diagnostic evidence, never a full pass.
- Propagated to `.claude/skills/testing-standards/SKILL.md`: check actual hook verdicts for benign
  unsupported syntax before claiming parser mutants equivalent. Full official verification remains pending.
- Official targeted mutation verification passed its full table baseline and killed this replacement:
  `1 mutants: 0 problem(s)`, exit 0. This focused proof does not replace the pending full changed run.

## Addendum — 2026-10-03 (complete recovered-hooks verification)

- The reviewed source `9d035a18` completed the official `make mutate-changed` run in isolated Linux:
  `417 mutants: 0 problem(s)`, exit 0. All 413 behavior-changing mutants were killed, including both
  corrected equivalence labels; the four surviving equivalent replacements were independently audited
  against their actual hook predicates. No stale pattern or unexpected survivor remained. Source bytes
  stayed unchanged throughout. Earlier interrupted runs remain diagnostic history, not pass evidence.
- Fresh Node 22 `make lint` and `make tooling` passed. Tasks 164, 170, 172 and 173 were completed through
  the Backlog CLI only after this proof. The final task/learning commit changes metadata only; fresh full
  tests and final lint/tooling plus exact-head review remain required before publication.
## Addendum — 2026-10-02 (TASK-171: stock Bash parses the case table too)

- **A green Linux table can still fail to parse on stock macOS Bash.** The sharding table's
  nonempty/nonerror check put `case` inside command substitution. Bash 3.2.57 interpreted a case-pattern
  `)` as the substitution's end: `make tooling` reported a syntax error and 32 passed/1 failed.
  Move that same case outside the substitution, store its result and assert the same value; keep the
  condition and expectation intact. Evidence: the red table in `/tmp/latex-timing-focused.log` and
  [recovery results](../../docs/results/2026-10-02-mutation-sharding-recovery.md).
- The same 33-row table then passed on both Bash 3.2.57 and Bash 5.3.9, with ShellCheck green.
  Evidence: `/tmp/mutation-tooling-recovery.log`.
- Propagated to: `.claude/scripts/tests/test-mutate-shard.sh` and the case-table portability guidance
  in `.claude/skills/testing-standards/SKILL.md`. Verify on stock Bash and the CI version when available;
  ShellCheck passed while stock Bash execution failed.
