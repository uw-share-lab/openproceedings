---
name: dedup-rules
description: The deduplication standard for ingestion — the merge order (identical id, then the OpenReview forum link a PMLR listing carries, then normalized title within the same venue and year), the hard never-merge rules including the venuetriage (title, "") no-year over-merge trap, how merged fields and claims combine, the post-dedup reconcile that makes an OpenReview-accepted paper the crawled proceedings don't list `unknown`, and the merges.csv / conflicts.csv audit formats and property tests. Use when writing or reviewing backend/src/openproceedings/ingest/dedup.py or reconcile.py, reading merges.csv or conflicts.csv, or investigating a paper that vanished or doubled between snapshots.
---

# Dedup rules (spec 01 §Pipeline 4)

The same paper appears on OpenReview and in the proceedings (NeurIPS in every year, ICML 2023+), and
sometimes in the RIS import too. Dedup produces exactly one record per paper and never folds two papers
into one. **An over-merge is worse than a duplicate:** a duplicate shows up in the hit count, but an
over-merge silently deletes a paper from someone's systematic review.

## Merge order (as built: `backend/src/openproceedings/ingest/dedup.py`)
1. **Identical id, then the forum link**, in any source: the same OpenReview forum id (case-sensitive) in the same venue and
   year, including a RIS record whose URL carries `?id=<forum>`, or the same proceedings id (one paper
   reached by both Trust-Evals searches). One forum id in two venue-years is a conflict
   (`venue_year_not_merged`), never a merge.
   **Then the forum link (TASK-105).** A cluster's forum ids are its own (an OpenReview native id) plus
   every forum id a kept `urls.forum` claim names (`urls.forum_id()`: `openreview.net/forum?id=<id>`, one
   `id`). PMLR's index links each paper's forum from ICML 2023 (recorded for v202, v235 and v267; v28 has
   no link). Clusters that share a forum id
   in the same venue and year merge **whatever their titles say**, before any title match. The link is
   refused (a `conflicts.csv` row with `field = forum_id`, never a merge) when the forum id's records are
   in different venue-years (`venue_year_not_merged`), when the group would hold two forum ids or two
   proceedings ids, such as two listings linking one forum (`ambiguous_not_merged`), or when the track
   rule below fails (`track_not_merged`, e.g. a workshop note linked from a proceedings volume). One
   source on both sides doesn't block a link: the id, not the title, says which paper it is.
2. **Same dedup title key, same `venue`, same `year`.** Build the key from the token-contract
   `normalize()` output of the title's NFC form, joined by single spaces (`.claude/skills/token-contract/SKILL.md`), so dedup and
   search agree on what counts as the same title for NFC text (tokenizer 2's `normalize` doesn't NFC first, so a non-NFC title
   with a backslash indexes other tokens than its key: the tokenizer side is fixed separately on branch fix/tokenizer-nfc-form). Never write a second normaliser. The NFC step (TASK-168) makes
   the key form-independent: tokenizer 2 reads LaTeX before its per-character NFKC, so before it an NFD `Caf\e\u0301`
   lost its `e` to a `\e` command and `Erd\H{o\u030b}s` was no accent macro. `test_every_canonically_equivalent_title_has_one_key`
   pins `title_key(NFC(t)) == title_key(NFD(t)) == title_key(t)`. The real corpus held no non-NFC title (2026-09-29).

3. **An imported record that matched nothing: same abstract key, same `venue`, same `year` (TASK-179).** An
   imported record is a cluster whose only source is `ris` after steps 1 and 2 (`dedup.IMPORTED`). Its title is
   Google Scholar's, which drops math (`$R^2$-Guard` → `-Guard`) and may be a preprint's earlier title; its
   abstract is the publisher's page text. It merges with the same venue-year's clusters that keep an abstract
   with its **abstract key**: `dedup.abstract_key`, `sha256:` + 16 hex of the abstract's `title_key`, and `""`
   (never a match) under `MIN_ABSTRACT_TOKENS` = 50 tokens. Same machinery as step 2 (`_join`, `_merging`,
   `_mergeable`, the chain re-check), so every never-merge rule below holds, set-aside rivals included. A bucket
   with no imported record is never formed: a crawled listing and a note sharing only an abstract stay apart
   (NeurIPS 2023 D&B `3sRR2u72oQ` and its retitled listing, the one such pair on the 2026-10-05 crawl; lifting
   the restriction is an owner decision). Abstracts are normalised only in venue-years that still hold an
   imported record. Never loosen the title key instead: `A$^2$Search` and `ASearch` with different abstracts are
   two papers.

