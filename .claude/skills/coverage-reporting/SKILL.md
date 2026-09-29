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
±1%** (`|delta_pct| ≤ 1%`), **or an owner-accepted exception** (below). Cells with no official count are reported (as `no source`) but not gated;
other tracks are reported, not gated. The same definition appears in spec 00. The gate is soft until M4
and then blocks the M4 milestone, not individual PRs.

**Owner-accepted exceptions** (spec 07 §C). When two primary sources disagree and the project owner decides
to keep the record as its source classifies it, the gap is accepted, never papered over:
1. Write a decision record (`decision-records` skill) naming the paper(s), the options and why.
2. Add an `accepted` table under the cell in `docs/results/coverage-causes.toml`, next to its `cause`:
   ```toml
   ["ICLR 2013 main".accepted]
   indexed = 23            # the exact counts accepted, not a tolerance
   official = 24
   reason = "…"
   papers = ["op:iclr:2013:11y_SldoumvZl"]   # record ids, one per paper of the gap
   accepted_by = "project owner"   # a role; the only one allowed
   accepted_on = 2026-09-29        # a TOML date, unquoted
   decision = "decision-016"
   ```
   Every key is required; unknown keys, `indexed`/`official` below 1 (a gap is never accepted), counts
   already within ±1%, `papers` that are empty, repeated or not record ids, an `accepted_by` other than
   `project owner` (a role, never a name), control characters (newlines included) in any string, a
   `decision` that isn't `decision-<n>`, or one with no `backlog/decisions/<id> - *.md` are refused, and
   `op eval coverage` stops before writing anything.
3. The cell passes (`✓ accepted exception`, counted apart from "within ±1%" in the verdict line, listed under
   "Owner-accepted exceptions" and on stderr) **only while both counts are exactly the accepted ones and the
   papers are the gap**: |official − indexed| of them, each in the index's snapshot, and outside the cell for
   an under-count (inside it for an over-count). Anything else fails the cell as `drifted`, with the failed
   check (or the accepted and observed counts) in its cause note: re-classify it before touching the
   exception. A gap cell stays `✗ gap`. An exception whose cell is within ±1% or not gated is reported as
   stale, and `--check` exits 1 until it is removed.
4. Only the gate report applies exceptions. `GET /coverage` and the `/coverage` page report the raw ±1% per
   cell, so an accepted cell is served with `within_gate: false` (spec 07 §C).

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
- A conference's own list vs OpenReview's decision label: ICLR 2013's list has "Factorized Topic Models"
  (`11y_SldoumvZl`) as a conference paper; OpenReview decides it a workshop poster. Kept as OpenReview says,
  accepted at 23 vs 24 (decision-016).
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
line (`**M4 gate: PASS|FAIL** — n of m gated cells within ±1%; k gaps; e owner-accepted exceptions`). Then a table per venue: every cell,
indexed accepted, official, Δ, `delta_pct` to one decimal, gate (✓, ✗, `✗ gap` for a gated official cell with
no records, `not gated` for another track, `no source` for a main or D&B cell with no official count),
missing abstracts, the venue-year's `unknown`-track and `unknown`-status counts, and **statuses indexed**
(`none (no records)` on a gap in a venue-year with no record at all). Δ% is rounded to one decimal; the gate compares exactly. Then a cause note for
every failing cell, from `docs/results/coverage-causes.toml` (`["NeurIPS 2021 datasets_benchmarks"]`
`cause = "…"`) or **unclassified** (a `drifted` cell also shows its exception's accepted and observed counts),
and any note for a cell that no longer fails (remove it). Then "Owner-accepted exceptions": each accepted one
(counts, who, when, decision, reason, papers, cause), and any stale one. Then every
proceedings listing that skipped entries or whose count disagreed with its page, and every OpenReview crawl
that is incomplete, has coverage gaps, conflicts, unmapped venues or non-routine skipped groups (`proposal`
and `container` are routine; `not_a_v2_venue`, which can be an unreadable group, and `no_submission_venue_id`
are not), or skipped anything but
`not_submission` replies. Then totals of records, missing abstracts, `unknown` track and status. The report is
written atomically; a same-day run replaces it. `--check` exits 1 when the gate fails (a matched accepted exception passes) or an exception is stale. The methods text cites this report (with its
snapshot hash) as the database-scope caveat.

## Gotchas
- `unknown` track records are *not* silently added to main to close a gap — they are the gap.
- Counts are per snapshot; a coverage number without its snapshot hash is uncitable.
