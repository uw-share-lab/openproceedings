# `uv run --locked` installs whatever lock is checked out, so a pre-push `make lint` runs a PR's dependencies

**Key lesson:** To keep a session from executing a PR's dependencies, guard every entry point that syncs (`make sync`/`lint`/`test`/…, `setup-dev.sh`, the pre-push hook's `make lint`), not just `make test`: `uv run --locked` syncs the venv to the checked-out `uv.lock` before it runs anything, so on a Dependabot branch even `make lint` installs and runs the PR's ruff and mypy.

- **Date:** 2026-10-13 · **Task:** task-243 · **Area:** tooling
- **Artifacts:** `.claude/commands/dependabot-review.md`, `.claude/scripts/dependabot/prs.py` (`preflight`'s marker, `ci`), `Makefile` (`dep-code-allowed`), `.githooks/pre-push`, `scripts/setup-dev.sh`, `.claude/scripts/tests/test-no-dep-code.sh`, decision-048's 2026-10-13 TASK-243 addendum, branch `feat/cloud-routine-no-dep-code`

## What we set out to do
Implement the owner's decision that a cloud `/dependabot-review` run (whose Claude App credential has
`workflows`, `contents`, repository-hooks and `checks` write) executes none of the PR's dependency code, and reads
CI's results for the head instead of running the tests.

## What we learned
- "Don't run `make test`" is not enough. Every Makefile target that touches Python uses `uv run --locked`, which
  syncs `.venv` to the checked-out `uv.lock` first (evidence: `Makefile` `lint:`, `fmt:`, `test:`, `openapi:`), so
  on a PR branch `make lint` installs the PR's versions (building any sdist runs its build backend) and runs them.
  The pre-push hook runs `make lint`, so a cloud push would have run them too. `setup-dev.sh` runs `uv sync`.
- `make tooling` is not dependency-free either: three case tables run pytest from `.venv/bin/python`
  (`test-early-failures.sh`, `test-hypothesis-profiles.sh`, `test-network-guard.sh`; without a venv they fail with
  "No module named 'hypothesis'"). They run `.venv` directly, not through `uv run`, so with a venv installed from
  `dev` before any PR is fetched they run `dev`'s code; that is why the cloud installs `dev`'s environment once at
  step 0 and nothing after.
- A file marker in git's common directory reaches every worktree of the clone (the stale-base worktree included)
  and can't come from a PR. The Makefile reads it with `git rev-parse --path-format=absolute --git-common-dir`;
  `--git-dir` would miss it in a linked worktree (a mutant and a row check this).
- The App has `checks` write, so a check run named `test` can be written by the session itself: `prs.py ci`
  counts only GitHub Actions' runs (`app.slug == "github-actions"`), and takes the latest run per name by id,
  since a rerun leaves the older run listed (PR #146's head lists `review-attested` twice).
- `npm audit signatures` needs the installed tree; `npm audit --package-lock-only` doesn't. In the cloud the
  former can't run and `npm_lock.py`'s registry checks stand in.

## Dead ends — don't repeat these
- Writing the marker into this checkout's real `.git` to test the guard: the common directory is shared with every
  other worktree of the clone (another agent's included), and the marker would refuse their `make test` too. The
  case table builds its own throwaway repos.

## Decisions (and what would change them)
- A marker and refusals, not a sandbox: the commands typed directly (`uv run`, `npm ci`, `npx`) stay unguarded,
  and the procedure and the cloud reviewer prompt keep them out. What would change it: a slip in a cloud run
  (then wrap `uv`/`npm` too), or a cloud session that can run code without the credential reachable.

## Follow-ups
- none new; TASK-243 keeps the cloud items still to confirm.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/agents/ci-engineer.md` (a new dependency target takes
  `dep-code-allowed`), `.claude/skills/autolint/SKILL.md`, `.claude/skills/repo-conventions/SKILL.md`, `CLAUDE.md`
  (Code quality), spec 08 §CI "Dependabot".
- Test or hook added? — `.claude/scripts/tests/test-no-dep-code.sh`, `prs ci` and marker rows in
  `dependabot_cases.py`, mutants in `gates.json` and `dependabot.json`.
