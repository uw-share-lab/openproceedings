---
id: TASK-281
title: >-
  Bound the length of a record id's native part (pmlr-, dblp-, ojs- and doi-
  forms are unbounded)
status: To Do
assignee: []
created_date: '2026-10-22 06:01'
labels:
  - ingest
  - security
dependencies: []
priority: low
ordinal: 187000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from the TASK-279 security review. The native part of a record id is validated per form (record.PROCEEDINGS_NATIVE, the forum-id rule), but the pmlr-v<N>-<key>, dblp-<key>, ojs-<id> and doi-<toc>.<n> forms have no length bound: a hostile PMLR index entry with a 2,100-character key, or an OJS article id of thousands of digits, gives a record whose id (stored in records.jsonl, every export and API response, and the URL /paper/<id>) is as long. decision-053 caps every other stored string and deliberately leaves the id alone, since cutting an id would rename the paper; since TASK-279 such a record still builds (its cut page URL still names it, caps.names_own_record). The longest id in snapshot 2026-10-16-03eab0ef56c4 is 53 characters. Bounding the forms (e.g. a key of at most 200 characters, an OJS id of at most 12 digits) makes the record invalid, so its crawler skips it as it skips any invalid entry: that is a refusal, so it needs the owner's decision, and it changes the native-id forms, so RECORD_SCHEMA_VERSION would be bumped (record-schema skill §Versions), which changes the manifest of the next snapshot built.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision record says whether native ids get a length bound, the bound per form, and what happens to a record over it (skipped and counted by its crawler, or kept), citing the measured longest ids
- [ ] #2 If bounded: record.py's forms carry the bounds with tests at the bound and one past it, RECORD_SCHEMA_VERSION is bumped per the record-schema skill, and spec 01 and the record-schema skill describe it
<!-- AC:END -->
