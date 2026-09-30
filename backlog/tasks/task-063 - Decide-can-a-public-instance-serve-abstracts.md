---
id: TASK-063
title: 'Decide: can a public instance serve abstracts?'
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-30 00:51'
labels:
  - decision
milestone: m-6
dependencies: []
ordinal: 62000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 00 open question 1. Check OpenReview, NeurIPS and PMLR terms.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decision recorded with sources
- [x] #2 Spec 00 §Open questions Q1 closed; README and spec 08 §Deploy state what is served
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision-018 (accepted, 2026-09-29): the public instance serves every abstract, with per-record attribution and source link and a takedown contact on every deployment; unlicensed years rely on Canadian fair dealing (Copyright Act s.29; CCH v. LSUC factors); UWaterloo copyright-office sign-off before the public launch (TASK-069); if refused, fall back to licensed abstracts only (PMLR v70+ CC BY 4.0, OpenReview CC0 clause / per-paper licence). Sources table in the record (OpenReview terms 2024-09-24 version, CC0 clause from the 2023-09-22 version; NeurIPS copyright FAQ; PMLR licence; arXiv CC0 as a future alternative). Spec 00 Q1 closed; spec 08 §Deploy and README state what is served and the prerequisites; testing-standards skill no longer calls Q1 unresolved (decision-004 unchanged: corpus stays out of git).

Gaps found (launch work, not implemented here): (1) result list (hit-item.tsx) shows the abstract with outbound links but no authors and no statement of the abstract's source, so PMLR's citation+hyperlink is met only on the paper page (authors, Links, provenance table with source link); (2) no licence field on records: OpenReview's per-note license is dropped by _public_projection, needed for the refusal fallback; (3) no takedown contact anywhere in frontend, API or docs (no footer/about page); belongs to TASK-065 or TASK-069. Exports carry UR links and T2 but no source/licence statement.
<!-- SECTION:NOTES:END -->
