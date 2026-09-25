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
| Differential | Hypothesis random ASTs: `TantivyEngine == ReferenceEngine` on the 5k fixture snapshot | 0 counterexamples in 2,000 examples per CI run, 50k nightly |
| Tokenizer parity | Index tokens == `normalize.py` tokens over the whole corpus | 0 diffs |
| Semantic invariant | Search results identical with 06 on and off | 0 diffs |
| Determinism | Same canonical query + `index_version` → identical order and scores | 0 diffs |

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
of sources lives in `docs/results/coverage-sources.md`, each with a citation).

**The M4 gate:** every **main-track and D&B cell for which an official accepted count exists** is within
±1%. Cells with no official count are reported but not gated. The same definition appears in 00 and in the
`coverage-reporting` skill. Also report, per cell: missing-abstract count, `unknown`-track count, and
**statuses indexed**, meaning which statuses the sources for that venue-year can even contain. For example,
pre-2021 NeurIPS and ICML 2020–22 come from proceedings only, so no rejected papers exist there to exclude.
The methods text cites the coverage report (with its snapshot hash) as the database-scope caveat.
`/coverage` in the UI renders the same data.

## D. Classification audit (report)

Sample 50 records per `track` value (stratified by venue and year). Two reviewers label each one blind.
Report accuracy and Cohen's κ. Start with venuescout's 92 human-verified workshop calls as a seed set. The
target is ≥99% accuracy on `workshop` vs non-workshop, because a workshop slipping into a main-track search
is the specific failure this project exists to prevent.

## E. Performance (CI benchmark)

The 03 budgets are measured with `pytest-benchmark` on the fixture index in CI (a relative regression over
20% fails) and on the full index nightly.

## F. Usefulness of near-misses (report, M5)

This is 06's recall@25 protocol, using the review's Covidence included set as ground truth.
