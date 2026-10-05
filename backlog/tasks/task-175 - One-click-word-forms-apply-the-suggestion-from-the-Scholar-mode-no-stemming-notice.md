---
id: TASK-175
title: >-
  One-click word forms: apply the $ suggestion from the Scholar-mode no-stemming
  notice
status: To Do
assignee: []
created_date: '2026-10-05 01:47'
labels:
  - frontend
  - query
  - ux
milestone: m-3
dependencies: []
references:
  - docs/specs/05-frontend.md
  - docs/specs/02-query-language.md
ordinal: 119000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A reviewer who pastes a Google Scholar string gets far fewer papers than the same string means in Scholar, because Scholar stems and openproceedings matches exactly (guarantee 1). On 2026-10-04 the Trust-Evals primary string returned 27 papers as typed and 67 once $ was added by hand to five terms. The COMPAT_NO_STEMMING notice says to add $ but leaves the typing to the user, who may not know which terms it names. Stemming in the engine is ruled out by guarantee 1; the fix is an explicit rewrite of the query text that the user triggers and sees (guarantees 3 and 6).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The no-stemming notice offers an action that rewrites the query text, adding $ to the terms the notice names; the engine, tokenizer and index are unchanged and nothing is expanded unless the rewritten text says so (00 guarantee 1)
- [ ] #2 The rewrite is visible in the editor and the URL before or as the search runs, is undoable, and the saved query string alone reproduces the result set (00 guarantees 3, 4)
- [ ] #3 Every expansion the added wildcards produce is shown as existing wildcard expansions are (00 guarantee 6)
- [ ] #4 Terms where $ is invalid or already present (phrases' inner words per spec 02, filter values, terms with a wildcard) are left alone, with tests for each case
- [ ] #5 Spec 05 and the syntax help describe the action as built
<!-- AC:END -->
