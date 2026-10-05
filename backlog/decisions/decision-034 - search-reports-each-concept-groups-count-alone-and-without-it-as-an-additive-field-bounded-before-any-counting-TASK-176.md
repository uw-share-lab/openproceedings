---
id: decision-034
title: >-
  /search reports each concept group's count alone and without it, as an
  additive field bounded before any counting (TASK-176)
date: '2026-10-05 07:20'
status: accepted
---
## Context

A reviewer's string is an AND of concept groups, and when it returns few papers nothing showed which group was cutting. On 2026-10-04 the Trust-Evals string returned 67 papers on index `05a0541717f6`, and it took a script to learn that its trust group was the bottleneck. The engine can answer exactly, with no semantic layer: count each group on the same index, under the same filters.

Three things had to be settled.

**What is counted.** "Top-level" is the facets' and the default filters' notion (decision-001): the canonical effective tree's top-level AND conjuncts. A count of a group with no filters at all (15,724 / 1,340 / 18,871 on the example) is not comparable with `total`, so every count keeps the query's filters. Two numbers were considered, and the owner decided on 2026-10-05 to report both: the group alone (how wide it is: 6,343 / 529 / 9,303) and the query without the group (what it removes given the others: 139 / 2,337 / 181 against the total of 67).

**Where it lives.** Options: (1) an additive field always sent on `GET /search`; (2) an opt-in parameter; (3) a separate endpoint. An opt-in parameter gives one response two shapes, and the UI would always send it. A separate endpoint parses, admits and charges the query a second time (decision-010) and can answer from another `index_version` than the `total` it is compared with.

**What it may cost.** Decision-010 charges position verification only, and counting adds none: every tree counted holds only clauses the request already verified. What it does cost is collections, each of which reads the kept clauses again. The first implementation also stored each counted tree in the shared `compiled` memo. Measured in review on the 5k fixture, 10 one-word groups and one kept `NOT (… 158 wildcards …)` (4,522 expanded terms, no verified clause, one rate-limit token) took 1,198 ms against 259 ms and stored 12 `compiled` entries of 114,356 units against 2 of 19,106, of a 500,000-unit budget every client shares. A kept `NOT (model NEAR/10 model*)` had its id term set rebuilt 20 times. Two ways to bound what remains were considered: a rate-limit charge per counted group, or a cutoff decided before any counting. A slow or failing counting job also failed or held the whole search, and on a pool shared with the facets it could delay other clients' searches.

## Decision

`GET /search` always sends an additive `groups` field (option 1). A **group** is a top-level AND conjunct of the canonical effective tree that searches text and is not negated; every other conjunct (filter clauses, the inserted defaults, ORs of filters, negated text) is kept for every count. Each counted group has `span` (its code-point range in `q`), `total` (the group alone: the query with every other group removed) and `total_without` (the query with that group removed). The shape is `{counts, groups_total, limit, not_counted}`; `not_counted` is an open enum (decision-009), null exactly when `counts` is filled: `fewer_than_two_groups`, `too_many_groups`, `too_costly`, `busy`, `count_failed`, `timed_out`. In every case the response is a 200 and the search itself is whole.

The counting is bounded before it starts, by a cutoff rather than a charge:

| Bound (`ApiConfig`, `op serve` flag, `/meta` `limits`) | Default | Over it |
|---|---|---|
| `max_counted_groups` | 10 | `too_many_groups` |
| `max_counted_terms`: the terms the trees counted read | 5,000 | `too_costly` |
| `max_counted_ids`: the verified ids they read | 300,000 | `too_costly` |

Both sums are **N·G + 2·N·K** over the 2 × N trees counted, for N groups weighing G in all and kept text clauses weighing K (a wildcard weighs its expansions, a filter nothing; a position-verified clause weighs its matched ids per field). A cutoff was chosen over a rate-limit charge because the cost is known exactly before any work; a refusal costs the client nothing and loses only the extra; and a charge would either price every ordinary three-group search for a cost only a query built for it has, or still let one request do the work.

Nothing a count compiles is stored in the `compiled` memo: each non-filter conjunct is compiled once per request and every tree's query is built by ANDing those (`TantivyEngine.counts`). The collections are memoised in `faceted`, as the facets' are. Counting runs on its own two workers, never the facet pool. Once the rest of the search is done it waits 50 ms for a job no worker has taken (`busy`) and 2 s for one that is running (`timed_out`); an abandoned job stops before its next collection, and any failure of the job is `count_failed`, never the search's.

Search records, exports and `op search` carry no counts.

## Consequences

- The counts are exact and reproducible: a function of the canonical query and the `index_version` (guarantee 4), equal to ReferenceEngine's count of the same tree, never below `total`, and nothing the page, `total`, the facets or `excluded` are computed from reads them (guarantee 5). `tests/unit/test_group_counts.py` and `tests/contract/test_group_counts.py` hold all of this, the memo cost on the 158-wildcard shape (the plain search's 2 entries and 19,106 units, exactly), and each `not_counted` reason.
- No `index_version`, `canonical_hash` or `query_version` input changes, and no stored record changes: old records replay as before.
- Whether a query is `too_costly` depends on the instance's bounds as well as the query and index, so two instances with different bounds can answer the same query with and without counts. Both always return the same search.
- The ids bound is decided after the request's own compile, so a request that is `too_costly` by its ids has already been admitted, charged and verified under decision-010, exactly as the same search without counts.
- The defaults leave the real review strings far inside: on the real index the Trust-Evals strings read 30 to 243 terms and 0 to 65,286 ids. A changed kept clause makes every group collect again, within the same bounds.
- Other clients' counting can cost a search its counts and at most the 50 ms grace of its time. `busy` is logged at DEBUG (a state under load), `timed_out` at WARNING, `count_failed` at ERROR with the error's type and never its message.
- Spec 04 §SearchResponse `groups` states the rule and the measurements; spec 05 §Components 3 and copy BD-12 the builder's wording; the `api-contract` and `logging-standards` skills carry the shape and the log lines.
- Revisit if a count ever needs a verification of its own (then it falls under decision-010's charge), if real review queries start meeting `too_costly` (raise the bounds, measured on the real index), or if the counts move outside the request.

