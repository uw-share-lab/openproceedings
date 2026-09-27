---
id: decision-008
title: >-
  Refuse queries whose canonical form exceeds the cap; judge wildcard detachment
  on folded pieces (QUERY_VERSION 2)
date: '2026-09-27 11:05'
status: accepted
---
## Context

The M3a review gate (query semantics) found two places where what parses was inconsistent with spec 02.

1. **The canonical string could exceed the 2,000-code-point cap.** `parse` checks the cap on the input,
   but the canonical form is longer than the input: the default filters are written out
   (`AND track:(datasets_benchmarks OR main OR position) AND status:accepted`, 71 characters), every
   juxtaposition becomes ` AND ` (4 more characters per term), `title:(a OR b)` puts the prefix on every
   leaf, and parentheses are added. A search record keeps the canonical string and replay re-parses it
   (`records.py`, natively), as does pasting it back. So a query that was accepted and saved could
   replay as `mismatch` with `PARSE_TOO_LONG`: a reproducibility bug (guarantee 4). Options: (a) refuse
   at parse time any query whose canonical string is over the cap; (b) let the canonical re-parse use a
   higher cap; (c) shorten the canonical form. (b) makes a pasted canonical string behave differently
   from typed text, and (c) changes every canonical string and hash for a corner case. The project owner
   chose (a).
2. **Wildcard detachment was judged on raw characters.** Spec 02 says a wildcard goes "directly after a
   letter or digit" and that NFKC look-alikes act as what they fold to. The lexer (task-075's `Token.reach`)
   asked whether the last word reached the end of the stem's raw characters, so `abcd⒈*` (`⒈` folds to
   `1.`) was accepted as `abcd1*` while its NFKC spelling `abcd1.*` was `PARSE_WILDCARD_DETACHED`, and
   `abcd⑴*` (`(1)`) searched `"abcd 1*"`. Options: (a) keep raw characters (the look-alike stays a
   loophole); (b) judge on the folded pieces. The project owner chose (b).

## Decision

After canonicalising, `parse` refuses a query whose canonical string is longer than `MAX_QUERY_LENGTH`
with `PARSE_TOO_LONG`, spanning the whole input and stating the canonical length and how much the
canonical form added. A wildcard is attached only if the **last folded piece** of its stem is a letter or
digit (`normalize.tokenize_with_tail`); otherwise it is `PARSE_WILDCARD_DETACHED`, and the message names
the piece and the raw text it came from (`follows `.` (from `⒈`)`). Both change which queries parse, so
`QUERY_VERSION` goes from `"1"` to `"2"` (spec 04 §Conventions, index-versioning skill).

## Consequences

- Every accepted query's canonical string is itself an accepted, idempotent query (property
  `test_an_accepted_query_near_the_cap_replays_from_its_canonical_string`; contract
  `test_records_at_cap.py`: a record saved at the cap is `reproduced`).
- The effective input limit is lower than 2,000 for long queries: with juxtaposition and the defaults,
  inputs from about 1,170 code points up can be refused. A near-cap differential against `feat/m3a-api`
  (5,000 valid queries of 1,000–2,000 code points) changed 2,026 from accepted to `PARSE_TOO_LONG`, all
  with an old canonical string of 2,001–3,394 code points, and none of any other kind. If reviewers hit
  this with real search strings, revisit option (b) above.
- Detachment: `abcd⒈*`, `abcd⒈̸*`, `abcd⑴*`, `abcd⑴̸*` are now detached; `abcd½*` (`1⁄2`, last piece `2`)
  and `abcd≠ͅ*` (last piece `ι`) stay attached. A 46,711-input fuzz differential (random queries,
  every multi-piece NFKC character as a stem's final character with `*`, U+0338 and `$`) changed 5,097
  native and 5,136 Scholar parses from accepted to `PARSE_WILDCARD_DETACHED`, each after a stem whose
  final character folds to several pieces (184 distinct characters), none otherwise, and no canonical
  string of a query accepted by both changed.
- `Token.reach` no longer decides anything that parses; it is kept because the frozen task-073 oracle
  (`tests/unit/tokenize_before.py`) compares it. No token changes, so `TOKENIZER_VERSION` stays `"2"`.
- `QUERY_VERSION` `"2"` changes every `canonical_hash` (decision-003). No search records exist yet (nothing
  has been released), so nothing replays as `drifted`; the Trust-Evals snapshot hashes were regenerated
  (their canonical strings are unchanged).
- Spec 02 (§Grammar wildcards, §Token semantics on `reach`, §Error handling, §Outputs `QUERY_VERSION`),
  `lexer.py`'s docstring and the `query-grammar` and `token-contract` skills say so.

