---
id: TASK-056
title: Scholar comparison report
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-10-05 08:38'
labels:
  - eval
milestone: m-4
dependencies:
  - TASK-054
  - TASK-030
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 07 §B (scholar-comparison-protocol skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every disagreement classified; 'our bug' class is 0
- [x] #2 docs/results/<date>-scholar-comparison.md with review.csv for human calls
- [x] #3 Report notes decision-002: in Scholar mode the PoP string main-2-pop reads unquoted multi-word | items as phrases, unlike Google Scholar; its differences are classed compat_reading, not misses
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. eval/scholar_compare.py: the reusable core (read a RIS set, match by spec 01's merge rules, scope, classify every disagreement), pure functions TASK-177 calls too.
2. eval/scholar_report.py: review rows (unresolved + a tenth spot check), Markdown report, atomic write that never erases a person's calls.
3. op eval scholar in cli.py (--ris, --query-file/--name/--query, --years, --venues, --index, --out, --date, --notes, --check).
4. Unit tests on hand-built fixtures, one per class; CLI test on a small built index.
5. Real run on index 05a0541717f6 against the mended Trust-Evals export; commit docs/results/2026-10-04-scholar-comparison.md and its review rows.
6. Specs 07 §B and 08 §CLI, README, CLAUDE.md, the protocol skill, agent and command as built; a learning entry.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-27 re-scope (owner): deferred until the full system (M3b UI + M4 crawlers) is built.

2026-10-04 (worktree task-056-scholar-report, off feat/review-comparison-tools): built and run.

AC 2 and 3 are met. AC 1: our_bug is 0 on all three strings, and every disagreement has an automated class except 6 Scholar-only records per string that the corpus holds without an abstract (ICML 2026), which are unsettled. Those, the 3 coverage_gap rows (their links point to Springer, NeurIPS slides and IEEE: probably Scholar's venue, not a gap) and the scholar_missed rows (6, 6 and 0) await a person in docs/results/2026-10-04-scholar-comparison-review.csv (39 unresolved rows, 530 spot-check rows). AC 1 is left unticked until those are filled in or the owner accepts them as classified.

Real run (index 05a0541717f6, scope 2020-2026, Scholar set 1,810 papers in scope of 1,834 records): main-7-most-updated 27 results, 21 in both, 1,789 only Scholar (1,748 full_text, 32 stemming, 3 coverage_gap, 6 unsettled), 6 only openproceedings (scholar_missed); main-7-dollar 67 results, 51 in both, 16 only openproceedings (10 compat_reading, 6 scholar_missed); main-2-pop 88 results, 65 in both, 23 only openproceedings (all compat_reading). No filtered rows.

For the main session to file (no ids created here): (a) owner decision on the stemming stand-in (inflection only; quoted words also get forms; it pairs suite with suit) and whether to use a published stemmer; (b) the 6 ICML 2026 records with no abstract in the corpus; (c) a person to fill the review file; (d) optional: a full per-row classification file beside the report; (e) TASK-177 calls scholar_compare.read_ris / MatchIndex.build / scope_and_match / compare_query, and should build MatchIndex once per loaded index (about 15 s for 95,877 records) rather than per request.

2026-10-04, after review (REQUEST CHANGES): fixed on the same branch. The report now says what each match rests on: of 1,807 matched papers, 1,277 match a crawled record and 530 a record only this set's own import put in the index (ICLR 2026 415, ICML 2026 111, ICLR 2025 3, ICLR 2024 1); the index has no crawled 2026 record, so nothing can be only in openproceedings there. Denominator is now 1,817 papers in scope (7 records with no venue whose title an in-scope record has are kept as unsettled). Filters are judged before the text; full_text is no longer called a lower bound, and a prefix-reading sensitivity figure is printed (0 of 1,713 for main-7-most-updated). 37 RIS-only matches share a title with another index record and are unsettled (1 in the same venue and year: op:iclr:2024:iclr-c3eb94d149aea08c28505d1e5234a21a and op:iclr:2024:QHROe7Mfcb are one paper under two ids).

New headline (main-7-most-updated): 27 results, 21 in both, 1,796 only Scholar (1,713 full_text = 94.3%, of them 1,247 crawled and 466 RIS-only; 30 stemming; 3 coverage_gap; 50 unsettled), 6 only openproceedings; our_bug 0 on all three strings. Review file: 689 rows, 168 unresolved.

More for the main session to file: (f) dedup miss: the RIS import's iclr-c3eb94d1… record was not merged with OpenReview's QHROe7Mfcb (same title, ICLR 2024); (g) 36 RIS-only ICLR 2026 records share a title with a 2025 NeurIPS/ICML/ICLR record: probably a wrong mended venue or year in the import; (h) crawl 2026, or rebuild the comparison index without the import, before the RIS-only rows are cited.

2026-10-05: re-run on index 5ec5231adae2 after the 2026 crawl (TASK-178): 1,800 of 1,807 matches now rest on a crawled record, 7 RIS-only; report docs/results/2026-10-05-scholar-comparison.md. The 2026-10-04 report is kept as the run on index 05a0541717f6.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
op eval scholar compares a Scholar RIS set with the review's strings on one pinned index (eval/scholar_compare.py core, eval/scholar_report.py writer), matching by forum id, proceedings id in its venue-year, then title with venue and year, and classing every disagreement in the protocol's order with the reference engine. Final run on index fd13d8d27535 (docs/results/2026-10-05-scholar-comparison.md): 1,813 Scholar papers in scope, 1,805 matched, all to crawled records; main-7-most-updated returns 33 (21 in both, 12 only here), the $ string 101 (51 in both, 50 only here); 1,752 Scholar-only papers (96.6%) are full_text; our_bug 0. The 48 unresolved rows of the review file carry calls made by an AI assistant at the owner's direction (stated in the report's notes), and the report's Human calls section reads them back: every disagreement classified. The stemming stand-in is decision-038. Two review rounds; the 2026-10-04 run on 05a0541717f6 is kept as history.
<!-- SECTION:FINAL_SUMMARY:END -->
