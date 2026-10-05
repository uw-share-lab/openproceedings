# An extra computed on every search needs its own bound, its own workers and a failure that costs only the extra

**Key lesson:** Before adding per-request work beside a search (counts per concept group here), decide its bound from the parsed query before any of it runs, give it workers the search's own work never queues behind, cancel what the search stopped waiting for, and make every way it can fail an answer of its own (`not_counted`), because the existing cost guard (decision-010) charges only position verification and the shared `compiled` memo must never hold a tree no search ran.

- **Date:** 2026-10-05 · **Task:** TASK-176 · **Area:** engine, api, frontend
- **Artifacts:** `backend/src/openproceedings/search.py` (`GROUP_COUNT_WAIT_SECONDS`, `GROUP_COUNT_GRACE_SECONDS`, `_GROUP_POOL`), decision-034, spec 04 §SearchResponse (`groups`), `frontend/src/builder/group-counts.ts`, commits df6ac30e, af63f471, a8d95f84

## What we set out to do
Show, for a query that is an AND of concept groups, how many papers each group matches alone and how many
the query would match without it, on the same index and under the same filters, as an additive field of
`/search`.

## What we learned
- **The guard that exists may not charge the work you add.** Decision-010 bounds position-verified clauses.
  Counting a group runs collections, which it does not charge, so the first version let a query of many
  groups and a kept `NOT` of many wildcards do unbounded work the rate limit saw as one request. It took
  three fix commits, each for a cost the last one missed: terms read (`max_counted_terms`, a formula
  over the trees counted, known before any counting), then verified ids (`max_counted_ids`), then the wait.
  Each is a threshold decided up front, answered whole with `not_counted: too_costly` (commits df6ac30e,
  af63f471).
- **A shared memo must hold only what a search ran.** The per-group trees ("the query without group N") are
  never searched by anyone. Compiled into the engine's `compiled` memo they would have evicted real queries'
  entries; they are compiled per request and nothing is stored, and a test pins that the review's shape
  leaves the shared memos exactly as the plain search does (df6ac30e).
- **Its own workers, and a wait for a job nobody took.** On the facet pool, counting made facets queue behind
  it. With two workers of its own, other clients' counting jobs could still add the whole wait to a search
  whose job was only queued; a job no worker has started within the grace period is now cancelled and the
  search answers `not_counted: busy`, and the longer wait applies only to a running job (a8d95f84).
- **Failure isolation is a contract, so say it in the type.** A worker's own `TimeoutError` is
  `count_failed`; only the search's wait is `timed_out`. Neither is ever the search's failure: the hits,
  total and facets are the sequential ones, field for field.
- **Match the UI's group to the server's by a term inside the span, not by index or text.** The canonical
  form collapses `(model OR model)` and deduplicates a group written twice, so positions and counts of
  groups differ between what was typed and what was counted (`group-counts.ts`: a term lies in at most one
  top-level span; the second copy says "same as group N", read from the server's `ast`).

## Dead ends — don't repeat these
- A rate-limit weight in place of a threshold: it prices the request after the work is done.
- One wait for both "queued" and "running": the queue time belongs to other clients.

## Decisions (and what would change them)
- Decision-034 records the field, its bounds and why they are thresholds; a measured cost model per
  collection would let the bound become a budget.

## Follow-ups
- Filed by the main session with the batch's follow-up tasks.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `fastapi-conventions` (§Handlers: an extra beside a search),
  `api-contract` (`groups`, `not_counted`, the three `/meta` limits), specs 03, 04, 05, 08, decision-034.
- Test or hook added? — the contract tests that pin the memo's entries and units, the bounds, the grace
  period and each `not_counted` value (commits above).
