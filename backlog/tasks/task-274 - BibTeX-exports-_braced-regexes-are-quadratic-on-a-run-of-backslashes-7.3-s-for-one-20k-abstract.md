---
id: TASK-274
title: >-
  BibTeX export's _braced regexes are quadratic on a run of backslashes (7.3 s
  for one 20k abstract)
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-20 15:18'
updated_date: '2026-10-21 22:37'
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
- [ ] #1 _braced's patterns start a match only at the start of a backslash run, with identical output (exhaustive short-string comparison)
- [ ] #2 A CPU-growth test (tests/timing.py) on _braced over a long backslash run, failing on the old patterns
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
