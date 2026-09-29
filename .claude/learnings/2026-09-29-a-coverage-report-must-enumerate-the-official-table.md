# A coverage report built from the snapshot's cells cannot see a missing venue-year

**Key lesson:** A coverage gate has to walk the official table and look each cell up in the snapshot, not the other way round. `coverage.breakdown` (and `GET /coverage`) only iterate cells the snapshot holds, so a gated cell with no records would never appear and would pass by omission.

- **Date:** 2026-09-29 · **Task:** task-054 · **Area:** eval
- **Artifacts:** `backend/src/openproceedings/eval/coverage_report.py` (`gate`, `render`), `backend/tests/unit/test_coverage_report.py::test_a_gated_official_cell_with_no_records_is_a_reported_gap_never_a_silent_zero`

## What we set out to do
Build `op eval coverage` (TASK-054 AC#3), which writes the dated spec 07 §C report with the M4 gate verdict.

## What we learned
- `coverage.breakdown` builds `venue_years[].tracks` only from the manifest's `counts`, so a venue-year the crawl never reached has no row and no `within_gate`. A verdict of "every row passes" would call that a PASS (evidence: `breakdown` iterates `counts`; the test above fails if `gate` iterates the snapshot's cells).
- Spec 07 §C already says it: "any venue-year with no source is a reported gap, never a silent zero". The report enumerates `OFFICIAL_ACCEPTED`'s gated keys and renders a missing one as `✗ gap` (0 indexed).
- Reusing `api.coverage.compute` on the index, not recounting, keeps the report equal to `/coverage` by construction. The snapshot is verified exactly as the server verifies it (`api.state.snapshot_records`).

## Dead ends — don't repeat these
- `snapshot.render(result, reports, built_at, crawls)`: the second argument is RIS import reports. Passing crawl reports there files them under `sources.ris`, and the listings section stays empty.

## Decisions (and what would change them)
- Cause notes live in `docs/results/coverage-causes.toml`, keyed `"<Venue> <year> <track>"`, so a regenerated report keeps a person's classification. An unclassified failing cell says **unclassified**, never a guessed cause.
- `--check` turns the verdict into the exit status, for CI or a release gate. By default the command always writes the report.
- OpenReview crawls are reported when they are incomplete, have coverage gaps, unmapped venues or skipped groups, or skipped anything but `not_submission` (reply and decision notes, routine on every crawl). Otherwise every venue-year would be listed and the real problems lost among them.

## Follow-ups
- [ ] task-054 — the first live crawl's report and the classification of every failing cell (AC#2).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/coverage-reporting/SKILL.md` (§Report shape as built), `docs/specs/07-evaluation.md` §C, `docs/specs/08-ops-and-tooling.md` (CLI table), `CLAUDE.md` (layout)
- Test or hook added? — `backend/tests/unit/test_coverage_report.py`
