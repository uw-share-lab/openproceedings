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

Implementation limits (the implementer's, adopted after review; confirmed by the owner on 2026-09-29, TASK-139): the twin must be withdrawn (not desk-rejected: a
desk rejection for a duplicate submission can leave the same pdf beside the presented copy) and in the same track
as the accepted record (a withdrawn conference note says nothing about an accepted workshop version); a record
with no OpenReview pdf has no twin; the row names every twin found.

The owner's answers to the questions this record left open (2026-09-29, TASK-139):
1. A blind note with **no decision at all** (no decision note in its forum) and a withdrawn twin (same pdf, same
   track) becomes `withdrawn`, with evidence naming the twin(s) and the listing page. Nothing disagrees here: the
   twin's withdrawal is the only status signal, so this is not a ranking between signals.
2. A **rejected** blind note with a withdrawn twin stays `rejected` (as implemented; now pinned by a test).
3. **Desk-rejected** twins do not count (as implemented; pinned by a test).
4. The implementation limits above (withdrawn twins only, same track, no pdf means no twin) are confirmed.

Implementation details of answer 1 (the implementer's, TASK-139; pending owner confirmation):
- The status claim cites the **first** twin's listing page (twins in id order; a claim has one url) and reads
  `no decision note in the forum; withdrawn twin <id> shares the pdf (invitation=…)`, naming every twin.
- There is **no `conflicts.csv` row**: the accepted case has one because its signals disagree; this case has
  nothing unresolved.
- The record is **never collapsed** with its twin by the duplicate collapse, even if their content matched: the
  rule changes a status, never which records exist.
- Only the found absence of a decision note (`no decision note in the forum`) counts. A note `unknown` for another
  reason stays `unknown`: decision notes that disagree, a decision string not in the table, no submission number
  to find the decision note by, a forum a dry run didn't fetch, `Invite to Workshop Track`.
- The twins are the records withdrawn by their listing before the rule runs, so the result is independent of
  record order and a second run changes nothing.
- The crawl report moves each such note out of `unmapped` (where its missing decision note was counted) into its
  own `withdrawn_by_twin` count, present in the manifest only when non-zero, so the crawl's attention warning and
  the coverage report's crawl listing stop reporting notes that are answered.

## Consequences

- `openreview_v1.withdrawn_twins` runs after a venue-year's listings and before the duplicate collapse; ICLR 2018
  `S1p31z-Ab` is `status:unknown` and ICLR 2018 main counts 336, the official number. ICLR 2021 main stays at 859
  of 860 (`xGZG2kS5bFk` is `unknown`, within ±1%).
- Records change, so the next snapshot's `snapshot_hash` and `index_version` change for ICLR 2018. A saved search
  that matched `S1p31z-Ab` under `status:accepted` still reproduces on its pinned `index_version` while that
  index exists (`op index retire` refuses a pinned version, TASK-085); it replays as `drifted` only if the pinned
  index is gone and it runs on a newer one.
- Desk-rejected twins are not flagged (none on the 2026-09-29 cache); the owner confirmed this (answer 3).
- Only an accepting status is flagged against a withdrawn twin. A rejected blind note with a withdrawn twin (10 in
  ICLR 2018) keeps both statuses: neither is in a default search, and the owner confirmed it (answer 2).
- Since TASK-139 the 12 undecided ICLR 2018 blind notes with a withdrawn twin are `withdrawn` (answer 1): on the
  2026-09-29 cache ICLR 2018 main goes from 13 `unknown` / 83 `withdrawn` to 1 `unknown` (`S1p31z-Ab`) / 95
  `withdrawn`; accepted stays 336 and no other v1 year has such a pair. Their records change, so the next
  snapshot's `snapshot_hash` and `index_version` change; no default search matches them before or after
  (`status:accepted`). Any saved search with `status:withdrawn` or `status:unknown` whose results can include
  these records (not only ICLR 2018-scoped ones) still reproduces on its pinned `index_version`; run on the new
  index (the pinned one gone), it would replay as `drifted`. The ICLR 2018 crawl report's `unmapped` loses its
  12 `decision_note` entries, now `withdrawn_by_twin: 12`.
- Spec 01 §Sources (v1 as-built) and §Pipeline 5 (the manifest's `conflicts` keys), spec 04 (why `unresolved` is
  not in `dedup`), spec 07 §C (the coverage report lists every unresolved record with the cell it would count
  in), and the openreview-api, dedup-rules, snapshots and coverage-reporting skills say so.
- Revisit when an ICLR accepted-list source or per-paper overrides exist: either could resolve these records
  from outside OpenReview, with its own claim and precedence.

