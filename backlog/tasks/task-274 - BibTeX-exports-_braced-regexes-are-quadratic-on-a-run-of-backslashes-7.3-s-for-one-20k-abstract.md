---
id: TASK-274
title: >-
  BibTeX export's _braced regexes are quadratic on a run of backslashes (7.3 s
  for one 20k abstract)
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-20 15:18'
updated_date: '2026-10-21 23:01'
labels:
  - export
  - security
dependencies: []
priority: high
ordinal: 181000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-272's security sweep (2026-10-20), pre-existing: export.py _BRACE/_SPECIAL/_AT (lines ~417, 446, 447) try a match at every position in a run of backslashes, so a stored abstract '{' + 20,000 backslashes + 'x&@' costs 7.3 s CPU in _braced (5k: 464 ms; bare patterns at 100k: 29-68 s). An OpenReview author controls an abstract (capped at 20k); every public /export?format=bibtex that includes the record pays it; DOI and URL fields have no length cap. Candidate fix, checked equivalent on short strings by the reviewer: (?<!\\)(\\*)[{}], (?<!\\)(\\*)([&%#]), (?<!\\)(\\*)@. Must be fixed before a public instance (TASK-064/TASK-135).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 _braced's patterns start a match only at the start of a backslash run, with identical output (exhaustive short-string comparison)
- [x] #2 A CPU-growth test (tests/timing.py) on _braced over a long backslash run, failing on the old patterns
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Reproduce: time _braced on '{' + n backslashes + 'x&@' (old patterns).
2. Anchor each pattern at the start of a backslash run with (?<!\\): _BRACE, _SPECIAL, _AT.
3. AC1: exhaustive comparison of _braced, _balances and _debraced against the old patterns over every string up to a fixed length from {\\, {, }, &, %, #, @, x}; keep the existing Hypothesis property (frozen function) and add one comparing old-pattern and new-pattern functions on tricky text.
4. AC2: tests/timing.py growth test on _braced over a long backslash run (each of brace, special, @ shapes); show it fails with the old patterns and passes with the new.
5. Check DOI/url fields go through _braced; file anything left as a follow-up.
6. Docs (bibtex-format skill, spec 04 if it describes escaping), learnings, review gate, finalize.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fix: _BRACE, _SPECIAL and _AT anchored with (?<!\\) (export.py). Equivalence: a match never ends on a backslash, so the unanchored scan only ever matched at a run's start.
AC #1 evidence: tests/unit/test_export_braced.py compares the three patterns' spans and groups, and _braced/_debraced/_balances (both modes), to the pre-TASK-274 patterns on all 299,593 strings of up to 6 characters over \\{}&%#@x; a Hypothesis property compares _braced on longer strings. One-off run beyond the suite: patterns identical on all 19,173,961 strings up to length 8; functions identical on all 2,396,745 up to length 7.
AC #2 evidence: test_braced_is_linear_in_a_backslash_run (growth, n=1,000 vs 4,000, 8 calls a sample, limit 8). Old patterns: brace 15.80, special 15.98, at 15.80, all 15.94 (all: 16.5 ms -> 267 ms a call), all four fail. New: 3.88, 3.95, 3.82, 3.88 (all: 0.33 ms at 4,000). The task's abstract ('{' + 20,000 backslashes + 'x&@'): 6,620 ms CPU old, 1.6 ms new.
DOI and url: both exported through _braced (export.py _bibtex: url, doi; abstract_source's url too), so the fix covers them. Remaining: record.py validates DOI and URL shape but caps no length (decision-026 caps only titles and abstracts; author names are uncapped too), so an export writes them whole: follow-up to file at the end of the branch.

Mutation check of the equivalence tests: three wrong patterns (_SPECIAL with \\? for \\*, _BRACE matching only {, _AT refusing after x) each fail all three. Local: make test (9151 passed, 3 skipped; vitest 4954 passed), make lint, make tooling green; make mutate-changed: no mutants cover the diff. CHANGELOG: generated from merged PRs at release time (spec 08 §Release), nothing to run on a feature branch.

Follow-up filed: TASK-279 (ingest length caps for DOI, URL and author fields).
<!-- SECTION:NOTES:END -->
