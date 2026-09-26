---
id: TASK-015
title: 'Scholar/PoP compatibility mode and source: alias table'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - query
milestone: m-1
dependencies:
  - TASK-012
  - TASK-005
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
mode=scholar: |, source: → venue: via alias table, PoP $ as WoS wildcard, translations[] (spec 02 §Compatibility).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every Trust-Evals protocol string parses with zero errors; canonical forms snapshot-tested
- [ ] #2 source:PMLR → venue:ICML with a translation notice; unknown source: values are errors
- [ ] #3 Alias table covers every source value in the 17 corpus export names
<!-- AC:END -->
