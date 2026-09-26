---
id: TASK-013
title: Canonical form and canonical_hash
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 02:20'
labels:
  - query
milestone: m-1
dependencies:
  - TASK-012
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Fully parenthesised, uppercase operators, sorted filters, defaults explicit (spec 02 §Outputs).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 parse(canonical).canonical == canonical (Hypothesis, 2k CI / 50k nightly)
- [x] #2 AST → string → AST is the identity
- [x] #3 canonical_hash = sha256(canonical + TOKENIZER_VERSION); query_version constant defined
- [x] #4 Golden (decision-001): filters canonicalise in order venue, year, track, status, then others alphabetically; values in a single-field OR group are sorted
<!-- AC:END -->
