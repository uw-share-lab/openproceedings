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
date, source) and `dblp_aaai.toml` a `[[track]]` table for single keys dblp's page typos misplace: a main-key entry
or ACM work whose start page is in a range takes the range's track, else `main`; not-paper rows win. Short invited
talks, panels and keynotes become not-paper rows. Robot competition entries are `other`; full-length invited papers,
2008's Short Papers and entries no official page lists stay `main`.

## Consequences

AAAI 1980–2008: 891 entries move off `main` and 21 more are not-paper rows (4,709 records); AIES 2018–2023: 108
move to `student_abstract` and 18 keynotes are not-paper rows (557 records). Record content changes, so a new
snapshot (and index) changes `snapshot_hash`; no schema, tokenizer or query version changes, and saved searches
replay as `drifted`. Specs 00, 01, 02, 05, 07, the track-taxonomy skill and the research note describe the rules;
`backend/tests/unit/ingest/test_track_rules_replay.py` pins the counts over the pinned data. A range holding no
paper stops the crawl (`stale_section`). Revisit if an official AIES 2018–2023 table of contents becomes readable,
or for the IAAI papers in the 1996–1999 volumes and 2005's Sultanik05 and Thornton05, which stay `main`.