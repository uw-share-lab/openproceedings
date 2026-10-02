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
| Differential | `backend/tests/differential/` | **5k fixture snapshot** | `TantivyEngine == ReferenceEngine`, 0 counterexamples in 200 (PR CI) / 50k (nightly, its own 8-way split `differential` job: TASK-057) |
| Contract | `backend/tests/contract/` | 5k fixture index via `TestClient` | every endpoint, OpenAPI snapshot, export round-trips, record replay (reproduced + drifted + mismatch) |
| Frontend unit | `frontend/**/*.test.ts(x)` (Vitest) | mocked API from generated types | builder↔AST, URL reducer |
| e2e | Playwright | `backend/tests/e2e/fixture_server.py` builds/serves the temporary 5k index; production frontend build | the 05 §Testing flow end to end |
| Bench | pytest-benchmark | fixture index (`bench` workflow, advisory), 80k report (`report_80k.py`) | >20% regression of the minimum fails the `bench` check |
| Nightly | property/golden fixtures and exhaustive Unicode inputs | no full corpus | the whole backend suite at the `ci` profile (2,000), oracle-backed and remaining properties at 50k, exhaustive tokenizer check, differential@50k (8 parallel jobs), spec 03 benchmarks with their budgets plus the ~80k report, full gate/tooling mutation run (TASK-057) |

## Fixtures (`backend/tests/fixtures/`)
- **Golden 200:** hand-built records whose text is written to be tricky (benchmark/benchmarking,
  trust/trustworthy, hyphens, LaTeX, phrases spanning title/abstract, NEAR order). Every expected ID set is
  written by a person and cross-checked against `ReferenceEngine`.
- **5k snapshot (decision-004): synthetic**, generated deterministically by a committed script in the
  snapshot format (`records.jsonl` + `manifest.json`), covering every venue × year × track × status so
  filters and exclusion accounting are exercised, with realistic vocabulary, LaTeX and Unicode. It is
  versioned: regenerating it is a PR with its own manifest diff, and changes the fixture `index_version`.
  Real-corpus checks (tokenizer parity, task-029) run locally against the maintainer's snapshot, never in
  CI: the real corpus is never committed (decision-004). Decision-018 (00 open question 1, closed) lets a
  public instance serve abstracts; it does not put real abstracts in git or in CI fixtures.
- Recorded HTTP fixtures (VCR-style) for each crawler source and year schema (01 §Testing), scrubbed of
  real text (decision-004). Tests never
  hit the network, and it is **enforced**: `backend/tests/conftest.py` makes every non-loopback socket
  connection and DNS lookup raise `NetworkBlockedError` for the whole session (`test_no_network.py`). A test
  that needs a response gets a recorded fixture; there is no marker to opt out. Recording fixtures is a
  manual `op ingest` run by a person, never part of `make test` or CI.
- **Frontend stubs answer with the API's own fixtures**, not hand-typed partial bodies: a `GET /coverage`
  stub serves `src/components/coverage/coverage-fixture.json`, a record stub `record-fixture.json` (both kept
  equal to the served API by backend contract tests). A partial body typed as the response is a lie the
  compiler can't see: the next component that reads one more field crashes in an unrelated test file
  (TASK-110, `concept-builder.test.tsx`).

## Rules
1. **TDD.** Write the failing test first, watch it fail for the right reason, then implement. A bug fix
   starts with a test that reproduces it.
2. **Never mark a test `xfail`, `skip` or `@pytest.mark.flaky` to get green**, and never loosen an assertion
   (set equality → subset, exact count → `>=`) to pass. A red test is a finding: fix the code or open a
   Backlog task and keep it red on a branch that isn't merged.
3. **Never delete a golden row.** Add one for every bug ever found. Changing an expected value needs the
   reason in the commit message and routes to `exactness-guardian`.
4. **Sets, not samples.** Assert full ID sets and exact `total`/`excluded`, not "first hit is X".
5. **Determinism.** No wall clock, randomness or network in tests (network is blocked by conftest); Hypothesis runs under a named profile
   (`property-testing`). Its wall-clock checks (deadline, `too_slow`) are gates only on CI runners: the local
   `dev` profile turns them off, and `pr`, `ci` and `nightly` keep them (decision-024).
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
hook or tooling script ships with a mutant in `.claude/scripts/mutants/*.json` (`gates.json`, or a file of its own such as `merge-group.json`), and with a case-table row
that kills it. A row that passes only because something else fails first (a stale index, a parser crash
that fails closed, an unreviewed HEAD) does not count. Isolate the one check the row is about.
