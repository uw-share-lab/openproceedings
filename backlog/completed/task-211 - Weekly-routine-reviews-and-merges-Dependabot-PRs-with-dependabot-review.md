---
id: TASK-211
title: Weekly routine reviews and merges Dependabot PRs with /dependabot-review
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-10-07 20:29'
updated_date: '2026-10-08 00:31'
labels:
  - ops
  - tooling
milestone: m-4
dependencies: []
ordinal: 146000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner decision 2026-10-07: Dependabot PRs into dev are handled by a weekly scheduled Claude routine (a cloud Claude Code session on a fresh clone, with no access to the owner's machine). It reviews each open Dependabot PR, fixes what is needed, attests and queues it, and leaves anything suspicious open for the owner. Rejected alternative: exempting dependabot[bot] from the learnings/review-attested gates. This task commits the procedure (from the run that merged #123-#125 on 2026-10-07) as the /dependabot-review command plus tested helper scripts under .claude/scripts/dependabot/, and states the routine in spec 08 §CI "Dependabot" with a decision record.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 .claude/commands/dependabot-review.md holds the full procedure, self-contained for a cloud session with zero context, ending in a merged / left-open summary
- [x] #2 .claude/scripts/dependabot/ holds standard-library, typed helper scripts (uv.lock vs PyPI, npm lock vs the registry, manifest/lock pins, docker digests, Actions pins, libc restore, PR listing, queue watch)
- [x] #3 The scripts have a case table under .claude/scripts/tests/ run by make tooling, and mutants run by make mutate-changed
- [x] #4 The command is registered in roster_index.py and .claude/README.md is regenerated
- [x] #5 Spec 08 §CI Dependabot states the weekly routine, what it may merge and what it must leave open; a decision record explains why
- [x] #6 prs.py check gates each PR before anything of it runs (Dependabot-only verified commits, files by ecosystem, head unchanged); checkers reject changes beyond versions and pins and releases younger than 7 days; dependabot.yml sets a 7-day cooldown
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Script each check from the 2026-10-07 run under .claude/scripts/dependabot/ (stdlib, subprocess for every outside call), test with fakes on PATH, mutants; write the command; spec 08 + decision-048.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Scripts verified against the real #123-#125 diffs: uv_lock.py passes #125's head, npm_lock.py passes #124's merged head and FIXes Dependabot's original commit 34059c0f (the eslint-config-next caret), docker_digest.py passes #123 incl. gh attestation verify for astral-sh/uv. github_actions PRs are reviewed too (actions_pins.py), since Dependabot watches that ecosystem.

Review gate round 1 (code, security, qa, docs/methodology): the routine runs untrusted PR code, so checkers run from dev's copy, prs.py check gates the PR first, every checker rejects changes beyond versions and pins, tests run without the GitHub token, queueing uses --match-head-commit; per-file PyPI provenance on both versions; 7-day cooldown in dependabot.yml plus a checker stop; any new Python release (patch too) is the owner's (crawl-cache replay needs data/).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added /dependabot-review (.claude/commands/dependabot-review.md), the procedure a weekly cloud Claude routine runs on each open Dependabot PR into dev (decision-048; spec 08 §CI, The weekly routine). The checks are scripted in .claude/scripts/dependabot/ (stdlib, typed, mypy --strict in make lint) and run from dev's copy. prs.py check gates each PR (Dependabot-only verified commits, files by ecosystem, head unchanged). uv_lock.py, npm_lock.py, docker_digest.py and actions_pins.py verify the supply chain against PyPI, the npm registry, the image registry and tag refs, reject any change beyond versions and pins, and stop uv/npm releases younger than 7 days. restore_libc.py repairs dropped libc; prs.py also lists and watches the queue. dependabot.yml sets a 7-day cooldown; the pre-push and autofix hooks run their tools without the GitHub token. Hard stops are never merged; github-actions PRs are attested and queued by the owner (no workflows scope). Tests: test-dependabot.sh (136 rows, fakes for curl/npm/gh, fixed clock) in make tooling; 121 mutants in mutants/dependabot.json and 7 in gates.json. Verified live against PRs 123-125. Four review rounds; every Must and Should fixed.
<!-- SECTION:FINAL_SUMMARY:END -->
