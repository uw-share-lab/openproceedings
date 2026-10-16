---
id: TASK-217
title: 'AIES 2026 proceedings: add OJS section rows once published'
status: Done
assignee: []
created_date: '2026-10-10 03:47'
updated_date: '2026-10-16 20:41'
labels:
  - ingest
  - new-venues
milestone: m-4
dependencies: []
ordinal: 150000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
AIES 2026 (Malmö, 2026-10-12..14) was not on ojs.aaai.org on 2026-10-09. When AIES Vol. 9 appears, op ingest ojs --journal AIES stops on the unlisted volume; run scripts/ojs_section_census.py and add its rows to ingest/ojs_sections.toml.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 AIES 2026 rows verified and counts equal; snapshot diff additions only
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16: AIES Vol. 9 is on ojs.aaai.org (issues 743-746). scripts/ojs_section_census.py AIES --refresh (live): complete, 18 pages, completeListSize 716 = 715 live + 1 deleted header; Vol. 7 171 and Vol. 8 279 unchanged; Vol. 9 265 = A26-1 Main Track I 67, A26-2 Main Track II 60, A26-3 Main Track III 57, A26-4 Main Track IV 59 (243 main) + A26-SA Student Abstracts 22 (student_abstract; its one deleted header is counted, never a record); no front matter, no unavailable article. Five [[section]] rows added; no code change (TASK-202's note that AIES 2026 needs only a table row held). op ingest ojs --journal AIES: 0 requests (the census's cache), count_ok for v7, v8, v9.

Snapshot 2026-10-16-03eab0ef56c4 vs 2026-10-11-93c2937e2f29: added 265 (all op:aies:2026:ojs-*), removed 0, rekeyed 0, changed 0, display_only 0, abstract_kind 0, withheld 0; provenance_only 449 = every AIES 2024-2025 record, differing only in provenance fetched_at (all 449) and url (50, the records on a later ListRecords page, whose claims name a new opaque resumptionToken); content hashes and display fields identical. Cause: the census had to run with --refresh (the cached AIES first pages predated Vol. 9), which re-read the AIES chain. AAAI, IASEAI and every other source are untouched. The lead ruled this meets AC #1 (2026-10-16).

Official count: the AIES-26 program PDF's co-chairs' welcome states 1,001 reviewed and 249 accepted (44 oral + 205 poster); OJS publishes 243 main, so 6 accepted papers have no listing (-2.4%, outside the gate). The owner chose (2026-10-16) to leave AIES 2026 main ungated with a cited UNGATED_NOTES entry, following IASEAI 2026; no decision record.

Review round 1 (2026-10-16): the note's first wording ('the 6 accepted papers not in the proceedings have no listing') was wrong. The program's sessions list 244 papers, matched title by title: the 243 OJS main-track records plus #1030 'Knowable Errors: Architectural Foreseeability and the Case for AI Recklessness in Safety-Critical Deployment', which is not on OJS. Its Student Panel lists 25 entries: the 22 OJS student abstracts plus #37, #85 and #105. So only 5 of the chairs' 249 are named nowhere found. The note, coverage-sources.md, spec 07 and the research note now say this. The ruling (ungated) is unchanged. '44 oral' is now '44 orals or discussions', as the source has it.

Review round 2 (2026-10-16): correction to round 1: the 3 Student Panel entries not on OJS are #39 ('Toward Responsible and Sustainable AI Training Data Pipelines'), #85 and #105. #37 is on OJS as 'Pragmatic Explainable Machine Learning'. Per session type, the program lists 28 + 16 = 44 papers in paper and discussion sessions (the chairs' 44) and 200 in poster sessions (against 205), so the 5 unnamed papers are all posters. Note wording now: 'not named in the program or the proceedings'.

AC #1 met (2026-10-16): the five AIES 2026 rows were verified against the census and issue page 746, and the ingest's listed counts equal the table's (count_ok v7-v9). The snapshot diff was accepted by the lead as additions only: 265 added and 0 changed, removed, rekeyed or display-only. The 449 provenance-only records differ only in fetched_at (all) and url (50) because of the --refresh census. AAAI, IASEAI and every other source are untouched. Local checks: make test (9105 passed, 3 skipped; frontend 4953 passed), make lint, make tooling. Index 78d2e70310f3 has parity 0 differences over 173,518 records. Coverage --check passes 81 of 82. Local data/indexes/current was switched b4f335e07e70 -> 78d2e70310f3 after every check passed (rollback: point it back at b4f335e07e70). Follow-ups for the lead to file: include AIES 2026 in op eval openalex's official-abstract audit once TASK-135 allows OpenAlex fetches.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added AIES 2026 (Vol. 9) to ojs_sections.toml from a live census on 2026-10-16: Main Track I-IV 67/60/57/59 (243 main) and Student Abstracts 22. No code change was needed, as TASK-202's note expected. Ingested from the cache, then built snapshot 2026-10-16-03eab0ef56c4: +265 records vs 2026-10-11-93c2937e2f29, no content changes, and 449 AIES 2024-2025 records provenance-only because of the --refresh census. Index 78d2e70310f3 has parity 0. The coverage gate passes 81 of 82, and the report was regenerated. Local current was switched (rollback b4f335e07e70). Official count: the program co-chairs state 249 accepted (44 orals or discussions, 205 posters). The program's sessions list 244 papers (44 + 200): the 243 published main-track papers plus program paper #1030, which is not in the proceedings. The other 5 accepted papers, all posters, are named in neither. The owner left AIES 2026 main ungated, 2026-10-16, with a cited UNGATED_NOTES entry (IASEAI precedent, no decision record). This corrects the first note's 'no listing' wording and the round-1 '#37', which should have been '#39'. Docs: spec 01/07, coverage-sources.md, research note §AIES 2026, README, snapshots skill, learnings addendum.
<!-- SECTION:FINAL_SUMMARY:END -->
