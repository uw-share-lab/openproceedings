---
id: TASK-282
title: >-
  dblp year parsing trusts str.isdigit(): a non-ASCII digit crashes int() or is
  read as a year
status: To Do
assignee: []
created_date: '2026-10-22 22:23'
updated_date: '2026-10-22 22:23'
labels:
  - ingest
  - security
dependencies: []
priority: low
ordinal: 185000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the TASK-281 review (2026-10-22). sources/dblp.py:256 and sources/dblp_aaai.py:64 test a year with str.isdigit(), which is true for any Unicode digit: int('²') raises a bare ValueError that aborts the crawl, and int('١٩٨٠') silently reads 1980. Input is the pinned, digest-checked dblp release, so the risk is low; the other parsers already read ASCII digits only (decision-055).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Both read a year only from ASCII digits (re.fullmatch('[0-9]{4}') or str.isascii() and isdigit()), anything else is no year, with tests for a superscript and an Arabic-Indic year
<!-- AC:END -->
