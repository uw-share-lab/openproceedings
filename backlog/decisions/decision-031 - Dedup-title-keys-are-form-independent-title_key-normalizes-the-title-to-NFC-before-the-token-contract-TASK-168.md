---
id: decision-031
title: >-
  Dedup title keys are form-independent: title_key normalizes the title to NFC
  before the token contract (TASK-168)
date: '2026-10-03 02:05'
status: accepted
---

## Context

The dedup title key (`ingest/dedup.py` `title_key`) was the token contract's `normalize(title)` joined by single spaces. The dedup-auditor reported that the NFC and NFD forms of one title can get different keys (TASK-155 review). If so, two copies of one paper that differ only in Unicode form would not merge.

TASK-168 searched for it on current dev:
- no split for any code point or mark sequence on its own (68,116 exhaustive cases, 300,000 random base+marks, 60,000 random titles);
- a reproducible split once a backslash comes before a letter whose NFD starts with an ASCII letter. `normalize` reads LaTeX on the raw text before its per-character NFKC, so `\` + `e` + U+0301 starts the command `\e`:
  - NFD `Caf\é` keys `caf`, while NFC keys `caf e`;
  - `Erd\H{ő}s` keys `erd o s` in NFD and `erdos` in NFC;
  - 2,633 of 3,000 random titles with such backslashes split.

Marks stored in a non-canonical order also changed the key. Options considered:
1. Leave keys form-dependent.
2. NFC-normalize the title inside `title_key` (ingest only).
3. Normalize the whole string in the tokenizer before LaTeX parsing (a `TOKENIZER_VERSION` bump and an index rebuild). The separate tokenizer-3 implementation uses NFKC at this step; dedup's explicit step remains NFC.

## Decision

Dedup keys are form-independent: `title_key(t)` is `normalize(NFC(t))` joined by spaces. So `title_key(t) == title_key(NFC(t)) == title_key(NFD(t))` for every canonically equivalent spelling.

## Consequences

- Ingest-only (dedup, reconcile, crawl matching, the twin rule); search and the index are untouched, so `index_version` and search records are unaffected. Dedup and search now agree on "same title" for NFC text only; search's own form-dependence (option 3) is fixed separately by the owner's request on branch fix/tokenizer-nfc-form (its own TOKENIZER_VERSION decision).
- Real data: the 2026-09-29 snapshot holds 0 non-NFC titles of 124,208 title claims; a scratch rebuild of the cache with and without the change gave byte-identical snapshots (merges.csv and conflicts.csv unchanged).
- Pinned by `test_every_canonically_equivalent_title_has_one_key` (a Hypothesis property with the reproduced examples) in `backend/tests/unit/ingest/test_dedup.py`; spec 01 (merge step b) and the dedup-rules skill say so.
