---
id: TASK-265
title: 'Nightly mutate: 16 shards (a shard ran past 140 min)'
status: Done
assignee: []
created_date: '2026-10-19 05:49'
updated_date: '2026-10-19 11:49'
labels:
  - ci
dependencies: []
priority: high
ordinal: 175000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Nightly 39191247944 on 993772e9 (the 0.4.0 candidate) failed only because mutate shard 10/12 was cut off at 140 min after ~135 mutants (0 FAIL); shard 3 took 138. The TASK-253/254 cmdparse mutants grew the set. Raise the matrix to 16 shards (nightly.yml says to add shards before one nears 140).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 nightly.yml mutate matrix has 16 shards, comments and spec 08 say so
- [x] #2 test-mutate-shard.sh checks 16 shards complete, disjoint and balanced
- [x] #3 a nightly on the new dev head has every mutate shard green under 140 min
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
16 shards; test-mutate-shard.sh covers 16 (39 passed); make lint and make tooling green. AC#3 is checked on the next nightly.

AC#3: nightly 39221205207 on b24060b8: all 16 mutate shards green, slowest 126 min of 140. #171, #172.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
make mutate runs as 16 nightly shards (12 until 2026-10-19); the first 16-shard nightly was green with the slowest shard at 126 min.
<!-- SECTION:FINAL_SUMMARY:END -->
