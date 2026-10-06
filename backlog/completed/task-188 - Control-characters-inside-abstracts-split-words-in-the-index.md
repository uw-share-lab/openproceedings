---
id: TASK-188
title: Control characters inside abstracts split words in the index
status: Done
assignee: []
created_date: '2026-10-05 08:39'
updated_date: '2026-10-06 00:06'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 132000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-180 cleaned titles only. Some abstracts hold U+0002 where a line-break hyphen was (modal, ity), so the word indexes as two tokens and an exact search for it misses the paper. Cleaning them changes stored bytes of existing records, so it needs its own decision on the rule and on the version bump.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The rule for control characters in abstracts is decided and recorded; affected records are counted on the current snapshot; the change, if made, bumps what index-versioning requires and the snapshot diff lists every changed record
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Shared record._spaced; record.abstract_text and record.controls_evidence (title_text/title_evidence keep their names). 2. Apply at every abstract source: openreview_v2._abstract (v1 and v2), ris._abstract, common.clean_abstract (NeurIPS, PMLR pages); ICLR archive has no abstract. 3. TDD: table, token-identity test, Hypothesis property, one test per importer. 4. Spec 01, record-schema and openreview-api skills, decision-036 forward note.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Rule (decision-044, owner 2026-10-05): each non-whitespace Cc in an abstract becomes one space, whitespace collapsed, before the snippet check; the claim's evidence gains ' (<n> control characters replaced by a space)' (after the route and url on a RIS claim, which dedup.attribution reads). Count on snapshot 2026-10-05-10b5a205a63f: 59 abstracts, 117 characters (U+0002 x106, U+000F x6, U+0008 x4, U+0000 x1); 98 between letters. Tokens unchanged (property test_the_stored_abstract_keeps_the_raw_abstracts_tokens), so no TOKENIZER_VERSION/SCHEMA_VERSION bump (index-versioning: new snapshot = nothing to bump). The model does not refuse a Cc in an abstract, so older snapshots still load. snapshot.diff reports a changed abstract under 'changed' (HASHED fields), so the next snapshot's diff lists the 59; the rebuild itself is the operator's (not run here). Verified: uv run pytest -q -n 4 backend/tests/unit/ingest 1647 passed; mypy --strict backend/src clean; ruff clean; make tooling passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Abstracts now get decision-036's title rule (decision-044): every importer (OpenReview v1/v2, RIS, NeurIPS and PMLR pages) replaces each control character with a space via record.abstract_text and says so in the abstract claim's evidence (record.controls_evidence). Tokens are unchanged, so no version bump; the next snapshot changes the stored text and content hash of the 59 affected records, which snapshot diff lists. Spec 01 states the 'quanti fying' limit. Verified by unit tests (table, token identity, Hypothesis property, one per importer): ingest suite 1647 passed, mypy strict and ruff clean.
<!-- SECTION:FINAL_SUMMARY:END -->
