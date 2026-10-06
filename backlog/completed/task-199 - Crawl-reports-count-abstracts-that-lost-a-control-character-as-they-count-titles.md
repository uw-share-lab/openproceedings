---
id: TASK-199
title: >-
  Crawl reports count abstracts that lost a control character, as they count
  titles
status: Done
assignee: []
created_date: '2026-10-06 01:27'
updated_date: '2026-10-06 19:00'
labels:
  - ingest
  - observability
milestone: m-4
dependencies: []
ordinal: 142000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-188 (decision-044) replaces each control character in an abstract by one space at import and records the count only in the abstract claim's evidence. OpenReview crawl reports count titles that lost one (title_control_characters) but have no matching counter for abstracts, so a crawl's attention summary can't show it. Raised by the TASK-188 implementer on 2026-10-06.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every importer that supplies an abstract reports how many abstracts had a control character replaced, beside the title counter, with tests and spec 01 as built
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. abstract_control_characters on the OpenReview v1/v2 CrawlReport, ListingReport (NeurIPS, PMLR) and RIS ImportReport, manifest only when > 0, on the finished/mined/ris_import lines, never a WARNING. 2. Count from the importer's own abstract_text number: openreview_v2._abstract returns it and note_record fills a spaced set (forum ids; the crawl counts those still records); common.clean_abstract's count returned by the listing _record into ListingReport.count; ris._abstract/_record return it. Never parse evidence (security note). 3. TDD per importer, including a RIS spoofed-evidence test. 4. Spec 01, logging-standards and openreview-api skills.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Security review of the v0.1.1 batch (2026-10-06): RIS abstract claims carry evidence taken from the file (scholarmend:<source> <evidence>) before the replacement note, so a counter must count only crawled-source claims, or anchor its pattern to the known evidence prefixes; a crafted RIS evidence string could otherwise fake the count.

Implemented as planned. Security: no evidence regex is used for abstracts; test_the_abstract_counter_cannot_be_faked_by_evidence_text pins that a RIS evidence ending in '(5 control characters replaced by a space)' counts 0. Title counter unchanged (still read from crawled title evidence, which only our code writes). Listing reports and RIS have no title counter; not added (out of scope). Verified: uv run pytest -q -n 4 backend/tests/unit/ingest 1677 passed; test_coverage_report 78 passed; mypy --strict backend/src clean; ruff clean; make tooling passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Crawl and import reports now count the records whose abstract lost a control character (abstract_control_characters), beside title_control_characters: OpenReview v1/v2 crawl reports and finished line, NeurIPS/PMLR listing reports and mined lines, RIS import reports; in manifests only when above 0, never a WARNING. The count is the importer's own replacement number, never read from claim evidence, so a crafted RIS evidence string cannot fake it. Spec 01 and the logging-standards/openreview-api skills updated. Verified by per-importer tests plus a spoofing test; ingest suite 1677 passed, mypy strict and ruff clean.
<!-- SECTION:FINAL_SUMMARY:END -->
