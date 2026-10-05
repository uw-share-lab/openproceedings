---
id: TASK-179
title: >-
  Dedup: an imported RIS copy whose title lost a math symbol, or that shares a
  ris claim, is not merged with its crawled paper
status: To Do
assignee: []
created_date: '2026-10-05 05:12'
labels:
  - ingest
  - dedup
milestone: m-4
dependencies: []
references:
  - docs/specs/01-ingestion.md
ordinal: 123000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-178 on snapshot 2026-10-05-47d4e190ca81: 7 accepted records exist only because the Trust-Evals RIS import holds a second copy of a crawled paper that dedup did not merge. Five differ from the crawled title only by a lost math symbol (tau-bench, R2-Guard, Adapt-infinity, RobotArena infinity, A2Search: op:iclr:2025:iclr-1b126cc3… = roNSXZpUDN, iclr-a07e87ec… = CkgKSqZbuC, iclr-a6610efd… = EwFJaXVePU; op:iclr:2026:iclr-2aa3da3c… = OutljIofvS, iclr-dcbdb995… = 3CPzUWIoNf), one has the same title key as its twin but both records hold a ris claim (op:iclr:2024:iclr-c3eb94d1… = QHROe7Mfcb), and one is probably the same paper under an earlier title (op:iclr:2026:iclr-6b41e04c…, perhaps CwoM9T55lG; unconfirmed). They inflate accepted counts (ICLR 2026 main 5,354 instead of 5,351), count a paper twice in the Scholar comparison, and show a paper twice in results.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each of the six confirmed pairs merges into one record under a rule stated in spec 01 and the dedup-rules skill, with merges.csv naming the rule; no never-merge rule is weakened (title alone across venue or year still never merges)
- [ ] #2 The retitled seventh case is either merged on evidence the rule can state or left separate and listed as a known duplicate with its reason
- [ ] #3 Property and table tests cover a title differing only by a lost math symbol, and two records that each hold a ris claim; the dedup invariants still hold
- [ ] #4 A snapshot rebuilt from the same cache shows only these merges as differences from 2026-10-05-47d4e190ca81 (op snapshot diff reviewed), and RIS-only accepted records are 0 or each is explained
<!-- AC:END -->
