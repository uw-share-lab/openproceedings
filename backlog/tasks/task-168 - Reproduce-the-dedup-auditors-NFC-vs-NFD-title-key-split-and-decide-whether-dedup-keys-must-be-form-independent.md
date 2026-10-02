---
id: TASK-168
title: >-
  Reproduce the dedup-auditor's NFC-vs-NFD title-key split, and decide whether
  dedup keys must be form-independent
status: In Progress
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-02 18:12'
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
- [ ] #1 The auditor's generator, seed or examples are recovered, or an equivalent search is run on current dev; the result (reproduced or not, with the characters involved) is in the notes
- [ ] #2 If not reproduced, the task is completed as not reproduced, with the search that was run
- [ ] #3 If reproduced: the real snapshot's dedup is re-run with a form-independent key and the change in merges is recorded, and a decision record states whether dedup keys become form-independent; if they do, the change has a property test (title_key(NFC(t)) == title_key(NFD(t))) and the dedup-rules skill and spec 01 are updated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Search (2026-10-02, current dev). The auditor's generator wasn't recovered, so an equivalent search was run:
(1) Exhaustive: every assigned code point whose NFC/NFD/NFKC/NFKD differs from itself, alone and between letters, 68,116 cases: 0 NFC-vs-NFD splits.
(2) 300,000 random (letter + 1-4 combining marks) pairs over all of Unicode: 0 NFC-vs-NFD splits. 488 raw-vs-NFC splits from marks stored out of canonical order (e.g. U+0345 before another mark).
(3) 60,000 random titles of precomposed and decomposed letters: 0 NFC-vs-NFD splits; 5 NFKC-vs-NFKD.
REPRODUCED with backslashes. normalize() reads LaTeX on the raw text before its per-character NFKC, so a backslash before a letter whose NFD starts with an ASCII letter begins a command. Examples: NFD 'Caf\e+U+0301' keys 'caf' but NFC 'Caf\é' keys 'caf e'; 'Erd\H{ő}s' NFC 'erdos' vs NFD 'erd o s' (the mark inside the braces breaks the accent macro); '\ḡx' 'gx' vs 'x'. 3,000 random titles of ASCII words with accented letters: 0 split without backslashes, 2,633 split with them. Characters involved: '\' + any precomposed Latin/Greek/Cyrillic letter (U+00C0-U+024F and others), and accent-macro braces.
Fix: ingest/dedup.py title_key normalizes to NFC before normalize(), so title_key(NFC t) == title_key(NFD t) == title_key(t) (marks in any canonical order too). Property test test_every_canonically_equivalent_title_has_one_key. Spec 01 and the dedup-rules skill are updated.
Real data: data/snapshots/2026-09-29-d552baa07aed holds 124,208 title claims, 0 of them not NFC, so no key changes; scratch rebuild below.
<!-- SECTION:NOTES:END -->
