---
id: TASK-235
title: >-
  op eval openalex: measure OpenAlex against AAAI's archived pages for AAAI
  1980-2008, and re-run the audit on the final snapshot
status: In Progress
assignee: []
created_date: '2026-10-11 05:08'
updated_date: '2026-10-16 15:28'
labels:
  - eval
  - new-venues
dependencies: []
priority: medium
ordinal: 164000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The OpenAlex audit (docs/results/2026-10-10-openalex-audit.md) compares OpenAlex only where an official abstract also exists (AAAI 2010+, AIES 2024-2025, FAccT 2022/2025/2026), so OpenAlex's fidelity for AAAI 1980-2008 is unmeasured (its Caveats say so). Now that the aaai_library source fills those years first, the records where OpenAlex's extract also has a work give a free measure (review-methodologist, gate C round 1). Add it to op eval openalex, and re-run the audit on the snapshot built after the archive harvest, since the title-route attaches and the no-abstract figures change once aaai_library fills first.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 op eval openalex reports, for AAAI 1980-2008 records with both an aaai_library abstract and an OpenAlex work, the exact, near-exact and differs rates, with tests
- [x] #2 The audit is re-run on the final snapshot and docs/results, spec 07 §G and the coverage page's linked audit cite it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-11: the audit was re-run on the final snapshot 2026-10-11-93c2937e2f29 (docs/results/2026-10-11-openalex-audit.md): DOI route unchanged (2,122 compared, 83.1% exact or near-exact); title route 19 attaches, 18 agree, 1 an OCR variant of the same surname. Left: measure OpenAlex against aaai_library's official AAAI 1980-2008 abstracts.

2026-10-16: op eval openalex adds library_check (eval/openalex_audit.py): the fill replayed with aaai_library abstracts set aside, each OpenAlex text compared with AAAI's. docs/results/2026-10-16-openalex-audit.md on 2026-10-11-93c2937e2f29: 4,536 aaai_library records; 1,131 with an OpenAlex text: exact 361 (31.9%), near-exact 223 (19.7%), truncated 16, similar 408 (36.1%), differs 123 (10.9%); 109 a work with no abstract; title_unmatched 3,216, title_ambiguous 20, rebuild refusals 60. Spec 07 §G, docs/README, README and the coverage page's audit link updated.
<!-- SECTION:NOTES:END -->
