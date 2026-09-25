---
name: coverage-reporting
description: The spec 07 §C coverage standard — indexed accepted counts per venue × year × track compared with official accepted counts, the rules for docs/results/coverage-sources.md (one cited source per cell), the ±1% M4 gate on main-track cells, the missing-abstract and unknown-track counts, and the known ways official numbers disagree with each other. Use when running `op eval coverage`, editing coverage-sources.md, reviewing the /coverage page or GET /coverage, or deciding whether M4 is done.
---

# Coverage reporting (spec 07 §C)

## What is measured
For every **venue × year × track** cell, from a pinned snapshot / `index_version`:
- `indexed_accepted` — records with `status:accepted` in that cell.
- `official_accepted` — from `docs/results/coverage-sources.md`.
- `delta = indexed − official`, `delta_pct = delta / official`.
- Plus per cell: `missing_abstract` count, and per venue-year: `track:unknown` and `status:unknown` counts.

`op eval coverage` writes `docs/results/<YYYY-MM-DD>-coverage.md`. `GET /coverage` and the `/coverage` page
render the **same data** (no second computation in the UI), with source and snapshot date shown per cell.

## The gate (M4)
**|delta_pct| ≤ 1% for every main-track cell** (`track:main`, and `datasets_benchmarks` where an official
count exists). Other tracks are reported, not gated. The gate is soft until M4 and then blocks the M4
milestone, not individual PRs. A cell with no official source is `no source` — it fails the gate rather
than passing by default.

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
`delta_pct` to one decimal, gate ✓/✗, and cause notes for every ✗. Totals of `missing_abstract` and
`unknown`. Command that produced it.

## Gotchas
- `unknown` track records are *not* silently added to main to close a gap — they are the gap.
- Counts are per snapshot; a coverage number without its snapshot hash is uncitable.
