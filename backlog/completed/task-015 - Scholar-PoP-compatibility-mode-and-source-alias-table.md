---
id: TASK-015
title: 'Scholar/PoP compatibility mode and source: alias table'
status: Done
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 03:33'
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
- [x] #1 Every Trust-Evals protocol string parses with zero errors; canonical forms snapshot-tested
- [x] #2 source:PMLR → venue:ICML with a translation notice; unknown source: values are errors
- [x] #3 Alias table covers every source value in the 17 corpus export names
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
query/compat.py + parse(q, "scholar"): exact source: alias table covering all 17 corpus exports (PMLR warns), decision-002 phrase grouping for PoP | items (asked of the review lead), PoP $ notices, native canonical output; all ten protocol strings parse.
<!-- SECTION:FINAL_SUMMARY:END -->
