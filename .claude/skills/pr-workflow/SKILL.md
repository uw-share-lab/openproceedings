---
name: pr-workflow
description: The openproceedings branch and PR flow (feature → PR → dev → PR → main), the per-sha review records that gate push and PR creation, the order of /review-gate then /open-pr, the six required CI checks, and the second-approval rule for main. Use when starting a branch, preparing to push, opening or promoting a PR, or diagnosing a push/PR the hooks blocked.
---

# PR workflow

## The flow
```
<type>/<slug> ──PR──► dev ──PR (promotion)──► main
```
- `dev` and `main` take **no direct commits, pushes or merges** (`enforce-pr-workflow.sh`). All work is on
  a branch cut from an up-to-date `origin/dev`: `git fetch origin && git switch -c <type>/<slug> origin/dev`,
  where type is `feat`, `fix`, `chore`, `docs` or `test` (e.g. `feat/wildcard-expansion`); a release's own
  bookkeeping uses `release/X.Y.Z` and `release/X.Y.Z-back-merge` (spec 08 §Release).
- Feature PRs target `dev`. `main` is only updated by a `dev → main` promotion PR (`release-manager`,
  spec 08 §Release), which needs **a second person's approving review** (branch protection) on top of green
  checks, and `dev` up to date with `main`: after each promotion, `main` is merged back into `dev`.
- Branch protection: both `dev` and `main` accept only PRs whose required checks are green.

## Closing order (CLAUDE.md §Closing workflow — approvals are per-commit)
1. Tests and lint green locally, **scaled by risk** (§Local test runs). Paste the command and the result,
   never a claim.
2. Backlog task updated via the CLI (criteria checked, notes, final summary); a finished task is moved with
   `backlog task complete <id>` (`.claude/skills/task-hygiene/SKILL.md`).
3. Docs, specs and READMEs as-built in the same branch.
4. `/record-learnings` → commit the entry and regenerated `INDEX.md`.
5. `/review-gate` → routed reviewers, every finding dispositioned, `record-review.py APPROVE` for HEAD.
6. `git push -u origin <branch>`, then `/open-pr` (writes the body, creates the PR, `--attest`s it).
7. Once the PR merges: `git worktree remove <its worktree>` and `git branch -d <branch>` (GitHub deletes the
   remote branch). A worktree left behind goes stale; one with uncommitted work is archived as a patch before
   it is removed, never deleted blind.

## Local test runs (by risk; owner's rule, 2026-09-29, TASK-121)
CI's required `test` job runs the full backend and frontend suite on every PR (backend under pytest-xdist, properties
at 200 examples; nightly reruns it at 2,000), and nothing merges without it. `make test` runs the backend in parallel
too (`-n auto`). The local run is there to catch a failure before the CI round, so it is sized to what the diff can
break. `make lint` and `make tooling` always run (the pre-push hook runs them too).

