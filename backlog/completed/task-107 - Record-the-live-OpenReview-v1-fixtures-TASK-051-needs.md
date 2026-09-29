---
id: TASK-107
title: Record the live OpenReview v1 fixtures TASK-051 needs
status: Done
assignee:
  - '@codex'
created_date: '2026-09-27 22:46'
updated_date: '2026-09-29 01:35'
labels:
  - ingest
  - testing
milestone: m-4
dependencies: []
ordinal: 104000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Needs OPENREVIEW_USERNAME/PASSWORD. Record: an ICLR 2020 accepted forum and an ICLR 2021 accept decision note; one ?invitation= listing page per v1 year (only 2013, 2014, 2016 and 2023 Blind exist); withdrawn notes for ICLR 2018-2020 and desk-rejected for 2020-2022; an ICLR 2017 workshop-invitation note; the ICLR 2023 Blogposts invitation and a note; NeurIPS 2021-22 withdrawn/desk-rejected listings (or proof empty); a NeurIPS 2022 D&B note; an ICLR 2017 authors string. Extend the adapter table from them; closes TASK-051 AC#2.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All listed fixtures recorded and scrubbed,Adapter table extended; ICLR 2020 accepted papers get status accepted,TASK-051 AC#2 ticked
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Record the missing authenticated OpenReview v1 listing, decision, withdrawn, desk-rejected, D&B, Blogposts, workshop and author-shape evidence through the existing paced client. 2. Scrub every capture, inspect the committed projection for tokens and personal data, and add fixture-driven regression cases before changing adapter behavior. 3. Extend only the live-proven adapter invitation and decision tables, then verify offline crawl/replay and conflict handling. 4. Run targeted ingest tests and the full repository gates; update TASK-051 AC#2 and finalize both tasks only when every required status shape is evidenced.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recorded 27 public responses in the authenticated 2026-09-29 run and committed 25 nonredundant scrubbed fixtures; one role-scoped ICLR 2017 workshop listing was rejected by the public-projection guard and deleted, then replaced with public-by-id evidence. Credential/token/email/profile scans passed. TASK-051 AC #2 is checked and TASK-051 is Done. Validation: 278 targeted OpenReview tests; full backend 5100 passed, 2 skipped; make tooling and make lint passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Recorded and scrubbed every required OpenReview v1 shape, including accepted ICLR 2020/2021 forums, ICLR withdrawn/desk-rejected listings, BlogPosts, NeurIPS empty status listings, D&B and early author/workshop schemas. Extended adapters only from observed values, closed TASK-051 status coverage, and verified privacy plus 5100 backend tests and all lint/tooling gates.
<!-- SECTION:FINAL_SUMMARY:END -->
