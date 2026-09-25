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
