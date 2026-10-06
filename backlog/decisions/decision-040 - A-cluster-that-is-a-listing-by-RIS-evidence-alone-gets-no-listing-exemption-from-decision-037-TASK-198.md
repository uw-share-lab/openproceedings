---
id: decision-040
title: >-
  A cluster that is a listing by RIS evidence alone gets no listing exemption
  from decision-037 (TASK-198)
date: '2026-10-05 23:54'
status: accepted
---
## Context

decision-037 lets an imported record (sources `ris` alone) merge with a crawled cluster by abstract (step 3,
`abstract_venue_year`), but never with a record that is no listing and is rejected, withdrawn or
desk-rejected: `ris` ranks last for status, so the merged record would keep that status. A cluster that is a
listing is exempt, because a crawled listing names an accepted paper. `is_listing` counts a cluster as a listing
when a proceedings source claims it, or when any claim's `urls.proceedings`/`urls.pdf` names a proceedings id,
including a RIS row's. So in TASK-174's shape (a rejected OpenReview note, its forum id's RIS row naming a
proceedings paper, and an import of that paper with the same abstract) the note's cluster is a listing by RIS
evidence alone, the import merges into it, and the record keeps OpenReview's `rejected`. The dedup-auditor
found this on 2026-10-05 while reviewing the fix for nightly run 37353576315 (TASK-198).

Options: keep the exemption for every listing; or grant it only to a cluster that is a listing by crawled
evidence (a proceedings source's claim, or a crawled note's own proceedings URL), so RIS evidence alone never
lets a rejected, withdrawn or desk-rejected cluster absorb an import.

## Decision

The project owner chose (2026-10-05) the second: for decision-037's exemption in steps 2 and 3, a cluster is a
listing only by crawled evidence. A proceedings id named by a RIS row alone does not make it one. `is_listing`
keeps its meaning elsewhere (reconcile, the track rule); the exemption uses the narrower test.

## Consequences

- No import takes a `rejected`, `withdrawn` or `desk-rejected` status through a merge on RIS evidence. A crawled
  note that names its own proceedings URL is crawled evidence, so it keeps the exemption and its status
  (`LISTED_REJECTED_NOTE`); no crawler emits such a note today.
- In TASK-174's shape the import stays a separate record until a crawl lists the paper.
- `test_dedup_props.py`'s abstract-merge property asserts the narrower rule, with `REJECTED_NOTE_RIS_LISTING`
  pinned as no merge; TASK-198 implements it.

