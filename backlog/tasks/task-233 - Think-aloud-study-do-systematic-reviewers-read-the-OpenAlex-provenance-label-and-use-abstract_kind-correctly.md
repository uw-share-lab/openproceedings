---
id: TASK-233
title: >-
  Think-aloud study: do systematic reviewers read the OpenAlex provenance label
  and use abstract_kind correctly
status: To Do
assignee: []
created_date: '2026-10-11 05:08'
updated_date: '2026-10-11 05:58'
labels:
  - usability
  - new-venues
dependencies: []
priority: low
ordinal: 162000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The milestone C design assumes that a reviewer who sees 'Abstract via OpenAlex' on a hit or paper page, or the Abstract source facet, understands that the text is a third party's and chooses abstract_kind:official when that matters. No source supports this and no study checks it (hci-researcher, gate C round 1; research note §Does an inline provenance label let a reviewer judge and filter fallback text?: no evidence found). Run a small think-aloud with systematic reviewers on the results, paper and /coverage pages (usability-tester).

Ethics: not submitted
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The Ethics: line reads cleared <file #> or not required (ORE confirmed <date>) before any session
- [ ] #2 A protocol with tasks covering the label, the /coverage explanation and the Abstract source facet is written to docs/usability
- [ ] #3 Sessions with at least five systematic reviewers are run and their findings written to docs/usability, with any copy or design change filed as tasks
<!-- AC:END -->
