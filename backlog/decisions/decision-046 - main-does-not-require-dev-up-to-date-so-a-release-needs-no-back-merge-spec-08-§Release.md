---
id: decision-046
title: >-
  main does not require dev up to date, so a release needs no back-merge (spec
  08 §Release)
date: '2026-10-06 00:09'
status: accepted
---
## Context

A promotion merges `dev` into `main` with a merge commit, which `dev` lacks. `main`'s branch protection
required the branch up to date with it (`required_status_checks.strict: true`), so the next promotion was
blocked until `dev` held that commit, and every release ended with a `release/X.Y.Z-back-merge` PR: a
merge with no file changes that still ran a review gate, CI and the merge queue (#102, #104, #110). The owner
asked whether it was needed (2026-10-06). Options considered:

1. Turn off "require up to date" on `main`. The next promotion merges cleanly (`main`'s merge commits change
   no file `dev` lacks), and `changelog.py` places each PR by whether its merge commit is in a tag's history
   (`release_of`), never by `dev`'s, so the changelog is unaffected.
2. Fast-forward `main` to `dev` so the two stay equal. GitHub's PR merge methods can't fast-forward (a rebase
   merge rewrites commits), so this needs a direct push to `main`, past its PR requirement.
3. Keep the back-merge and make its PR cheaper.

## Decision

The owner chose option 1 on 2026-10-06. `main`'s `required_status_checks.strict` was set to false; the
before/after protection was compared and nothing else changed (the six required checks, the PR requirement,
zero required approvals, admins included, no force-push or deletion). A release has no back-merge step.

## Consequences

- Spec 08 §Release step 7, §Branch protection, the release-manager agent and the pr-workflow and
  repo-conventions skills say so; step 6's tag-ruleset output goes into the merged promotion PR as a comment.
- `dev` never contains `main`'s promotion merge commits. `git merge-base --is-ancestor origin/main origin/dev`
  is no longer a release check.
- Rollback: `gh api -X PATCH repos/<owner>/<name>/branches/main/protection/required_status_checks -F
  strict=true`, and spec 08's step 7 back-merge (as it stood at 0.1.0) returns.

