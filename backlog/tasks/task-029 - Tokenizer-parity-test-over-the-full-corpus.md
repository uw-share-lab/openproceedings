---
id: TASK-029
title: Tokenizer parity test over the full corpus
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 21:31'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-023
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Index tokens == normalize.py tokens for every record (spec 03 §Tokenizer).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 0 diffs on the Trust-Evals snapshot
- [x] #2 Fails loudly with the first differing record and token
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented engine/parity.py + op index parity --index <v> [--snapshot]: reads back from the built index (not the build's intent): each document's stored field through exact_v1 == normalize() of the snapshot record's raw text, in id order; each (field, term) document frequency from Tantivy's term dictionary (terms_with_prefix(field, "") lists it whole, tested) == the count from normalize(); the first difference raises ParityError (an IndexBuildError, so the CLI exits 1) naming record, field, token index and both tokens, or the term and both counts; also refuses an index from another snapshot and records missing on either side. Tests on the synthetic 5k corpus (LaTeX, NFKC, CJK, astral): passes with independently computed record and term counts; a skewed normalize names the first record/field/token; a dropped dictionary term is named; the CLI prints differences 0. AC1 run locally on the real Trust-Evals corpus (built into the session scratchpad, since data/snapshots still holds the old-format snapshot of the same name): 1,805 records, 17,780 terms, 0 differences, 3 s. Docs: spec 03 §Tokenizer as-built, spec 08 CLI row, tantivy-indexing skill (corrected: the real-corpus run is local, never nightly CI), release-manager runbook.
<!-- SECTION:NOTES:END -->
