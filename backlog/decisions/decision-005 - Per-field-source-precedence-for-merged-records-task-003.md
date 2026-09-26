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

## Evidence on abstract recency (2026-09-26, settled)

scholarmend (`ledger.py`) ranks the proceedings abstract above OpenReview's on the grounds that "a
camera-ready revision can leave [the OpenReview note] behind"; the review lead's sources say OpenReview is
the more current. An authenticated check against OpenReview (API v2 notes and their edit history) on the
Trust-Evals cache paired each cached OpenReview abstract with a proceedings abstract only when the match
was unique on both sides: 8 pairs. In all 3 pairs that are the same paper, OpenReview's current abstract
equals the proceedings text. The 5 that differ are all workshop notes (SafeGenAI, SeT LLM @ ICLR 2024,
MINT@NeurIPS 2024) or an unpublished ICML 2026 submission matched to a different publication's
proceedings abstract; none ever carried the proceedings text. So there is no evidence that OpenReview lags
the proceedings for the same paper, and the only disagreements found are distinct publications, which
dedup never merges (a workshop note never merges into a proceedings record). OpenReview-first stands.
The sample is small; the local real-corpus checks (decision-004) will report any title/abstract
conflicts at scale through `conflicts.csv`. scholarmend is left unchanged while the Trust-Evals screening
that used its output is in progress.

A second, independent check the same day (another session, recorded in the scholarmend notes) matched on
exact titles: the 243 cached OpenReview and 1,633 cached proceedings abstracts share only 2 papers, both
identical; and 22 ICML 2024/25 abstracts on OpenReview match the public PMLR pages in wording (13 exactly,
7 up to punctuation/whitespace, 2 up to markup such as `\textbf{63.7\%}` vs `63.7%`). That markup
tokenizes identically (golden rows in `tests/golden/test_tokens.py`), so OpenReview-first never changes
what a query matches; only the displayed text differs.
