---
id: decision-029
title: >-
  Link ICLR 2017 workshop copies to their conference twins as two records with
  twin claims, never merged; the RIS importer reads scholarmend 0.1.5's
  invitation by the crawler's twin rule (TASK-159, TASK-157)
date: '2026-10-02 07:24'
status: accepted
---
## Context

ICLR 2017's OpenReview workshop listing (`ICLR.cc/2017/workshop/-/submission`, 161 notes on the 2026-09-29 crawl)
holds resubmissions of conference papers. They are separate notes with their own forum ids, so they were separate
records from their conference twins (TASK-152, `docs/results/2026-10-01-iclr-2017-workshop-copies.md`). With the
default filters off, such a paper appears twice under "identified".

A tally over the cached listings (`docs/results/2026-10-02-iclr-2017-twins.md`):
- **18 `Submitted to ICLR 2017` notes.** Each has exactly one conference note with its title, and its `_bibtex`
  url names that note.
- **35 `ICLR 2017 Invite to Workshop` notes.** All 35 `_bibtex` urls name the same unrelated conference forum,
  `B1akgy9xx`, which looks like an OpenReview default. 34 of them have exactly one conference title match.
- **1 note with no `content.venue`.** It has exactly one conference title match.
- **Other v1 venue-years.** None has a non-main submission note whose dedup title key matches a main-track
  submission: ICLR 2014 workshop, 2023 Tiny Papers and BlogPosts, NeurIPS 2021–2022 D&B.

Options:
- **(a) Link both groups.** Each copy and its twin stay two records, linked by a claim.
- **(b) Link only the 18 `_bibtex` pairs**, and defer the title-only ones.
- **(c) Collapse each copy into its twin**, as the crawler does for identical notes (TASK-125, TASK-132).

Collapsing would break dedup-rules §Never merge: two forum ids are two submissions, and these have different
outcomes, workshop/`unknown` against main/`rejected` for the 18. It would also drop records from the PRISMA counts.
The track rule (decision-005, dedup-rules) would also keep the 18 apart, since their tracks differ. A bare `_bibtex`
rule would have linked all 35 `Invite to Workshop` notes to one wrong record.

Separately, the RIS importer could not tell a workshop copy from a real main-track rejection: scholarmend's
claims for both are the same venueid, forum id and `venue_string` (TASK-152). scholarmend 0.1.5 now emits the v1
note's top-level submission invitation as an `invitation` claim (TASK-157).

## Decision

**Linking (the owner, 2026-10-02: option a).** We link, never merge.
- **What counts as a copy.** A record from a non-main v1 submission listing whose dedup title key matches exactly
  one record from the main-track submission listing is a copy of it. Where several main-track records share the
  key, it is a copy of the one its `_bibtex` url names.
- **When `_bibtex` counts.** Only when it names a record with the copy's title.
- **When nothing is matched.** An empty title key is never matched. A copy with several matches and no `_bibtex`
  naming one stays unlinked.
- **The claim.** Each side gets one `twin` claim (source `openreview_v1`) whose value is the other records' ids,
  sorted, with evidence saying how it was linked.
- **Counting.** The crawl report counts the links in `twins_linked`, and the ambiguous copies in
  `twins_ambiguous`, so refusals are auditable from the manifest.
- **Scope.** The rule is generic over the v1 adapters; only ICLR 2017 matches today.

**The RIS importer (TASK-157)** reads scholarmend 0.1.5's `invitation` claim through the crawler's own rule
(`openreview_v1.is_twin_outcome`, `submission_listing`). A main-track outcome on a note of a non-main submission
listing, where the venueid names no track, is the conference twin's outcome. So the record takes the listing's
track and an `unknown` status, and the claim is kept as an `invitation` claim. An entry without the claim is
read as before.

## Consequences

- **What the rebuild links** (2026-09-29 cache). 53 copies: 18 by `_bibtex` and title, 34 `Invite to Workshop`
  by title, and 1 with no venue by title. They link to 51 conference records:
  - 18 main/rejected `Submitted to ICLR 2017` notes. One of these has two copies: its `_bibtex` copy and the
    no-venue copy.
  - 33 workshop/unknown `Invite to Workshop` notes on the conference listing. One of these has two copies.

  So 53 pairs touch 104 distinct records, not 106: two conference records each hold a two-id `twin` value.
- **What changes in the snapshot.** `op snapshot diff` against `2026-09-29-d552baa07aed` shows only those 104 as
  `provenance_only`, each gaining one claim. `merges.csv` and `conflicts.csv` are byte-identical. Tracks,
  statuses, `content_hash` and every count are unchanged. The manifest gains `twins_linked: 53` for ICLR 2017;
  `twins_ambiguous` is absent because it is 0.
- **"Identified" is unchanged.** Linked twins are two records, and the tool removes neither before screening.
  A reviewer's own duplicate step belongs in the review's own "duplicates removed" count.
- **Record schema 4.** `ClaimField` gains `twin` (a tuple) and `invitation`, both provenance only. The manifest's
  `record_schema_version` and the OpenAPI claim-field enum change; the enum is open, so the change is additive.
  `render` refuses a `twin` claim naming a record the snapshot doesn't hold.
- **scholarmend 0.1.5 is pinned.** The RIS reports' `parser_version` reads 0.1.5. The committed Trust-Evals cache
  predates 0.1.5, so no current record carries an `invitation` claim. A re-import with 0.1.5 claims moves up to
  18 RIS-only ICLR 2017 records from main/rejected to workshop/unknown, which `op snapshot diff` shows.
- **Deferred.** A visible "see also" in the results and exports, including clickable twin ids on the paper page.
  The link shows today in the paper page's provenance table. Whether a takedown of one twin should follow the
  link to the other is also open.
- **Where else.** Recorded in spec 01 (§Record schema provenance, §Sources RIS row, the v1 rules), and in the
  record-schema, dedup-rules, openreview-api, openreview-venueids and snapshots skills and the ris-importer agent.
- **Revisit** if another venue-year gains copies, or if `_bibtex` becomes reliable enough to link on alone.

