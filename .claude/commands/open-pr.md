---
description: Open the PR for the current branch into dev — after /review-gate has approved HEAD and the learnings entry is committed — and attest the review in the PR body for CI
argument-hint: "(optional) base branch, default dev (a dev→main promotion doesn't use this command)"
allowed-tools: Read, Grep, Glob, Bash
---

Open a pull request for the current branch. Base: ${ARGUMENTS:-dev}.

1. Confirm `require-review.sh` will pass: an APPROVE record exists for `git rev-parse HEAD` under
   `$(git rev-parse --git-common-dir)/op-reviews/`, and the branch adds a `.claude/learnings/` entry vs
   the base. If not, stop and say which step (`/record-learnings`, `/review-gate`) is missing.
2. `git push -u origin <branch>` (the hook re-checks the record).
3. Write the PR body from the Backlog task(s) and the commits: **Summary**, **Spec(s)** touched, **Tests**
   (what ran locally, commands + results, by `pr-workflow` §Local test runs; CI's `test` job runs the full suite), **Review** (reviewers run, finding counts by severity, dispositions),
   **Learnings** (the entry path + key lesson). **No AI attribution line** — `block-ai-attribution.sh`
   rejects it.
4. `gh pr create --base <base> --title "<type>: <summary>" --body-file <file>`.
5. `python3 .claude/scripts/record-review.py APPROVE <dispositions.md> --attest` to add the
   `<!-- op-review: <sha> APPROVE -->` line that CI's `review-attested` check reads.
6. A `dev → main` promotion doesn't use this command (steps 1, 2 and 5 don't apply to it): spec 08 §Release
   step 5 opens it with `gh pr create --base main --head dev`, and it needs a second person's approval.
Report the PR URL and which CI checks it must pass.
