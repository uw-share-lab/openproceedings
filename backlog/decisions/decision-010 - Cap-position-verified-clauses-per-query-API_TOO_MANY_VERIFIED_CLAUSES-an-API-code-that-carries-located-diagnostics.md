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

`ApiConfig.max_verified_clauses` (default 8; 16 since round 3, see Consequences) caps the position-verified clauses of one query. The API counts
them from the AST (`engine.compile.verified_clauses`, by `verifies`'s rule; a test holds the count equal to
the compiler's) after the parse and before anything compiles, on every route that runs a query (`/search`,
`/export`, `POST /records`) and on a replay's re-parsed canonical (`GET /records/{id}`, `/diff`,
`/export?record_id=`). More than the cap is **422 `API_TOO_MANY_VERIFIED_CLAUSES`**, whose envelope carries
one diagnostic per verified clause spanning it in `q` (a replay over it is withheld instead: see
Consequences, round 3). Within the cap the query costs `ApiConfig.verified_cost` per clause, and the cap
times that cost fits the smaller bucket (round 3), so a query within the cap can always run and one at the
cap empties the client's bucket.

`op search` has no such cap: it is the API's serving policy, like the rate limit and `API_BUSY`, not a
change to what a query means. The same query and `index_version` give the same ids through both whenever the
API runs it.

## Consequences

- The registry gains `API_TOO_MANY_VERIFIED_CLAUSES` (422); spec 04 §Error handling has its row, and
  `ErrorBody.diagnostics` is documented as present on it as on `PARSE_*`, `FIELD_*` and `WILDCARD_*`.
  `ErrorCode` is an open enum (decision-009), so this is additive within `/api/v1`.
- The frontend draws its diagnostics as squiggles, as for a parse error (spec 05 §Error handling).
- **A replay over a limit is withheld, not refused (M3a review gate round 3).** A record saved before an
  operator lowered the cap (or the candidate ceiling below) is not re-run on this instance, but it stays
  readable: `GET /records/{id}` and `/diff` answer 200 with `replay.refused` set to the code, every count
  null, nothing compiled and nothing charged for its clauses, and `replay.verified_clauses` giving the
  count (the record page reads "could not be re-run: `API_TOO_MANY_VERIFIED_CLAUSES` — this instance's limit
  is below the record's N position-verified clauses"). It is never presented as reproduced or as
  membership-identical, and the withholding itself is never a `mismatch` and logs no `replay_mismatch`. On the
  record's own index under its own query version the status is `drifted` with `changed: []`; the checks that
  need no run (the canonical re-parse, the index's inputs, the stored list's hash and total) still apply,
  and one failing is a `mismatch`, logged as always. Elsewhere it is `drifted` with its changed inputs. A new
  status value (`withheld`) was considered and rejected: the replay `status` is a closed enum in `/api/v1`
  (decision-009), so a new value would be a breaking change, while `refused` (an open error-code enum)
  already says why nothing was compared. `/export?record_id=` still streams the stored ids (it hands over
  the stored list from the pinned index and never re-runs the query; only a `mismatch` blocks it). Raising
  the limit replays the record in full.
- **The clause count is not the cost; candidates are (M3a review gate round 3).** A clause's cold
  verification reads every candidate document (each holding all its items in the field, ~40 µs each), so
  8 clauses of a common word NEAR itself (`(a NEAR/50 a) OR … (4o NEAR/49 4o)`) held the only slot for
  63 s on the synthetic 80k index while costing 60 tokens against a 60 s refill. `ApiConfig.
  max_verification_candidates` (default 300,000, about 12 s of verification) bounds the candidates of one
  query, summed over its verified clauses and their fields, counted from the inverted index before any is
  verified (`TantivyEngine.candidates`, every clause counted cached or not, so a refusal never depends on
  the memos). Over it is **422 `API_QUERY_TOO_COSTLY`**, a new registry code carrying one located diagnostic
  per clause with its counts. A new code rather than `API_TOO_MANY_VERIFIED_CLAUSES` with a reason: the two
  have different remedies (fewer clauses, versus narrower clauses: longer stems, rarer words), a client
  branches on the code, not on a message, and `ErrorCode` is open (decision-009), so it is additive.
  Measured on the synthetic 80k index (candidates summed; cold verification): the exploit 686,684 (refused,
  counted in 4 ms); 8 × `model NEAR/k model*` 543,208 (refused); `"calibrat* trust" OR trust NEAR/3 trust`
  137,933 (5.4 s, served); `a NEAR/50 a` 96,580 (3.7 s); `trust NEAR/5 model*` 66,720 (2.9 s);
  `"large language model*"` 57,516 (2.3 s); `trust NEAR/5 model` none (not verified). The heaviest real
  review query, the published Trust-Evals `main-2-pop` string in Scholar mode, reads 247,793 (10.2 s) there
  (2,251 on the real 1,805-paper corpus, about 100,000 scaled to 80k), so the default sits above it and
  below the exploit shapes: 300,000. `backend/tests/contract/test_verification_scale.py` holds this at a
  5k-scaled ceiling in CI and at the true defaults on a built 80k index (`OP_BENCH_80K=1`): the exploit (8
  and 16 clauses) refused before any verification, every Trust-Evals string served in both modes (the one
  that doesn't parse in native mode, `main-2-pop`'s `AI$`, is the parser's 422, not a limit's).
- **The clause cap is a backstop, raised to 16 (round 3).** With the candidate ceiling bounding the actual
  cost, the clause cap only has to stop a query of absurdly many clauses before anything is counted. At 8 it
  refused `main-2-pop` (10 verified clauses in Scholar mode), a systematic reviewer's real, published
  search string, and the API must not refuse a real review query. 16 admits every Trust-Evals string with
  room to spare; a 16-clause exploit is refused by the candidate ceiling instead. The per-clause cost falls
  to 60 / 16 = 3.75 at the default bucket, so a query at the cap still costs the whole bucket (60).
- **Every clause up to the cap costs its share.** Capping a charge at the bucket made clauses past
  capacity ÷ weight free (at the then defaults, 8 cost what 6 did). A configured `verified_weight` × the cap
  must now fit the smaller bucket (the config refuses it otherwise), and without one the per-clause cost is
  the export weight lowered to fit (default min(10, 60 / 16) = 3.75). `op serve` takes `--max-verified-clauses`
  and `--max-verification-candidates`.
- A refusal after the verified charge was taken (`API_QUERY_TOO_COSTLY`, or `API_BUSY` from a slot) gives
  the charge back; within a request every compile shares the ids it verified (`tantivy_engine.Scope`), so no
  clause is verified twice however the memos are trimmed, and the facet worker never verifies (no slot).
- Revisit if cold verification gets cheaper (task-080's successors) or runs outside the request.
