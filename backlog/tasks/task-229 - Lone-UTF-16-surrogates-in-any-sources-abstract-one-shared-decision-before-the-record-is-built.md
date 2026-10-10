---
id: TASK-229
title: >-
  Lone UTF-16 surrogates in any source's abstract: one shared decision before
  the record is built
status: To Do
assignee: []
created_date: '2026-10-10 17:22'
labels:
  - ingest
dependencies: []
ordinal: 159000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From milestone C Task 7 review (2026-10-10). A JSON-escaped lone surrogate (\ud800) passes clean_abstract/abstract_text and only fails later at record._utf8, which stops the whole crawl. OpenAlex refuses such an abstract itself (abstract_unusable); the other JSON/XML sources do not. Changing the shared clean step to drop them would turn a loud stop into a silently missing abstract, so decide per source (refuse the claim and count it, or stop) and pin it with tests.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every source's handling of a lone surrogate in an abstract is decided, tested, and documented in spec 01
<!-- AC:END -->
