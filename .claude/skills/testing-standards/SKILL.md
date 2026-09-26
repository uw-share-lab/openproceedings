---
name: testing-standards
description: The openproceedings test pyramid from spec 07 — unit, golden, differential, contract, e2e, bench and nightly suites, where each lives, which fixture each uses (the 200-record golden fixture, the 5k fixture snapshot), TDD order, and the hard rules (never xfail or skip to get green, never delete a golden row, never claim a pass you didn't run). Use when writing or reviewing tests, adding a fixture, deciding which suite a case belongs in, or when CI's test job fails.
---

# Testing standards (spec 07)

## The pyramid — each suite, what it proves, its gate
| Suite | Path | Fixture | Gate |
|---|---|---|---|
| Unit | `backend/tests/unit/` | inline values | 100% pass |
| Golden tokens | `backend/tests/golden/test_tokens.py` | 02 table + ≥100 cases | 100% pass |
| Golden queries | `backend/tests/golden/` | hand-built **200-record** fixture | 100% pass, exact ID sets |
| Differential | `backend/tests/differential/` | **5k fixture snapshot** | `TantivyEngine == ReferenceEngine`, 0 counterexamples in 2,000 (CI) / 50k (nightly) |
| Contract | `backend/tests/contract/` | 5k fixture index via `TestClient` | every endpoint, OpenAPI snapshot, export round-trips, record replay (reproduced + drifted + mismatch) |
| Frontend unit | `frontend/**/*.test.ts(x)` (Vitest) | mocked API from generated types | builder↔AST, URL reducer |
| e2e | Playwright | `op serve` over the fixture index | the 05 §Testing flow end to end |
| Bench | pytest-benchmark | fixture index (CI), full index (nightly) | >20% relative regression fails |
| Nightly | — | full corpus | differential@50k, tokenizer parity (0 diffs), semantic invariant, determinism |

## Fixtures (`backend/tests/fixtures/`)
- **Golden 200:** hand-built records whose text is written to be tricky (benchmark/benchmarking,
  trust/trustworthy, hyphens, LaTeX, phrases spanning title/abstract, NEAR order). Every expected ID set is
  written by a person and cross-checked against `ReferenceEngine`.
- **5k snapshot:** a deterministic sample of the real corpus in the snapshot format (`records.jsonl` +
  `manifest.json`), stratified across venue × year × track × status so filters and exclusion accounting
  are exercised. It is versioned: regenerating it is a PR with its own manifest diff, and changes the
  fixture `index_version`. Verify at implementation time that abstract licensing (00 open question 1)
  allows committing the sample; if not, it is built in CI from a pinned cache.
- Recorded HTTP fixtures (VCR-style) for each crawler source and year schema (01 §Testing). Tests never
  hit the network.

## Rules
1. **TDD.** Write the failing test first, watch it fail for the right reason, then implement. A bug fix
   starts with a test that reproduces it.
2. **Never mark a test `xfail`, `skip` or `@pytest.mark.flaky` to get green**, and never loosen an assertion
   (set equality → subset, exact count → `>=`) to pass. A red test is a finding: fix the code or open a
   Backlog task and keep it red on a branch that isn't merged.
3. **Never delete a golden row.** Add one for every bug ever found. Changing an expected value needs the
   reason in the commit message and routes to `exactness-guardian`.
4. **Sets, not samples.** Assert full ID sets and exact `total`/`excluded`, not "first hit is X".
5. **Determinism.** No wall clock, randomness or network in tests; Hypothesis runs under a named profile
   (`property-testing`).
6. **Claim only what you ran.** Report the command and its summary line (`412 passed in 9.1s`).

## Commands
`uv run pytest backend/tests/unit backend/tests/golden -q` (fast loop) ·
`HYPOTHESIS_PROFILE=ci uv run pytest backend/tests/differential -q` ·
`uv run pytest backend/tests/contract -q` · `npm test` · `npx playwright test`.

## What goes where
Pure function → unit. Anything that decides *what matches* → golden (+ differential if it touches
compilation). Anything the frontend or a script depends on → contract. User-visible flow → e2e.

## Mutation testing (gates and tooling)
`make mutate` / `make mutate-changed` / `mutate.py --match` (spec 08 §Mutation testing). Every new check in a
hook or tooling script ships with a mutant in `.claude/scripts/mutants/gates.json`, and with a case-table row
that kills it. A row that passes only because something else fails first (a stale index, a parser crash
that fails closed, an unreviewed HEAD) does not count. Isolate the one check the row is about.
