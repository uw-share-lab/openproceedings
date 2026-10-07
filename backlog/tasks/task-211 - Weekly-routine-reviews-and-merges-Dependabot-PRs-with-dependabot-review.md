---
id: TASK-211
title: Weekly routine reviews and merges Dependabot PRs with /dependabot-review
status: In Progress
assignee: []
created_date: '2026-10-07 20:29'
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
- [ ] #1 .claude/commands/dependabot-review.md holds the full procedure, self-contained for a cloud session with zero context, ending in a merged / left-open summary
- [ ] #2 .claude/scripts/dependabot/ holds standard-library, typed helper scripts (uv.lock vs PyPI, npm lock vs the registry, manifest/lock pins, docker digests, Actions pins, libc restore, PR listing, queue watch)
- [ ] #3 The scripts have a case table under .claude/scripts/tests/ run by make tooling, and mutants run by make mutate-changed
- [ ] #4 The command is registered in roster_index.py and .claude/README.md is regenerated
- [ ] #5 Spec 08 §CI Dependabot states the weekly routine, what it may merge and what it must leave open; a decision record explains why
<!-- AC:END -->
