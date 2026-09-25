---
name: pr-workflow
description: The openproceedings branch and PR flow (feature → PR → dev → PR → main), the per-sha review records that gate push and PR creation, the order of /review-gate then /open-pr, the four required CI checks, and the second-approval rule for main. Use when starting a branch, preparing to push, opening or promoting a PR, or diagnosing a push/PR the hooks blocked.
---

# PR workflow

## The flow
```
feat/<slug> ──PR──► dev ──PR (promotion)──► main
```
- `dev` and `main` take **no direct commits, pushes or merges** (`enforce-pr-workflow.sh`). All work is on
  a branch cut from an up-to-date `origin/dev`: `git fetch origin && git switch -c feat/<slug> origin/dev`.
- Feature PRs target `dev`. `main` is only updated by a `dev → main` promotion PR (`release-manager`),
  which needs **a second person's approving review** (GitHub ruleset) on top of green checks.
- Branch protection: both `dev` and `main` accept only PRs whose required checks are green.

## Closing order (CLAUDE.md §Closing workflow — approvals are per-commit)
1. Tests green locally (`uv run pytest`, `npm test`). Paste the command and the result, never a claim.
2. Backlog task updated via the CLI (criteria checked, notes, status).
3. Docs brought to as-built if behaviour changed.
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
  It refuses a dirty tree, an undispositioned finding, a rejected `[must]`, or a `fixed <sha>` that is not
  an ancestor of HEAD. Never hand-write a record; fix what the script names.
- `--attest` adds `<!-- op-review: <sha> APPROVE -->` to the PR body; CI's `review-attested` step compares
  it to the PR head sha. After pushing a fix to an open PR, re-run the gate and `--attest` again.

## Required CI checks
| Check | Covers |
|---|---|
| `lint` | ruff, ruff-format, mypy --strict; eslint, tsc, prettier; markdown links |
| `test` | pytest unit/golden/differential@2k/contract; vitest; OpenAPI→TS freshness |
| `claude-tooling` | `python3 .claude/scripts/lint_tooling.py` + `.claude/hooks/tests/*.sh` |
| `pr-gates` | no AI attribution in commits/PR body, a learnings entry (or `no-learning` label), review attested for head sha |
`e2e`, `bench` and `nightly` also run (spec 08 §CI); treat a red one as blocking unless the PR says why.

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
