---
id: TASK-282
title: >-
  Digit checks trust str.isdigit(): a non-ASCII digit in a Retry-After header or
  a dblp year crashes float()/int()
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-10-22 22:23'
updated_date: '2026-10-23 03:08'
labels:
  - ingest
  - security
dependencies: []
priority: medium
ordinal: 185000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the TASK-281 review and the closing reviews (2026-10-22). str.isdigit() is true for any Unicode digit, but int()/float() don't accept them all. (1) sources/http.py _seconds (float(text) if text.replace('.', '', 1).isdigit()) reads the Retry-After header of any 429 or 5xx (retry_after, lines 456 and 904 on origin/dev) and ratelimit-remaining/ratelimit-reset on every 200 (_respect_budget, lines 538-543, called at 462); urllib decodes headers as latin-1, so a byte 0xB2 arrives as '²' and float('²') raises a ValueError no fetch loop catches: any crawled host can abort a run with one header. (2) sources/dblp.py:256 and sources/dblp_aaai.py:64 read a year with raw.isdigit(): int('²') raises and int('١٩٨٠') silently reads 1980 (input is the pinned, digest-checked dblp release, so lower risk). coverage.py, cli.py, ris.py, query/canonical.py and query/parser.py already check isascii(). The first filing called eval/coverage_report.py:229 (an operator file) raising by design; the review found it raised a bare ValueError on '²' and read '٢٠١٤' as 2014, so this task fixed it too, along with the readers the review found next to these (see ACs #3 and #4).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Both dblp year readers take a year only from ASCII digits, anything else is no year, with tests for a superscript and an Arabic-Indic year
- [x] #2 http._seconds reads only ASCII digits (one optional '.'); a non-ASCII value is no hint, never an exception, with tests for a latin-1 '²' in Retry-After on a 429 and in ratelimit-remaining on a 200 (_respect_budget, called outside the fetch try)
- [x] #3 http.retry_after treats a Retry-After HTTP-date parsedate_to_datetime refuses with OverflowError as no hint, and takedown_check.retry_after converts at most two digits after leading zeros (longer is the 60s cap), with tests
- [x] #4 eval/coverage_report._cell_key and scripts/{openalex,dblp_aaai,aaai_library}_census.py check isascii() and bound the digits before int(); the coverage_report heading test covers '²', an Arabic-Indic year and 5,000 digits (the scripts have no test harness)
- [x] #5 .claude/hooks/lib/cmdparse.py git_bool reads only ASCII digits as a number and never calls int() (push.followTags=² or 5,000 digits no longer raise in require-review.sh), with case-table rows in test-openproceedings-gates.sh and mutants in gates.json
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. http._seconds: take the value only when what is left after one optional '.' is ASCII digits (the repo's isascii() and isdigit() idiom); anything else is no hint (None).
2. dblp.check_extract and dblp_aaai._year_of: a year only from ASCII digits, the same idiom.
3. Tests through the real fetch path with the scripted transport: a latin-1 '²' (b'\xb2' decoded as latin-1) in Retry-After on a 429 (falls back to the back-off step) and in ratelimit-remaining or ratelimit-reset on a 200. dblp: a superscript and an Arabic-Indic year are no year in both readers.
4. Check every other isdigit hit in backend/src; report or fix.
5. make test, make lint, make tooling (mutate-changed covers tooling mutants only, not backend/src).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Code review (2026-10-22): _respect_budget (http.py:538-543) reads ratelimit-remaining and ratelimit-reset through _seconds on every 200 response, outside the transport's try (line 462), so the 200 path aborts a crawl too, not only 429/5xx.

Implemented (2026-10-22): http._seconds, dblp.check_extract's year and dblp_aaai._year_of now need isascii() and isdigit(), the idiom coverage.py, cli.py, ris.py and query/parser.py use (no shared helper exists). Tests: test_fetch.py test_a_non_ascii_retry_after_on_a_429_is_no_hint ('²', '1²', '١٢', '1.²': the first back-off step, 5s) and test_a_non_ascii_ratelimit_header_on_a_200_is_no_hint (remaining '²': no budget wait; reset '²' with remaining 0: the 60s default); test_dblp.py and test_dblp_aaai.py test_a_year_of_non_ascii_digits_is_no_year ('²', an in-range and an out-of-range Arabic-Indic year: refused as unlisted with no year). All 12 failed before the fix.
isdigit sweep (grep -rn isdigit backend/src, 17 hits): coverage.py:71, cli.py:1319, ris.py:279, canonical.py:158, parser.py:137 already check isascii(); aaai_library.py:245 and openalex_audit.py:147 are predicates with no int(); normalize.py:251/302 and lexer.py:282-283/515 are the tokenizer's math and currency rules (no int(), token contract; lexer.digit folds NFKC on purpose); eval/coverage_report.py:229 reads an operator file: '²' raises a bare ValueError without the file's message and '٢٠١٤' reads 2014; reported to the lead, not changed here (the task scopes it as by design).
Validation: make test (backend 9366 passed, 3 skipped; frontend 4954 passed), make lint, make tooling all green.

Review round 1 (2026-10-22): security found that a Retry-After HTTP-date past what a datetime holds (year 99999999999, or a huge offset) made parsedate_to_datetime raise OverflowError, uncaught: http.retry_after now catches it (test_a_retry_after_date_past_what_a_datetime_holds_is_no_hint). takedown_check.retry_after converted any length of ASCII digits (5,000 raise past int()'s 4,300-digit limit): it now converts at most two digits after leading zeros, longer is the 60s cap. scripts/openalex_census.py, scripts/dblp_aaai_census.py and scripts/aaai_library_census.py trusted bare isdigit() too and now check isascii(). eval/coverage_report.py:229 fixed the same way (a '²' or Arabic-Indic year heading is refused with the file's message). Sweep count corrected: 16 isdigit hits in backend/src on origin/dev (17 on this branch: the _seconds docstring names isdigit()). The .claude/scripts hits read curl's %{http_code} and git numstat: ASCII by construction, unchanged. The line numbers in the description are origin/dev's (the fix shifted http.py by 3).

Round 1 validation: make test (backend 9371 passed, 3 skipped; frontend 4954 passed), make lint, make tooling green.

Review round 2 (2026-10-22): the dblp year readers (and scripts/dblp_aaai_census.py) also bound the year to four digits (int() raises past 4,300; rows of 5,000 nines added); coverage_report's year heading likewise (<= 4); openalex_census and aaai_library_census bound their header and CDX length to 18 digits. The round-1 note's 'reported to the lead, not changed here' for coverage_report.py is superseded: fixed in round 1. .claude/hooks sweep: 9 hits, mostly fd-redirect checks with no int(); require-review.sh:366 reads git numstat; cmdparse.git_bool runs int() on a git config value, so '²' raises, but the hooks turn an exception into exit 2 (fail closed), so it is left to the lead (not changed: a hooks change routes to security and qa with mutants).

Round 2 validation: make test (backend 9373 passed, 3 skipped; frontend 4954 passed), make lint, make tooling green.

Round 3 (lead's direction, 2026-10-22): cmdparse.git_bool fixed after all (supersedes the round-2 note leaving it to the lead): digits = v.removeprefix('-'); a number is ASCII digits that are not all zeros, no int(). Old code raised on '²', '--1' and 5,000 digits (require-review.sh turned it into exit 2, fail closed). Rows: push.followTags 1, -0010, 5,000 nines (block); 000, -0, ², --1 (allow). Three mutants added to gates.json (Unicode digit, zero, negative); mutate.py --match git_bool --jobs 2: 4 of 4 killed. mutate.py --changed --check: 276 mutants, 0 unrunnable; the full --changed run (276 cmdparse mutants, ~2 min each here) was not run locally: nightly runs every mutant. make tooling (test-openproceedings-gates.sh 1650 passed) and make lint green.
<!-- SECTION:NOTES:END -->
