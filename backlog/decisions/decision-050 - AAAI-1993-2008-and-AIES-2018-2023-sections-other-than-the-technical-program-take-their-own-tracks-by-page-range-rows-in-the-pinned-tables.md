---
id: decision-050
title: >-
  AAAI 1993-2008 and AIES 2018-2023 sections other than the technical program
  take their own tracks, by page-range rows in the pinned tables
date: '2026-10-10 15:20'
status: accepted
---
## Context

Milestone B (decision-049) made every AIES 2018–2023 Crossref record `main` (Crossref has no sections) and kept
AAAI 1980–2008's doubtful entries as `main` papers. The default search therefore counted AIES student abstracts
and keynotes and AAAI's student abstracts, consortium, demo, IAAI and robot entries as main papers, while OJS gives
the same kinds their own tracks from 2010 (AAAI) and 2024 (AIES). TASK-224/225/226 gathered the evidence (Wayback
copies of the official aaai.org contents pages for AAAI 1993–2008; page position alone for AIES, whose ACM DL blocks
bots) and the controller ruled for the owner on 2026-10-10. Options considered: per-key track rows for every
entry (exact but ~1,000 rows, and a row can't show a section); page-count thresholds (refused: the track taxonomy
forbids page-count heuristics, and some section entries are long); page-range rows per official section (chosen).

## Decision

We give `dblp_aaai.toml` and `acm_proceedings.toml` a `[[section]]` table (year, page range, track, label, check
date, source) and `dblp_aaai.toml` a `[[track]]` table for single keys dblp's pages can't place: a main-key entry
or ACM work whose start page is in a range takes the range's track, else `main`; not-paper rows win. Short invited
talks, panels and keynotes become not-paper rows (counted, not indexed). The IAAI papers in the 1996–2008 volumes
are `iaai`. Robot competition entries are `other`, and so are 2006–2008's NECTAR and Senior Member Papers, as the
owner decided for the same sections from 2010 (TASK-218, `ojs_sections.toml`), so one section kind has one track in
every year. Invited entries over two pages, 2008's Short Papers and entries no official page lists stay `main`. In a
year or proceedings with section rows, an entry with no readable start page and no row stops the crawl
(`unplaced_page`), so nothing falls to `main` unseen.

## Consequences

AAAI 1980–2008: 1,089 entries move off `main` and 21 more are not-paper rows (4,709 records: 3,567 `main`, 399
`student_abstract`, 158 `consortium`, 127 `demo`, 232 `iaai`, 173 `other`, 53 `workshop`); AIES 2018–2023: 108 move to
`student_abstract` and 18 keynotes are not-paper rows (557 records). AIES `main` claims in a proceedings with section
rows now name the pages they fall outside, so those 377 records change provenance only (AIES 2020, which has no
section row, keeps its decision-049 wording). Record content changes, so a new snapshot (and index) changes
`snapshot_hash`; no schema, tokenizer or query version changes, and records saved on an index built from an earlier
snapshot replay as `drifted`. No public instance has served an index built from the earlier snapshots (hosting is parked, TASK-064), so only locally saved records are affected. Specs 00, 01, 02, 05, 07, the track-taxonomy and dedup-rules skills and the research
note describe the rules; `backend/tests/unit/ingest/test_track_rules_replay.py` pins the counts over the pinned data;
the coverage report's scope lines say which entries are counted but not indexed. A range holding no paper stops the
crawl (`stale_section`). Revisit if an official AIES 2018–2023 table of contents becomes readable, or for 2005's
Sultanik05, Thornton05 and WangL05, which no official page places and which stay `main`.

Rulings recorded during review (the controller for the owner, 2026-10-10):
- AIES at 108 `student_abstract` is accepted, not the first ruling's 96: the contents-page range wins.
- The IAAI papers of the 1996–1999 volumes are `iaai` by the IAAI contents pages (18, 32, 22, 17).
- BarishKCMPS00 is `iaai`: the IAAI-2000 page lists it first under Emerging Applications, printed without a page.
- 2006–2008 NECTAR and Senior Member Papers are `other` (91 entries), and 2006's 18 AAAI Member Abstracts are `other`
  by key rows, dblp giving them no pages.
- 2005's demonstration and robot sections are on `aaai05contents.php`, without page numbers; the ranges come from the
  entries' paper pages.