Step 2 only runs **across sources**: the clusters' provenance source sets must be disjoint
(OpenReview ↔ proceedings), **`ris` aside** (TASK-179): RIS is a route, each RIS row names its paper by a forum
id or a proceedings id, and the id checks (at most one forum id and one proceedings id per record) judge two RIS
rows. So a note's cluster that holds the RIS row of its forum id still merges with the same paper's RIS row
under its proceedings id (ICLR 2024 `QHROe7Mfcb`); two RIS rows naming two forum ids or two proceedings ids
never merge. Two OpenReview notes with different forum ids are different submissions
even when their titles match. For example, a main-track paper and a same-year workshop version share a
title, and both must survive. Each step-1 cluster is judged by the record its claims resolve to: its
track, its sources, and the key of every title claim it **keeps**. A same-source title that a newer
claim superseded is only reported (`newest:`), never matched on, because the output record no longer
carries it and a second run would then merge differently. Missing that match leaves a duplicate, the
safe direction.

## Never merge
- Across `venue` or `year`. The key is `(venue, year, title_key)`, and there's no fallback key.
- When `year` is missing. A record without a year never reaches dedup (it fails `PaperRecord`
  validation). This is the venuetriage lesson: a `(title, "")` key merged every year-less record that
  shared a title.
- When `title_key` is empty (a title of punctuation or math only).
- When the key matches **more than one** candidate from one source (`ris` aside: its rows are judged by the
  ids they name, TASK-179), two different forum ids (own or
  linked: a PMLR listing whose link names forum Y never title-merges with note X), or two
  different proceedings papers (proceedings ids come from native ids *and* `urls.proceedings`/`urls.pdf`
  claims, `ingest/urls.py`). That's ambiguous: write a `conflicts.csv` row and keep them all separate.
  The same holds when two keys chain clusters that must not share a record: every cluster in the chain
  stays separate (`field = title_key_chain`).
  Dedup never decides that two OpenReview notes are one paper. A v1 workshop copy and its conference twin (ICLR
  2017: 53 copies) are not one: they stay two records, each with a `twin` claim naming the other, added by the
  crawler (`openreview_v1.link_twins`, TASK-159, decision-029). Dedup keeps the claim in provenance and never
  merges on it. The one case where two notes are one paper, API v1's NeurIPS
  2021 notes that repeat a paper under a second id and number with identical content (300 main-track papers on
  the 2026-09-29 crawl), is collapsed by the crawler before records reach dedup
  (`openreview_v1.collapse_duplicate_submissions`, TASK-125; openreview-api skill), so the survivor merges
  with its proceedings record here. So is a **silent twin** (TASK-132): a note with no non-null `venue` and no
  non-null `venueid` (status `unknown`, in a year whose one status carrier is `content.venue`) is dropped when its
  paper's only other record is an accepted note identical to it in everything but status, presentation and
  venueid (`openreview_v1.collapse_silent_twins`; NeurIPS 2021 `W6e384Lkjbw` into `rDdb26AQ0SO`, the one case
  on the 2026-09-29 crawl), and only if every note it stands for after the identical-note collapse is silent
  too (TASK-147). Anything else short of identical (another pdf or title, two statuses, a rejected
  twin) still arrives as two notes and stays ambiguous: dedup never judges it (TASK-126's set-aside keeps an
  `unknown` note a rival). Of identical notes the kept one is the lowest number, a tie-break, not the one the
  proceedings name: NeurIPS 2021's proceedings pages link the kept forum for 177 of the 297 accepted pairs and
  the dropped one for 120 (`0hJ-U3aqUDf` kept, `rvKD3iqtBdk` linked), and for the silent twin they link the
  dropped `W6e384Lkjbw`. No NeurIPS importer claims that link as `urls.forum` today, so title matching merges
  all 297 and the silent twin's note. If one ever does, the forum link would point those 121 at a note the
  crawl dropped: the survivor must then follow the proceedings' link (collapse to the linked note, or re-point
  the link to the kept one), or those 121 go unmerged or ambiguous.
