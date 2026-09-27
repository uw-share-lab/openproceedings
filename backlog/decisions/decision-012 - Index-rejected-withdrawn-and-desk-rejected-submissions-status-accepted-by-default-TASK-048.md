---
id: decision-012
title: >-
  Index rejected, withdrawn and desk-rejected submissions; status:accepted by
  default (TASK-048)
date: '2026-09-27 20:15'
status: accepted
---
## Context

Spec 00 open question 2 (M4): OpenReview makes some rejected, withdrawn and desk-rejected submissions
public. Should the crawl index them? The options were (a) index only accepted papers, so a default
search can never show a rejected one; (b) index everything public and let the default `status:accepted`
filter (spec 02 §Default filters) remove the rest, with the removal counted in `excluded` (guarantee 6),
the same pattern workshops already use; (c) keep them in the snapshot but out of the index.

Option (a) makes a reviewer's "records removed before screening" number impossible to report and hides
the grey literature a systematic review may deliberately include (a rejected ICLR paper is still a
public, citable manuscript). Option (c) makes `status:rejected` a query no instance can answer. The
query layer, the exclusion accounting (spec 03 §Exclusion accounting) and the exports (spec 04: RIS `KW`
and `N1`, BibTeX `@unpublished`) already handle every status value, so (b) costs no new mechanism.

What is actually public differs by venue (verified live, 2026-09-27, `docs/research/2026-09-27-openreview-and-proceedings-facts.md`):
ICLR publishes every rejected, withdrawn and desk-rejected submission (group `public_submissions`,
`public_withdrawn_submissions`, `public_desk_rejected_submissions` all true; ICLR 2025: 3,703 accepted,
4,908 rejected, 2,991 withdrawn, 70 desk-rejected). NeurIPS and ICML set all three to false: only authors
who opt in make a rejected paper public (NeurIPS 2024 main: 201; ICML 2025: 162; ICML 2023–2024: none),
and withdrawn or desk-rejected ones are almost never public. Proceedings (NeurIPS before 2021, ICML from PMLR) list accepted papers only.

## Decision

The owner decided (2026-09-27): we index every public rejected, withdrawn and desk-rejected submission
with `status:rejected`, `status:withdrawn` or `status:desk_rejected`, taken from the submission note's
`content.venueid` suffix (v2), or in API v1 years from its `content.venue` string, decision note or
withdrawn / desk-rejected invitation (never the bare v1 venueid, which rejected papers carry too:
TASK-091), and the default `status:accepted` filter excludes them, each counted in the exclusion banner's status buckets.

## Consequences

- The M4 crawlers list the `…/Rejected_Submission`, `…/Withdrawn_Submission` and
  `…/Desk_Rejected_Submission` venueids (v2), and the withdrawn and desk-rejected invitations (v1),
  explicitly; nothing is filtered at ingestion (track-taxonomy skill). TASK-050, 051 and 054 own this.
- `excluded.status.{rejected,withdrawn,desk_rejected}` counts only what the venue made public: complete
  for ICLR, the opt-in minority for NeurIPS and ICML 2025+, zero for ICML 2023–2024 and for
  proceedings-only years. The coverage
  report (TASK-054) and spec 07 §C must say so per venue-year, so nobody reads a small NeurIPS
  rejected count as a rejection rate.
- The default query and its canonical string are unchanged (`status:accepted` was already the default),
  so `canonical_hash` values and saved search records don't change; an index built from the M4 snapshot
  has a new `index_version`, and replaying an M2 record against it reports `drifted` with larger
  `excluded` counts, never a silently different set.
- Spec 00 §Open questions Q2 is closed; spec 01 §Track taxonomy (status handling) and spec 02 §Default
  filters say what each status covers.
- Revisit if a venue asks that rejected submissions not be redistributed (bound up with spec 00 Q1,
  abstract redistribution, M6).

