---
id: TASK-215
title: >-
  New venues milestone C: OpenAlex abstract fallback for AAAI, AIES and FAccT,
  the abstract_kind field and filter (index schema 4)
status: Done
assignee: []
created_date: '2026-10-10 03:47'
updated_date: '2026-10-11 00:15'
labels:
  - ingest
  - query
  - new-venues
milestone: m-4
dependencies: []
ordinal: 148000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Milestone C of docs/plans/2026-10-09-new-venues-design.md: sources/openalex.py fills abstracts only where no official one exists (new venues only), abstract_kind (official|openalex|none) derived field, the abstract_kind: filter on index schema 4 (SchemaForm flag, 422 on a schema-3 index), coverage and export labels, and an audit of OpenAlex against official abstracts.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 No official abstract is ever replaced; NeurIPS/ICLR/ICML untouched
- [x] #2 abstract_kind: filters identically in Tantivy and the reference matcher
- [x] #3 OpenAlex fidelity audit written to docs/results
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Milestone C built and verified on the real data (2026-10-10). The OpenAlex extract (sha256 7fea58b983252594b9ad3fb4788022f81b64adf579ce9cee129abf91a9c5c49c: 5,808 candidates, 49 lookups, 3,005 works) fills abstracts only where no official one exists. Snapshot 2026-10-10-22a339940466 (173,253 records); op snapshot diff against 2026-10-10-9efa49481112 shows 2,158 changed, abstract only, abstract_kind none->openalex 2,158, 0 added/removed/rekeyed, only AAAI, AIES and FAccT ids (NeurIPS, ICLR, ICML untouched). Fill by DOI 1,097 of 1,099; by title 1,061 of 4,709 AAAI 1980-2008, 3,648 stay without an abstract. Index 9977ed00669f (schema 4, tokenizer 3, 173,253 docs): full parity 0 differences (212,911 terms, 340,773 phrases); abstract_kind:openalex gives 2,158 on both engines, identical. Coverage: op eval coverage --check PASS, 83 of 84 gated cells (ICLR 2013 accepted exception), docs/results/2026-10-10-coverage.md. Fidelity audit: docs/results/2026-10-10-openalex-audit.md. Schema-2 indexes retired 2026-10-10. Benchmarks: real corpus worst first-page p95 with group counts 76.5 ms (within 100 ms); synthetic 80k main-3-sources 110.7 ms is over the budget (65 ms without group counts: TASK-176 counting, not schema 4), stated in spec 03 and filed as a follow-up. Schema 4 own regression (5-field combo in group counts) found by the 80k bench and fixed in 566cafcd.
<!-- SECTION:FINAL_SUMMARY:END -->
