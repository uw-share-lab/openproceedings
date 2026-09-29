---
id: decision-016
title: >-
  ICLR 2013 main is an owner-accepted coverage exception: keep OpenReview's
  workshop decision for Factorized Topic Models (TASK-054)
date: '2026-09-29 22:17'
status: accepted
---
## Context

The M4 coverage gate (spec 07 §C, TASK-054) requires every gated main-track and D&B cell with an official
count to be within ±1%. ICLR 2013 main is the last failing cell of the first full crawl once the in-flight
crawler fixes land: 23 indexed accepted records against an official 24. With an official count of 24, one
paper is a 4.2% gap, so the cell cannot pass on tolerance.

The missing paper is "Factorized Topic Models" (OpenReview id `11y_SldoumvZl`). It is on ICLR's official 2013
conference list (`https://iclr.cc/archive/2013/conference-proceedings.html`, the source of the official 24 in
`docs/results/coverage-sources.md`), but its OpenReview decision is `conferencePoster-iclr2013-workshop`, which
the v1 adapter maps to the workshop track (`ingest/sources/openreview_v1.py`). Both sources are primary; they
disagree about one paper.

Options considered:
- (a) Reclassify the record as main-track, overriding OpenReview's decision with a special case in the
  adapter or a per-record override. This makes the count match but puts a hand edit into the classification,
  against the rule that classification follows the source's own label (`openreview-venueids`), and it
  changes `index_version` for one record.
- (b) Lower the official count to 23. Refused: the coverage standard never adjusts an official number to fit.
- (c) Leave the cell failing. The gate would then never pass on a disagreement that is not a bug.
- (d) Keep OpenReview's decision and record the gap as an owner-accepted exception, visible in every report,
  that passes the cell only while the counts stay exactly 23 vs 24.

## Decision

The project owner decided (2026-09-29): we keep OpenReview's decision for "Factorized Topic Models" (the
record stays `track:workshop`) and accept ICLR 2013 main at exactly 23 indexed vs 24 official as a documented
exception, recorded under `["ICLR 2013 main".accepted]` in `docs/results/coverage-causes.toml`.

## Consequences

- `op eval coverage` passes ICLR 2013 main while its counts are exactly 23 and 24, marks the cell
  `✓ accepted exception`, and lists the exception (reason, paper, who accepted it, when, this record) in the
  report's "Owner-accepted exceptions" section and on stderr. `--check` counts it as passing.
- If either count changes (a record lost or gained, or the official count revised), the exception no longer
  matches: the cell fails again as `drifted` and needs a new classification, never a silent pass. If the cell
  comes within ±1% or stops being gated, the exception is reported as stale and should be removed.
- No record, classification rule or `index_version` changes; searches for `track:main year:2013 venue:ICLR`
  return 23 papers, and the paper is found with `track:workshop`.
- Spec 07 §C and the `coverage-reporting` skill state the rule for owner-accepted exceptions
  (`eval/coverage_report.py`; tests in `backend/tests/unit/test_coverage_report.py`).
- Revisit if OpenReview relabels the paper, if ICLR's archive list changes, or if another cell needs an
  exception (each needs its own decision record).

