---
id: TASK-155
title: Bound combining-mark runs or abstract length at ingest
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-10-01 12:29'
updated_date: '2026-10-02 03:13'
labels:
  - security
  - ingest
dependencies: []
references:
  - backend/src/openproceedings/query/normalize.py
priority: low
ordinal: 130000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: TASK-067 review gate (security-reviewer). CPython's own NFKC/NFC canonical reordering stays superlinear when combining classes alternate: `a` + `\u0301\u0338` x n tokenizes in about 2 s at 80k characters and 15 s at 200k (measured 2026-10-01, after TASK-067 made the tokenizer's own scan linear). `q` is capped at 2,000 code points, but a stored abstract has no length cap, so a hostile abstract would cost every search that highlights it and the index build. Fix: cap a run of combining marks, or an abstract's length, at ingest. Either changes snapshot content (and so snapshot_hash and index_version), so it needs a decision on the cap.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A decision records the cap (mark-run length or abstract length) and what happens to text over it (truncated, refused, or reported)
- [x] #2 Ingest applies the cap, with a test of a hostile mark-heavy abstract, and the snapshot manifest reports the records it changed
- [x] #3 Tokenizing the largest abstract the cap allows stays under a stated time budget (a CPU-time ratio test like test_a_run_of_marks_is_linear)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Owner decision 2026-10-01: cap runs of combining marks at 8 per base character (drop extras) and abstracts at 20,000 characters (truncate), both trimmed and flagged, never silently.
1. New ingest/caps.py: is_mark (NFKD starts with a non-zero canonical combining class), cap_marks, cap(field, text) -> (text, note), cap_record, cap_records. Marks capped in title and abstract (both indexed and highlighted); length cap on the abstract only. Every claim whose value is trimmed gets the note appended to its evidence (shown on the paper page); the record's own field is trimmed alike so its content_hash and attribution stay consistent.
2. Applied once in snapshot.load_sources, before dedup, so every source's claims compare as before.
3. Manifest key trimmed (sorted ids) written only when non-empty, like withheld: an untouched corpus keeps the same manifest keys; snapshot_built log carries the count.
4. TDD: unit tests for caps (runs, bases, start-of-text run, the five NFKD-only marks, truncation + strip, notes), a build test with a hostile RIS abstract (records, evidence, manifest), and a CPU-time test that tokenizing the largest capped abstract stays within a budget.
5. Decision-026, spec 01 (Normalize step, record schema, manifest), record-schema and snapshots skills.
6. Real data: rebuild from the main checkout's data/cache into a scratch data dir and compare records.jsonl with 2026-09-29-d552baa07aed byte for byte.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Needs an owner decision on the cap. Deferred from the TASK-067 review gate.

Owner decision 2026-10-01 recorded as decision-026: marks capped at 8 per base character (title and abstract), abstracts at 20,000 characters, both trimmed and flagged (claim evidence 'trimmed at ingest (decision-026): ...', manifest key trimmed, build log count). Built in ingest/caps.py, applied once in snapshot.load_sources before dedup. Mark = NFKD starts with a non-zero combining class (922 combining characters plus U+0F73, U+0F75, U+0F81, U+FF9E, U+FF9F).
Tests: backend/tests/unit/ingest/test_caps.py (22): mark classes (exhaustive), both caps, notes, record and claims trimmed alike, attribution kept, RIS evidence url kept first, a snapshot build with a hostile RIS abstract (records, evidence, manifest trimmed), no trimmed key when nothing is trimmed, and AC #3: the largest capped abstract (8 alternating marks per base, 20,000 characters) tokenizes within 20x plain text of that length and under 0.5 s (measured about 0.02 s; the uncapped run 0.46 s at 40k marks).
Real data (byte-identical check): the main checkout's data/cache cloned to a scratch dir; op snapshot build with origin/dev code (05eff53) and with the branch rebased on 4001c40 (1236e96), both into scratch snapshot dirs. Both produced 2026-09-29-d552baa07aed: records.jsonl, merges.csv and conflicts.csv are byte-identical (cmp) to the real snapshot's; the manifest differs only in built_at; trimmed: 0 in the build log. Corpus facts: longest abstract 4,995 characters (longest abstract claim 5,729), longest mark run 1 in any title or abstract, record or claim.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ingest now caps indexed text (decision-026, the owner's decision of 2026-10-01). A run of combining marks in a title or abstract keeps 8 marks per base character, and an abstract keeps 20,000 characters (then trailing whitespace and … are stripped). Both are trimmed and flagged, never silently: each trimmed claim's evidence ends with 'trimmed at ingest (decision-026): <what>' (shown in the paper page's provenance), and the snapshot manifest's 'trimmed' lists the records (only when non-empty). ingest/caps.py runs once in snapshot.load_sources before dedup, on the record and its claims alike, so content_hash and the abstract attribution stay consistent. The worst text the caps allow tokenizes linearly (test). A rebuild of the real 2026-09-29 cache gives the same snapshot, 2026-09-29-d552baa07aed: records.jsonl, merges.csv and conflicts.csv are byte-identical. Spec 01, the record-schema and snapshots skills and CLAUDE.md are updated.
<!-- SECTION:FINAL_SUMMARY:END -->