| The diff touches | Run locally before pushing |
|---|---|
| `backend/src/**`, `**/pyproject.toml`, `uv.lock`, `**/package.json`, `package-lock.json` | `make test` (the full suite) |
| `frontend/src/**`, frontend root config (`frontend/*.config.*` but `playwright.config.ts`, `frontend/tsconfig.json`), or the API contract `backend/tests/contract/openapi.json` | `npm test --workspace frontend`; and when it touches a file a backend test reads (any `frontend/src/**/*.json`, the goldens and fixtures, `src/api/schema.ts`, or `openapi.json`; the last two change only through `make openapi`), also `uv run pytest` (the whole backend suite); and for `next.config.ts` or `postcss.config.mjs`, which change the production build, also `npm run build --workspace frontend` (and `make e2e` when its `headers()` or `src/lib/security-headers.ts` change: a bad CSP builds but blocks scripts at runtime) |
| `frontend/e2e/**`, `frontend/playwright.config.ts`, `backend/tests/e2e/**` | `make e2e` (CI's `e2e` job is advisory, so this is the only run that must pass) |
| shared test code: any `conftest.py`, `backend/tests/{strategies,corpus}.py`, `backend/tests/fixtures/**`, or any `backend/tests` module another test imports (`grep -rn "<module name>" backend/tests --include='*.py'` finds both `from tests.x.<module> import …` and `from tests.x import <module>`) | `make test` (both suites: a frontend test reads `backend/tests/fixtures/queries/`) |
| other tests only | the changed test files; for a changed data file (e.g. `backend/tests/differential/*.json`, `backend/tests/golden/*.json`), the tests that read it (`grep -rln "<file name>" backend/tests frontend/src`) |
| `.claude/hooks/**`, `.claude/scripts/**`, `.githooks/**`, `.github/**`, `Makefile` | `make tooling` and `make mutate-changed` |
| `docs/specs/**`, `docs/results/**`, `backlog/**` (tests on both sides read them: the syntax-help golden, diagnostics, official counts, the Covidence fixture, the backlog check, decision records, and the methods text reads spec 05) | `make test` (both suites) |
| other docs: `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `docs/{design,research,plans,usability}/**`, `.claude/` markdown | nothing beyond `make lint` and `make tooling` |
| anything the rows above don't name | `make test` (unlisted means full: the table fails safe) |

A diff that spans rows runs the union. When in doubt, run `make test`. The PR's **Tests** section says exactly
what ran locally, and that CI runs the full suite; never claim a full-suite pass that wasn't run.

The learnings commit comes **before** the review because the review record is keyed to the exact HEAD
sha. Any commit after an approval — a typo fix, a rebase, an amend — produces a new sha with no record, and
`require-review.sh` blocks the push until `/review-gate` runs again.

## Review records
- Stored at `$(git rev-parse --git-common-dir)/op-reviews/<sha>`, first line `APPROVE` or
  `REQUEST_CHANGES`. Inside `.git`, never committed, shared across worktrees.
- Written **only** by `python3 .claude/scripts/record-review.py APPROVE <dispositions.md> [--attest]`.
  Finding lines are `- [must|should|nit] … → <disposition>`; the tag may be any case, the bullet `-` or
  `*`, indented or not. A tag on a line that isn't a well-formed bullet is refused as malformed.
- It refuses: a dirty tree; an undispositioned finding; a `[must]` dispositioned as anything but
  `fixed <sha>`; a `fixed <sha>` that is not an ancestor of HEAD **or is already on `origin/dev`** (it
  predates the review), or any `fixed <sha>` while `origin/dev` doesn't resolve (fetch it first); a `task-NNN` that doesn't exist; a `rejected:` reason shorter than three words;
  and a file that says `No findings.` while also listing findings. Never hand-write a record (`require-review.sh` blocks a Bash or file-tool write under
  `op-reviews/`); fix what the script names.
- Records are **per-sha**: an approval covers exactly one commit.
- `--attest` adds `<!-- op-review: <sha> APPROVE -->` to the PR body; CI's `review-attested` step compares
  it to the PR head sha. After pushing a fix to an open PR, re-run the gate and `--attest` again.

## Required CI checks (six)
| Check (workflow) | Covers |
|---|---|
| `lint` (`lint.yml`) | `make lint`: ruff format/check, mypy --strict (once `backend/src` exists), shellcheck; prettier, eslint, tsc; then actionlint |
| `test` (`test.yml`) | pytest unit/golden/differential/contract under pytest-xdist, properties at the `pr` profile (200 examples, 2 s deadline); vitest; OpenAPI→TS freshness |
| `claude-tooling` (`claude-tooling.yml`) | `make tooling`: roster lint, `.claude/README.md` + learnings index freshness, backlog hygiene, every hook case table |
| `attribution` (`pr-gates.yml`) | no AI attribution in any commit message or the PR title/body |
| `learnings` (`pr-gates.yml`) | the branch adds or extends a learnings entry, or is labelled `no-learning` |
| `review-attested` (`pr-gates.yml`) | the PR body attests APPROVE for the head sha |

The advisory `e2e` and `bench` checks should also be green before merge; `nightly` is scheduled rather
than a PR check (spec 08 §CI); its `suite-ci` job reruns the whole backend suite at the `ci` profile (2,000
examples), so a property failure that needs more than 200 examples surfaces within a day (TASK-127).

**Learnings rule.** Only a file named `YYYY-MM-DD-<slug>.md` directly in `.claude/learnings/` counts, added
*or* modified: extending an existing entry with a dated addendum satisfies the gate. `README.md`,
`_TEMPLATE.md`, `INDEX.md` and anything else don't. A same-repo `dev → main` promotion is exempt from
`learnings` and `review-attested` (locally, `require-review.sh` exempts `--base main --head dev`).

## PR body shape (`/open-pr`)
**Summary** · **Spec(s)** touched · **Tests** (commands + results) · **Review** (reviewers, counts by
severity, dispositions) · **Learnings** (entry path + key lesson). No attribution footer.

## Gotchas
- `--label no-learning` is for PRs that taught nothing (a typo). Using it to skip the journal is a
  `pr-reviewer` Must.
- Don't rebase an approved branch "just to tidy" — it discards the approval.
- Stacked branches: base the PR on `dev` anyway; the diff routing uses `origin/dev...HEAD`.
- A hook block is information, not an obstacle. Read its stderr; never work around it with `--no-verify`
  or by calling git through another wrapper.

## Merge method
Merge PRs into `dev` with a **merge commit** (`gh pr merge <n> --merge --delete-branch`), not a squash:
review dispositions and learnings entries cite branch commit SHAs, and a squash would leave those references
pointing at commits that aren't on `dev`. To change a PR body, use `gh api -X PATCH repos/{owner}/{repo}/pulls/<n>`;
`gh pr edit` fails here on the retired Projects (classic) API.
