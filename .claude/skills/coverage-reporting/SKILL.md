---
name: coverage-reporting
description: The spec 07 §C coverage standard — indexed accepted counts per venue × year × track compared with official accepted counts, the rules for docs/results/coverage-sources.md (one cited source per cell), the ±1% M4 gate on every main-track and D&B cell with an official count, the per-cell missing-abstract, unknown-track and statuses-indexed columns, and the known ways official numbers disagree with each other. Use when running `op eval coverage`, editing coverage-sources.md, reviewing the /coverage page or GET /coverage, or deciding whether M4 is done.
---

# Coverage reporting (spec 07 §C)

## What is measured
For every **venue × year × track** cell, from a pinned snapshot / `index_version`:
- `indexed_accepted` — records with `status:accepted` in that cell.
- `official_accepted` — from `docs/results/coverage-sources.md`.
- `delta = indexed − official`, `delta_pct = delta / official`.
- Plus per cell (spec 07 §C): `missing_abstract` count, `track:unknown` count, and **statuses indexed**:
  which statuses the sources for that venue-year can even contain. For example, pre-2021 NeurIPS and ICML
  2020–22 come from proceedings only, so no rejected papers exist there to exclude. Also `status:unknown`
  counts per venue-year.

`op eval coverage` writes `docs/results/<YYYY-MM-DD>-coverage.md`. `GET /coverage` and the `/coverage` page
render the **same data** (no second computation in the UI), with source and snapshot date shown per cell.

## The gate (M4)
Exactly spec 07 §C: **every main-track and D&B cell for which an official accepted count exists is within
±1%** (`|delta_pct| ≤ 1%`). Cells with no official count are reported (as `no source`) but not gated;
other tracks are reported, not gated. The same definition appears in spec 00. The gate is soft until M4
and then blocks the M4 milestone, not individual PRs.

## `docs/results/coverage-sources.md` — rules
One row per cell:
```
| venue | year | track | official_accepted | what it counts | source (URL or citation) | accessed |
```
- Every number has a **citation** a reader can check: the conference's own statistics page or blog post,
  the proceedings index (PMLR volume, NeurIPS proceedings site), or the OpenReview venue's accepted group.
  No number from memory, a tweet, or a secondary aggregator unless no primary exists (then say so).
- "What it counts" is mandatory: orals + spotlights + posters? before or after withdrawals? including
  position papers?
- Dated `accessed` field; sources change. Updating a number is a PR with the old value kept in the
  commit message.
- Roles, not names, for who verified a row.

## Known disagreements (why a cell can be off without a bug)
- Announced acceptance counts vs final proceedings (post-acceptance withdrawals, camera-ready no-shows).
- PMLR volume counts vs OpenReview accepted counts for ICML (verify per year at implementation time).
- NeurIPS D&B track: separate count, and ≤2023 proceedings use `Datasets_and_Benchmarks` aliased to
  `_Track` — misclassification shows up as main-track surplus + D&B deficit.
- ICML position papers counted inside or outside the main total.
- Deduplication across OpenReview and proceedings: an under-merge shows as surplus, an over-merge as
  deficit. Cross-check with `merges.csv`/`conflicts.csv` (`dedup-rules`).
When a cell misses the gate, classify the cause in the report (source definition, classification,
dedup, crawl gap) before changing anything. Never adjust the official number to fit.

## Report shape
Header: date, snapshot hash, `index_version`, source file revision. Table per venue with all cells,
`delta_pct` to one decimal, gate ✓/✗ (or "not gated" for a cell with no official count), the
`missing_abstract`, `unknown`-track and **statuses indexed** columns, and cause notes for every ✗. Totals
of `missing_abstract` and `unknown`. Command that produced it. The methods text cites this report (with its
snapshot hash) as the database-scope caveat.

## Gotchas
- `unknown` track records are *not* silently added to main to close a gap — they are the gap.
- Counts are per snapshot; a coverage number without its snapshot hash is uncitable.
