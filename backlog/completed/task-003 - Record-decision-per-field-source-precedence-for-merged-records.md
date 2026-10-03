---
id: TASK-003
title: 'Record decision: per-field source precedence for merged records'
status: Done
assignee:
  - '@jeevan'
created_date: '2026-09-25 22:06'
updated_date: '2026-09-26 15:44'
labels:
  - ingest
  - decision
milestone: m-2
dependencies: []
references:
  - .claude/skills/dedup-rules/SKILL.md
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
When OpenReview and proceedings disagree (title casing, abstract, authors, status), which source wins per field. dedup-rules proposes a table; confirm before M4.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 backlog decision created with the precedence table and rationale
- [x] #2 spec 01 §Error handling references it
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
decision-005: OpenReview first for title/abstract/authors (the venues' own platform, current first; proceedings where OpenReview lacks the paper, then RIS); OpenReview venueid for track/status; venue/year from the crawl scope, disagreements to conflicts.csv. Chosen by the review lead 2026-09-26 (first proceedings-first, then switched). Spec 01 §Error handling and the record-schema skill reference it.
<!-- SECTION:FINAL_SUMMARY:END -->
