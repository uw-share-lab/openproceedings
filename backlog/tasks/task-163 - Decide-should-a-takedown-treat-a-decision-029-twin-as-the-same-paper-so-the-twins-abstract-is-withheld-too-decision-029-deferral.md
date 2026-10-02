---
id: TASK-163
title: >-
  Decide: should a takedown treat a decision-029 twin as the same paper, so the
  twin's abstract is withheld too? (decision-029 deferral)
status: In Progress
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-02 18:12'
labels:
  - decision
  - ops
  - dedup
  - deferred
dependencies:
  - TASK-159
references:
  - >-
    backlog/decisions/decision-022 -
    A-takedown-withholds-an-abstracts-display-not-its-matching-on-every-loaded-index-version-the-takedown-list-and-log-live-in-the-data-directory-TASK-136.md
  - >-
    backlog/decisions/decision-029 -
    Link-ICLR-2017-workshop-copies-to-their-conference-twins-as-two-records-with-twin-claims-never-merged-the-RIS-importer-reads-scholarmend-0.1.5s-invitation-by-the-crawlers-twin-rule-TASK-159-TASK-157.md
  - backend/src/openproceedings/takedowns.py
priority: low
ordinal: 133000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: decision-029 (TASK-159), Consequences, Deferred: owner decision needed. Under decision-022 a takedown withholds an abstract's display; the record and its matching stay. decision-022 already follows a listed id to other ids that are the same paper (merges and rekeys, `takedowns.same_paper`). decision-029 keeps an ICLR 2017 workshop copy and its conference twin as two records linked by a `twin` claim, never merged, so a takedown of one copy today leaves the other copy's abstract displayed. Question: should `same_paper` treat a `twin` claim as the same paper? Options: (1) no, the listed id and its merges only; (2) yes, follow the twin claim; (3) no, but `op takedown check` reports that a twin still shows its abstract.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The owner picks an option; a decision record (`backlog decision create`) states it with the options considered and cites decision-022 and decision-029
- [ ] #2 If the answer changes behaviour, a follow-up task is filed for `takedowns.same_paper`, its tests and spec 08 (§Deploy, the takedown procedure); otherwise spec 08 says a takedown does not follow a twin claim
<!-- AC:END -->
