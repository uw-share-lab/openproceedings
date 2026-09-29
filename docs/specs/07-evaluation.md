# 07 — Evaluation

Status: **draft for review** · depends on: all parts · owns: the evidence that the guarantees hold

## Purpose

Turn each guarantee in 00 into something that can be checked. Some checks are CI gates (they fail the
build). Others are reports (they're regenerated and committed as dated results, never quoted from memory).

## A. Exactness (CI gates)

| Suite | What | Gate |
|---|---|---|
| Golden tokens | 02's table plus 100 or more normalization cases | 100% pass |
| Golden queries | Query → expected ID set on a hand-built 200-record fixture, with the cases written to be tricky (benchmark/benchmarking, trust/trustworthy, hyphens, LaTeX, phrases that span fields, NEAR ordering) | 100% pass |
| Differential | Hypothesis random ASTs: `TantivyEngine == ReferenceEngine` on the synthetic 5k fixture snapshot (decision-004) | 0 counterexamples in 200 examples per PR CI run, 2,000 and 50k nightly |
| Tokenizer parity | Stored text, positions (phrase read-back) and every term's document frequency in the index == `normalize.py`, over the whole corpus (term frequency only as far as the phrases imply) | 0 diffs |
| Semantic invariant | Search results identical with 06 on and off | 0 diffs |
| Determinism | Same canonical query + `index_version` → identical order and scores | 0 diffs |

As built (task-028): the differential is `backend/tests/differential/`, on a synthetic 5k corpus generated
in memory and hash-pinned (decision-004), with a Zipfian vocabulary: rare terms, hapaxes, and stems that
pass the 200-term cap. Trees are drawn from the corpus's own dictionary. For any tree an engine may get,
all-negative ones included, it compares:
- match sets;
- wildcard expansions, or the refusal;
- disjunctive facets;
- `total` for every sort, and the `year_asc` order;
- for trees that parse, the exclusion counts.

Shrunk counterexamples are kept in `differential-regressions.json` and replayed on every run. The 50k
nightly job is task-057.

## B. Scholar comparison (report, `op eval scholar`)

Replay the review's strings, starting with **Most Updated**, against the index (limited to the same venues
and years). Compare with the Scholar result set, which is the Trust-Evals `clean.ris` plus the 2020–2024
delta. Match papers by the merge rules in 01. Classify every disagreement:

| Only in Scholar, because… | Only in openproceedings, because… |
|---|---|
| matched only in full text | Scholar missed it (known recall gap) |
| matched only through stemming (e.g. `benchmarks`) | Scholar dropped it because of its 1,000-result cap or truncation |
| workshop / competition / rejected (filtered here, counted in `excluded`) | |
| not in the corpus (a coverage gap: fix 01) | |
| **our bug** (investigate; must be 0) | |

The classification is automatic where possible (for example, re-run the query with the stemmed variants
added, and check the track). The rest goes to `review.csv` for a person to decide. The output is
`docs/results/<date>-scholar-comparison.md`. This report is also a result the paper itself can use:
*how much of Scholar's result set comes from full-text matches and stemming.*

## C. Coverage (report plus a soft gate at M4)

For each venue × year × track: indexed accepted count compared with the official accepted count (the table
of sources lives in `docs/results/coverage-sources.md`, each with a citation; `official_counts.py` is its
machine-readable copy, which `GET /coverage` serves, and a test holds the two equal).

**The M4 gate:** every **main-track and D&B cell for which an official accepted count exists** is within
±1%, or an owner-accepted exception (below). Cells with no official count are reported but not gated. The same definition appears in 00 and in the
`coverage-reporting` skill. Also report, per cell: missing-abstract count, `unknown`-track count, and
**statuses indexed**, meaning which statuses the sources for that venue-year can even contain. For example,
NeurIPS 2013–2020 and ICML 2013–2022 come from proceedings only, so no rejected papers exist there to
exclude; NeurIPS and ICML on OpenReview hold only the rejected papers whose authors opted in, while ICLR
holds every rejected, withdrawn and desk-rejected submission (decision-012). The crawl window is 2013 on
(decision-013); any venue-year with no source is a reported gap, never a silent zero. ICLR 2014–2016 are
not gaps: their public archive listings supply accepted main-track records (TASK-096).
The source of statuses indexed is spec 01's source table as `ingest/statuses.py` holds it (spec 01
§Pipeline 5); the snapshot manifest records them per venue-year, and the missing abstracts and sources per
cell (manifest format 2, TASK-082).
The methods text cites the coverage report (with its snapshot hash) as the database-scope caveat.
`GET /coverage` serves every column per cell (`venue_years[].tracks`: sources, indexed accepted,
`official_accepted` with its citation, `delta`, `delta_pct`, `gated`, `within_gate`, missing abstracts) and
the statuses indexed per venue-year; `/coverage` in the UI renders the same data.
As built (TASK-054): `op eval coverage` renders `docs/results/<date>-coverage.md` from that same computation
(`api.coverage.compute` on the index, `eval/coverage_report.py`). It adds the gate verdict over every gated
official cell, with a cell the snapshot holds no record for as a gap (0 indexed, ✗); a cause note for every
failing cell, read from `docs/results/coverage-causes.toml` (`["<Venue> <year> <track>"]` with a `cause`) or
**unclassified**, with the file's sha256 in the header; every proceedings listing whose crawl skipped entries or
disagreed with its page's count; and every OpenReview crawl that is incomplete or has coverage gaps, conflicts,
unmapped venues, non-routine skipped groups or non-routine skipped notes. `--check` exits 1 when the gate fails.

