---
id: TASK-250
title: >-
  op eval openalex: author-check the 123 AAAI 1980-2008 'differs' records and
  add AIES 2026, once TASK-135 allows OpenAlex requests
status: Done
assignee: []
created_date: '2026-10-16 22:50'
updated_date: '2026-10-28 06:15'
labels:
  - eval
  - new-venues
dependencies:
  - TASK-135
priority: low
ordinal: 163000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-235 (PR #152, docs/results/2026-10-16-openalex-audit.md) compared OpenAlex with aaai_library for AAAI 1980-2008: of 1,131 records, 123 (10.9%) 'differs'. Title matches aren't checked against authors, so some may be another paper attached by the title route. The existing author check needs about 3 live OpenAlex requests. TASK-217 (PR #155) added AIES 2026 (265 records, official abstracts from OJS); the audit doesn't cover it yet. Both were deferred because OpenAlex's Terms of Service (revised 2026-10-02) conflict with the CC0 statement decision-049 relied on, and the owner directed no new OpenAlex requests until TASK-135 is answered (2026-10-16).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The author check runs on the 123 'differs' records and the report splits them into wrong-paper attaches and genuinely different texts, with tests
- [x] #2 op eval openalex covers AIES 2026, and the audit is re-run on the then-current snapshot and cited from spec 07 §G
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Judge each aaai_library differs attach by OpenAlex's authors (title route's _judge, authors_url): wrong vs agree vs unverifiable; render the split with text shape. 2. Add AIES 2026 to AUDITED. 3. Offline replay on the current snapshot, then one live run for the uncached requests; write the 2026-10-28 report offline; cite it from spec 07 §G and docs/README.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-28: the owner lifted the 2026-10-16 hold on new OpenAlex requests for this task, ahead of TASK-135's answer. Requests use a generic user agent and never send the owner's address (the polite-pool mailto is not used).

Snapshot: 2026-10-16-03eab0ef56c4 (index 78d2e70310f3, current on dev at the run). Offline replay first: 0 requests, every 2026-10-16 figure unchanged. Live run (keyless, crawl.openalex_fetcher, no contact address): 9 OpenAlex requests (6 DOI batches for AIES 2026's 265 records, 3 author batches for the 123 differs works); the committed report was rendered with --offline (0 requests) and reproduces byte for byte.
Split of the 123 differs: 122 genuinely different texts of the same paper (shared author surname; 63 open with the same 5 search tokens, 86 OpenAlex texts >=1.5x AAAI's, 47 both, median 2.4x); 1 looks wrong by the surname rule (op:aaai:1998:dblp-Pedersen98a, pedersen/pederson), a near spelling, likely the same first author (by a character ratio, not checked by a person); 0 unverifiable. The 2026-10-11 ruling stands.
AIES 2026 on the DOI route: 262/265 exact (98.9%), 1 differs, 2 no_openalex. DOI route total 2,387 compared, 84.8% exact or near-exact.
Review: code-reviewer, review-methodologist, docs-reviewer + observability-reviewer (rounds 1-2), one UX/usability/a11y pass on the /coverage link; 17 findings (8 should, 9 nit), shoulds all fixed. Tests: test_openalex_audit.py 45 passed, coverage-report.test.tsx 32 passed, make lint, make tooling; full make test not run locally (machine load 150-190; lead's direction), CI runs it. Rebased onto dev after #212 (PR #211).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
op eval openalex now author-checks every aaai_library 'differs' text (the title route's _judge, one request per 50 works) and splits it: of 123, 122 genuinely different texts of the same paper (47 open alike and run >=1.5x as long), 1 looks wrong but is a near-spelled surname (Pedersen98a, likely the same author), 0 unverifiable. AIES 2026 joins the DOI route: 262/265 exact, 1 differs, 2 with no work; DOI route 2,387 compared, 84.8% exact or near-exact. Report docs/results/2026-10-28-openalex-audit.md on snapshot 2026-10-16-03eab0ef56c4, cited from spec 07 §G, README, docs/README and /coverage. 9 OpenAlex requests, keyless, no contact address.
<!-- SECTION:FINAL_SUMMARY:END -->
