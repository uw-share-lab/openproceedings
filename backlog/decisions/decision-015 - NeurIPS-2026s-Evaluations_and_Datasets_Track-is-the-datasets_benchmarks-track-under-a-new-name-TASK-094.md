---
id: decision-015
title: >-
  NeurIPS 2026's Evaluations_and_Datasets_Track is the datasets_benchmarks track under a new name
  (TASK-094)
date: '2026-09-27 21:15'
status: accepted
---
## Context

A live check on 2026-09-27 (`docs/research/2026-09-27-openreview-and-proceedings-facts.md`) found the
group `NeurIPS.cc/2026/Evaluations_and_Datasets_Track`. It has no notes yet, and there is no
`NeurIPS.cc/2026/Datasets_and_Benchmarks_Track`. Before TASK-094 the classifier read the new id as
`other`, which the default `track:(main OR datasets_benchmarks OR position)` clause excludes. So every
2026 D&B-style paper would have been dropped from default searches without anyone noticing, even though
the same kind of paper in 2021–2025 is included.

There were three options:
- (a) Map the new id to `datasets_benchmarks`.
- (b) Add a new track value, `evaluations_datasets`.
- (c) Leave it as `other` until notes appear.

## Decision

(a). NeurIPS renamed the track and replaced the old one; the Datasets and Benchmarks group did not come
back for 2026. A reviewer who searches the D&B track expects the 2026 papers in it. Keeping a single
value means the default track clause, the canonical string and `canonical_hash` all stay the same.
Option (b) would change them, and a review filtering on `datasets_benchmarks` would silently lose
2026. Option (c) is the silent exclusion described above.

## Consequences

- `classify.py` maps `("NeurIPS", ("Evaluations_and_Datasets_Track",))` to `datasets_benchmarks`.
  Spec 01 §Track taxonomy, spec 02's `track:` row, and the openreview-venueids and track-taxonomy skills
  all say so.
- No record in the current snapshot has this venueid, so no content hash or `index_version` changes
  now. The first 2026 crawl indexes those papers straight into `datasets_benchmarks`.
- If NeurIPS gives the new track a scope that clearly differs from D&B (for example, evaluations-only
  papers with no dataset), revisit this: a new track value would then be a spec change that adds to the
  default clause.
