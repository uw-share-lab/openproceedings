---
id: TASK-100
title: ux-writer review of the editor's new 'couldn't be checked' strings
status: Done
assignee: []
created_date: '2026-09-27 21:11'
updated_date: '2026-10-01 12:40'
labels:
  - frontend
  - docs
milestone: m-3
dependencies: []
ordinal: 97000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-041 added strings for 429, 503 API_BUSY, non-JSON 5xx and network failures ('The query couldn't be checked: …', Check again). Review them against the copy deck and add them there.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every new editor string is in docs/design/2026-09-27-copy-deck.md with its state,Rewrites applied and tests pinned
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Also review: copy deck BD-10 (TASK-043 builder strings) and TASK-042's new strings ('Type a four-digit year in both boxes, the earlier first.', 'Page N is past the last page…', 'No papers on page N…', 'Every year.' / 'Admits …', 'Loading the paper…', 'No provenance recorded.').

Also review TASK-044's new strings, listed in docs/design/2026-09-27-export-records-and-paper.md 'As built (TASK-044)'.

Reviewed every string in the description and the notes (TASK-041 editor, BD-10, TASK-042's year/paging/paper strings, TASK-044's export/save/record strings) and added each to the copy deck: ED-18, SB-10, RH-16–17, BD-10 (reviewed), EX-E10, SV-10–11, RC-16 (as built) to RC-19, PA-9.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
ux-writer review of the strings TASK-041–044 added after the copy deck's hand-off; all now in docs/design/2026-09-27-copy-deck.md with a before/after table. Rewrites applied and pinned by Vitest: the editor's 'couldn't be checked' line puts the server's message after a full stop (was a colon, giving a mid-sentence capital) and the network case says 'the server couldn't be reached. Check your connection.' (also the record page's CantLoad); the year line says 'Includes' (was 'Admits'); the builder's Exclude row is 'leave-out terms' / '+ Leave out terms' (the glossary keeps 'excluded' for default filters); the save's 409 sentence reads 'the record would cite a different index from the one whose counts you saw'. ux-writing skill gained the colon rule and the excluded/NOT note. Methods-text variants are spec 05's and were not changed.
<!-- SECTION:FINAL_SUMMARY:END -->
