---
id: TASK-043
title: Concept-group query builder
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 20:27'
labels:
  - frontend
milestone: m-3
dependencies:
  - TASK-041
ordinal: 42000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 05 §Components 3 (query-builder-engineer).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Builder ↔ AST round-trip tests
- [ ] #2 Read-only fallback when the AST doesn't fit the group shape
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design (TASK-033, 2026-09-27): docs/design/2026-09-27-concept-group-builder.md + copy deck §3. Builder walks the server ast of the draft (never parses text); fits = top And of Or-of-leaves groups, one optional Not (Exclude row), top-level filters shown as read-only limits. Read-only notice names the first non-fitting construct with its kind and span (proximity, AND inside OR, a limit inside OR, NOT of a combination), focus moves to it. Builder edits are draft edits; Search dispatches builderEdit. Text->Builder->Text without an edit must leave the text byte-for-byte as typed; edited groups write canonical-equal q. Reorder by buttons (and Alt+Up/Down), no drag; focus after removal goes to the previous term/group. Test with main-7-most-updated in Scholar mode (source: limits keep their text).

Pre-pass fixes that land in TASK-043: pasted lists in one term offer 'Split into n terms' by default, else the chip says 'searched as one phrase' (M5); scope on each chip (S9); Search never disabled by the builder (S10); limits line says 'search first to edit them in Filters, or edit them in Text' (S8).
<!-- SECTION:NOTES:END -->
