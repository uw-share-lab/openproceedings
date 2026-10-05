---
id: TASK-180
title: 'Ingest: a title holding a C0 control character drops the paper'
status: In Progress
assignee: []
created_date: '2026-10-05 05:12'
updated_date: '2026-10-05 07:36'
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
- [x] #1 The rule for control characters in a title (and the other text fields the record model validates) is decided, recorded as a decision and stated in spec 01: what is removed or replaced, and that the stored title is otherwise the source's
- [x] #2 xHMNX3l8rx is imported with a readable title; the NeurIPS 2026 invalid note is identified and either imported or its refusal explained
- [x] #3 Tokenization of an affected title is unchanged in meaning (token-contract): the tokens are those of the title without the control characters, with tests; any version bump the change requires is made
- [x] #4 No other record's bytes change in a rebuild from the same cache, or each change is listed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Rule built: the OpenReview importers (v1 and v2, record.title_text) replace each control character (Unicode Cc: C0, DEL, C1) in a title with a space and collapse whitespace; the claim's evidence says how many, a DEBUG line names the forum. A space because the tokenizer already reads a control character as a separator, so the stored title's tokens are the raw title's (the one exception, a control just inside dollar-math, is pinned by a test). Abstracts, authors and keywords are untouched (the record never refused controls there; dozens of crawled abstracts hold U+0002). Scratch rebuild from the same cache: 4 records added and no other record's content changed: op:iclr:2026:xHMNX3l8rx (workshop accepted, two U+0002), op:neurips:2026:KlvYZ17FPi (Workshop/WiML rejected, a trailing NUL in title and a keyword: this is the NeurIPS 2026 invalid note), op:iclr:2024:PqjQmLNuJt (main rejected, U+0002) and op:iclr:2023:6l46OaYQvu3 (v1, main withdrawn). No version bump: only records that were refused before are affected; no tokenizer, index-schema or record-schema input changed. AC 1 waits on the decision record (text proposed to the lead).

Review fix (2026-10-05): the rule now runs in every importer (RIS, NeurIPS, PMLR and ICLR archive as well), where a control character would have failed the import or dropped the listing; the rebuild's records are byte-identical to the first scratch build. decision-036.
<!-- SECTION:NOTES:END -->
