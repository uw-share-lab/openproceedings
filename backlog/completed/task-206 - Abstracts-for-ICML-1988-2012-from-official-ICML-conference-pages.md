---
id: TASK-206
title: Abstracts for ICML 1988-2012 from official ICML conference pages
status: Done
assignee: []
created_date: '2026-10-07 03:15'
updated_date: '2026-10-07 05:44'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 149000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
dblp gives no abstracts, so pre-2013 ICML records are title-only. Some years' official ICML sites survive (icml.cc/2012/papers, icml.cc/Conferences/2009/abstracts.html) or are pinned in the Internet Archive. The owner (2026-10-06) asked for these abstracts in the same batch: only official ICML/IMLS pages, live or a pinned web.archive.org capture; never ACM DL, Scholar, Semantic Scholar, author pages or arXiv.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 docs/research records a survey of every ICML year 1988-2012: which official pages hold per-paper abstracts
- [x] #2 A checked-in table lists each year's source URL(s), capture timestamp when archived, verified date and paper counts
- [x] #3 Abstracts attach to dblp records only by exact title key within the year; an ambiguous or missing match leaves the abstract null and is counted
- [x] #4 Abstract provenance names the source page (and capture timestamp); spec 01's abstract-source rule has a decision-047 clause
- [x] #5 Per year: dblp records, abstracts attached, unmatched, years with no source are reported
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Survey every ICML year 1988-2012 for official pages with abstracts (docs/research/2026-10-06-icml-pre-2013-abstract-sources.md); table each page (icml_sites.toml: URL or pinned capture, official URL, parser, charset, verified entries); parse each page; attach by exact title key, one-to-one, in dblp.mine_year; count unmatched, ambiguous, unjoined, dropped.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Sources used: 2001, 2003, 2004 (Internet Archive captures of the conference sites), 2007 (icml.cc list + 150 Oregon State captures), 2008-2012 (icml.cc). None: 1988-1996, 1999, 2000, 2002, 2005, 2006. Not used: 1997 and 1998 (submission abstracts with authors' contact details) - an owner question, not filed as a task (no id reserved). Attached 1,290 of 2,675; unmatched page entries 46 (retitled papers, one withdrawn), ambiguous 0, 2007 dropped 1 (empty page). Focused review fixes: five 2007 captures are UTF-8 (rows fixed, entries refetched, runtime guard for UTF-8 read as cp1252), captures limited to official hosts, dropped/unjoined counted, duplicate paper numbers refused, capture timestamps checked.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Abstracts for pre-2013 ICML come from official ICML pages only: icml.cc (the 2007 list, 2008-2012) and pinned Internet Archive captures of the 2001, 2003, 2004 and 2007 conference sites (ingest/icml_sites.toml: 159 pages with charset and verified count; survey in docs/research/2026-10-06-icml-pre-2013-abstract-sources.md). An abstract attaches only when one page entry and one dblp paper of the year share the exact title key: 1,290 of 2,675 records; 46 page entries unmatched, 0 ambiguous, 1 dropped; no source for 1988-1996, 1999, 2000, 2002, 2005 and 2006 (per-year table in docs/research/2026-10-06-pre-2013-neurips-icml-sources.md). Claims name the page as fetched, the official URL and the capture. A wrong charset, a changed count, a duplicate paper number or a capture of a non-official host stops the crawl. 1997/1998 submission abstracts (with contact details) are not used: an owner question. Tests: test_icml_sites.py and a Fetcher charset test; make test, lint and tooling pass.
<!-- SECTION:FINAL_SUMMARY:END -->
