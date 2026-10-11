---
id: TASK-225
title: >-
  Owner review: doubtful AAAI 1980-2008 entries (invited-talk abstracts, panel
  statements, conf/aaai/1991w)
status: Done
assignee: []
created_date: '2026-10-10 10:37'
updated_date: '2026-10-10 15:20'
labels:
  - ingest
  - new-venues
milestone: m-4
dependencies: []
ordinal: 158000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Milestone B kept these as papers (main) and excluded conf/aaai/1991w (an edited book dblp dates 1993): five one-page '(Abstract)' entries that look like invited talks (Feigenbaum93, Simon93, Abarbanel96, Wellman97, ArkinF97), the 1996 'Panel Statements', the 1990 panelists' statements, one-page video/demo abstracts. See the research note §AAAI 1980-2008. Decide per entry: not_paper rows in ingest/dblp_aaai.toml or keep.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Owner decision recorded; dblp_aaai.toml updated if any
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Ruling 2: the 14 named entries become [[not_paper]] rows in dblp_aaai.toml (the five (Abstract) talks via TASK-226's invited-talk rows, SelmanBDHMN96 and the eight 1990 panelists as panel rows); the 9 video/demo abstracts become demo through TASK-226's 1993/1994 ranges; 1991w stays excluded. Ruling 4: where TASK-226's official contents disagree (ChangN94, ArkinF97's kind), the contents win.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built per rulings 2 and 4: SelmanBDHMN96 and the eight 1990 panelists are panel not_paper rows; the five (Abstract) entries are invited-talk not_paper rows via TASK-226 (ArkinF97's kind is invited talk, the 1997 contents list it so); the 9 video/demo abstracts are demo via TASK-226's 1993/1994 ranges; 1991w stays excluded; ChangN94 is student_abstract (in the official 1994 Student Abstracts, which win over 'keep main'). Snapshot 2026-10-10-df9a9f8b2143: the 9 panel removals show in the diff.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
dblp_aaai.toml: 9 panel not_paper rows added (with TASK-226's invited-talk rows covering the five abstracts) and the 9 video/demo abstracts demo by TASK-226's ranges; 1991w excluded; ChangN94 student_abstract per the official contents. Verified by test_track_rules_replay.py and op snapshot diff (2026-10-10-df9a9f8b2143).
<!-- SECTION:FINAL_SUMMARY:END -->
