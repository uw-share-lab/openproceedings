---
id: decision-045
title: >-
  An import's title merge is refused when its own abstract matches a different
  crawled record in the venue-year that no title partner holds (TASK-189)
date: '2026-10-06 00:05'
status: accepted
---
## Context

TASK-189, found reviewing TASK-179: dedup's title step (step 2) never consults the abstract. An imported
record's title is Google Scholar's rendering, which can drop math (`$R^2$-Guard` arrives as `-Guard`), so it can
equal a different paper's title key in the same venue-year (a note titled `Guard`) and merge on title while its
own-page abstract is another record's. Separately, a forum-id RIS row and a proceedings-id RIS row with one
title and different long abstracts merge. No real instance of either is known on snapshot
`2026-10-05-10b5a205a63f`. A broad refusal ("the abstracts differ") would wrongly split papers whose main and
workshop notes share an abstract (decision-037 counts 14 such pairs) and RIS rows whose abstracts differ only by
version (OpenReview and camera-ready abstracts often differ).

## Decision

The project owner chose (2026-10-05) a narrow refusal: an import's title merge is refused when the import
keeps an abstract from its own page (`_own_abstract`) that none of its title partners keeps, but a crawled
record in the same venue and year does. Step 3 (`abstract_venue_year`, decision-037) then joins the import to
that record. Two RIS rows with one title and different abstracts still merge.

## Consequences

- `-Guard` joins `$R^2$-Guard` by its abstract, not `Guard` by its title.
- Papers whose title partners share the abstract, and RIS rows whose abstracts differ, merge as before.
- The effect on real data was measured on 2026-10-06 (below, "Real-cache rebuild").

## As built (2026-10-06)

- "A crawled record" holds the abstract through a crawler's abstract claim only, not a RIS row's abstract
  inside a crawled cluster: a title merge in the same step can replace that RIS claim, and a second dedup run
  then merged an import the first had kept apart (`YIELD_TO_A_REPLACED_RIS_ABSTRACT`, `test_idempotent`).
- When the record holding the import's abstract is one step 3 can't merge with (a workshop note, by the track
  rule), the import yields anyway and stays a separate record, with `title_key` `ambiguous_not_merged` rows.
  A duplicate costs a reviewer one extra screen; a wrong merge would lose a paper. Accepted on that basis.

## Real-cache rebuild (2026-10-06)

`op snapshot build --from data/cache` with the v0.1.1 batch's code (TASK-188, 189, 190, 197, 198; branch
`feat/v011-dedup-perf` at `331c29c3`), into a scratch directory, gave snapshot `2026-10-05-5d9adbf42f0f`.
`op snapshot diff` against the served `2026-10-05-10b5a205a63f`: 0 added, 0 removed, 0 rekeyed, 59 changed
(the abstract alone in each: decision-044's control characters), `merges.csv` identical (28,861 rows). So this
decision and decision-040 change no merge on the current corpus. `conflicts.csv` has 9,112 rows instead of
9,126: the 14 `abstract_key` `track_not_merged` rows decision-037's amendment drops for a pair already reported
under `title_key` (the served snapshot predates that amendment); each pair keeps its `title_key` row.
