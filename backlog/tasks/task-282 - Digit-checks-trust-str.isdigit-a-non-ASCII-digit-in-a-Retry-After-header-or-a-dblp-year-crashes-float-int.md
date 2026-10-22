---
id: TASK-282
title: >-
  Digit checks trust str.isdigit(): a non-ASCII digit in a Retry-After header or
  a dblp year crashes float()/int()
status: To Do
assignee: []
created_date: '2026-10-22 22:23'
updated_date: '2026-10-22 22:25'
labels:
  - ingest
  - security
dependencies: []
priority: medium
ordinal: 185000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the TASK-281 review and the closing docs review (2026-10-22). str.isdigit() is true for any Unicode digit, but int()/float() don't accept them all. (1) sources/http.py _seconds (float(text) if text.replace('.', '', 1).isdigit()) reads the Retry-After and ratelimit-reset headers of any 429 or 5xx (retry_after, lines 456 and 904); urllib decodes headers as latin-1, so a byte 0xB2 arrives as '²' and float('²') raises a ValueError outside the fetch loop's except (OSError, HTTPException): any crawled host can abort a run with one header. (2) sources/dblp.py:256 and sources/dblp_aaai.py:64 read a year with raw.isdigit(): int('²') raises and int('١٩٨٠') silently reads 1980 (input is the pinned, digest-checked dblp release, so lower risk). coverage.py, cli.py, ris.py, query/canonical.py and query/parser.py already check isascii(); eval/coverage_report.py:229 reads an operator file and raises by design.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 http._seconds reads only ASCII digits (one optional '.'); a non-ASCII value is no hint, never an exception, with a retry_after test for a latin-1 '²' header on a 429
- [ ] #2 Both dblp year readers take a year only from ASCII digits, anything else is no year, with tests for a superscript and an Arabic-Indic year
<!-- AC:END -->
