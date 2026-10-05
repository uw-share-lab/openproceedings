---
id: TASK-180
title: 'Ingest: a title holding a C0 control character drops the paper'
status: To Do
assignee: []
created_date: '2026-10-05 05:12'
labels:
  - ingest
milestone: m-4
dependencies: []
references:
  - docs/specs/01-ingestion.md
ordinal: 124000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The 2026 ICLR crawl (TASK-178) skipped one accepted workshop paper, forum xHMNX3l8rx (Workshop/LLM_Reasoning), as invalid because its title holds two U+0002 control characters; the NeurIPS 2026 crawl skipped one note as invalid too (cause not yet read). A real paper is missing from the corpus over invisible characters the source left in a title.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The rule for control characters in a title (and the other text fields the record model validates) is decided, recorded as a decision and stated in spec 01: what is removed or replaced, and that the stored title is otherwise the source's
- [ ] #2 xHMNX3l8rx is imported with a readable title; the NeurIPS 2026 invalid note is identified and either imported or its refusal explained
- [ ] #3 Tokenization of an affected title is unchanged in meaning (token-contract): the tokens are those of the title without the control characters, with tests; any version bump the change requires is made
- [ ] #4 No other record's bytes change in a rebuild from the same cache, or each change is listed
<!-- AC:END -->
