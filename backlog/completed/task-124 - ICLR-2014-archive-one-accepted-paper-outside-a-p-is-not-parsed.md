---
id: TASK-124
title: 'ICLR 2014 archive: one accepted paper outside a <p> is not parsed'
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 20:47'
updated_date: '2026-09-29 20:47'
labels:
  - ingest
  - bug
milestone: m-4
dependencies: []
priority: high
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The first full crawl's coverage trial (2026-09-29) had ICLR 2014 main at 34 of 35 (count_ok false: the page lists 35). The 2014 Google Sites page puts one entry, 'Unit Tests for Stochastic Optimization' (arXiv 1312.6055), in a bare <span><b><a> with its authors in a following <div><i>, instead of the <p> title and author paragraphs the other 34 use; _google_sites_entries only accepts a paper anchor inside a <p>, so it is skipped.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 _google_sites_entries also reads a paper anchor with no <p> ancestor, taking as authors only the first inline element of the block after the anchor's inline wrapper, and none when that block opens with loose text; elements are located by identity
- [x] #2 Compact cases in the live page's markup and nesting (later entries inside the block; twin wrappers; loose text) are tested, the decoy-link cases still hold, and on the cached live page the parser gives 35 entries with correct authors (checked by hand; the recorded fixture is trimmed to 2 entries)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
ICLR 2014's archive parser now reads a paper link outside any <p>: its authors are the first inline element of the block after the link's inline wrapper, and none if that block opens with loose text. The live page sets one of its 35 papers, 'Unit Tests for Stochastic Optimization' (arXiv 1312.6055), as a bare <span><b><a> with authors in the next <div><i>, a <div> that then holds every later entry; it was dropped, so the trial counted 34 of 35. Checked by hand on the cached live page: 35 entries, the other 34 identical to before, and the new one with Tom Schaul, Ioannis Antonoglou and David Silver (the recorded fixture is trimmed to 2 entries, so no test pins 35). A first version took the whole <div> (~40 authors on the live page) while its compact test passed; the tests now use the page's nesting, twin wrappers (elements are found by identity, not value, which had raised RecursionError) and a block opening with text.
<!-- SECTION:FINAL_SUMMARY:END -->
