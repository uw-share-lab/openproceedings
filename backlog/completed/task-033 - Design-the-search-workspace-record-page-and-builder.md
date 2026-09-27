---
id: TASK-033
title: 'Design the search workspace, record page and builder'
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 20:29'
labels:
  - ux
  - frontend
milestone: m-3
dependencies:
  - TASK-039
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Design docs in docs/design/ covering states (empty, zero results, errors, too many expansions) (ux-design skill; /design-feature).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Wireframes and interaction specs for /search, /record/[id], builder, exclusion banner
- [x] #2 Heuristic pre-pass by usability-auditor; findings dispositioned
- [x] #3 ux-writer copy for every diagnostic and banner string
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-27 re-scope (owner): build the full system before any human study. TASK-032 (interviews) moves to after the full system; this design proceeds from spec 05, the user-research/ux-design skills' personas and a usability-auditor heuristic pre-pass. Its dependency on TASK-032 is removed.

Delivered docs/design/2026-09-27-{search-workspace,concept-group-builder,export-records-and-paper,coverage-and-syntax-help,copy-deck,heuristic-prepass}.md. Grounded in spec 05, user-research personas/JTBD (assumptions, marked), PRISMA/PRISMA-S and the observed Covidence check (screeners can't see status/track). Heuristic pre-pass: designer self-check (SC-1..SC-32) + usability-auditor run as a separate read-only agent (8 Must, 15 Should, 8 Nit) - all dispositioned; no severity 3-4 open. Diagnostic messages captured verbatim from the parser on this branch and reviewed by ux-writer; 7 registry rewrites proposed (not applied). Implementation notes appended to TASK-041..046. Items for the main session to file as tasks (worktree agents don't reserve ids): API identified_total/unclassified_total (blocks TASK-044 AC#1), RecordRequest.index_version pin, GET /records/{id}?replay=false, /coverage crawl_dates_kind + identification_citable, reducer year action, per-clause spans for non-toggleable clauses, registry wording rewrites.

backlog task complete was refused in the agent worktree sandbox; status left In Progress with every AC ticked - the main session completes it after the merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Designed the M3b UI in six docs under docs/design/ (search workspace with every state incl. each ClauseReason/reducer refusal, 422/429/413/503/non-JSON/index swap; builder; export menu with the Covidence status/track warning, save with index check, record page for reproduced/drifted/refused/withheld/mismatch/bootstrap with methods-text rules; paper page; coverage; syntax help; copy deck; heuristic pre-pass). Verified: q rewrites checked against filter-clause-golden.json, messages captured from the parser, pre-pass by an independent usability-auditor run with every finding dispositioned; make lint and make tooling pass.
<!-- SECTION:FINAL_SUMMARY:END -->
