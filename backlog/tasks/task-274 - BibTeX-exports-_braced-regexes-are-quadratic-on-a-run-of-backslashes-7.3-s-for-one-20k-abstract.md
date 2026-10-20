---
id: TASK-274
title: >-
  BibTeX export's _braced regexes are quadratic on a run of backslashes (7.3 s
  for one 20k abstract)
status: To Do
assignee: []
created_date: '2026-10-20 15:18'
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