- **Except a rival that can't be the listed paper (TASK-126).** When a title group is refused but holds a
  listing, the clusters that can never be that listing's paper are set aside and the rest are judged again
  (`_merging`, `_not_the_listed_paper`): a non-listing cluster whose track the track rule below keeps from
  every listing in the group (a workshop note; a Creative AI note beside only a main-track listing, or a
  main-track note beside only a Creative AI one, TASK-137; never an `unknown` track) or whose status is
  `rejected`, `withdrawn` or `desk_rejected` (proceedings list only accepted papers).
  The rest merge if `_mergeable` lets them; the set-aside clusters stay separate records, each with a
  `conflicts.csv` row against the first listing: `track_not_merged` for the track, `ambiguous_not_merged`
  for the status. On the 2026-09-29 crawl this merged 201 listings whose title an accepted workshop paper
  shares (NeurIPS 2023-2025 main, D&B and position, ICLR 2024/2025) and the 11 NeurIPS 2021 D&B round-2
  papers whose rejected round-1 note shares the title. Its limits: a listing is never set aside, and a
  status or track of `unknown` stays a rival (it may be the listed paper, so two such candidates are still
  ambiguous), as does every other accepted submission: two accepted OpenReview notes with one listing
  still refuse. Status only breaks a rivalry: a lone rejected note still merges with its listing (the
  proceedings then decide its status, decision-005). A set-aside cluster never merges through a second
  key. A track one can't: a key's group with a listing sets it aside again, and one without refuses it on
  forum ids. A status
  one can, since `_mergeable` ignores status and a lone rejected note merges with its listing on another
  key; the chain re-check (the whole chained group, judged by `_mergeable`) then refuses it only because
  every non-listing record carries its own forum id (a record without one must name itself in a
  proceedings URL), which differs from the forum id of the note the listing merged with. The chain splits
  into its step-1 clusters: the pair is not merged either (the safe direction, never a merge).
- **Against the track rule** (`_family`, `_mergeable`), wherever a **proceedings listing** is involved (a
  cluster with a proceedings source *or* a proceedings id, so a RIS record with a `nips-`/`iclr-`/`pmlr-` id
  counts). Every cluster must be in one family: `proceedings` (`main`, `datasets_benchmarks`, `position`, i.e.
  `PROCEEDINGS_TRACKS`) or `creative_ai` (NeurIPS Creative AI, TASK-137), never both, never neither.
  Proceedings never host workshop papers, tiny papers, blogposts or competition entries. A non-listing record
  with track `unknown` also stays apart until evidence arrives (a `track_not_merged` row to review). The one
  exemption is a listing's *own* `unknown`: a PMLR volume that holds both main and position papers (v235,
  v267) can't say which track a paper is in, so it is `proceedings` family and merges with the OpenReview
  record, whose track wins by precedence. An `unknown` that an OpenReview track claim gives is never a listing's
  own, even in a cluster that is a listing only because a same-id RIS row, or the note itself, names a
  proceedings paper (TASK-174: the RIS row would otherwise bridge the note's `unknown` into the listing). A RIS
  row alone with track `unknown` and a proceedings URL is still a listing's own `unknown` (unchanged: RIS has
  only the listing's word for its track, and the listing's own track claim wins over RIS anyway).
  **Creative AI (TASK-137; decided by the owner, 2026-09-30).** A Creative AI listing merges with its own
  OpenReview note; other `other` tracks still never merge. The NeurIPS proceedings host Creative AI (2025: 64
  listings; 59 merge on the 2026-09-29 crawl, `docs/results/2026-09-30-creative-ai-merge.md`), which the taxonomy
  files under `other`. `other` also holds OpenReview forms no proceedings host (NeurIPS 2025
  `Education_Program`: 54 notes; `High_School_Projects_Track`, `Competition/LMC`, forms outside their year
  window, …), so `other` is **not** in `PROCEEDINGS_TRACKS` and reconcile never judges it. Instead a record is
  `creative_ai` (`dedup.is_creative_ai`) when it is NeurIPS, track `other`, and every source with a track claim
  claims `other` and backs it with Creative AI evidence of the record's year, all agreeing: a `venue_id_raw`
  claim that is `NeurIPS.cc/<Y>/Creative_AI_Track` bare or with a status suffix
  (`classify.is_creative_ai_venueid`), or a NeurIPS proceedings `urls.proceedings`/`urls.pdf` whose track token
  is `Creative_AI_Track`. So a Creative AI listing merges with its own Creative AI note (the paper's own note
  answers its track, decision-005; both say `other`, and the proceedings decide acceptance: OpenReview's bare
  Creative AI path is status `unknown`), and with nothing else: an `Education_Program` note, an `other` without
  that evidence, and a main-track note or listing all stay apart.
