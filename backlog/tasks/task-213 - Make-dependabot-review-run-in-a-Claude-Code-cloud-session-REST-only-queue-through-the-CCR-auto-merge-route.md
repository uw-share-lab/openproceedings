---
id: TASK-213
title: >-
  Make /dependabot-review run in a Claude Code cloud session: REST only, queue
  through the CCR auto-merge route
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-10-08 16:59'
updated_date: '2026-10-08 17:06'
labels:
  - tooling
  - ci
dependencies: []
references:
  - decision-048
  - .claude/commands/dependabot-review.md
ordinal: 146000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Live test runs of the weekly /dependabot-review routine (decision-048, TASK-211) in its real cloud environment on 2026-10-08 found it can't run as written: a Claude Code cloud session answers every GitHub GraphQL call with HTTP 403 ('GitHub GraphQL is not available from Claude Code sessions; use the REST API ...', naming CCR routes such as PUT/DELETE /repos/{owner}/{repo}/pulls/{n}/ccr/auto_merge), so prs.py list/check/watch, gh pr merge --auto --match-head-commit and record-review.py --attest all fail; and the token is a proxy-injected network secret (GH_TOKEN/GITHUB_TOKEN are placeholders, gh auth status says invalid, gh api user works), so step 0's checks can't pass. A maintainer running it locally with a real gh login must keep working.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 prs.py list, check and watch use GitHub REST only; check also compares GitHub's file and commit lists with git's
- [x] #2 prs.py preflight checks auth with gh api user, detects cloud vs local from GraphQL's answer, and checks the credential (no stored gh token in the cloud; token-shaped variables reported)
- [x] #3 prs.py queue uses PUT/DELETE .../ccr/auto_merge in the cloud and gh pr merge --auto --match-head-commit locally; it re-reads the head before and after, requires GitHub to show the PR set to merge, and undoes and reports anything else; any non-2xx leaves the PR open
- [x] #4 record-review.py --attest --pr <n> --repo <owner>/<name> attests over REST and refuses a PR not open at HEAD; a gh pr view failure other than 'no pull requests found' is an error
- [x] #5 The fake gh simulates the GraphQL 403 body and the CCR routes; case-table rows and mutants cover the new paths, all mutants killed
- [x] #6 The command doc, spec 08 and a decision-048 addendum describe the cloud/local split, the credential model and the residual head race; a learnings entry records the lesson
- [ ] #7 A one-off cloud run confirms the CCR PUT/DELETE request shape, the job-log download and gh attestation verify (owner's probe after merge)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built on branch chore/dependabot-review-rest. Verified locally: make lint and make tooling green (dependabot 205/0, gates 882/0 after rebasing onto TASK-212). Mutants: each changed mutant run against its own case table only (prs/_common against test-dependabot.sh, record-review against test-openproceedings-gates.sh) because machine load was 90-150; all killed; make mutate-changed was not run in full. Reviews: focused security+QA, then four full-gate rounds (code, docs, review-methodologist, security, qa), last APPROVE; dispositions all fixed. Live REST reads (timeline queue events, queue refs, merge_group runs, advisories) checked from a local login; the CCR route returns 404 outside a session. AC #7 waits for the owner's cloud probe after merge: the CCR PUT/DELETE request shape (body/params undocumented; any non-2xx leaves the PR open), whether DELETE dequeues an entry, the job-log download host, and gh attestation verify's sigstore hosts. One process slip: a single sed edit to decision-048's body (later edits via the Edit tool).

After the rebase onto TASK-212 (8e1b4319), make lint and make tooling are green again. c202eb9a answers an automated push security review's report that head-name validation, the queue-ref filter and URL quoting were removed (it saw an intermediate diff; all three are in the final prs.py at :115, :222, :436 and :441). It adds 15 rows (odd head names in check and list, and a crafted queue ref in watch; dependabot table 220/0), tightens HEAD_SHAPE to refuse '..', and adds 2 mutants. The dot-dot, head-shape and ref-filter mutants were run against test-dependabot.sh and killed. The URL-quoting mutant is marked equivalent, because the 40-hex ref filter runs first.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The /dependabot-review procedure and prs.py now use GitHub REST only and detect cloud vs local from GraphQL's answer; queueing uses the session's CCR auto-merge route in the cloud (head re-read before and after, undo on any doubt) and gh pr merge --match-head-commit locally; record-review.py attests over REST with --pr/--repo. The residual head race is recorded in decision-048's addendum and spec 08; it is closed by the queue's review-attested build against anyone who can't also rewrite the PR body. Open: AC #7, the owner's cloud probe.
<!-- SECTION:FINAL_SUMMARY:END -->