**Owner-accepted exceptions.** A gated cell outside ±1% passes the gate only if the project owner accepted its
gap in a decision record and `coverage-causes.toml` records it under the cell (`["<Venue> <year> <track>".accepted]`:
`indexed`, `official`, `reason`, `papers` (record ids), `accepted_by` (a role: `project owner`), `accepted_on`,
`decision`; every key required, no other allowed, no control characters, and the decision record must exist in
`backlog/decisions/`). It passes only while the cell's indexed and official counts are exactly the accepted ones
**and** its papers are the gap: exactly |official − indexed| of them, each a record of the index's snapshot, and
outside the cell for an under-count (inside it for an over-count). Anything else fails the cell again
(`drifted`, the failed check in its cause note); a gap (no records) is never accepted and stays `✗ gap`. The
report marks the cell `✓ accepted exception`, lists every exception in its own section and counts them in the
verdict line, and reports an exception whose cell is within ±1% or not gated as stale; `--check` exits 1 on a
stale exception too. ICLR 2013 main is one (decision-016). The exception is applied by the gate report
(`op eval coverage`) only: `GET /coverage` and the `/coverage` page report the raw ±1% per cell, so an accepted
cell is served with `within_gate: false`.

## D. Classification audit (report)

Sample 50 records per `track` value (stratified by venue and year). Two reviewers label each one blind.
Report accuracy and Cohen's κ. Start with venuescout's 92 human-verified workshop calls as a seed set. The
target is ≥99% accuracy on `workshop` vs non-workshop, because a workshop slipping into a main-track search
is the specific failure this project exists to prevent.

## E. Performance (CI benchmark)

The 03 budgets are measured with `pytest-benchmark` on the fixture index in CI (a relative regression over
20% fails) and on the full index nightly.

As built (task-031): `backend/tests/bench/test_bench.py` runs on the synthetic 5k index. It covers every
Trust-Evals string (a 50-hit search and `match_ids` with exclusions, cold cache) and the widest expansion
under the cap and one past it, and asserts each budget on the p95 of 30 rounds. In ordinary runs benchmarks
are disabled and run once as tests; the `bench` workflow enables them and compares the head with the base
(the minimum time, the statistic least moved by runner noise). It also covers every sort, a broad query (thousands of matches),
the widest wildcard inside a search, a multi-token NEAR, a nested NOT, draining an export, and a 500-record build. The check is advisory until it has proven
free of false failures on shared runners (spec 08); sub-millisecond calls repeat within a round (≥ ~1 ms each). The search benchmark is warm after one warm-up round; `match_ids` clears every cache
(verified clauses, expansions, compiled queries) every round, so it is cold.
The ~80k numbers, and the position-verified cases spec 03 exempts, are a report
(`backend/tests/bench/report_80k.py` → `docs/results/<date>-bench.md`), from the same synthetic generator at
80k with abstracts of realistic length. The nightly full-index run is task-057.

## F. Usefulness of near-misses (report, M5)

This is 06's recall@25 protocol, using the review's Covidence included set as ground truth.

## Error handling

- A gate that cannot run (a missing fixture snapshot, a crashed oracle) **fails** the build; it is never
  skipped or reported as passed.
- A report whose inputs are missing (no Scholar set, no official count for a cell) says so in the report
  and leaves that cell unscored; it never fills in an estimate.
- An **our bug** row in the Scholar comparison (§B) or a differential counterexample (§A) opens a Backlog
  task with the query and the shrunk AST before the report is committed.

## Testing

The evaluation tooling is tested like any other code:
- The report generators (`op eval scholar|coverage|audit|near-miss`) have unit tests on fixture inputs
  with known answers. For example, a coverage fixture with one cell off by 2% must fail the gate.
- The CI gates in §A are checked for teeth by mutation. Deleting the comparison, or the oracle call, must
  make the suite fail (`qa-auditor`).
- Dated reports in `docs/results/` are regenerated from their command, never edited by hand. A report
  whose command no longer reproduces it is a Should.