- **Every proceedings-id record names itself** in a kept `urls.proceedings`/`urls.pdf` claim (dedup
  refuses one that doesn't). Proceedings ids are read from those claims, so a merged record still carries
  the ids of the listings it absorbed, and a second run can't fold another listing in. URL forms,
  including NeurIPS up to 2021 (`/paper/<y>/hash/<h>-Abstract.html`, no track suffix) and upper-case hex,
  are parsed by `ingest/urls.py`. An `iclr_archive` proceedings claim is source-aware: its canonical target
  recomputes the OpenReview forum id or `iclr-<sha256(target)[:32]>`, so an arbitrary arXiv URL from another
  source cannot accidentally become ICLR identity evidence.

## Combining a merge
- The survivor's id uses the OpenReview forum id if any side has one (`.claude/skills/record-schema/SKILL.md`).
- The **union** of all claims is kept, one per (field, source). When one source claims a field twice
  (the same paper in both searches), the newest `fetched_at` wins and every other value that source gave,
  for any field, is a `newest:<source>` row; an exact fetch-time tie is a `tie:<source>` row (the kept
  value is then only a deterministic pick, by the value's exact JSON form, so a reviewer must look). For RIS the
  times are Publish or Perish query dates: UTC for entries `ris_offsets.toml` lists, local wall time otherwise
  (decision-025), so "newest" across a listed and an unlisted entry can be wrong within the offset. Superseded same-source claims are
  not kept in the record; merges.csv (`native_id`/`forum_id` rows) records that both inputs had the
  paper. Field values are re-resolved with the precedence table (`PRECEDENCE`, held as data), never
  "whichever record came first". So every input must already equal what its own claims resolve to;
  dedup refuses one that doesn't.
- A cross-source disagreement on `status`, `track` or the title **key** (decision-005: a title that
  differs only in case, punctuation or markup is no conflict) becomes a `precedence:<source>` row, and
  the winner comes from precedence. `venue` and `year` can't differ inside a merge: they're part of every
  merge key.
- **Track is decided per track** (decision-005 §Track in an OpenReview venue-year; the owner's decision,
  2026-09-29, TASK-130). Where OpenReview doesn't hold a venue-year's track, the proceedings decide it: ICLR
  2016 main comes from the archive and stays `main`. Within a track OpenReview holds, a paper whose listing
  merged with no OpenReview note takes its listing's track (the owner's second answer, 2026-09-29: NeurIPS 2025
  Creative AI, the renamed D&B papers, ICLR 2014's one unmerged archive paper). Where a note merged, its track
  wins. In code this is read per record, from the claims: an OpenReview track claim is the note's own
  `content.venueid` and wins (OpenReview first in `PRECEDENCE`); a record without one takes its listing's
  track. OpenReview claims no proceedings URL and the track rule keeps a note apart from every listing unless
  both are `proceedings` family or both are Creative AI. So where both answer, OpenReview's track is in
  `PROCEEDINGS_TRACKS`, or both say `other` on a Creative AI record (property
  `test_track_is_openreview_where_it_holds_the_paper_else_the_proceedings`).
- Iterate inputs in sorted-id order so the output doesn't depend on crawl order.

## Reconcile: acceptance the proceedings don't list (TASK-072, decision-005; `ingest/reconcile.py`)
After dedup, `op snapshot build` reconciles OpenReview acceptance against the crawled proceedings. Dedup can't:
it needs to know which listings were crawled, and whether completely.
- **Crawled** (`reconcile.crawled`, from the listing reports): a (proceedings source, venue, year) whose every
  listing is complete: it states a count (`stated`) and matched it (`count_ok`), every entry became a record (a
  repeated entry, `skipped.duplicate`, aside), and it names no volume left uncrawled (`see_also`). One incomplete
  listing and the whole venue-year is left alone (logged as `proceedings_reconcile_skipped`): a skipped entry or
  an unfollowed volume may hold the paper, and with no stated count nothing says the page showed every entry
  (NeurIPS 2021's D&B page states none, so NeurIPS 2021 is not judged).
- **Covered tracks**: `main`, `datasets_benchmarks` or `position` only, and only those the crawled listings'
  records hold: a listing's own track claim, or, for a listing that can't say (`unknown`: PMLR v235/v267 mix main
  and position papers), the track of the record it merged into. A track with no listing record (not published
  yet) is never judged.
- **Unlisted**: status won by an OpenReview `accepted` claim, in a covered venue-year and track, not a listing
  (no proceedings claim, no proceedings id), and sharing no title key and no forum id (own or linked) with any
  listing of the venue-year. A record that shares one but stayed apart may be the listed paper: it keeps its
  status, and dedup's not-merged row already names it (`shares_listing` in the log line).
- An unlisted record gains an **absence claim** per crawled source: `status=unknown` from that proceedings
  source, the listing that holds the track as `url`, that listing's index-page fetch as `fetched_at`
  (`ListingReport.fetched[0]`), evidence starting `not listed:` (`dedup.is_absence`; the prefix is reserved, see
  the record-schema skill). The proceedings outrank OpenReview for status, so `resolve` gives `unknown` and its
  `precedence:<source>` conflicts.csv rows, one per OpenReview source whose status claim differs; the OpenReview
  claims stay. An absence claim is **not a listing**: dedup leaves it out of a cluster's sources (and
  merges.csv's `sources`), so the record never looks listed and a second dedup changes nothing. Reconcile strips
  absence claims before it judges, so it is idempotent, and a claim a later crawl no longer supports disappears.
- Merges are never changed. Conflicts gain the reconciled records' status rows, and a reconciled record's
  earlier `precedence:` status rows give way to the ones its claims now resolve to, as dedup run again would
  write them: a note whose v2 said `accepted` and v1 `rejected` loses its v2-over-v1 row and has `unknown` over
  each instead, so every value it had is still named (TASK-154). No other row moves.
- Reconcile reads dedup's own rules, never copies: `dedup.PROCEEDINGS_SOURCES`, `dedup.PROCEEDINGS_TRACKS` and
  `dedup.is_listing`. Creative AI is not a covered track (`other` is not in `PROCEEDINGS_TRACKS`; TASK-137): an
  unlisted Creative AI note is never judged, and OpenReview gives its bare path status `unknown` anyway.
- **Known limit: a paper moved between years.** Reconcile compares within one venue-year, like dedup. A paper
  whose OpenReview note is in one year and whose listing is in another (a deferred camera-ready) is `unknown` in
  its OpenReview year, and its listing stays a separate record in the other year. No rule links them; a
  reviewer reading the `precedence:` row finds it by title.
- Reconcile never touches `track`; decision-005's track row is dedup's (§Combining a merge, per track).
- Properties (`backend/tests/unit/ingest/test_reconcile.py`): every reconciled record is what its claims
  resolve to; dedup on the output changes no record, merge or row; reconcile is idempotent; only unlisted
  OpenReview acceptances change, only to `unknown`, only by adding absence claims, only where a complete crawl
  covers the venue-year; rows only appear, except a changed record's superseded `precedence:` status rows, whose
  non-`unknown` values its new rows still name. The nightly counterexample that pinned that exception is an
  `@example` (TASK-154).

## Audit files (in the snapshot directory)
`merges.csv`: `survivor_id,merged_id,rule,key,venue,year,sources`, where `rule` is `forum_id`,
`native_id` (the same proceedings id), `forum_link`, `title_venue_year` or `abstract_venue_year`, and `key` is
the forum id, the native id, the linked forum id, the first shared title key or the abstract key
(`sha256:<16 hex>`; recompute it with `dedup.abstract_key` on either side's abstract). Step-1 rows point from a cluster's id to
itself (`survivor_id == merged_id`: one row per extra copy of that id); a `forum_link` row points from a
linked cluster's id (the PMLR listing) to the forum id's; a `title_venue_year` row then points from the
cluster id to the step-2 survivor, and an `abstract_venue_year` row from a step-2 cluster's id to the final
survivor. So every input id is an output id or a `merged_id`, once per copy, and
following the `forum_link`, `title_venue_year` and `abstract_venue_year` rows from any `merged_id` reaches an output record
(`snapshot.with_crawl_conflicts` follows them the same way).

`conflicts.csv`: `id,field,value_a,source_a,value_b,source_b,resolution`, where `resolution` is
`precedence:<source>` (the winner is `value_a`; a reconciled record's is `status`, `unknown` from the proceedings
source against each OpenReview status value), `newest:<source>` or `tie:<source>` (one source, two
values; the kept one is `value_a`), `ambiguous_not_merged`, `track_not_merged`,
`venue_year_not_merged`, or `unresolved:openreview_v1` (not dedup's: a v1 crawl found one note's own evidence
disagreeing, such as a withdrawn invitation and an accepted `content.venue`, or an accepted note whose pdf a
withdrawn note shares, decision-020; the record holds `unknown` for that
field, and `value_a`/`value_b` name each value with its evidence; `snapshot.with_crawl_conflicts` adds it). For the not-merged resolutions, `field` is `title_key`, `title_key_chain`, `abstract_key`,
`abstract_key_chain` (an imported record and the records sharing its abstract key that stayed apart, TASK-179),
`forum_id` (one forum id, own or linked, on records that stayed apart) or `forum_id_chain`, and the values
are the two record ids, with their sources (a set-aside rival's row is paired with the first listing of its
title group, TASK-126). Every row names an output record:
the not-merged rows are judged on the output records (every shared title key and forum id among records
that stayed apart), so a second run reports exactly the same rows; only `newest:`/`tie:` rows disappear,
because the merged record no longer holds the superseded claims.

Both files are sorted and deterministic. They're counted in `manifest.json` and reviewed by
`dedup-auditor` whenever dedup code or its inputs change.

## Property tests (`backend/tests/unit/ingest/test_dedup_props.py`, Hypothesis)
Pools collide on purpose (four titles, three forum ids, two proceedings papers per venue, every source,
track and status, tied fetch times, a `urls.forum` on a quarter of the records), plus a `chains` strategy
that builds the chain shape and a `links` strategy that builds the forum link's (a note and one or two
listings linking it or another forum, from its venue-year or another); `@example` rows pin the two
over-merges a review found and the link cases. Table tests from the recorded v235 and ICML 2024 note
fixtures: `test_dedup_forum_link.py`.
- An `abstract_venue_year` row (TASK-179; the `imports` strategy, and two long abstracts in every pool) joins
  clusters of one venue-year that both keep the row's abstract, in a group that held an imported record; a pool
  with no imported record has none.
- No output record combines inputs with different `(venue, year)`.
- Idempotent: `dedup(dedup(xs)).records == dedup(xs).records`, and the same conflict rows apart from
  `newest:`/`tie:`.
- Order-independent: `dedup(shuffle(xs)) == dedup(xs)`.
- Conservation: every input id is an output id or a `merged_id`, once per copy.
- A set-aside rival (TASK-126; the `rivals` strategy: a listing, its note, same-title workshop or
  not-accepted notes, sometimes a real rival) is never merged, has its `conflicts.csv` row, and blocks
  nothing: the listing and its note merge unless a real rival is present.
- Never folds two papers: distinct forum ids (own, or linked by a `urls.forum` claim), or distinct
  proceedings ids, never share a record, and a merge into a proceedings listing keeps a proceedings track, or
  `other` only where every input is Creative AI.
- A Creative AI listing merges with its own Creative AI note (TASK-137; the `creative` strategy: the listing,
  its RIS copy, its bare or rejected note, same-title `Education_Program`, evidence-less `other`, workshop and
  main-track notes, a second Creative AI note or a main-track listing) unless another candidate blocks it; every
  other-family record is set aside with its row, and only Creative AI inputs ever share its record.
