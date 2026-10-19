---
id: TASK-250
title: >-
  op eval openalex: author-check the 123 AAAI 1980-2008 'differs' records and
  add AIES 2026, once TASK-135 allows OpenAlex requests
status: To Do
assignee: []
created_date: '2026-10-16 22:50'
labels:
  - eval
  - new-venues
dependencies:
  - TASK-135
priority: low
ordinal: 163000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-235 (PR #152, docs/results/2026-10-16-openalex-audit.md) compared OpenAlex with aaai_library for AAAI 1980-2008: of 1,131 records, 123 (10.9%) 'differs'. Title matches aren't checked against authors, so some may be another paper attached by the title route. The existing author check needs about 3 live OpenAlex requests. TASK-217 (PR #155) added AIES 2026 (265 records, official abstracts from OJS); the audit doesn't cover it yet. Both were deferred because OpenAlex's Terms of Service (revised 2026-10-02) conflict with the CC0 statement decision-049 relied on, and the owner directed no new OpenAlex requests until TASK-135 is answered (2026-10-16).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The author check runs on the 123 'differs' records and the report splits them into wrong-paper attaches and genuinely different texts, with tests
- [ ] #2 op eval openalex covers AIES 2026, and the audit is re-run on the then-current snapshot and cited from spec 07 §G
<!-- AC:END -->
