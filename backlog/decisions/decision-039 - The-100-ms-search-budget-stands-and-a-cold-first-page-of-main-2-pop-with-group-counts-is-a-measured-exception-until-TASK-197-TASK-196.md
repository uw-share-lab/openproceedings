---
id: decision-039
title: >-
  The 100 ms search budget stands and a cold first page of main-2-pop with group
  counts is a measured exception until TASK-197 (TASK-196)
date: '2026-10-05 17:21'
status: accepted
---
## Context

Spec 03 budgets a search returning its first 50 hits, as `/search` runs it with each concept group's counts
(TASK-176), at p95 under 100 ms. The review gate of PR #105 measured one cold first page over it (TASK-196: the
wildcard-phrase query, p95 110.8 ms), at a 1-minute load of 4.5 to 9.8. Re-measured on 2026-10-05 at a load of
3.9 to 3.3, with every Trust-Evals string added to the report (`docs/results/2026-10-05-bench-group-counts.md`),
that query takes p95 84.4 ms, within the budget, but `main-2-pop` takes 190.1 ms with its counts (62.1 ms
without, 62.3 ms on a later page, which reads the counts from the memo). Its first group costs about 35 ms a
run and is collected again in each of the three counted trees that hold it (TASK-197 has the measurements).
The other nine strings take at most 44.2 ms. Three treatments were considered:

1. **Bring it under the budget before the v0.1.0 tag.** Reusing the group's matches inside one counting call
   halves those three trees but leaves the page near 120 ms; getting under 100 ms means sharing them with the
   page and its facets too, a change to the engine's memos that would need its own review gate and could not
   land and be released on 2026-10-05.
2. **Exempt group counts from the budget.** The budget would no longer describe what `/search` costs.
3. **Keep the budget, record this case as an exception "as measured", and fix it in a task.**

On 2026-10-05 the project owner asked for the fix to be attempted and, failing that, for the release to go
ahead with the exception recorded and the target reconsidered; the AI assistant session working for them chose
among these on the figures above.

## Decision

Option 3. The 100 ms p95 budget for a first page with its counts stands. Spec 03's "Exception, as measured
(decision-039, TASK-197)" names the `main-2-pop` cold first page and its figures; TASK-197 brings it under the
budget. The counts are not shortened, dropped or given a smaller wait to meet the budget: a count that comes
back is always exact.

## Consequences

- v0.1.0 ships with a cold first page of `main-2-pop` taking about 190 ms when a reviewer first runs it; the
  next page, and the same search again while the facet memo holds it, cost about 62 ms.
- The bench report times every Trust-Evals string, so a string over the budget shows in the report, not only
  in review.
- A budget measurement is only cited when the 1-minute load was under 5 at the start and the end.
- TASK-196 is closed by this decision; TASK-197 removes the exception when it lands.

## Outcome (2026-10-06)

TASK-197 (PR #112) gave the counting worker the request's own compile and collects a conjunct that several
counted trees share once, as an `ord` bitmap. Re-measured with `group_counts_report.py` at a 1-minute load of
3.4 at the start and 4.6 at the end (commit `66613463`; `docs/results/2026-10-06-bench-group-counts.md`), the
cold first page of `main-2-pop` with its counts takes p95 85.4 ms (73.8 ms median), from 190.1 ms, and every
Trust-Evals string is within the 100 ms budget. Spec 03's exception is removed; the budget stands as decided.

