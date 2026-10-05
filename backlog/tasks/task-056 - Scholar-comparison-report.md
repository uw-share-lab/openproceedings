---
id: TASK-056
title: Scholar comparison report
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-10-05 02:21'
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
- [ ] #1 Every disagreement classified; 'our bug' class is 0
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
<!-- SECTION:NOTES:END -->
