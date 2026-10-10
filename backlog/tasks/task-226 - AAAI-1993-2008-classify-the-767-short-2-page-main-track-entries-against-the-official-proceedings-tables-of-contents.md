---
id: TASK-226
title: >-
  AAAI 1993-2008: classify the 767 short (<=2 page) main-track entries against
  the official proceedings tables of contents
status: To Do
assignee: []
created_date: '2026-10-10 14:28'
labels:
  - data
  - aaai
dependencies: []
ordinal: 159000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-224/225 evidence (2026-10-10) found 767 AAAI main-track entries from 1993-2008 of two pages or fewer, mostly in trailing student-abstract, poster and demo blocks of each volume. Find an official AAAI table of contents per year (AAAI digital library, aaai.org proceedings pages, or the printed front matter), map each block to a track (student_abstract, demo, other, not a paper), and encode it as per-year page-range rules in dblp_aaai.toml so offline replay stays deterministic. Owner asked for this on 2026-10-10.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each of the 767 entries has a track backed by a cited official table of contents, or is listed as unresolved with the reason
- [ ] #2 Rules live in the pinned table, with replay tests; op snapshot diff reports only track changes
<!-- AC:END -->
