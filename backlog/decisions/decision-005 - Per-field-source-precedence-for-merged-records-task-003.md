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
are current well before the static proceedings site publishes, and ICLR is only on OpenReview. For
acceptance the lead's rule is the opposite: the official proceedings define the peer-reviewed boundary,
and a status conflict defaults to them; discrepancies are documented, not silently resolved.

## Decision

Precedence is data (scholarmend's ledger pattern): a listed source may answer a field, best first; an
unlisted source never answers it. All claims are kept, including the losing ones.

| Field | Precedence (best first) |
|---|---|
| `title`, `abstract`, `authors` | `openreview_v2`, `openreview_v1` (the venues' own platform, current first), then `neurips_proceedings`, `pmlr` (for papers or years not on OpenReview, e.g. ICML before its move), then `ris` |
| `status` | Where the venue-year's official proceedings (`neurips_proceedings`, `pmlr`) are published and crawled, they decide acceptance: listed → `accepted`; OpenReview says accepted but not listed → `status=unknown` plus a `conflicts.csv` row (never silently accepted or rejected; `unknown` is itemised in exclusion counts). Otherwise `openreview_v2`, `openreview_v1` via `content.venueid` only (never an invitation); `ris` only through its claims (spec 01) |
| `track` | `openreview_v2`, `openreview_v1` via `content.venueid`; proceedings only for venue-years not on OpenReview |
| `venue`, `year` | the source whose crawl scope defined the record, and it must agree with the venueid; a disagreement is a `conflicts.csv` row, never silently resolved |

Two same-rank sources that disagree produce a `conflicts.csv` row with `resolution=precedence:<source>`.
A **title** that differs between merged sources (beyond case and punctuation, i.e. a different dedup
title key) is also a `conflicts.csv` row with both titles, so a reviewer can see both and never screens
the same study twice; both titles stay in the record's claims.

## Consequences

- The searchable text is OpenReview's version wherever the paper is there, and the proceedings text
  otherwise; a methods section can say so.
- OpenReview notes can change after publication, but each claim is stored with its `fetched_at` in the
  snapshot, so a search pinned to an `index_version` stays reproducible; a later edit appears only in a
  new snapshot, as a `snapshot diff` change.
- Changing this table changes `content_hash` for affected records, so it is an `index_version` change.

## Open evidence question (2026-09-26)

scholarmend (`ledger.py`) ranks the proceedings abstract above OpenReview's on the grounds that "a
camera-ready revision can leave [the OpenReview note] behind"; the review lead's sources say OpenReview is
the more current. A cache comparison was inconclusive (17 prefix-matched pairs, several of them different
papers). The review lead is running an authenticated check of OpenReview revision history for the papers
whose abstracts differ. If OpenReview proves stale for camera-ready abstracts, the `title`/`abstract`/
`authors` row flips to proceedings-first here, with the evidence recorded. scholarmend is not changed
either way while the Trust-Evals screening that used its output is in progress.
