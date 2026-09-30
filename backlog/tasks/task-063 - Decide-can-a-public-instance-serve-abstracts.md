---
id: TASK-063
title: 'Decide: can a public instance serve abstracts?'
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-30 01:07'
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
Decision-018 (accepted, 2026-09-29): the public instance serves every abstract, each record attributed to its source with a link; a public instance names a takedown contact (private, local and dev deployments may omit it). The unlicensed years (NeurIPS 2013–2020, ICML 2013–2016, OpenReview years before its CC0 clause) rest on Canadian fair dealing alone (s. 29 and the CCH factors, in Context as the basis for the copyright office). The owner's answer on a refusal ("lets just show the abstracts") means no fallback: the UWaterloo copyright-office consultation is recommended, not a gate (TASK-135; TASK-069 AC#5 records its outcome, if any). Sources table in the record: OpenReview terms (2024-09-24 version; CC0 clause from 2023-09-22), NeurIPS copyright FAQ, PMLR agreement plus the ICML 2017 (v70) agreement for the CC BY boundary, arXiv CC0 as a future alternative; ICLR 2014 and the ICLR 2016 workshop track counted as OpenReview abstracts (2026-09-29 coverage report). Spec 00 Q1 closed; spec 08 §Deploy and README state what is served and the prerequisites; testing-standards skill updated (decision-004 unchanged).

Gaps found, now tasks: TASK-133 (takedown contact; proposed withhold-from-next-index_version procedure; pinned older versions still serve the abstract), TASK-134 (result list lacks authors and abstract source; PMLR citation+hyperlink met only on the paper page), both m-6 and TASK-069 dependencies. Not tasked: records carry no licence field (OpenReview's per-note license is dropped by _public_projection); only a licensed-only fallback would need it, and there is none. Exports carry URL links but no source/licence statement (TASK-134 AC#3 notes it).
<!-- SECTION:NOTES:END -->
