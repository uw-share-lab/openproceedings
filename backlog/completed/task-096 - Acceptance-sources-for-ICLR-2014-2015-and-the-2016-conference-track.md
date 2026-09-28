---
id: TASK-096
title: 'Acceptance sources for ICLR 2014, 2015 and the 2016 conference track'
status: Done
assignee:
  - '@codex'
created_date: '2026-09-27 20:49'
updated_date: '2026-09-28 01:07'
labels:
  - ingest
milestone: m-4
dependencies: []
priority: medium
ordinal: 93000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-013 crawls from 2013, but OpenReview can't answer these ICLR years (docs/research/2026-09-27-openreview-and-proceedings-facts.md): 2014's 88 notes all say 'submitted, no decision' with no decision notes; 2015 has no OpenReview group; 2016 has only the workshop track (125 notes, no decisions). Find a citable accepted-paper list (iclr.cc archive pages, proceedings.iclr.cc if it covers these years) and add it as a spec 01 source, or record them as coverage gaps.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each of ICLR 2014, 2015 and 2016 has a named source in spec 01 §Sources, or is listed as a gap on the coverage page with the reason
- [x] #2 Any new source has recorded fixtures (decision-004) and a proceedings-style accepted-only status rule
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Record and scrub the public iclr.cc archive/listing pages that cover ICLR 2014-2016. 2. Add an accepted-only ICLR proceedings adapter and offline replay path, starting with failing fixture-backed tests. 3. Document source coverage and verify focused/full gates.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented the public iclr.cc archive as source iclr_archive for 2014-2016. Verified live unique accepted-conference totals 35/31/80; the adapter records those stated totals, reports count mismatches, preserves 2014 Google Sites and 2015/2016 DokuWiki shapes, emits accepted/main records with target-derived identity, and replays offline.

Validation: make lint passed; focused post-review suite 473 passed; full make test passed (4119 backend, 2 opt-in skips, 304 frontend); make tooling passed; independent review found no remaining findings.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added the accepted-only ICLR 2014-2016 archive source, stable provenance/identity, recorded scrubbed fixtures, CLI/cache replay, schema/contracts, tests and documentation. Verified by the full lint, test and tooling gates plus independent review.
<!-- SECTION:FINAL_SUMMARY:END -->
