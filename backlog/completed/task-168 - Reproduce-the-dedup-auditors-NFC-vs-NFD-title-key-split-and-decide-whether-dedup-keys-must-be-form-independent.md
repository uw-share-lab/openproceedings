---
id: TASK-168
title: >-
  Reproduce the dedup-auditor's NFC-vs-NFD title-key split, and decide whether
  dedup keys must be form-independent
status: Done
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-03 02:13'
labels:
  - dedup
  - ingest
dependencies: []
references:
  - backend/src/openproceedings/ingest/dedup.py
  - backend/src/openproceedings/query/normalize.py
priority: low
ordinal: 138000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: the dedup-auditor's note in the TASK-155 review (2026-10-02), reported but not yet reproduced. The dedup title key (ingest/dedup.py title_key) is built with query/normalize.py normalize(). The auditor reported that for 177 of 3,000 random titles with combining marks, the NFC and NFD forms of one title got different keys, and that this predates TASK-155. A project-manager check on this branch found no split (0 of 3,000 Latin/Greek/Cyrillic titles; 0 of 3,000 with marks from Hebrew, Arabic, Devanagari, Thai and kana; hand cases in Hangul, kana with dakuten, Devanagari nukta and Vietnamese). TASK-155's own notes record a different split, 276 of 500 under the stored-order rule, which TASK-155 fixed. If the split is real, two copies of one paper differing only in Unicode form would not be merged.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The auditor's generator, seed or examples are recovered, or an equivalent search is run on current dev; the result (reproduced or not, with the characters involved) is in the notes
- [x] #2 The outcome is recorded truthfully: if not reproduced, complete as not reproduced with the search; if reproduced, explicitly record that not-reproduced closure is inapplicable and satisfy criterion 3
- [x] #3 If reproduced: the real snapshot's dedup is re-run with a form-independent key and the change in merges is recorded, and a decision record states whether dedup keys become form-independent; if they do, the change has a property test (title_key(NFC(t)) == title_key(NFD(t))) and the dedup-rules skill and spec 01 are updated
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Reproduce canonical-form title-key splits; retain scratch real-data dedup comparison; normalize dedup keys to NFC and pin a canonical-equivalence property; document decision-031 and the separate tokenizer-3 NFKC work.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Search (2026-10-02, current dev). The auditor's generator wasn't recovered, so an equivalent search was run:
(1) Exhaustive: every assigned code point whose NFC/NFD/NFKC/NFKD differs from itself, alone and between letters, 68,116 cases: 0 NFC-vs-NFD splits.
(2) 300,000 random (letter + 1-4 combining marks) pairs over all of Unicode: 0 NFC-vs-NFD splits. 488 raw-vs-NFC splits from marks stored out of canonical order (e.g. U+0345 before another mark).
(3) 60,000 random titles of precomposed and decomposed letters: 0 NFC-vs-NFD splits; 5 NFKC-vs-NFKD.
REPRODUCED with backslashes. normalize() reads LaTeX on the raw text before its per-character NFKC, so a backslash before a letter whose NFD starts with an ASCII letter begins a command. Examples: NFD 'Caf\e+U+0301' keys 'caf' but NFC 'Caf\é' keys 'caf e'; 'Erd\H{ő}s' NFC 'erdos' vs NFD 'erd o s' (the mark inside the braces breaks the accent macro); '\ḡx' 'gx' vs 'x'. 3,000 random titles of ASCII words with accented letters: 0 split without backslashes, 2,633 split with them. Characters involved: '\' + any precomposed Latin/Greek/Cyrillic letter (U+00C0-U+024F and others), and accent-macro braces.
Fix: ingest/dedup.py title_key normalizes to NFC before normalize(), so title_key(NFC t) == title_key(NFD t) == title_key(t) (marks in any canonical order too). Property test test_every_canonically_equivalent_title_has_one_key. Spec 01 and the dedup-rules skill are updated.
Real data: data/snapshots/2026-09-29-d552baa07aed holds 124,208 title claims, 0 of them not NFC, so no key changes; scratch rebuild below.

Scratch rebuild (2026-10-02; data/cache cloned into a mktemp dir, nothing written under data/): op snapshot build with origin/dev's code and with this branch both gave snapshot 2026-09-29-8adf9327771a. The two are byte-identical (records.jsonl, merges.csv, conflicts.csv), so the NFC key changes no merge on the real data. Against data/snapshots/2026-09-29-d552baa07aed: merges.csv and conflicts.csv are identical; op snapshot diff gives added 0, removed 0, rekeyed 0, changed 0, and 104 provenance_only (the TASK-159 twin claims merged since d552, not this change).
Deferred (reported to team-lead): search's own normalize() reads LaTeX before NFKC, so a non-NFC title with a backslash still indexes other tokens than its NFC form. That needs a TOKENIZER_VERSION bump. Today's impact is 0 (no non-NFC titles).

Tokenizer side (search's normalize, form-dependent before NFKC): per the owner (2026-10-02), fixed on its own branch fix/tokenizer-nfc-form (tokfix agent), not here. This PR changes only the dedup title_key.

Final integration cdb68cdb6fc12bd0ae9c23bed1788e1fd1c78511 on merged dev9152ecb: make test PASS6386backend/2optional skips and3217frontend; make lint/tooling PASS; make e2e PASS19. Fresh focused index/dedup/twins/checker/takedown tests PASS289. Logs /tmp/twins-finalization-{test,lint,tooling,e2e,focused}.log. Independent integrated all-role review APPROVE /tmp/twins-integrated-all-role-review.md. Final metadata commit and its fresh fulltest/lint/tooling remain required before publication.

Conditional AC2 applicability clarified without claiming not reproduced: the backslash/accent examples reproduced the defect, so AC3 is the operative resolution. Scratch reconstruction evidence remains preserved at the original twins2-rebuild directory and scratchpad reports; fresh final property tests pass. Dedup explicit NFC and tokenizer3 whole-string NFKC before LaTeX are separate steps.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Reproduced backslash/accent NFC-vs-NFD splits, so not-reproduced closure is inapplicable. Dedup title_key applies NFC before token normalization; property and examples pass. Preserved real-data scratch comparison: byte-identical records/merges/conflicts, zero changed merges from124208already-NFC titles. CLI decision-031, spec01 and dedup skill updated; tokenizer3 whole-string NFKC remains separately versioned.
<!-- SECTION:FINAL_SUMMARY:END -->
