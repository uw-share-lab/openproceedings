---
id: TASK-201
title: >-
  Dedup properties: a pool strategy that reaches import title merges beside
  crawled abstract holders, and a check against over-yielding
status: Done
assignee: []
created_date: '2026-10-06 04:43'
updated_date: '2026-10-06 19:03'
labels:
  - ingest
  - dedup
  - testing
milestone: m-4
dependencies: []
ordinal: 144000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The gate on the v0.2.0 nightly fix (2026-10-06, PR for fix/dedup-yield-property) found that test_dedup_props.py's decision-045 property detects a broken yield rule only through its @examples: with them removed, mutations 'never yield' and 'a partner with any abstract keeps the merge' pass all 2,000 ci examples, because the generic pool strategy rarely puts same-title imports next to crawled records holding their abstract (the nightly needed 50,000 examples). The property also checks only one direction: a rule that yields too often (any instead of all) passes every test.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A pool strategy (or a targeted one) reaches decision-045's shapes at the ci profile: the two mutations above fail the property without its @examples
- [x] #2 A test or property fails when the import yields although a title partner holds its abstract
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. yields() strategy in test_dedup_props.py: one venue-year, an import with its own abstract, same-title partners (crawled notes of every track/status, forum-id RIS rows, a listing) holding its abstract, another or none, and crawled records of other titles holding it (incl. workshop, rejected, a RIS row only); fed to decision-045's property as one_of(pools, yields()), pools untouched.
2. Over-yield: unit tests in test_dedup.py where a partner holds the abstract beside one that doesn't (any-instead-of-all), and a property direction if cheap.
3. Prove in a scratch worktree: with the property's @examples removed, mutations never-yield, partner-with-any-abstract and any-instead-of-all fail at HYPOTHESIS_PROFILE=ci; time the file at ci before/after.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
yields() strategy in test_dedup_props.py (one venue-year: an import with its own abstract; 1-2 same-title partners: a crawled note of any track/status, a forum id's RIS row, or a crawled listing, keeping its abstract, another or none; 0-2 other-title holders: a note (any track/status), a listing, or a note whose RIS row alone keeps it; plus noise). decision-045's property draws from one_of(pools, yields()); pools and records are unchanged (test_reconcile imports them).
Mutation matrix in a scratch worktree, the property's three @examples removed, HYPOTHESIS_PROFILE=ci, fresh .hypothesis each run: unmutated passes; never-yield FAILS (property); partner-with-any-abstract-keeps-the-merge FAILS (property); any-instead-of-all and no-partner-check pass the property (the record is the same, only the merge rule moves to step 3) but FAIL test_dedup.py: the two new over-yield unit tests (and test_a_title_partner_set_aside_by_the_track_rule_still_keeps_the_title_merge for any-instead-of-all; 7 failures for no-partner-check).
Runtime: test_dedup_props.py at ci -p no:randomly 101.7 s before, 93.3 s after (machine noise; the property's share ~9-10 s). Ingest unit dir 1675 passed; make tooling green.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
decision-045's property now draws from one_of(pools, yields()), a strategy that builds same-title imports beside crawled holders of their abstract (set-aside workshop and rejected rivals included), so 'never yield' and 'a partner with any abstract keeps the merge' fail at the ci profile with the @examples removed. Over-yielding (yielding although a title partner keeps the abstract) gives the same record by the wrong rule, so two unit tests in test_dedup.py pin the title_venue_year rule; they kill any-instead-of-all and a dropped partner check. Shared strategies unchanged; ci runtime of the file unchanged within noise. dedup-rules skill updated.
<!-- SECTION:FINAL_SUMMARY:END -->
