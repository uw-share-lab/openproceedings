---
id: TASK-192
title: >-
  Word forms: offer the subset that fits near the length cap, and say why a term
  was skipped
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
labels:
  - frontend
  - query
  - ux
milestone: m-3
dependencies: []
ordinal: 136000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-175 offers no Add $ at all when adding every $ would pass the 2,000-code-point query cap, although some would fit, and a term the notice names but that cannot take a $ gets only a generic sentence in the chooser.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Near the cap the terms that fit are offered and the rest are named as not fitting; each skipped term carries its reason from the server (an additive field); tests and spec 02/05 as built
<!-- AC:END -->
