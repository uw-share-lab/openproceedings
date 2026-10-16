---
id: TASK-217
title: 'AIES 2026 proceedings: add OJS section rows once published'
status: In Progress
assignee: []
created_date: '2026-10-10 03:47'
updated_date: '2026-10-16 20:08'
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
- [ ] #1 AIES 2026 rows verified and counts equal; snapshot diff additions only
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16: AIES Vol. 9 is on ojs.aaai.org (issues 743-746). scripts/ojs_section_census.py AIES --refresh (live): complete, 18 pages, completeListSize 716 = 715 live + 1 deleted header; Vol. 7 171 and Vol. 8 279 unchanged; Vol. 9 265 = A26-1 Main Track I 67, A26-2 Main Track II 60, A26-3 Main Track III 57, A26-4 Main Track IV 59 (243 main) + A26-SA Student Abstracts 22 (student_abstract; its one deleted header is counted, never a record); no front matter, no unavailable article. Five [[section]] rows added; no code change (TASK-202's note that AIES 2026 needs only a table row held). op ingest ojs --journal AIES: 0 requests (the census's cache), count_ok for v7, v8, v9.

Snapshot 2026-10-16-03eab0ef56c4 vs 2026-10-11-93c2937e2f29: added 265 (all op:aies:2026:ojs-*), removed 0, rekeyed 0, changed 0, display_only 0, abstract_kind 0, withheld 0; provenance_only 449 = every AIES 2024-2025 record, differing only in provenance fetched_at (all 449) and url (50, the records on a later ListRecords page, whose claims name a new opaque resumptionToken); content hashes and display fields identical. Cause: the census had to run with --refresh (the cached AIES first pages predated Vol. 9), which re-read the AIES chain. AAAI, IASEAI and every other source are untouched. The lead ruled this meets AC #1 (2026-10-16).

Official count: the AIES-26 program PDF's co-chairs' welcome states 1,001 reviewed and 249 accepted (44 oral + 205 poster); OJS publishes 243 main, so 6 accepted papers have no listing (-2.4%, outside the gate). The owner chose (2026-10-16) to leave AIES 2026 main ungated with a cited UNGATED_NOTES entry, following IASEAI 2026; no decision record.

Review round 1 (2026-10-16): the note's first wording ('the 6 accepted papers not in the proceedings have no listing') was wrong. The program's sessions list 244 papers, matched title by title: the 243 OJS main-track records plus #1030 'Knowable Errors: Architectural Foreseeability and the Case for AI Recklessness in Safety-Critical Deployment', which is not on OJS. Its Student Panel lists 25 entries: the 22 OJS student abstracts plus #37, #85 and #105. So only 5 of the chairs' 249 are named nowhere found. The note, coverage-sources.md, spec 07 and the research note now say this. The ruling (ungated) is unchanged. '44 oral' is now '44 orals or discussions', as the source has it.

Review round 2 (2026-10-16): correction to round 1: the 3 Student Panel entries not on OJS are #39 ('Toward Responsible and Sustainable AI Training Data Pipelines'), #85 and #105. #37 is on OJS as 'Pragmatic Explainable Machine Learning'. Per session type, the program lists 28 + 16 = 44 papers in paper and discussion sessions (the chairs' 44) and 200 in poster sessions (against 205), so the 5 unnamed papers are all posters. Note wording now: 'not named in the program or the proceedings'.
<!-- SECTION:NOTES:END -->
