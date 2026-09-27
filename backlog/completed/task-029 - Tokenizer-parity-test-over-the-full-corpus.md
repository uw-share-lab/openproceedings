---
id: TASK-029
title: Tokenizer parity test over the full corpus
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 22:25'
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

Review fixes. Must: the index-has-an-extra-term direction is tested (a term Tantivy invented), alongside the dropped-term one. Shoulds: tests for the snapshot-hash mismatch, a record missing from the index, extra documents first and last, the shorter-side case; positions are now genuinely read back (a phrase query per field of 2+ tokens restricted to the record's id; reversed tokens fail), and the docstring/spec 03/skill say exactly what each step reads back (the stored-text step only shows the text round-trips; term frequencies are checked only as far as the phrase read-back implies); ParityError is documented as the one error whose message quotes tokens (local stderr only), with a test that the cli_refused log never carries them; the CLI verifies the index before trusting its manifest and shares _index_path with op search (that cli.py change lands in task-030's commit, which refactors the same file). Nits: normalize runs through the build's own chunked, pooled generator (index.normalized, now shared), stored documents stream in ord order instead of a dict, the mid-stream ParityError-before-SnapshotError case is commented, and a 60-record multi-segment index is checked. Real corpus: 1,805 records, 17,780 terms, 3,600 phrases, 0 differences, 4 s.

Verification (APPROVE; build byte-identical before/after the normalized() refactor; pool shut down on consumer errors and killed workers; record pairing probed over 9 shapes; real corpus 0 differences) fixes: an end-to-end test swaps two neighbouring tokens in normalize's view with the stored-text step silenced, so only check_parity's phrase read-back at slop 0 can fail it (pins the call and the slop); missing-in-the-middle, two missing and extra-in-the-middle cases; a CLI test with the manifest removed gets one clean line, no traceback; check_parity takes the manifest the CLI already verified, so files are hashed once (that cli.py line lands with task-030's commit). Noted: at 80k the check takes ~100 s locally, 60% of it the phrase read-back; fine for a local command.
<!-- SECTION:NOTES:END -->
