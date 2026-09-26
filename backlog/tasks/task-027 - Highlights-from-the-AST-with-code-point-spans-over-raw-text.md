---
id: TASK-027
title: Highlights from the AST with code-point spans over raw text
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-024
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 03 §Highlights, spec 04 span units.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Spans are half-open code points over the raw stored field, via the normalize offset map
- [ ] #2 Phrase spans and expanded wildcard terms highlighted exactly; nothing else
- [ ] #3 Astral-plane character golden case
<!-- AC:END -->
