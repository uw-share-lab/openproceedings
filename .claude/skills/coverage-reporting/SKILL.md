---
name: coverage-reporting
description: The spec 07 §C coverage standard — indexed accepted counts per venue × year × track compared with official accepted counts, the rules for docs/results/coverage-sources.md (one cited source per cell), the ±1% M4 gate on every main-track and D&B cell with an official count, the per-cell missing-abstract, unknown-track and statuses-indexed columns, and the known ways official numbers disagree with each other. Use when running `op eval coverage`, editing coverage-sources.md, reviewing the /coverage page or GET /coverage, or deciding whether M4 is done.
---

# Coverage reporting (spec 07 §C)

## What is measured
For every **venue × year × track** cell, from a pinned snapshot / `index_version`:
- `indexed_accepted` — records with `status:accepted` in that cell.
- `official_accepted` — from `docs/results/coverage-sources.md` (its machine-readable copy is
  `backend/src/openproceedings/official_counts.py`, which `GET /coverage` serves; a row goes into both in one
  change, and `test_official_counts.py` fails when they differ).
- `delta = indexed − official`, `delta_pct = delta / official`.
- Plus per cell (spec 07 §C): `missing_abstract` count, `track:unknown` count, and **statuses indexed**:
  which statuses the sources for that venue-year can even contain. For example, pre-2021 NeurIPS and ICML
  2020–22 come from proceedings only, so no rejected papers exist there to exclude. Also `status:unknown`
  counts per venue-year.

`op eval coverage` writes `docs/results/<YYYY-MM-DD>-coverage.md`. `GET /coverage` and the `/coverage` page
render the **same data** (no second computation in the UI), with source and snapshot date shown per cell.
As built (TASK-082): `GET /coverage` serves each venue-year's `statuses_indexed` (from
`ingest/statuses.py`, recorded in the snapshot manifest) and its `tracks`, one per cell, with `records`,
`indexed_accepted`, `abstract_missing`, `sources`, `official_accepted`/`official_counts`/
`official_citation`/`official_accessed`, `delta`, `delta_pct` (unrounded percent), `gated` and
`within_gate` (null unless gated); `snapshot.crawl_dates` has each source's own window.

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
- PMLR volume counts vs OpenReview accepted counts for ICML: equal for 2023 (1,828), 2024 (2,610) and 2025
  (3,330 = 3,257 main + 73 position) on 2026-09-27; re-check each crawl.
- NeurIPS proceedings vs OpenReview: 2024 main 4,034 vs 4,035; 2021 main 2,334 vs 2,630 OpenReview v1
  "accepted" venues (unexplained; TASK-054). `docs/research/2026-09-27-openreview-and-proceedings-facts.md`.
- Rejected / withdrawn counts are complete only for ICLR; NeurIPS and ICML publish rejected papers only on
  the authors' opt-in (decision-012), so their "statuses indexed" cell says so.
- NeurIPS D&B track: separate count, and ≤2023 proceedings use `Datasets_and_Benchmarks` aliased to
  `_Track` — misclassification shows up as main-track surplus + D&B deficit.
- ICML position papers counted inside or outside the main total.
- Deduplication across OpenReview and proceedings: an under-merge shows as surplus, an over-merge as
  deficit. Cross-check with `merges.csv`/`conflicts.csv` (`dedup-rules`).
When a cell misses the gate, classify the cause in the report (source definition, classification,
dedup, crawl gap) before changing anything. Never adjust the official number to fit.

## Report shape
As built (`op eval coverage`, `backend/src/openproceedings/eval/coverage_report.py`, TASK-054). Header: date,
snapshot name and hash, `index_version`, the sha256 of `coverage-sources.md` and of `coverage-causes.toml` (or
"none"), the command. Then the verdict
line (`**M4 gate: PASS|FAIL** — n of m gated cells within ±1%; k gaps`). Then a table per venue: every cell,
indexed accepted, official, Δ, `delta_pct` to one decimal, gate (✓, ✗, `✗ gap` for a gated official cell with
no records, `not gated` for another track, `no source` for a main or D&B cell with no official count),
missing abstracts, the venue-year's `unknown`-track and `unknown`-status counts, and **statuses indexed**
(`none (no source)` on a gap). Δ% is rounded to one decimal; the gate compares exactly. Then a cause note for
every failing cell, from `docs/results/coverage-causes.toml` (`["NeurIPS 2021 datasets_benchmarks"]`
`cause = "…"`) or **unclassified**, and any note for a cell that no longer fails (remove it). Then every
proceedings listing that skipped entries or whose count disagreed with its page, and every OpenReview crawl
that is incomplete, has coverage gaps, unmapped venues or skipped groups, or skipped anything but
`not_submission` replies. Then totals of records, missing abstracts, `unknown` track and status. The report is
written atomically; a same-day run replaces it. `--check` exits 1 when the gate fails. The methods text cites this report (with its
snapshot hash) as the database-scope caveat.

## Gotchas
- `unknown` track records are *not* silently added to main to close a gap — they are the gap.
- Counts are per snapshot; a coverage number without its snapshot hash is uncitable.
