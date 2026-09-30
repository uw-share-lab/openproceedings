---
id: decision-005
title: Per-field source precedence for merged records (task-003)
date: '2026-09-26 15:43'
status: accepted
---
## Context

When the same paper comes from OpenReview and from the published proceedings (the ICLR archive, NeurIPS
proceedings, PMLR),
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
| `title`, `abstract`, `authors` | `openreview_v2`, `openreview_v1` (the venues' own platform, current first), then `iclr_archive`, `neurips_proceedings`, `pmlr` (for papers or years not on OpenReview, e.g. ICML before its move), then `ris` |
| `status` | Where the venue-year's official proceedings (`iclr_archive`, `neurips_proceedings`, `pmlr`) are published and crawled, they decide acceptance: listed → `accepted`; OpenReview says accepted but not listed → `status=unknown` plus a `conflicts.csv` row (the reconcile step after dedup, task-072, below) (never silently accepted or rejected; `unknown` is itemised in exclusion counts). Otherwise `openreview_v2`, `openreview_v1` via `content.venueid` only (never an invitation); `ris` only through its claims (spec 01) |
| `track` | `openreview_v2`, `openreview_v1` via `content.venueid`; proceedings only where OpenReview doesn't hold the venue-year's track (per track: the owner's decision, 2026-09-29, below); `ris` last (its track comes from those same claims, via scholarmend; in M2 it is the only source) |
| `venue`, `year` | the source whose crawl scope defined the record, and it must agree with the venueid; a disagreement is a `conflicts.csv` row, never silently resolved. As built, venue and year are part of every merge key, so they can't differ inside a merge; a forum id seen in two venue-years is a `venue_year_not_merged` row and the records stay apart |

Two same-rank sources that disagree produce a `conflicts.csv` row with `resolution=precedence:<source>`.
A **title** that differs between merged sources (beyond case and punctuation, i.e. a different dedup
title key) is also a `conflicts.csv` row with both titles, so a reviewer can see both and never screens
the same study twice; both titles stay in the record's claims.

**Same-source claims** (amended 2026-09-26, task-021 review): a record keeps one claim per (field,
source). When one source gives a field twice (the same paper in both Trust-Evals searches, or a
re-crawl), the newest `fetched_at` replaces the older claim, which is then written to `conflicts.csv` as a
`newest:<source>` row (or `tie:<source>` for an exact tie) when its value differs. "All claims are kept"
means every *source's* claim, including the ones precedence overruled.

**Built (task-072, 2026-09-29): the reconcile step after dedup** (`ingest/reconcile.py`; dedup-rules skill
§Reconcile). "Published and crawled" means a (proceedings source, venue, year) whose every crawled listing is
complete: it states a count and the count matched, every entry became a record, and it names no volume left
uncrawled (`see_also`). The ICLR archive (2014–2016) counts as
official proceedings, as this table names it; on the 2026-09-29 crawl it changes nothing, since OpenReview
gives no accepted ICLR 2014–2016 conference paper. The rule applies per track: only a track the crawled
listings hold (`main`, `datasets_benchmarks`, `position`; a mixed PMLR volume's own `unknown` covers the tracks
its listings merged into). "Not listed" means merged with no listing and sharing no title key or forum id
with one; a record that shares one but stayed apart (ambiguous) keeps its status and its dedup row. The
derived `unknown` is a claim: `status=unknown` from the proceedings source, with the listing URL, that listing's
index-page fetch time and evidence `not listed: …` (a prefix reserved for it), which outranks OpenReview here, so the record equals what its
claims resolve to and the `precedence:<source>` row is the `conflicts.csv` row. That absence claim names no
paper, so dedup never counts it as a listing. The real-data check (4 records made `unknown` on snapshot
`2026-09-29-4cd2bba17cad`, built after task-128; 3 of them listed under another title) is
`docs/results/2026-09-29-reconcile-real-data.md`.

**Track in an OpenReview venue-year: per track (decided by the owner, 2026-09-29; task-130).** "On OpenReview"
in the `track` row means the venue-year's *track*, not the venue-year: the proceedings decide a paper's track
wherever OpenReview doesn't hold that venue-year's track. ICLR 2016 has only its workshop track on OpenReview, so
its 80 main papers come from the ICLR archive and keep track `main`. Where OpenReview does hold the track and
holds the paper, OpenReview's track claim wins over the proceedings' (a `precedence:openreview_*` row when they
differ). Where OpenReview holds the track but not the paper (a listing that merged with no note), the listing's
own track claim is the only one, and it answers.

As built, "OpenReview holds the track" is read per record, from the claims, not from a table of crawled
venueids. An OpenReview track claim is the note's own `content.venueid`, classified. So a record that carries
one is on a track OpenReview holds, and `PRECEDENCE` (OpenReview first) gives it that track. A record with
none takes the proceedings' track. The OpenReview crawlers claim no proceedings URL, so a note is never itself
a listing. Dedup keeps a note on a track the proceedings don't host (`workshop`, `unknown`, …) apart from every
listing (`track_not_merged`). So wherever both answer, OpenReview's track is one the proceedings host too. An
OpenReview `unknown` never overrules a listing's track, and a listing's `unknown` (a mixed PMLR volume) yields
to OpenReview's track. This was already the behaviour before the decision (task-072 left it as an open question),
so the decision changes no record: tests pin it (`test_dedup.py`, `test_dedup_props.py`, `test_reconcile.py`).
The real-crawl check is in `docs/results/2026-09-29-reconcile-real-data.md` §Track, decided per track.

The evidence the owner decided on (task-072's measurement on the 2026-09-29 crawl,
`docs/results/2026-09-29-reconcile-real-data.md`): 149 records in venue-years on OpenReview take their track
from a proceedings listing with no OpenReview claim. ICLR 2014: 1 (an accepted archive paper whose OpenReview
note didn't merge). ICLR 2016: 80 (OpenReview holds only its workshop track). NeurIPS 2021–2025 main and D&B: 4
(three are the same paper as an OpenReview note under another title, and one shares its title with two
OpenReview notes). NeurIPS 2025: 64 `other` (Creative AI) listings. Before task-128 fixed `html.py`'s charref
handling there were 151: two more listings whose mangled titles kept them apart. The alternative, taking the
track from nowhere (`unknown`), would have dropped ICLR 2016 main from 80 to 0 and ICLR 2014 main to 34 of 35
(−2.9%, outside the M4 gate's ±1%).

## Consequences

- The searchable text is OpenReview's version wherever the paper is there, and the proceedings text
  otherwise; a methods section can say so.
- OpenReview notes can change after publication, but each claim is stored with its `fetched_at` in the
  snapshot, so a search pinned to an `index_version` stays reproducible; a later edit appears only in a
  new snapshot, as a `snapshot diff` change.
- Changing this table can change a record's searchable or filterable values (title, abstract, track,
  status), and so its `content_hash`: that is an `index_version` change. A change that only moves
  `authors` (not hashed) is a display-only change and leaves the hash alone.

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
