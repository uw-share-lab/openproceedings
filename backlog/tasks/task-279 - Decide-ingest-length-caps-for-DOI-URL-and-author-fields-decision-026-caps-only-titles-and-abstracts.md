---
id: TASK-279
title: >-
  Decide: ingest length caps for uncapped stored string fields (DOI, URLs,
  authors, keywords, venue_id_raw, claim url and evidence)
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-10-21 23:01'
updated_date: '2026-10-22 08:09'
labels:
  - ingest
  - security
dependencies: []
priority: low
ordinal: 185000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-274. decision-026 (ingest/caps.py, CAPPED = title, abstract) caps only titles (1,000 characters) and abstracts (20,000). Every other stored string field is uncapped: ingest/record.py validates a DOI's shape (10.NNNN/suffix, one line) and each URL's (http(s), a host, one line) but not their length; author names, keywords and venue_id_raw have no cap; nor do provenance claims' url and evidence (Claim.url, Claim.evidence), which snapshots store and the API shows. Since TASK-274 the BibTeX export escapes every field in linear time (doi, url and author all go through export._braced), so a long value no longer costs quadratic CPU; what remains is size: a value of any length is stored and written whole into every export format (BibTeX, RIS, CSV, JSONL) and API response. These fields come from crawled sources (Crossref, OpenAlex, OpenReview, proceedings pages, the RIS cache), not from the reviewer. Decide whether to cap them at ingest (refuse or trim, flagged as decision-026 does) and at what lengths, or record why not.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A decision record says, for each uncapped stored string field (DOI, URLs, authors, keywords, venue_id_raw, claim url and evidence), whether it is capped at ingest, at what length and whether an over-cap value is refused or trimmed (and flagged), or why it is left uncapped
- [x] #2 If capped: ingest/caps.py applies the caps with tests, and the record-schema skill and spec 01 describe them
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Measure each uncapped stored string field's real maximum over snapshot 2026-10-16-03eab0ef56c4 (read-only) and pick caps with generous headroom so no current record is trimmed.
2. Owner decision 2026-10-22: cap + trim (decision-026's model), trimmed and flagged, never refused. Write the decision record (created last, after rebasing): per field cap, trim and flag; a cut DOI or URL is never used as an identifier (the record's urls slot is cleared, dedup's resolve and identity reads skip a cut urls.* claim, a cut claim url is dropped) and is kept only as display text in its claim.
3. ingest/caps.py: MAX_DOI, MAX_URL, MAX_AUTHOR, MAX_KEYWORD, MAX_VENUE_ID, MAX_INVITATION, MAX_EVIDENCE; cut as decision-026 cuts (NFKD length, before the last space); a second note form 'trimmed at ingest (decision-NNN):'; is_trimmed covers both; dedup skips cut identifiers.
4. Tests: per field at cap-1, cap, cap+1; Hypothesis property; flag presence; dedup skip; snapshot build with an over-cap DOI.
5. Docs as built: record-schema and snapshots skills, spec 01, CLAUDE.md layout line, decision-026 cross-reference.
6. Verify no version bump needed (caps return records unchanged within them), make test/lint/tooling, learnings, review gate, finalize, PR, merge queue.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Measured over snapshot 2026-10-16-03eab0ef56c4 (173,518 records, every claim): DOI 34, URL 154 (claim url 154), author 81, keyword 733 (an abstract split into keywords, ICLR 2025 d8hURACo0P), venue_id_raw 65, invitation none, evidence 469, id 53; at most 95 authors and 54 keywords per record. Caps: DOI 1,000, URL and claim url 2,048, author 1,000, keyword 2,000, venue_id_raw and invitation 500, evidence 4,000 (notes included). cap_record over every record of that snapshot returned each unchanged (changed=0; the 26 decision-026 already lists stay), so records.jsonl, snapshot_hash and index_version are unchanged: no RECORD_SCHEMA_VERSION, TOKENIZER_VERSION or SCHEMA_VERSION bump (the caps belong to the build, as decision-026's do). A cut URL whose cut changed what it names is not read as an id (unread_identifier); one whose cut left it alone still names its paper, so a long query string never refuses the build at dedup's self-naming check. Local: make test (9205 passed, 3 skipped; frontend 4954 passed), make lint, make tooling green; mutate-changed: no mutants cover the diff. Follow-up (file at the end): cap the number of authors and keywords per record.

decision-053 records the caps, the trim-and-flag rule and the handling of a cut DOI or URL (no link; an id only if the cut left what it names unchanged). Follow-up filed: TASK-280 (cap the number of authors and keywords per record).

Review round 1 (code, docs, observability, dedup, track-classifier, security, methodologist, qa): a cut venue id is an identifier too (it never fills venue_id_raw and counts against Creative AI); cap_record sets the urls slots and venue_id_raw with dedup.resolved_value (resolve's own rule: the next uncut claim, else null); caps._names survives an OJS id past Python's int digit limit; scholar_compare never joins on a cut DOI; a record whose own page URL was cut inside its own id refused the build at dedup's self-naming check. Round 2: round 1's fix for that (a note dedup read, 'it named its own record') was forgeable through RIS venue id evidence and credited the wrong record after a merge, so it was replaced: a URL that names its own record whole and that a cut would unname is kept whole, flagged, decided from the value and the record's id only. Measurements committed as docs/results/2026-10-22-stored-string-lengths.md (+ its check script; rerun at the round-1 code: records=173518 changed=0 flagged=26). Follow-up TASK-281 filed (bound native id length; and ojs.py's int() past the digit limit).

Automated security review (coordinator, after round 2): keeping a self-naming URL whole had no bound (an iclr_archive id hashes the whole target). Fixed: a URL the record's own id was read from is cut just past that id (caps._own_prefix); an iclr_archive target is cut and unread like any other, and dedup._archive_target_cut lets that record stand for itself only by the crawler's own claim. Tests: junk past the id, the id spelled twice, a URL already ending at the id (kept, flagged once), the archive exception limited by source and id form, the prefix check.

Review round 3: cutting a self-naming URL just past its id failed where a page's form goes on past the id (NeurIPS/ICLR track token, PMLR GitHub asset; build abort), let leading zeros past the cap, and didn't check the whole URL named the id. Replaced by caps._own_page: the id's canonical page rebuilt per form from the parsed id, kept only if it names the same id. The iclr_archive exception now also keeps the record's own id among its cluster's proceedings ids (the two-ids guard). Tests for each case.

Review round 4: a page with a tail of symbols only was cut inside .html and rebuilt without its Creative AI token; now a page first drops its query/params/fragment when that fits and names all the whole did (caps._page_only), and only a page whose path is past the cap is rebuilt. Tests now cover every rebuild form (dblp ICML/AAAI, OJS AIES/IASEAI, doi.org/dx/percent-encoded DOI, upper-case host), the own-id guard, and the archive id kept in its cluster by native. The D&B round in the rebuild was unreachable and removed. Docs: the Reserved bullet now says what a forged unread note could do and why no claim can carry one.

Review round 5: no Must; QA's Should (the own-id guard in _own_page untestable beside the final check) fixed by removing the early guard (the page is built from what the URL names, so the final check names-own test is the guard); tests pin the page-only length boundary and that a cut leaving what a URL names keeps its prefix. Docs: a forged cut note also lists the record as trimmed; the tail step named before the rebuild.
<!-- SECTION:NOTES:END -->
