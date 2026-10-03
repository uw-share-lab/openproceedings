---
id: TASK-048
title: 'Decide: index rejected and withdrawn submissions?'
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 20:48'
labels:
  - decision
milestone: m-4
dependencies: []
ordinal: 47000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 00 open question 2. Proposal: index them with status:rejected/withdrawn, excluded by default.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 backlog decision recorded
- [x] #2 Spec 00 §Open questions Q2 closed; spec 01 §Track taxonomy status handling and 02 §Default filters updated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner decision 2026-09-27 recorded as decision-012 (Context/Decision/Consequences). Live check (TASK-002): ICLR publishes every rejected/withdrawn/desk-rejected submission; NeurIPS and ICML only opt-in rejected papers. Spec 00 Q2 closed; spec 01 §Track taxonomy gained §Status handling (per API version); spec 02 §Default filters says what status:accepted removes; spec 07 §C statuses-indexed note.

Worktree sandbox refused 'backlog task complete' (2026-09-27); all ACs ticked and final summary written — main session: set Done and complete after merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Decided (owner, 2026-09-27): index every public rejected, withdrawn and desk-rejected submission with its status and exclude them by the default status:accepted, counted in the exclusion banner. decision-012; spec 00 Q2 closed; spec 01 §Status handling, spec 02 §Default filters and spec 07 §C updated. Canonical strings unchanged (status:accepted was already the default).
<!-- SECTION:FINAL_SUMMARY:END -->
