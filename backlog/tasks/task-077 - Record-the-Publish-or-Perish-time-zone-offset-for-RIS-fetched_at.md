---
id: TASK-077
title: Record the Publish or Perish time-zone offset for RIS fetched_at
status: To Do
assignee: []
created_date: '2026-09-27 00:05'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 75000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
M2 gate (review-methodologist): the RIS importer takes fetched_at from the M1 Query date, which Publish or Perish writes in the machine's local time; it is stored labelled UTC because the offset isn't recorded, so a crawl date near midnight can be a day off, and PRISMA-S keeps search and crawl dates apart. Record the offset (an ingest option or the cache's metadata) and convert, or mark such claims 'local, offset unknown'.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 fetched_at from a RIS import is either converted with a recorded offset or explicitly marked local
- [ ] #2 The snapshot manifest's crawl window says which
<!-- AC:END -->
