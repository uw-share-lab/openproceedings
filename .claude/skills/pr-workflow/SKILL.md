---
name: pr-workflow
description: The openproceedings branch and PR flow (feature → PR → dev → PR → main), the per-sha review records that gate push and PR creation, the order of /review-gate then /open-pr, the six required CI checks, and the solo-maintainer approval policy for main. Use when starting a branch, preparing to push, opening or promoting a PR, or diagnosing a push/PR the hooks blocked.
---

# PR workflow

## The flow
```
<type>/<slug> ──PR──► dev ──PR (promotion)──► main
```
- `dev` and `main` take **no direct commits, pushes or merges** (`enforce-pr-workflow.sh`). All work is on
  a branch cut from an up-to-date `origin/dev`: `git fetch origin && git switch -c <type>/<slug> origin/dev`,
  where type is `feat`, `fix`, `chore`, `docs` or `test` (e.g. `feat/wildcard-expansion`); a release's own
  bookkeeping uses `release/X.Y.Z` (spec 08 §Release).
- Feature PRs target `dev`. `main` is only updated by a `dev → main` promotion PR (`release-manager`,
  spec 08 §Release), which requires green checks but **no mandatory approving review** under the
  solo-maintainer policy applied on 2026-10-03; `main` doesn't require `dev` up to date, so there is no
  back-merge (decision-046).
- Branch protection: both `dev` and `main` accept only PRs whose required checks are green. `dev` merges
  through a **merge queue** (TASK-161, decision-027; §Merge method).

## Closing order (CLAUDE.md §Closing workflow — approvals are per-commit)
1. Tests and lint green locally, **scaled by risk** (§Local test runs). Paste the command and the result,
   never a claim.
2. Backlog task updated via the CLI (criteria checked, notes, final summary); a finished task is moved with
   `backlog task complete <id>` (`.claude/skills/task-hygiene/SKILL.md`).
3. Docs, specs and READMEs as-built in the same branch.
4. `/record-learnings` → commit the entry and regenerated `INDEX.md`.
5. `/review-gate` → routed reviewers, every finding dispositioned, `record-review.py APPROVE` for HEAD.
6. `git push -u origin <branch>`, then `/open-pr` (writes the body, creates the PR, `--attest`s it).
7. Once its checks are green, the PR goes into the merge queue (§Merge method). Once it merges:
   `git worktree remove <its worktree>` and `git branch -d <branch>` (GitHub deletes the remote branch). A
   worktree left behind goes stale; one with uncommitted work is archived as a patch before it is removed,
   never deleted blind.

## Local test runs (by risk; owner's rule, 2026-09-29, TASK-121)
CI's required `test` job runs the full backend and frontend suite on every PR (backend under pytest-xdist, properties
at 200 examples; nightly reruns it at 2,000, the differential at 50,000), and nothing merges without it. `make test` runs the backend in parallel
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
| `deploy/**` (Docker isn't assumed locally: CI's advisory `web-image` job builds the web image, so confirm it green on the PR) | `npx vitest run --root frontend src/lib/web-image.test.ts` (it reads `web.Dockerfile` and runs `web-build-gate.sh`), and `make tooling` (the digest-pin check); for `compose.yml`, `Caddyfile`, `api.Dockerfile`, `caddy.Dockerfile` or the scripts, also `deploy/smoke-test.sh` where Docker is available (no CI job runs it), and say in the PR which ran |
| `docs/specs/**`, `docs/results/**`, `backlog/**` (tests on both sides read them: the syntax-help golden, diagnostics, official counts, the Covidence fixture, the backlog check, decision records, and the methods text reads spec 05) | `make test` (both suites) |
| other docs: `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `CITATION.cff`, `docs/README.md`, `docs/{design,research,plans,usability}/**`, `.claude/` markdown | nothing beyond `make lint` and `make tooling` |
| anything the rows above don't name | `make test` (unlisted means full: the table fails safe) |

A diff that spans rows runs the union. When in doubt, run `make test`. The PR's **Tests** section says exactly
what ran locally, and that CI runs the full suite; never claim a full-suite pass that wasn't run.

### Several sessions on one machine (2026-10-05)
When agent sessions work in parallel worktrees, the full suite belongs to one of them at a time (two at once
took the load past 100 and failed Hypothesis deadlines and editor tests that were not broken); the others run
the affected tests. A long command runs in the **foreground**, behind a wait for the load if need be
(`until [ "$(uptime | sed 's/.*load averages: \([0-9]*\).*/\1/')" -lt 30 ]; do sleep 20; done; make test`):
a session that backgrounds its run and waits to be told can stop with its work uncommitted. Scratch files are
named after the task (`t181-test.log`), never `test.log`. Nothing a session starts listens on 8000 or 3000
(`OP_E2E_API_PORT` / `OP_E2E_WEB_PORT` for e2e). A session in a worktree reports its follow-ups; it creates no
Backlog ids.

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
| `lint` (`lint.yml`) | `make lint`: ruff format/check, mypy --strict (`backend/src` and the `/dependabot-review` scripts), shellcheck; prettier, eslint, tsc; then actionlint |
| `test` (`test.yml`) | pytest unit/golden/differential/contract under pytest-xdist, properties at the `pr` profile (200 examples, 2 s deadline); vitest; OpenAPI→TS freshness |
| `claude-tooling` (`claude-tooling.yml`) | `make tooling`: roster lint, `.claude/README.md` + learnings index freshness, backlog hygiene (no Done task in `tasks/`, no id used twice), digest pins in `deploy/`, the npm manifests against the lock (`npm_specs.py`, TASK-212), every case table |
| `attribution` (`pr-gates.yml`) | no AI attribution in any commit message or the PR title/body |
| `learnings` (`pr-gates.yml`) | the branch adds or extends a learnings entry, or is labelled `no-learning` |
| `review-attested` (`pr-gates.yml`) | the PR body attests APPROVE for the head sha |

All six also run on the merge queue's builds (`merge_group`). There, `merge_group_gate.py` runs
`attribution`, `learnings` and `review-attested` on **each** PR in the group. Each PR's current body must
attest APPROVE for the head the queue merged, and the PR must still be open (or already merged by this
group's own queue commit), target `dev` and have that head. Anything the script can't resolve fails the build (spec 08 §Merge queue).

The advisory `e2e`, `bench` and `web-image` checks (`web-image` runs only when a PR touches the paths spec 08
§CI lists: `deploy/`, the frontend, the npm manifests, `.dockerignore` or the workflow) should also be green before merge; `nightly` is scheduled rather
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
PRs go into `dev` as **merge commits**, not squashes: review dispositions and learnings entries cite branch
commit SHAs, and a squash would leave those references pointing at commits that aren't on `dev`.

**With the merge queue** (the `dev: merge queue` ruleset, applied 2026-10-02; spec 08 §Branch protection), add a
green PR to the queue with `gh pr merge <n> --auto`. That needs the repository's "Allow auto-merge" setting;
spec 08 §Git and PR rules gives the GraphQL `enqueuePullRequest` call that works without it. The queue's
MERGE method makes the merge commit, and GitHub deletes the branch. Don't rebase a PR because `dev` moved. Its review record and attestation cover
its head, and the queue tests that head on top of `dev` plus the PRs ahead of it. Several PRs can wait in
the queue at once. Rebase only when the queue drops a PR, either for a conflict or for a red queue build.
Then fix the cause, run the review round on the new head, `--attest` it, and queue it again. A push to a
queued PR also drops it from the queue.

To change a PR body, use `gh api -X PATCH repos/{owner}/{repo}/pulls/<n>`;
`gh pr edit` fails here on the retired Projects (classic) API.
