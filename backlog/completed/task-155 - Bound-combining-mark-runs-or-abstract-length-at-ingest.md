---
id: TASK-155
title: Bound combining-mark runs or abstract length at ingest
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-10-01 12:29'
updated_date: '2026-10-02 03:28'
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
Owner decision 2026-10-01, recorded as decision-026:
- Marks: a run of combining marks in a title or abstract keeps 8 marks.
- Length: an abstract keeps 20,000 characters.
- Both are trimmed and flagged. The flag is a note in the claim's evidence ('trimmed at ingest (decision-026): ...'), the manifest key trimmed, and the build log: a trimmed count on snapshot_built/snapshot_exists, plus a WARNING snapshot_trimmed when the count is non-zero.

Built in ingest/caps.py and applied once in snapshot.load_sources, before dedup.
- A mark is a character whose NFKD form starts with a non-zero combining class: 922 combining characters in Unicode 15.0, plus U+0F73, U+0F75, U+0F81, U+FF9E and U+FF9F.
- A run ends only at a letter or digit that is not a mark. The tokenizer joins a word across the invisible characters it drops, so those must not end a run.

Tests: backend/tests/unit/ingest/test_caps.py, 37 cases.
- Mark classes, checked exhaustively, and run rules for every separator.
- The token invariant: no token holds more than 2x8+2 consecutive non-starters.
- Both caps, and notes that give the length kept.
- The record and its claims trimmed alike, including a claim trimmed while the record's own text is not; attribution kept, and an RIS url kept first in the evidence.
- is_trimmed matches only the note's own form.
- A snapshot build with a hostile RIS abstract: records, evidence, the manifest's trimmed key, and the logs on both the built and the already-exists paths.
- No trimmed key when nothing is trimmed.
- AC #3: the largest capped abstract is 20,000 characters of a Thai base with 8 alternating marks (classes 220 and 230), all one word. It tokenizes within 20x plain text of the same length and under 0.5 s. Measured: about 0.03 s, against 0.014 s for plain text. The uncapped run is superlinear.

Byte-identical check on real data. I cloned the main checkout's data/cache into a scratch dir and ran op snapshot build into scratch snapshot dirs with three versions of the code:
- origin/dev 05eff53 (the baseline);
- the branch rebased onto 4001c40, at 1236e96;
- the branch after the review fixes, at eee6cbc.
All three produced 2026-09-29-d552baa07aed. records.jsonl, merges.csv and conflicts.csv are byte-identical (cmp) to the real snapshot's. The manifest differs only in built_at. The build log shows trimmed: 0, and no snapshot_trimmed warning.

Corpus facts:
- The longest abstract is 4,995 characters; the longest abstract claim is 5,729.
- The longest mark run in any title or abstract, record or claim, is 1.
- Under the final run rule, 0 titles or abstracts are trimmed.

Review round 1 (code-reviewer, security-reviewer, docs-reviewer, observability-reviewer):
- Security found a bypass. When any non-mark reset a run, 8-mark runs split by ZWJ, U+FE00, U+034F, a soft hyphen, U+20DD or LaTeX \- reached NFC as one run: 1.3 s at 72k characters, about 4x per doubling. Fixed by the run rule above.
- The other findings are fixed too: the note gives the length kept; is_trimmed matches the exact note form; the claim-only trim is tested; both log paths carry trimmed and the warning; the docs are as-built.
- Deferred to the owner: a title length cap. Security proposed 1,000 code points. The run rule already makes title cost linear, and the owner's decision covers abstracts only.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ingest now caps indexed text (decision-026, the owner's decision of 2026-10-01):
- Marks: a run of combining marks in a title or abstract keeps 8 marks. A run ends only at a letter or digit, so marks split by characters the tokenizer joins across still count as one run.
- Length: an abstract keeps 20,000 characters, then trailing whitespace and … are stripped.

Both trims are flagged, never silent:
- Each trimmed claim's evidence carries 'trimmed at ingest (decision-026): <what>', which the paper page's provenance shows.
- The snapshot manifest's trimmed key lists the records, written only when non-empty.
- The build logs a count, plus a WARNING snapshot_trimmed when it is non-zero.

ingest/caps.py runs once, in snapshot.load_sources, before dedup, on the record and its claims alike, so content_hash and the abstract attribution stay consistent. No token formed from capped text holds a long run of marks (tested), and the worst capped abstract tokenizes linearly (tested).

A rebuild of the real 2026-09-29 cache gives the same snapshot, 2026-09-29-d552baa07aed: records.jsonl, merges.csv and conflicts.csv are byte-identical. Spec 01, the record-schema, snapshots and logging-standards skills, and CLAUDE.md are updated.
<!-- SECTION:FINAL_SUMMARY:END -->
