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
- The effect on real data is measured by a rebuild on the real cache, recorded in TASK-189.

