---
id: decision-005
title: Per-field source precedence for merged records (task-003)
date: '2026-09-26 15:43'
status: accepted
---
## Context

When the same paper comes from OpenReview and from the published proceedings (NeurIPS proceedings, PMLR),
the sources can disagree on title casing, abstract text, author lists and status. Spec 01 keeps every
claim and needs a per-field rule for which one a record shows; the record-schema skill proposed a table.
The review lead first chose proceedings first, then (the same day, 2026-09-26) switched to OpenReview
first: NeurIPS uses OpenReview as its official submission, review and hosting platform, so its records
are current well before the static proceedings site publishes, and ICLR is only on OpenReview.

## Decision

Precedence is data (scholarmend's ledger pattern): a listed source may answer a field, best first; an
unlisted source never answers it. All claims are kept, including the losing ones.

| Field | Precedence (best first) |
|---|---|
| `title`, `abstract`, `authors` | `openreview_v2`, `openreview_v1` (the venues' own platform, current first), then `neurips_proceedings`, `pmlr` (for papers or years not on OpenReview, e.g. ICML before its move), then `ris` |
| `track`, `status` | `openreview_v2`, `openreview_v1` (only `content.venueid` decides, never an invitation); proceedings only for venue-years not on OpenReview (then `status=accepted`); `ris` only through its claims (spec 01) |
| `venue`, `year` | the source whose crawl scope defined the record, and it must agree with the venueid; a disagreement is a `conflicts.csv` row, never silently resolved |

Two same-rank sources that disagree produce a `conflicts.csv` row with `resolution=precedence:<source>`.

## Consequences

- The searchable text is OpenReview's version wherever the paper is there, and the proceedings text
  otherwise; a methods section can say so.
- OpenReview notes can change after publication, but each claim is stored with its `fetched_at` in the
  snapshot, so a search pinned to an `index_version` stays reproducible; a later edit appears only in a
  new snapshot, as a `snapshot diff` change.
- Changing this table changes `content_hash` for affected records, so it is an `index_version` change.
