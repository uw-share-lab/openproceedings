---
name: dedup-rules
description: The deduplication standard for ingestion — the merge order (identical id, then the OpenReview forum link a PMLR listing carries, then normalized title within the same venue and year), the hard never-merge rules including the venuetriage (title, "") no-year over-merge trap, how merged fields and claims combine, and the merges.csv / conflicts.csv audit formats and property tests. Use when writing or reviewing backend/src/openproceedings/ingest/dedup.py, reading merges.csv or conflicts.csv, or investigating a paper that vanished or doubled between snapshots.
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
   `id`). PMLR's index links each paper's forum from ICML 2023 (v202 per the research notes; only v235 is
   recorded in `backend/tests/fixtures/http/pmlr/`, and v28 has no link). Clusters that share a forum id
   in the same venue and year merge **whatever their titles say**, before any title match. The link is
   refused (a `conflicts.csv` row with `field = forum_id`, never a merge) when the forum id's records are
   in different venue-years (`venue_year_not_merged`), when the group would hold two forum ids or two
   proceedings ids, such as two listings linking one forum (`ambiguous_not_merged`), or when the track
   rule below fails (`track_not_merged`, e.g. a workshop note linked from a proceedings volume). One
   source on both sides doesn't block a link: the id, not the title, says which paper it is.
2. **Same dedup title key, same `venue`, same `year`.** Build the key from the token-contract
   `normalize()` output joined by single spaces (`.claude/skills/token-contract/SKILL.md`), so dedup and
   search agree on what counts as the same title. Never write a second normaliser.

Step 2 only runs **across sources**: the clusters' provenance source sets must be disjoint
(OpenReview ↔ proceedings ↔ RIS). Two OpenReview notes with different forum ids are different submissions
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
- When the key matches **more than one** candidate from one source, two different forum ids (own or
  linked: a PMLR listing whose link names forum Y never title-merges with note X), or two
  different proceedings papers (proceedings ids come from native ids *and* `urls.proceedings`/`urls.pdf`
  claims, `ingest/urls.py`). That's ambiguous: write a `conflicts.csv` row and keep them all separate.
  The same holds when two keys chain clusters that must not share a record: every cluster in the chain
  stays separate (`field = title_key_chain`).
- A paper whose track the proceedings don't host (anything but `main`, `datasets_benchmarks`,
  `position`) into a **proceedings listing**: a cluster with a proceedings source *or* a proceedings id,
  so a RIS record with a `nips-`/`iclr-`/`pmlr-` id counts. Proceedings never host workshop papers. A
  non-listing record with track `unknown` also stays apart until evidence arrives; once the crawlers land
  (M4) such duplicates show up as `track_not_merged` rows to review. The one exemption is a listing's
  *own* `unknown`: a PMLR volume that holds both main and position papers (v235, v267) can't say which
  track a paper is in, so it merges with the OpenReview record, whose track wins by precedence.
- **Every proceedings-id record names itself** in a kept `urls.proceedings`/`urls.pdf` claim (dedup
  refuses one that doesn't). Proceedings ids are read from those claims, so a merged record still carries
  the ids of the listings it absorbed, and a second run can't fold another listing in. URL forms,
  including NeurIPS up to 2021 (`/paper/<y>/hash/<h>-Abstract.html`, no track suffix) and upper-case hex,
  are parsed by `ingest/urls.py`.

## Combining a merge
- The survivor's id uses the OpenReview forum id if any side has one (`.claude/skills/record-schema/SKILL.md`).
- The **union** of all claims is kept, one per (field, source). When one source claims a field twice
  (the same paper in both searches), the newest `fetched_at` wins and every other value that source gave,
  for any field, is a `newest:<source>` row; an exact fetch-time tie is a `tie:<source>` row (the kept
  value is then only a deterministic pick, by the value's exact JSON form, so a reviewer must look). Superseded same-source claims are
  not kept in the record; merges.csv (`native_id`/`forum_id` rows) records that both inputs had the
  paper. Field values are re-resolved with the precedence table (`PRECEDENCE`, held as data), never
  "whichever record came first". So every input must already equal what its own claims resolve to;
  dedup refuses one that doesn't.
- A cross-source disagreement on `status`, `track` or the title **key** (decision-005: a title that
  differs only in case, punctuation or markup is no conflict) becomes a `precedence:<source>` row, and
  the winner comes from precedence. `venue` and `year` can't differ inside a merge: they're part of every
  merge key.
- Iterate inputs in sorted-id order so the output doesn't depend on crawl order.

## Audit files (in the snapshot directory)
`merges.csv`: `survivor_id,merged_id,rule,key,venue,year,sources`, where `rule` is `forum_id`,
`native_id` (the same proceedings id), `forum_link` or `title_venue_year`, and `key` is the forum id, the
native id, the linked forum id or the first shared title key. Step-1 rows point from a cluster's id to
itself (`survivor_id == merged_id`: one row per extra copy of that id); a `forum_link` row points from a
linked cluster's id (the PMLR listing) to the forum id's; a `title_venue_year` row then points from the
cluster id to the final survivor. So every input id is an output id or a `merged_id`, once per copy, and
following the `forum_link` and `title_venue_year` rows from any `merged_id` reaches an output record
(`snapshot.with_crawl_conflicts` follows them the same way).

`conflicts.csv`: `id,field,value_a,source_a,value_b,source_b,resolution`, where `resolution` is
`precedence:<source>` (the winner is `value_a`), `newest:<source>` or `tie:<source>` (one source, two
values; the kept one is `value_a`), `ambiguous_not_merged`, `track_not_merged`,
`venue_year_not_merged`, or `unresolved:openreview_v1` (not dedup's: a v1 crawl found one note's own evidence
disagreeing, such as a withdrawn invitation and an accepted `content.venue`; the record holds `unknown` for that
field, and `value_a`/`value_b` name each value with its evidence; `snapshot.with_crawl_conflicts` adds it). For the not-merged resolutions, `field` is `title_key`, `title_key_chain`,
`forum_id` (one forum id, own or linked, on records that stayed apart) or `forum_id_chain`, and the values
are the two record ids, with their sources. Every row names an output record:
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
- No output record combines inputs with different `(venue, year)`.
- Idempotent: `dedup(dedup(xs)).records == dedup(xs).records`, and the same conflict rows apart from
  `newest:`/`tie:`.
- Order-independent: `dedup(shuffle(xs)) == dedup(xs)`.
- Conservation: every input id is an output id or a `merged_id`, once per copy.
- Never folds two papers: distinct forum ids (own, or linked by a `urls.forum` claim), or distinct
  proceedings ids, never share a record, and a merge into a proceedings listing keeps a proceedings track.
