# Hardening the hook parser against deliberate evasion never converged

**Key lesson:** The Claude hooks guard against an agent's mistakes, not deliberate evasion. Judge a reported bypass by whether an agent would write it by accident, and decline the rest instead of growing cmdparse.

- **Date:** 2026-10-26 · **Task:** task-266, task-269 · **Area:** tooling
- **Artifacts:** `.claude/hooks/lib/cmdparse.py`, `.claude/hooks/{block-ai-attribution,enforce-pr-workflow}.sh`,
  2e74966b (round 3), 7bacedb0 (the revert), 6aed89bf (closing review)

## What we set out to do
Close every Must and Should in the TASK-266/269 review rounds on fix/hardening-batch.

## What we learned
- **Each parser fix opened new findings.** Round 3 reported 10 bypasses and round 4 about 12, and the automated security review added 5 more against the fixes in progress. The arithmetic-skip bypass (`((rm -rf data/snapshots) )`) came from the glob fix, which came from the variable-name fix. None of the round-4 forms is one an agent writes by accident: `touch rm; r? -rf …`, `X=env; $X rm …`, `\time cd`, `COMMAND eval cd`, `find -exec sh -c '…'`, zsh's `command cd`.
- **Strictness cost real commands.** Refusing unresolvable command names (round-3 N2, `UnresolvedName`) blocked `"$PYTHON" -m pytest`, `$EDITOR notes.md` and `$(which python3) -V`, and the round-4 zsh fix would have blocked `command cd "$WT"; git commit`.
- **The accidental forms are few and cheap.** The one reopened shape an agent plausibly writes, a Makefile-style `"${GIT:-git}" push` or `"${RM:-rm}" -rf …`, needed only a default rule, `cmdparse._default_name`, called from `_strip_prefixes` (6aed89bf).

## Dead ends — don't repeat these
- Treating every reviewer bypass as a Must or Should under the fix-all rule. A shell parser has no natural end to that list. An agent set on evasion can use `python3 -c 'import shutil; …'`, which no hook parses.

## Decisions (and what would change them)
- The owner stopped round-4 hardening at 2e74966b and reverted N2 (7bacedb0), with no follow-up task for round 4's forms (task-285 is a separate, accident-scope review). This would change if the hooks ever had to contain a hostile agent; that needs a sandbox, not a better parser.

## Follow-ups
- None for round 4. The diff was not kept in the repo, and the owner declined a task for it.
- [ ] task-285: a review of how cmdparse reads git config and options, held to the accident scope above. Unlike round 4's forms, a repo's real push.default or includeIf settings are what an agent meets by accident (owner, 2026-10-26).

## Propagated to
- Skill / agent / CLAUDE.md updated? — no: the scope belongs in the reviewers' brief. The owner's rule is recorded in this entry, which hook reviewers should be pointed at.
- Test or hook added? — the allow rows for `"$PYTHON" -m pytest`, `$EDITOR notes.md` and `"${PYTHON:-python3}" -m pytest -q` in `test-openproceedings-gates.sh` pin the over-blocking as gone.
