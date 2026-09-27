---
id: decision-010
title: >-
  Cap position-verified clauses per query: API_TOO_MANY_VERIFIED_CLAUSES, an API
  code that carries located diagnostics
date: '2026-09-27 12:22'
status: accepted
---
## Context

A position-verified clause (spec 03: a phrase with a wildcard item, a NEAR that isn't two distinct terms) is
verified in pure Python on a cache miss, holding one of `ApiConfig.verification_slots` (default 1) while it
runs. The M3a round-2 security review found that one request of many such clauses held the only slot clause
after clause: 66 NEAR clauses took about 2.4 s on the 5k fixture and would take a minute or more on 80k
records, while every other user's verified query got 503 `API_BUSY`. The rate limit charged such a query one
`verified_weight` whatever its size.

The refusal needs a code. Options considered:
1. A `PARSE_` code. Its prefix gives 422 and located diagnostics for free, but `PARSE_` codes are the
   grammar's (spec 02): `POST /parse` and `op search` would not report it, and a query that parses would
   carry a "parse" error.
2. A `WILDCARD_` code, by analogy with `WILDCARD_TOO_MANY_EXPANSIONS`. That cap is the engine's and `op search`
   applies it too; this one is a serving policy of the API, and it counts NEAR clauses that hold no wildcard.
3. An `API_` code, 422, that carries diagnostics like a query refusal. Chosen.

## Decision

`ApiConfig.max_verified_clauses` (default 8) caps the position-verified clauses of one query. The API counts
them from the AST (`api/deps.py::verified_clauses`, by `engine.compile.verifies`'s rule; a test holds the
count equal to the compiler's) after the parse and before anything compiles, on every route that runs a query
(`/search`, `/export`, `POST /records`) and on a replay's re-parsed canonical (`GET /records/{id}`, `/diff`,
`/export?record_id=`). More than the cap is **422 `API_TOO_MANY_VERIFIED_CLAUSES`**, whose envelope carries
one diagnostic per verified clause spanning it in `q` (on a replay, one diagnostic with `span: null`: the
record's canonical string is not the client's `q`). Within the cap the query costs `verified_weight` per
clause, at most the smaller bucket's capacity (`RateLimit.verified_charge`), so a query within the cap can
always run and a large one empties the client's bucket.

`op search` has no such cap: it is the API's serving policy, like the rate limit and `API_BUSY`, not a
change to what a query means. The same query and `index_version` give the same ids through both whenever the
API runs it.

## Consequences

- The registry gains `API_TOO_MANY_VERIFIED_CLAUSES` (422); spec 04 §Error handling has its row, and
  `ErrorBody.diagnostics` is documented as present on it as on `PARSE_*`, `FIELD_*` and `WILDCARD_*`.
  `ErrorCode` is an open enum (decision-009), so this is additive within `/api/v1`.
- The frontend draws its diagnostics as squiggles, as for a parse error (spec 05 §Error handling).
- A record saved before an operator lowered the cap can be refused on replay; raising the cap back replays it.
  Its stored ids stay exportable only through a replay, so the operator's cap should not go below the
  largest saved query's count.
- Revisit if cold verification gets cheaper (task-080's successors) or runs outside the request.
