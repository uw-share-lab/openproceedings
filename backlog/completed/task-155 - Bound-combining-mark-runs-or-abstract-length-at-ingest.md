---
id: TASK-155
title: Bound combining-mark runs or abstract length at ingest
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-10-01 12:29'
updated_date: '2026-10-02 03:50'
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
- A run ends only at a base: a letter or digit that is not a mark, and that the tokenizer keeps. The tokenizer's own LaTeX mask decides that (normalize.latex_mask, a new public wrapper of _latex_mask: KEEP, or SUB).
- A run is counted in NFKD non-starters, the base's own included.
- A run over the cap is rewritten in its NFKD form (marks in canonical order) and keeps its first 8, so every Unicode form of the same text trims alike.

Tests: backend/tests/unit/ingest/test_caps.py, 44 cases.
- Mark classes, checked exhaustively, and run rules for every separator.
- The accent-macro probe.
- A Hypothesis property over weighted random mixes of bases, marks, invisible characters, LaTeX macros, separators and math: no token from capped text holds more than 8 consecutive non-starters. It passes under the pr and ci profiles, and it fails the pre-round-2 rule.
- Precomposed bases, and form invariance (500 random marked titles against their NFD forms keep one dedup title key; the stored-order rule split 276).
- Both caps, and notes that give the length kept.
- The record and its claims trimmed alike, including the claim-only case; attribution and the RIS url kept.
- is_trimmed matches only the note's form.
- A snapshot build with a hostile RIS abstract: records, evidence, the manifest's trimmed key, and the logs on both paths.
- No trimmed key when nothing is trimmed.
- AC #3: the largest capped abstract is 20,000 characters of a Thai base with 8 alternating marks (classes 220 and 230), all one word. It tokenizes within 20x plain text of the same length and under 0.5 s. Measured: about 0.03 s, against 0.014 s for plain text.

Byte-identical check on real data. I cloned the main checkout's data/cache into a scratch dir and ran op snapshot build into scratch snapshot dirs with five versions of the code:
- origin/dev 05eff53 (the baseline);
- the branch rebased onto 4001c40, at 1236e96;
- after review round 1, at eee6cbc;
- after the auditors' fixes, at 4e7affb;
- after security round 2, at 854d7bb.
Every build produced 2026-09-29-d552baa07aed. records.jsonl, merges.csv and conflicts.csv are byte-identical (cmp) to the real snapshot's. The manifest differs only in built_at. The build log shows trimmed: 0 and no snapshot_trimmed warning.

Corpus facts:
- The longest abstract is 4,995 characters; the longest abstract claim is 5,729.
- The longest mark run is 1.

Review round 1 (code, security, docs, observability):
- Security found that invisible separators (ZWJ, U+FE00, U+034F, a soft hyphen, U+20DD, LaTeX \-) bypassed a run reset at any non-mark: 1.3 s at 72k characters, about 4x per doubling. Fixed: a run ends only at a letter or digit.
- The other findings are fixed: the note gives the length kept; is_trimmed matches the exact note form; the claim-only trim is tested; both log paths carry trimmed and the warning; the docs are as-built.

Round 2:
- code, docs and observability approved.
- dedup-auditor and track-classifier-auditor found that keeping marks in stored order split dedup title keys between Unicode forms of one title. Fixed by the NFKD count and canonical-order trim.
- Security round 2 found that the letter of a LaTeX accent macro around an invisible character (\H{ZWJ}) still reset the run, though the tokenizer drops it: 32,000 marks in one word, 0.37 s at 52k characters. Fixed by the tokenizer-mask base rule and the property.

Deferred to the owner (the lead is asking): a title length cap. Security recommends 1,000 code points as a backstop for bypasses not yet found.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ingest now caps indexed text (decision-026, the owner's decision of 2026-10-01):
- Marks: a run of combining marks in a title or abstract keeps 8 marks. A run ends only at a letter or digit the tokenizer keeps (its own LaTeX mask), so invisible characters and LaTeX markup it joins across can't split a run. Runs are counted in NFKD, and a run over the cap is trimmed in canonical order, so every Unicode form of the same text trims alike and dedup keys that matched still match.
- Length: an abstract keeps 20,000 characters, then trailing whitespace and … are stripped.

Both trims are flagged, never silent:
- Each trimmed claim's evidence carries 'trimmed at ingest (decision-026): <what>', which the paper page's provenance shows.
- The snapshot manifest's trimmed key lists the records, written only when non-empty.
- The build logs a count, plus a WARNING snapshot_trimmed when it is non-zero.

ingest/caps.py runs once, in snapshot.load_sources, before dedup, on the record and its claims alike. A Hypothesis property shows no token from capped text holds more than 8 consecutive non-starters, and the worst capped abstract tokenizes linearly.

A rebuild of the real 2026-09-29 cache gives the same snapshot, 2026-09-29-d552baa07aed: records.jsonl, merges.csv and conflicts.csv are byte-identical. A title length cap is with the owner. Spec 01, the record-schema, snapshots and logging-standards skills, and CLAUDE.md are updated.
<!-- SECTION:FINAL_SUMMARY:END -->
