---
id: decision-041
title: >-
  Abstract matching stays import-only; crawled listings are not merged by
  abstract (TASK-187)
date: '2026-10-05 23:54'
status: accepted
---
## Context

decision-037 limits the `abstract_venue_year` merge (dedup step 3) to groups holding an imported record: an
abstract never joins two crawled records. TASK-187 asked whether to extend it to crawled listings. On snapshot
`2026-10-05-10b5a205a63f`, exactly one crawled pair would merge if it were: NeurIPS 2023 D&B note `3sRR2u72oQ`
and its retitled proceedings listing `nips-39736af1…`. The other 1,706 same-abstract groups are twins or
duplicate submissions that must stay apart. An extended rule would have to tell a retitled listing from a twin,
with the real pair and the negative cases as tests.

## Decision

The project owner chose (2026-10-05) not to extend it. Abstract matching stays import-only.

## Consequences

- The retitled NeurIPS 2023 D&B pair stays as two records, a known duplicate; it is no wrong merge, and both
  records match a query that matches either.
- No rule has to separate retitles from 1,706 twin groups.
- A future snapshot with many retitled pairs would be the reason to reopen this.

