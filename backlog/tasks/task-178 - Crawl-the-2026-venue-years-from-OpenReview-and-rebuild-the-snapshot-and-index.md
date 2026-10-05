---
id: TASK-178
title: Crawl the 2026 venue-years from OpenReview and rebuild the snapshot and index
status: In Progress
assignee: []
created_date: '2026-10-05 02:43'
updated_date: '2026-10-05 03:04'
labels:
  - ingest
  - eval
milestone: m-4
dependencies: []
references:
  - docs/specs/01-ingestion.md
  - docs/specs/07-evaluation.md
ordinal: 122000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The first live crawl (2026-09-29) stopped at 2025. The index holds ICLR 2026 (415 records) and ICML 2026 (111) only as imports from the Trust-Evals RIS, and NeurIPS 2026 not at all, so for 2026 a search can only return papers the review's Google Scholar search already found, and the Scholar comparison (TASK-056) matches 530 Scholar records against their own import. The review's criteria centre on 2025-2026. Found 2026-10-04 by TASK-056's review; the owner approved the crawl the same day.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ICLR 2026, ICML 2026 and, if OpenReview has published it, NeurIPS 2026 are crawled; every venueid and presentation string the crawl met is classified or reported, none silently defaulted (01 track taxonomy)
- [ ] #2 A new snapshot and index are built; the snapshot diff against 2026-09-29-d552baa07aed is reviewed and shows the RIS-only 2026 records merging into crawled ones or explains each that does not
- [ ] #3 The coverage report is regenerated on the new index with a sourced official count for each 2026 cell that has one, and the M4 gate result stated (07 section C)
- [ ] #4 The Scholar comparison is re-run on the new index and its RIS-only share reported (07 section B)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Detached crawl from the main checkout: data/crawl-logs/run-2026.sh (op ingest openreview --venue ICLR|ICML|NeurIPS --years 2026, sequential), started 2026-10-05T02:42Z; status lines in data/crawl-logs/status. 2. Read each report for unparseable venueids or presentation strings (spec 01 lists ICLR 2026 Oral and ICML 2026 spotlight as seen but unrecorded) and fix the classifier with recorded fixtures if needed. 3. op snapshot build, op snapshot diff against 2026-09-29-d552baa07aed, op index build, op index parity. 4. op eval coverage; add official 2026 accepted counts to coverage-sources.md where published. 5. Re-run op eval scholar on the new index (TASK-056).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-05 (UTC) crawl, ICLR and ICML read from the cache (NeurIPS 2026 still waiting on OpenReview's hourly budget). ICLR 2026: 22,825 records; main 5,351 accepted / 8,351 rejected / 5,204 withdrawn / 908 desk-rejected; workshop 2,933 / 71 rejected / 6 withdrawn / 1 unknown; unknown_track 0. ICML 2026: 11,078; main 6,341 accepted / 214 opt-in rejected; position 213 / 28 rejected; workshop 4,267 / 5 rejected / 10 unknown; unknown_track 0. Presentation strings met: ICLR 2026 Oral 224 (now oral), ICLR 2026 Poster 5,127; ICML 2026 spotlight 536 and Position Paper Track spotlight 38 (now spotlight); ICML 2026 regular 5,805 and Position Paper Track regular 175 stay unmapped on purpose (not a presentation word; owner to decide poster / stated-none / unmapped), so ICML 2026 reports presentation_unmapped 5,980. An offline replay of the copied 2026 cache with the new table gives the same counts with presentation_unmapped 0 (ICLR) and 5,980 (ICML). Other findings: the one invalid ICLR note is workshop paper xHMNX3l8rx (LLM_Reasoning, accepted), refused because its title holds two U+0002 control characters; the 11 workshop unknowns carry a public .../Workshop/<name>/Submission venueid (undecided); ICLR.cc/2026/Workshop/Re-Align is an empty placeholder group (domain OpenReview.net, no content), so nothing was listed under it; the 81 missing abstracts are all of Workshop/AFA, whose notes have no abstract field. Fixtures: iclr-2026/notes-presentation-conference, icml-2026/notes-presentation-{conference,position-paper-track}, icml-2026/notes-rejected, icml-2026/notes-workshop-submission (trimmed from the cache, scrubbed). No version bump: presentation is outside content_hash and no schema, tokenizer or record-schema input changed. Build the snapshot from a checkout that has this change, or the 798 oral/spotlight records come out null.
<!-- SECTION:NOTES:END -->
