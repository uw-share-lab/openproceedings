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
  where type is `feat`, `fix`, `chore`, `docs` or `test` (e.g. `feat/wildcard-expansion`).
- Feature PRs target `dev`. `main` is only updated by a `dev → main` promotion PR (`release-manager`),
  which needs **a second person's approving review** (GitHub ruleset) on top of green checks.
- Branch protection: both `dev` and `main` accept only PRs whose required checks are green.

## Closing order (CLAUDE.md §Closing workflow — approvals are per-commit)
1. Tests and lint green locally (`make test`, `make lint`, `make tooling`). Paste the command and the
   result, never a claim.
2. Backlog task updated via the CLI (criteria checked, notes, final summary); a finished task is moved with
   `backlog task complete <id>` (`.claude/skills/task-hygiene/SKILL.md`).
3. Docs, specs and READMEs as-built in the same branch.
4. `/record-learnings` → commit the entry and regenerated `INDEX.md`.
5. `/review-gate` → routed reviewers, every finding dispositioned, `record-review.py APPROVE` for HEAD.
6. `git push -u origin <branch>`, then `/open-pr` (writes the body, creates the PR, `--attest`s it).

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
  predates the review); a `task-NNN` that doesn't exist; a `rejected:` reason shorter than three words;
  and a file that says `No findings.` while also listing findings. Never hand-write a record; fix what the
  script names.
- Records are **per-sha**: an approval covers exactly one commit.
- `--attest` adds `<!-- op-review: <sha> APPROVE -->` to the PR body; CI's `review-attested` step compares
  it to the PR head sha. After pushing a fix to an open PR, re-run the gate and `--attest` again.

## Required CI checks (six)
| Check (workflow) | Covers |
|---|---|
| `lint` (`lint.yml`) | `make lint`: ruff format/check, mypy --strict (once `backend/src` exists), shellcheck; prettier, eslint, tsc; then actionlint |
| `test` (`test.yml`) | pytest unit/golden/differential@2k/contract; vitest; OpenAPI→TS freshness |
| `claude-tooling` (`claude-tooling.yml`) | `make tooling`: roster lint, `.claude/README.md` + learnings index freshness, backlog hygiene, every hook case table |
| `attribution` (`pr-gates.yml`) | no AI attribution in any commit message or the PR title/body |
| `learnings` (`pr-gates.yml`) | the branch adds or extends a learnings entry, or is labelled `no-learning` |
| `review-attested` (`pr-gates.yml`) | the PR body attests APPROVE for the head sha |

`e2e`, `bench` and `nightly` are **planned (M1+)** and don't exist yet (spec 08 §CI).

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
