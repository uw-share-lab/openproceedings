---
id: TASK-159
title: >-
  Link ICLR 2017 workshop-listing copies to their conference twins (within-crawl
  duplicates)
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-10-02 00:41'
updated_date: '2026-10-02 07:25'
labels:
  - ingest
  - dedup
milestone: m-4
dependencies: []
references:
  - backend/src/openproceedings/ingest/dedup.py
  - backend/src/openproceedings/ingest/sources/openreview_v1.py
  - docs/results/2026-10-01-iclr-2017-workshop-copies.md
  - .claude/skills/dedup-rules/SKILL.md
  - .claude/skills/openreview-venueids/SKILL.md
priority: low
ordinal: 134000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: a TASK-152 (PR #63) deferral (`docs/results/2026-10-01-iclr-2017-workshop-copies.md` §Duplicates within the ICLR 2017 crawl). ICLR 2017's workshop listing (`ICLR.cc/2017/workshop/-/submission`, 161 notes on the 2026-09-29 crawl) holds resubmissions of conference papers as separate OpenReview notes with their own forum ids, so they are separate records from their conference twins. Two groups: the 18 whose `content.venue` is "Submitted to ICLR 2017" (each shares its title with a conference-listing note that is itself "Submitted to ICLR 2017", and each one's `_bibtex` url names that twin's forum, e.g. `rkB_5hEKe` -> `ryh_8f9lg`), and 34 of the 35 "ICLR 2017 Invite to Workshop" notes, whose titles match a conference note but whose `_bibtex` names no twin (0 of 34). The two groups differ: the 18 pair a workshop/`unknown` record (since TASK-152) with a main/`rejected` one, while the 34 pair two workshop/`unknown` records (the twins are the conference listing's "Invite to Workshop" notes; a read-only re-tally of the 2026-09-29 cache for this task, not in the results doc, so re-measure it). In both groups what keeps them apart is dedup-rules §Never merge: two different forum ids are different submissions, and dedup never decides that two OpenReview notes are one paper. With the default filters off, a query counts each such paper twice under "identified"; the defaults remove both copies, since none is accepted. This predates TASK-152, which changed no merge. The precedent for deciding two OpenReview notes are one paper is in the crawler, before dedup (`openreview_v1.collapse_duplicate_submissions`, TASK-125; `collapse_silent_twins`, TASK-132), not in dedup; decision-005 governs which source wins a merged field.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A decision record says whether a workshop copy and its conference twin are collapsed into one record (in the crawler, as TASK-125/TASK-132 do, or in dedup) or stay two records linked to each other, and how the link is shown and exported; it cites dedup-rules §Never merge, the track rule (for the 18) and decision-005, and may decide the 18 and the 34 differently
- [x] #2 The pairs are found by evidence that names the twin (the `_bibtex` forum id for the 18) and, if the decision allows it, by exact normalized title within ICLR 2017 for the 34; a test over recorded fixtures covers a `_bibtex` pair, a title-only pair (linked or left unlinked, as the decision says), and a workshop note with no twin that stays unlinked
- [x] #3 A real-data before/after snapshot (`op snapshot diff`) shows only ICLR 2017 pairs change, with the counts in the notes (including the 34 twins' venue strings, re-measured), and a default-filters-off query that matches some pairs shows "identified" before and after (unchanged if the decision is link-only)
- [x] #4 spec 01, the record-schema and dedup-rules skills and the openreview-venueids 2013/2017 row describe the rule as built
- [x] #5 No two records with different forum ids become one record (the owner chose link, not merge); every link is recorded on both records as a `twin` claim with its evidence and counted in the crawl report's `twins_linked`, and a copy left unlinked because several main-track submissions share its title (its `_bibtex` naming none) is counted in `twins_ambiguous`, so refusals are auditable from the manifest
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner decision 2026-10-02: link, don't merge (option a), recorded as decision-029.

Built in openreview_v1.link_twins (rule 6, after the collapses):
- A copy is a record from a non-main submission listing whose dedup title key matches exactly one main-track submission-listing record. With several matches, it is a copy of the one its _bibtex url names.
- An empty title key is never matched.
- _bibtex counts only when it names a same-title record: all 35 ICLR 2017 Invite to Workshop notes' _bibtex name one unrelated forum, B1akgy9xx.
- Each side gets a twin claim (source openreview_v1, a sorted tuple of the other ids, with evidence of how it was linked).
- The crawl report counts twins_linked and twins_ambiguous; the manifest keys appear only when non-zero.
- render refuses a twin claim naming a record the snapshot doesn't hold.
- Record schema 4: ClaimField gains twin and invitation; the OpenAPI enum is regenerated and is open, so additive.

Tests (test_openreview_v1.py):
- a _bibtex pair linked both ways; a title-only pair whose _bibtex names another forum;
- no match, or two matches, stays unlinked (twins_ambiguous 1, DEBUG line); a _bibtex picking one of two;
- a twin with two copies; punctuation-only titles never matched;
- a dropped twin, and a dropped copy, never named (rule 6 runs after rule 5);
- the claims survive dedup, an RIS merge, a takedown and render;
- render refuses a dangling twin.

Real data: a clone of the main checkout's data/cache, rebuilt into scratch dirs at 29d5266 and again at c340afd after the review fixes, with identical output. The baseline is 2026-09-29-d552baa07aed (TASK-155's byte-identical rebuilds); the result is 2026-09-29-8adf9327771a.
- op snapshot diff: added, removed, rekeyed, changed and display_only all 0; provenance_only 104.
- merges.csv and conflicts.csv: cmp-identical.
- Manifest: record_schema_version 3 to 4; ICLR 2017 twins_linked 53; RIS parser_version 0.1.4 to 0.1.5; snapshot_hash and built_at.

