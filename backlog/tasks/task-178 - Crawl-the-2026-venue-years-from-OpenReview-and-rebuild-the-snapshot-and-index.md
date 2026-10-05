---
id: TASK-178
title: Crawl the 2026 venue-years from OpenReview and rebuild the snapshot and index
status: In Progress
assignee: []
created_date: '2026-10-05 02:43'
updated_date: '2026-10-05 05:19'
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
- [x] #3 The coverage report is regenerated on the new index with a sourced official count for each 2026 cell that has one, and the M4 gate result stated (07 section C)
- [x] #4 The Scholar comparison is re-run on the new index and its RIS-only share reported (07 section B)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Detached crawl from the main checkout: data/crawl-logs/run-2026.sh (op ingest openreview --venue ICLR|ICML|NeurIPS --years 2026, sequential), started 2026-10-05T02:42Z; status lines in data/crawl-logs/status. 2. Read each report for unparseable venueids or presentation strings (spec 01 lists ICLR 2026 Oral and ICML 2026 spotlight as seen but unrecorded) and fix the classifier with recorded fixtures if needed. 3. op snapshot build, op snapshot diff against 2026-09-29-d552baa07aed, op index build, op index parity. 4. op eval coverage; add official 2026 accepted counts to coverage-sources.md where published. 5. Re-run op eval scholar on the new index (TASK-056).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-05 (UTC) crawl, ICLR and ICML read from the cache (NeurIPS 2026 still waiting on OpenReview's hourly budget). ICLR 2026: 22,825 records; main 5,351 accepted / 8,351 rejected / 5,204 withdrawn / 908 desk-rejected; workshop 2,933 / 71 rejected / 6 withdrawn / 1 unknown; unknown_track 0. ICML 2026: 11,078; main 6,341 accepted / 214 opt-in rejected; position 213 / 28 rejected; workshop 4,267 / 5 rejected / 10 unknown; unknown_track 0. Presentation strings met: ICLR 2026 Oral 224 (now oral), ICLR 2026 Poster 5,127; ICML 2026 spotlight 536 and Position Paper Track spotlight 38 (now spotlight); ICML 2026 regular 5,805 and Position Paper Track regular 175 stay unmapped on purpose (not a presentation word; owner to decide poster / stated-none / unmapped), so ICML 2026 reports presentation_unmapped 5,980. An offline replay of the copied 2026 cache with the new table gives the same counts with presentation_unmapped 0 (ICLR) and 5,980 (ICML). Other findings: the one invalid ICLR note is workshop paper xHMNX3l8rx (LLM_Reasoning, accepted), refused because its title holds two U+0002 control characters; the 11 workshop unknowns carry a public .../Workshop/<name>/Submission venueid (undecided); ICLR.cc/2026/Workshop/Re-Align is an empty placeholder group (domain OpenReview.net, no content), so nothing was listed under it; the 81 missing abstracts are all of Workshop/AFA, whose notes have no abstract field. Fixtures: iclr-2026/notes-presentation-conference, icml-2026/notes-presentation-{conference,position-paper-track}, icml-2026/notes-rejected, icml-2026/notes-workshop-submission (trimmed from the cache, scrubbed). No version bump: presentation is outside content_hash and no schema, tokenizer or record-schema input changed. Build the snapshot from a checkout that has this change, or the 798 oral/spotlight records come out null.

2026-10-05, reports on the new index (branch task-178-rebuild-reports): snapshot 2026-10-05-47d4e190ca81 (hash 47d4e190ca816d89ff22bc88206e5e730929c14efbaa5a5213e5b36afde8a866, 133,632 records; was 95,877 in 2026-09-29-d552baa07aed), index 5ec5231adae2 (tokenizer 3, schema 3). Snapshot diff as reviewed by the session lead: 38,133 ids added (all 2026), 378 removed (ICLR 2026 RIS-only iclr-<hash> ids merged into crawled records), no crawled record removed, no track/status/venue/year change on kept ids, 27 titles and 6 abstracts changed; 7 RIS-only records remain.

Coverage (AC 3): docs/results/2026-10-05-coverage.md. M4 gate PASS: 44 of 45 gated cells within 1%, 0 gaps, 1 owner-accepted exception (ICLR 2013 main, decision-016). New official row: ICLR 2026 main 5,357 (final fact sheet; the PC retrospective says 5,355; no proceedings index read), indexed 5,354, delta -3. ICML 2026 main has no row: the fact sheet's 6,552 is main plus position and no source states the main track alone, so a derived 6,339 is not recorded (reported as no source; index 6,341 + 213 = 6,554 vs 6,552). NeurIPS 2026: nothing public. The official numbers were read by the session lead on 2026-10-05; this session did not re-fetch them. The report gained a section listing accepted records only an imported set holds: ICLR 2024 main 1, ICLR 2025 main 3, ICLR 2026 main 3; without them the deltas are 0, 0 and -6.

Scholar comparison (AC 4): docs/results/2026-10-05-scholar-comparison.md and -review.csv (589 rows, 51 unresolved). 1,815 papers in scope; 1,807 matched: 1,800 to a crawled record, 7 RIS-only (was 1,277 / 530). our_bug 0 on all three strings. main-7-most-updated: 33 results, 21 in both, 12 only openproceedings (6 of them 2026), full_text 1,753 (96.6%; 6 RIS-only), stemming 32, coverage_gap 3, unsettled 6. main-7-dollar: 101 results, 51 in both, 50 only openproceedings (34 from 2026; 38 compat_reading, 12 scholar_missed). main-2-pop: 114 results, 65 in both, 49 only openproceedings (26 from 2026; all compat_reading).

The 7 RIS-only records are all second copies of a crawled paper that dedup did not merge: iclr-c3eb94d1 = QHROe7Mfcb (ICLR 2024; same title, both hold a ris claim); iclr-1b126cc3 = roNSXZpUDN, iclr-a07e87ec = CkgKSqZbuC, iclr-a6610efd = EwFJaXVePU (ICLR 2025) and iclr-2aa3da3c = OutljIofvS, iclr-dcbdb995 = 3CPzUWIoNf (ICLR 2026): the imported title lost its math symbol (tau, R^2, infinity, A^2), so the title keys differ; iclr-6b41e04c is probably CwoM9T55lG (ICLR 2026) under an earlier title. The 36 ICLR 2026 imports that shared a title with a 2025 record all merged into crawled ICLR 2026 accepted records; the 2025 records are earlier versions of the same work (24 workshop papers only, 10 rejected submissions only, 2 both), correctly separate: the import's venue and year were right.

2026-10-05, later: ICML 2026 main now has a row, replacing the 'no row' above (owner's request). It is a rule-3 list count by the session lead: 6,554 OpenReview-linked posters on the virtual-site paper list (74 TMLR/JMLR journal-track posters excluded) minus the 213 on the position-papers listing = 6,341, equal to the indexed 6,341. The fact sheet's combined 6,552 is kept under Disagreements. Gate on 5ec5231adae2: PASS, 45 of 46 gated cells within 1% plus the ICLR 2013 exception; coverage-sources.md has 46 rows.
<!-- SECTION:NOTES:END -->
