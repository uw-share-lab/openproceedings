---
name: dedup-rules
description: The deduplication standard for ingestion — the two-step merge order (identical forum id, then normalized title within the same venue and year), the hard never-merge rules including the venuetriage (title, "") no-year over-merge trap, how merged fields and claims combine, and the merges.csv / conflicts.csv audit formats and property tests. Use when writing or reviewing backend/src/openproceedings/ingest/dedup.py, reading merges.csv or conflicts.csv, or investigating a paper that vanished or doubled between snapshots.
---

# Dedup rules (spec 01 §Pipeline 4)

The same paper appears on OpenReview and in the proceedings (NeurIPS in every year, ICML 2023+), and
sometimes in the RIS import too. Dedup produces exactly one record per paper and never folds two papers
into one. **An over-merge is worse than a duplicate:** a duplicate shows up in the hit count, but an
over-merge silently deletes a paper from someone's systematic review.

## Merge order
1. **Identical OpenReview forum id** (case-sensitive), in any source. That includes a RIS record whose
   URL carries `?id=<forum>`.
2. **Same dedup title key, same `venue`, same `year`.** Build the key from the token-contract
   `normalize()` output joined by single spaces (`.claude/skills/token-contract/SKILL.md`), so dedup and
   search agree on what counts as the same title. Never write a second normaliser.

Step 2 only runs **across sources** (OpenReview ↔ proceedings ↔ RIS). Two OpenReview notes with different
forum ids are different submissions even when their titles match. For example, a main-track paper and a
same-year workshop version share a title, and both must survive.

## Never merge
- Across `venue` or `year`. The key is `(venue, year, title_key)`, and there's no fallback key.
- When `year` is missing. A record without a year never reaches dedup (it fails `PaperRecord`
  validation). This is the venuetriage lesson: a `(title, "")` key merged every year-less record that
  shared a title.
- When `title_key` is empty (a title of punctuation or math only).
- When the key matches **more than one** candidate on the other side. That's ambiguous: write a
  `conflicts.csv` row and keep them all separate.
- A proceedings record into an OpenReview record whose track is not one the proceedings list (`main`,
  `datasets_benchmarks`, `position`). Proceedings never host workshop papers.

## Combining a merge
- The survivor's id uses the OpenReview forum id if either side has one (`.claude/skills/record-schema/SKILL.md`).
- The **union** of all claims is kept. Field values are re-resolved with the precedence table, never
  "whichever record came first".
- A disagreement on `status`, `track` or `year` between merged sources becomes a `conflicts.csv` row, and
  the winner comes from precedence.
- Iterate inputs in sorted-id order so the output doesn't depend on crawl order.

## Audit files (in the snapshot directory)
`merges.csv`: `survivor_id,merged_id,rule,key,venue,year,sources`, where `rule` is `forum_id` or
`title_venue_year` and `key` is the forum id or the title key.

`conflicts.csv`: `id,field,value_a,source_a,value_b,source_b,resolution`, where `resolution` is
`precedence:<source>`, `ambiguous_not_merged`, or `unresolved`.

Both files are sorted and deterministic. They're counted in `manifest.json` and reviewed by
`dedup-auditor` whenever dedup code or its inputs change.

## Property tests (`backend/tests/unit/ingest/test_dedup_props.py`, Hypothesis)
- No output record combines inputs with different `(venue, year)`.
- Idempotent: `dedup(dedup(xs)) == dedup(xs)`.
- Order-independent: `dedup(shuffle(xs)) == dedup(xs)`.
- Conservation: every input id is either a survivor or appears as `merged_id` exactly once.
- Two OpenReview inputs with distinct forum ids are never merged.
