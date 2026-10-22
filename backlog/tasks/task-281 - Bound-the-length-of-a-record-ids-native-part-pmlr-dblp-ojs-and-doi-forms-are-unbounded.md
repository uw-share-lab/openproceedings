---
id: TASK-281
title: >-
  Bound the length of a record id's native part (pmlr-, dblp-, ojs- and doi-
  forms are unbounded)
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-10-22 06:01'
updated_date: '2026-10-22 20:54'
labels:
  - ingest
  - security
dependencies: []
priority: low
ordinal: 187000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from the TASK-279 security review. The native part of a record id is validated per form (record.PROCEEDINGS_NATIVE, the forum-id rule), but the pmlr-v<N>-<key>, dblp-<key>, ojs-<id> and doi-<toc>.<n> forms have no length bound: a hostile PMLR index entry with a 2,100-character key, or an OJS article id of thousands of digits, gives a record whose id (stored in records.jsonl, every export and API response, and the URL /paper/<id>) is as long. decision-053 caps every other stored string and deliberately leaves the id alone, since cutting an id would rename the paper; since TASK-279 such a record still builds, because a URL the record's own id was read from becomes an address of that id's page, rebuilt from the id (so that URL, too, is as long as the id plus a fixed host and path). Also in scope: sources/ojs.py's int() on an OAI header's article id raises a bare ValueError past Python's 4,300-digit limit, aborting the crawl rather than refusing the entry (the TASK-279 review, round 2). The longest id in snapshot 2026-10-16-03eab0ef56c4 is 53 characters. Bounding the forms (e.g. a key of at most 200 characters, an OJS id of at most 12 digits) makes the record invalid, so its crawler skips it as it skips any invalid entry: that is a refusal, so it needs the owner's decision, and it changes the native-id forms, so RECORD_SCHEMA_VERSION would be bumped (record-schema skill §Versions), which changes the manifest of the next snapshot built.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A decision record says whether native ids get a length bound, the bound per form, and what happens to a record over it (skipped and counted by its crawler, or kept), citing the measured longest ids
- [x] #2 If bounded: record.py's forms carry the bounds with tests at the bound and one past it, RECORD_SCHEMA_VERSION is bumped per the record-schema skill, and spec 01 and the record-schema skill describe it
- [x] #3 sources/ojs.py refuses an article id past the bound (or past the int digit limit) as a CrawlError, never a bare ValueError, with a test
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. record.py: MAX_NATIVE_KEY=200 (pmlr and dblp keys), MAX_NATIVE_DIGITS=12 (ojs article id, pmlr volume, each side of doi-<toc>.<n>) in PROCEEDINGS_NATIVE; RECORD_SCHEMA_VERSION 9 -> 10.
2. sources/ojs.py: an article id over 12 digits (or past the int digit limit) is a CrawlError, before int().
3. acm_table._PAPER and urls.pmlr/ojs_article bounded the same way, so no bare ValueError on a hostile volume or DOI number.
4. Tests at the bound and one past it per form; crawler skip/count tests.
5. FILES_HASH re-pinned; decision-055, spec 01, record-schema skill; read-only check that every record of 2026-10-16-03eab0ef56c4 still validates.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
decision-055 (owner, 2026-10-22): MAX_NATIVE_KEY=200 (pmlr, dblp keys), MAX_NATIVE_DIGITS=12 (ojs id, pmlr volume, each side of doi-<toc>.<n>; acm_table.DOI_DIGITS the same). RECORD_SCHEMA_VERSION 9 -> 10; test_combined_snapshot.FILES_HASH re-pinned (SNAPSHOT_HASH unchanged). sources/ojs._number raises CrawlError(oai_unreadable) before int(); urls.pmlr/ojs_article and ris._int read at most 12 digits past leading zeros. Tests at the bound and one past it per form (test_record.py) and per crawler (pmlr, dblp ICML, dblp AAAI, RIS, OJS, Crossref, urls). caps: decision-053's 'kept whole' own-page branch removed (a bounded id's page always fits). Read-only check: all 173,518 records of 2026-10-16-03eab0ef56c4 validate at schema 10; longest id 53.

Review round 1: ris._int converts the zero-stripped digits (a zero-padded volume no longer reaches int's limit); ojs._number counts digits after leading zeros like urls; pmlr._VOLUME_PREFIX and neurips._COUNT bounded; ris._readable skips an evidence URL urlparse refuses.

Review round 2: dedup._site/_names_native read an evidence URL urlparse refuses as naming nothing; ris._readable covers UR lines; html.joined drops a listing link urljoin refuses (PMLR, NeurIPS); pmlr.heading decided by the first Volume heading (_VOLUME_HEADING); tests for each.

Review round 3: iclr._paper_anchor and aaai_library.same_capture guarded (html.joined / ValueError); a PMLR block with an unreadable link is unlinked; a NeurIPS see-also is kept as written; a test pins _names_native's False.
<!-- SECTION:NOTES:END -->
