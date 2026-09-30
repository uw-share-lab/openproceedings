---
id: decision-020
title: >-
  OpenReview v1 status signals that disagree stay unknown, including a withdrawn
  twin of an accepted note (TASK-113)
date: '2026-09-30 00:52'
status: accepted
---
## Context

OpenReview API v1 gives a paper's status through several signals: the listing invitation a note appears under
(the withdrawn and desk-rejected invitations, decision-012), `content.venue`, `content.decision` and the forum's
decision note. TASK-051 made the v1 crawler set a field to `unknown` when one note's own signals disagree, with an
`unresolved:openreview_v1` row in `conflicts.csv`, and left open (TASK-113) whether one signal should instead
outrank another.

The evidence from the 2026-09-29 crawl is that no fixed ranking is right:
- ICLR 2021 `xGZG2kS5bFk` (Dance Revolution) is listed under the withdrawn invitation, yet its `content.venue` says
  `ICLR 2021 Poster`, and it was presented at ICLR 2021 and is on the official accepted list. "Withdrawn outranks
  accepted" would drop a real paper.
- ICLR 2018 `S1p31z-Ab` (ELMo) has a decision note `Accept (Poster)`, while `SJTCsqMUf`, the same pdf
  (`/pdf/590cfe03…`), is listed under the withdrawn invitation; the paper was withdrawn and published elsewhere,
  not presented at ICLR 2018. "Accepted outranks withdrawn" would count a paper ICLR never presented.

The second case was silent: the two notes are two records (different forum ids, never merged, spec 01
§Pipeline 4) and each looked consistent on its own, so ICLR 2018 main counted 337 accepted against an official
336. The same crawl has 24 such blind/withdrawn pdf pairs in ICLR 2018 and none in any other v1 year: the blind
note is accepted in 1 (ELMo), rejected in 10, `Invite to Workshop Track` in 1, and undecided in 12.

Options considered:
- (a) A fixed precedence (withdrawn over accepted, or accepted over withdrawn): wrong for one of the two papers
  above whichever way it points.
- (b) Per-paper overrides, or an ICLR accepted-list source that decides: they would resolve both, but are new
  sources of truth that need their own design (later work, not here).
- (c) Keep `unknown` for every disagreement, and also flag the pair case: an accepted note whose pdf a
  withdrawn note shares.

## Decision

The project owner decided (2026-09-29): when OpenReview v1 signals disagree about a status, the field stays
`unknown`, with no ranking between signals. That now also covers two notes of one paper: an accepted record
whose pdf a withdrawn record of the same crawl shares becomes `unknown` with an `unresolved:openreview_v1` row
naming both signals; the twin keeps its own status.

Implementation limits (the implementer's, adopted after review; pending owner confirmation): the twin must be withdrawn (not desk-rejected: a
desk rejection for a duplicate submission can leave the same pdf beside the presented copy) and in the same track
as the accepted record (a withdrawn conference note says nothing about an accepted workshop version); a record
with no OpenReview pdf has no twin; the row names every twin found.

## Consequences

- `openreview_v1.withdrawn_twins` runs after a venue-year's listings and before the duplicate collapse; ICLR 2018
  `S1p31z-Ab` is `status:unknown` and ICLR 2018 main counts 336, the official number. ICLR 2021 main stays at 859
  of 860 (`xGZG2kS5bFk` is `unknown`, within ±1%).
- Records change, so the next snapshot's `snapshot_hash` and `index_version` change for ICLR 2018; a saved search
  that matched `S1p31z-Ab` under `status:accepted` replays as `drifted`.
- Desk-rejected twins are not flagged (none on the 2026-09-29 cache); whether one should be is a possible
  follow-up.
- Only an accepting status is flagged against a withdrawn twin. A rejected blind note with a withdrawn twin (10 in
  ICLR 2018) keeps both statuses: neither is in a default search, and the owner's decision names the accepted
  case. The 12 undecided blind notes with a withdrawn twin stay `unknown`; marking them withdrawn (which would
  clear ICLR 2018's 12 unknowns) was suggested by research but is not part of this decision (a possible
  follow-up).
- Spec 01 §Sources (v1 as-built) and §Pipeline 5 (the manifest's `conflicts` keys), spec 04 (why `unresolved` is
  not in `dedup`), spec 07 §C (the coverage report lists every unresolved record with the cell it would count
  in), and the openreview-api, dedup-rules, snapshots and coverage-reporting skills say so.
- Revisit when an ICLR accepted-list source or per-paper overrides exist: either could resolve these records
  from outside OpenReview, with its own claim and precedence.