The 104 records:
- 53 copies: 18 Submitted to ICLR 2017, linked by _bibtex and title, whose twins say Submitted to ICLR 2017 (main/rejected); 34 Invite to Workshop, linked by title, whose twins are Invite to Workshop on the conference listing (workshop/unknown); 1 with no venue, linked by title, whose twin is one of the 18's.
- 51 conference twins: 18 main/rejected and 33 workshop/unknown. Two of them hold two-id values: one of the 18 has its _bibtex copy plus the no-venue copy, and one Invite twin has two copies.
- So 53 pairs touch 104 distinct records, not 106.

Identified: the record set and every indexed or hashed field are identical, and provenance is neither indexed nor filtered, so every query's identified count is unchanged; a linked pair is two records, as before.

Only ICLR 2017 matches: the other v1 adapters' non-main listings have 0 title matches.

Docs: spec 01 (provenance, v1 rule, Reporting note), the record-schema, dedup-rules, openreview-api, openreview-venueids and snapshots skills, docs/results/2026-10-02-iclr-2017-twins.md.

AC #3 was reworded at the lead's direction (link, not merge: twin claims and the twins_linked/twins_ambiguous counts instead of the audit files).

Reviews: code, docs, observability, api-contract, security, qa, dedup-auditor, track-classifier-auditor and review-methodologist all approved after one round of fixes.

Deferred, filed by the lead: a visible see-also in the results and exports, including clickable twin ids on the paper page; whether a takedown of one twin should follow the link.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
ICLR 2017's workshop-listing copies are now linked to their conference twins, never merged (the owner's decision, decision-029). The v1 crawler's link_twins gives each side a twin claim naming the other. A copy is a non-main submission whose dedup title key matches exactly one main-track submission, or several of which its _bibtex names one. _bibtex alone is never trusted: all 35 Invite to Workshop notes name one unrelated forum. On the 2026-09-29 cache this links 53 copies to 51 conference records (104 records, two of them with two copies). op snapshot diff shows exactly those 104 as provenance_only, and merges, conflicts, tracks, statuses, hashes and identified counts are unchanged. twins_linked and twins_ambiguous count the links and refusals in the crawl report. Record schema 4 adds the twin claim field.
<!-- SECTION:FINAL_SUMMARY:END -->
