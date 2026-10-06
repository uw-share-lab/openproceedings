---
id: decision-043
title: >-
  A search record never notes a comparison; the compare panel gives a citable
  sentence instead (TASK-195)
date: '2026-10-05 23:57'
status: accepted
---
## Context

The compare panel (`POST /compare`, TASK-177, decision-035) shows a comparison's counts (kept, dropped, not
in the index, added) on screen and in the downloaded CSVs, and nothing else keeps them. The review gate's
usability and methodology reviewers (2026-10-05) asked what a methods section may cite (TASK-195). Options:
store a note of the comparison in the search record (the file's sha256, its counts and the date, as an
optional field), or keep the record as it is and give the panel a citable sentence.

## Decision

The project owner chose (2026-10-05) the second. A search record never notes a comparison. The panel offers a
copyable sentence stating the counts, the `index_version`, the query's `canonical_hash`, the file's sha256
and the date, worded per the prisma-reporting skill.

## Consequences

- A search record stays the query and its index pin, so its replay contract (guarantee 4) is unchanged.
- No information about a reviewer's file is stored anywhere (decision-035); the sentence carries the file's
  sha256, which the reviewer can recompute from their own copy.
- A methods section cites the sentence, with the record's id for the search itself.

