---
id: TASK-155
title: Bound combining-mark runs or abstract length at ingest
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-10-01 12:29'
updated_date: '2026-10-02 04:16'
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
Owner decisions, recorded as decision-026:
- 2026-10-01: a run of combining marks in a title or abstract keeps 8 marks; an abstract keeps 20,000 characters.
- 2026-10-02: a title keeps 1,000 characters. The longest of the snapshot's 95,877 titles, title claims included, is 192.
- All trims are flagged, never silent. The flag is a note in the claim's evidence ('trimmed at ingest (decision-026): ...'), the manifest key trimmed, and the build log: a trimmed count on snapshot_built/snapshot_exists, plus a WARNING snapshot_trimmed when the count is non-zero.

Built in ingest/caps.py and applied once in snapshot.load_sources, before dedup.
- A mark is a character whose NFKD form starts with a non-zero combining class: 922 combining characters in Unicode 15.0, plus U+0F73, U+0F75, U+0F81, U+FF9E and U+FF9F.
- A run ends only at a base: a letter or digit that is not a mark, and that the tokenizer keeps. The tokenizer's own LaTeX mask decides that (normalize.latex_mask, a new public wrapper of _latex_mask: KEEP, or SUB).
- A run is counted in non-starters: the base's own in NFD, plus each mark's in NFKD.
- A run over the cap has its base and marks decomposed in canonical order and keeps its first 8. Every other character is kept as it was, so every Unicode form of the same text trims alike.
- Trimmed and cut text is tidied: a title is whitespace-collapsed, and an abstract is stripped of whitespace and … at both ends.

Tests: backend/tests/unit/ingest/test_caps.py, 54 cases.
- Mark classes, checked exhaustively; run rules for every separator; the accent-macro probe.
- A Hypothesis property over weighted hostile mixes: no token from capped text holds more than 8 consecutive non-starters. It fails the pre-round-2 rule.
- A Hypothesis property that every capped title and abstract still builds a PaperRecord.
- Spacing-accent regressions (´ ¨ ˘ U+1FBD … ℃ !), and form invariance (500 random marked titles against their NFD forms; the stored-order rule split 276).
- The title and abstract length caps, counted in NFKD and cut before the last space that fits. NFC, NFD, NFKC and NFKD forms of a title over 1,000 characters keep one dedup title key. There are fallback cut points, and notes that give the lengths kept.
- The record and its claims trimmed alike, including the claim-only case; attribution and the RIS url kept.
- is_trimmed matches only the note's form.
- A snapshot build with a hostile RIS abstract: records, evidence, the manifest's trimmed key, and the logs on both paths.
- No trimmed key when nothing is trimmed.
- AC #3: the largest capped abstract is 20,000 characters of a Thai base with 8 alternating marks (classes 220 and 230), all one word. It tokenizes within 20x plain text of the same length and under 0.5 s. Measured: about 0.03 s, against 0.014 s for plain text.

Byte-identical check on real data. I cloned the main checkout's data/cache into a scratch dir and ran op snapshot build into scratch snapshot dirs with eight versions of the code:
- origin/dev 05eff53 (the baseline);
- the branch rebased onto 4001c40, at 1236e96;
- eee6cbc, 4e7affb, 854d7bb and 7453910, after each review round;
- 565b5f7, with the title cap;
- e7939b2, with the NFKD-length cut.
Every build produced 2026-09-29-d552baa07aed. records.jsonl, merges.csv and conflicts.csv are byte-identical (cmp) to the real snapshot's. The manifest differs only in built_at. The build log shows trimmed: 0 and no snapshot_trimmed warning.

Corpus facts:
- The longest title is 192 characters.
- The longest abstract is 4,995 characters; the longest abstract claim is 5,729.
- The longest mark run is 1.

Reviews:
- Round 1: security found that invisible separators bypassed a run reset at any non-mark (1.3 s at 72k characters). The other findings (note length, is_trimmed form, claim-only test, logs, docs) are fixed.
- Round 2: code, docs and observability approved. dedup-auditor and track-classifier-auditor found stored-order trimming split title keys across Unicode forms; fixed and confirmed by both. Security found that LaTeX accent-macro letters reset runs (32,000 marks in one word); fixed with the tokenizer's mask, and the property was added.
- Round 3: security found that NFKD-decomposing every character of a trimmed run made spacing accents into double spaces, so one hostile title aborted the build, and … became ... under a marks-only note. Fixed: only marks and the base are decomposed, text is tidied, and the record property was added. Security approved at 85db071.
- Then the owner added the title length cap, which security recommended.

Rejected (security Nit): is_trimmed accepts a forged note suffix in operator-controlled RIS evidence; only the operator controls that file, and security accepted it.

Re-confirms at cbd3fb1:
- Security approved the title cap (3,000 hostile pairs, 0 failures).
- dedup-auditor approved, with two Nits.
  - Nit 1: an NFKD source's split spacing accents can trim differently. Documented as a limit: only canonical forms trim alike.
  - Nit 2: the length caps counted code points as stored, so forms were cut differently.
- track-classifier-auditor raised the same point as a Should: 900 of 900 random over-length pairs split their key, and cutting in NFC still split 24 because U+0F73 and U+0958 never recompose.
- Fixed in 5e5237a, as the auditor and the lead proposed: a length cap counts the NFKD length and cuts before the last space that fits. With no space it cuts before the last base that fits, and with neither, where it fits. The length cut runs before the mark cap. Every form keeps the same words, and this is tested across NFC, NFD, NFKC and NFKD.
- The rebuild at e7939b2 is byte-identical.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ingest now caps indexed text (decision-026, the owner's decisions of 2026-10-01 and 2026-10-02):
- Marks: a run of combining marks in a title or abstract keeps 8 marks. A run ends only at a letter or digit the tokenizer keeps (its own LaTeX mask), so invisible characters and LaTeX markup it joins across can't split a run. A run over the cap has its base and marks decomposed in canonical order before its first 8 are kept, so every Unicode form of the same text trims alike and dedup keys that matched still match. Other characters are kept as they were.
- Length: a title keeps 1,000 characters and an abstract 20,000, counted in NFKD and cut before the last space that fits, so every Unicode form keeps the same words.
- Trimmed text is tidied so the record accepts it.

All trims are flagged, never silent:
- Each trimmed claim's evidence carries 'trimmed at ingest (decision-026): <what>', which the paper page's provenance shows.
- The snapshot manifest's trimmed key lists the records, written only when non-empty.
- The build logs a count, plus a WARNING snapshot_trimmed when it is non-zero.

ingest/caps.py runs once, in snapshot.load_sources, before dedup. Hypothesis properties show that no token from capped text holds more than 8 consecutive non-starters, and that every capped title and abstract still builds a record. The worst capped abstract tokenizes linearly.

A rebuild of the real 2026-09-29 cache gives the same snapshot, 2026-09-29-d552baa07aed: records.jsonl, merges.csv and conflicts.csv are byte-identical. Spec 01, the record-schema, snapshots and logging-standards skills, and CLAUDE.md are updated.
<!-- SECTION:FINAL_SUMMARY:END -->
