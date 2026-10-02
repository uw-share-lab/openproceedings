---
id: TASK-168
title: >-
  Reproduce the dedup-auditor's NFC-vs-NFD title-key split, and decide whether
  dedup keys must be form-independent
status: To Do
assignee: []
created_date: '2026-10-02 09:27'
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
