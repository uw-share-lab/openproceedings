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
| Nightly | property/golden fixtures and exhaustive Unicode inputs | no full corpus | the whole backend suite at the `ci` profile (2,000), every property at 50k as a 5-part `properties` matrix, the year-edit property as 4 seeded `year-edits` jobs, exhaustive tokenizer check, differential@50k (12 parallel jobs of 4,166 or 4,167), spec 03 benchmarks with their budgets plus the ~80k report (`benchmarks` job), gate/tooling mutation run of every mutant as 12 `mutate` shards (`mutate.py --shard i/12`; TASK-057, TASK-171) |

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
  stub serves `src/components/coverage/coverage-fixture.json`, a record stub `record-fixture.json`, a
  comparison stub `src/components/compare/compare-fixture.json` (all kept equal to the served API by backend
  contract tests). A partial body typed as the response is a lie the
  compiler can't see: the next component that reads one more field crashes in an unrelated test file
  (TASK-110, `concept-builder.test.tsx`).

- **e2e instances.** `fixture_server.py` serves one index from three configurations (API port: default;
  +1 `tight`: low group-count bounds, rate limit and comparison cooldown on, a tiny comparison file cap; +2
  `plain`: comparisons off). A spec reaches a state only another configuration gives with
  `useInstance(page, "tight")` (`frontend/e2e/instances.ts`, which re-addresses the page's API calls), never by
  writing the answer in the browser. Tests on `tight` share one client network, so one that needs a
  comparison waits out another's cooldown through the panel's own Retry. Add a configuration there rather
  than a second fixture server.
- **A test of CodeMirror's parse reads the whole tree.** `syntaxTree(state)` is what CodeMirror parsed within
  its start-up time budget (wall clock), so under load it can be the tree of a prefix: use
  `ensureSyntaxTree(state, length, timeout)` in a test (`grammar.test.ts`; it failed about once a run at load
  100 before, and a test there now pins it with a clock that outruns the budget). A test that passes only
  when the machine is quick is waiting on a time budget somewhere: find it before raising a timeout.
- **e2e ports.** Playwright's fixture API and web server listen on 8000 and 3000 unless `OP_E2E_API_PORT` /
  `OP_E2E_WEB_PORT` are set (`playwright.config.ts`, `fixture_server.py`, and every spec that calls the API
  directly read the same two). Locally the config reuses a server already on its port, so with another
  instance on 8000/3000 an unset run would test *that* instance: set both variables. The owner's dev servers
  run `main`-branch code on the real index, so from a worktree an unset run failed all 66 tests; always run
  `OP_E2E_API_PORT=8100 OP_E2E_WEB_PORT=3100 make e2e`. The fixture server also listens on the API port + 1 and
  + 2 (`tight`, `plain`; TASK-182), so the web port never sits there (`/dependabot-review` step 5 picks both).

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
7. **Untrusted input gets a timing-bounded test.** A regex over server output (an XML prolog skip) backtracked
   exponentially; use a linear `find` loop, and test adversarial input (many PIs, unterminated) with a CPU
   growth check (§CPU growth checks), in a daemon thread with a generous join when a hang is possible. A
   repeated group that must be followed by a delimiter it can never give back is written possessive
   (`(?:\.\d++)*+`): greedy, Python's `re` keeps state per repetition (63 MB on a 1 MB value, TASK-272), so
   bound the peak with `backend/tests/timing.py`'s `peak_bytes` (tracemalloc) beside the CPU check; bytes don't depend on the runner's cache.
   A `search`/`finditer`/`sub` pattern that opens with a run (`(\\*)[{}]`) tries a match at every character of a
   run that nothing ends, each attempt reading the rest of the run: quadratic. Anchor it where the run starts
   (`(?<!\\)(\\*)[{}]`). That gives the same matches only when no match ends inside a run *and* an attempt that
   fails at a run's first character fails at every later one too: true of `(\\*)X`, whose repeat can stop at
   any length of the run, false of a parity pattern such as `(?:\\\\)*@`, which stops only at even lengths and anchored misses the match in `\\\@` (three backslashes). Show it with an
   exhaustive comparison of the matches over every short string of the characters it reads (TASK-274).
   A run that must hold a word and then end at a delimiter (`[?&][a-z0-9_]*?(?:token|key)[a-z0-9_]*=`) reads the
   rest of the run once for every place the word appears in it; check the word with a lookahead and take the run
   once, possessive (`[?&](?=[a-z0-9_]*(?:token|key))[a-z0-9_]*+=`, TASK-275). When one pattern is found quadratic,
   time every pattern beside it that the same text reaches on the same hostile shapes: TASK-275 and TASK-276 each
   named one, and the function holding it had a second (`scrub`'s query pattern, `_split_entry`'s separator).
8. **A failure that appears in one checkout only is a stored example.** The `.hypothesis` database holds an input
   no `@example` covers. Extract the falsifying input and pin it as an `@example` before bisecting or calling it
   pre-existing (a database copied between checkouts stores choice sequences, so the bisect proves nothing; the
   idempotence bug of 2026-10-10 was real). Check "pre-existing" in a detached temporary worktree
   (`git worktree add --detach`), never with `git stash`, which every worktree shares.

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
that fails closed, an unreviewed HEAD) does not count. Isolate the one check the row is about. Text kept
identical in several files (the shared AI-attribution pattern) is mutated in all of them at once with `also`
(`{label, file, old, new, also: [files]}`); a one-file mutant there is killed only by the identity row (TASK-243).
A table that exercises only some files says so in its header comment (`# mutate-scope: <file> …`, repo-relative paths exactly as a mutant's `file`), and `mutate.py`
then runs it only for those files' mutants, so a failure from load is never credited with another file's (TASK-238); a
declared path that doesn't exist is refused (exit 2). A mutant's `old` text must occur exactly once in each of its files,
and its edit must leave a file that compiled still compiling (`mutate.py --check`, in `make tooling`, refuses `STALE`,
`AMBIGUOUS` and `UNCOMPILABLE` ones: TASK-254). Make an `old` text unique with the lines around it, and write a `new`
that compiles (`if False:` for a removed branch, `pass` for a removed body).
An `equivalent` label needs evidence for the actual replacement, including a distinguishing negative case
and a positive control. Dropping an explicit default and forcing its opposite are different mutations:
`--no-renames` makes an unchanged learning rename look newly added, even though `--find-renames` gives 0/0.
Compare actual hook verdicts for benign unsupported syntax too: a conservative parser can intentionally
block a shape that a mutant allows. Identical destructive-case verdicts alone do not prove equivalence.

A killing row decays when later work changes what blocks it first (TASK-261, nine nightly survivors). It can decay
because a "made-up" fallback case becomes a known one: `caffeinate` became a known wrapper in TASK-248, so the
unknown-wrapper rows stopped reaching their fallback. It can decay because a newer fail-closed check refuses the
probe for its own reason: `HOOK_INPUT='{}'` became malformed to `guard_payload`, and a missing message file became
unreadable under TASK-243. And it can decay because the fixture differs by OS: on Linux, `mktemp -d` is under
`/tmp`, so `find /tmp .` was blocked by its first start. So:
- a row probing a fallback uses a name that can never join the known set (`unknown-wrapper`);
- a block row's other inputs are well formed, present and harmless, so only the check under test can block;
- a start or path in a row lives inside the table's own root, never at a system path.
When the nightly reports a survivor, apply that one mutant and run its table on the OS that reported it, before
assuming the row still kills it.

Case tables must also parse on the developer platform's Bash. Stock macOS Bash 3.2 can misparse a
case-pattern `)` inside command substitution; compute the case result in a variable outside `$(...)`
and keep the same assertion. Run the table with stock Bash as well as the CI version when available.
Capture controlled runner output on the line before a `check` call and pass the variable as data;
`lint_probes.py` forbids command substitutions inside assertion arguments even for tooling tables.

## CPU growth checks

For adversarial algorithmic scaling checks, keep the input sizes and growth cutoff fixed. Measure thread CPU
time in batches, pair the small and large measurements in each round, alternate their order, and compare the
median paired growth ratio. Independent fastest calls at each size can compare unlike CPU/allocation phases
even though thread CPU time excludes preemption. Keep allocation, copying and reference-counted freeing in
the measurement, but pause the cyclic garbage collector while a call is timed: a full collection walks the
whole test worker's heap, not the input, and fires mostly on the side that keeps more objects alive (the
ICML 2007 hostile page failed at 8.09 and 8.24 in CI's xdist workers that way, runs 38176036366 and
38197206724). Before changing a sampling method, demonstrate that the former quadratic behavior still fails
the same cutoff; a green optimized implementation alone does not prove the check works.
`backend/tests/timing.py` is the one implementation (`cpu`, `growth`, `assert_near_linear`: 4x the input under 8x the CPU time, median of paired rounds, collector paused; `backend/tests/unit/test_timing.py` shows
a quadratic in work and one in allocation fail it, and that no collection runs inside a timed call); use it
(or its `cpu`, for a one-size CPU bound) for every linear-time test, including batched ones (`growth(...,
calls=8)`); `peak_bytes` is its memory bound, for a check whose CPU time depends on the runner (§7). Work another thread does (a request TestClient serves) is invisible to this thread's CPU clock:
pass `growth` a `measure` that reads that thread's own CPU time and pauses the collector (`collector_paused`),
as `contract/test_verification_scale.py`'s `width_is_free` reads the server's `verify_cpu_ms` from each
request's access line, never the request's wall time. Never assert a wall-clock bound at one size: on a shared
runner, beside four xdist workers running 50,000-example properties, a 17 ms parse took 1.9 s and a 5 ms page
2.5 s (nightlies 37943547380, 38056534247). A wall-clock bound in a concurrency test is set by the hold it
tells apart (under the 2 s wait it would otherwise wait), never tighter.
`backend/tests/unit/test_latex_scan.py` (unclosed math openers, TASK-171 recovery),
`backend/tests/unit/engine/test_highlight_speed.py` (tokenizer stretches) and
`backend/tests/unit/ingest/test_html.py` (`escape_bare_lt`) apply it in batches.
