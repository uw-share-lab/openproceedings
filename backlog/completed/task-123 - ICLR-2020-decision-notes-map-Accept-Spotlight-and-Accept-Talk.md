---
id: TASK-123
title: 'ICLR 2020 decision notes: map Accept (Spotlight) and Accept (Talk)'
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 20:38'
updated_date: '2026-09-29 20:38'
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
The first full crawl's coverage trial (2026-09-29) found ICLR 2020 main at 531 accepted against the official 687 (-22.7%), with exactly 156 records status unknown. The v1 adapter's ICLR 2020 decision table maps only 'Accept (Poster)' and 'Reject', but the cached decision notes hold 1,526 Reject, 531 Accept (Poster), 108 Accept (Spotlight) and 48 Accept (Talk): 108 + 48 = 156. Classification gap, not a crawl gap.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The ICLR 2020 decision table maps Accept (Spotlight) to accepted/spotlight and Accept (Talk) to accepted/oral
- [x] #2 Recorded, scrubbed live fixtures of a Spotlight and a Talk decision (with their submissions) are ingested as accepted with that presentation; the venueid table covers them
- [x] #3 The ICLR 2018 and 2019 tables are checked against the crawl's full tally (every decision note is read) and miss no accept form; for 2021, whose crawl reads a decision note only when content.venue leaves a forum open, the docs say which forms are verified and that the rest are unseen
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
ICLR 2020's decision table now maps Accept (Spotlight) → accepted/spotlight and Accept (Talk) → accepted/oral. The first full crawl's coverage trial had ICLR 2020 main at 531 of 687 (−22.7%) with 156 status-unknown records; the cached decision notes hold 108 spotlights and 48 talks (156). Recorded, scrubbed live forums of each (HklSeREtPB, BkgzMCVtPB; public-projection checked before saving) are ingested as accepted with their presentation, with venueid-table rows. ICLR 2018 and 2019, whose decision notes are all read, miss no accept form in the full tally. ICLR 2021 decides from content.venue first and reads a decision note only for a forum venue leaves open, so its tally sees only Reject; Accept (Poster) is verified on paper 2910 and the docs say other 2021 accept forms are unseen. The openreview-api skill now says a table's strings come from a whole venue-year's tally, and the research note holds the tally.
<!-- SECTION:FINAL_SUMMARY:END -->
