---
id: decision-019
title: >-
  OpenReview v1 authors are split only when the piece count matches the author
  ids (TASK-113)
date: '2026-09-30 00:52'
status: accepted
---
## Context

OpenReview API v1 writes `content.authors` in shapes that TASK-051 could not read reliably. Early ICLR 2017 notes
give one string (`S1J0E-71l`: `"<name>"`; `S1HEBe_Jl`: `"<name>, <name>"`), and TASK-051 left
those records with no authors (`authors_unsplit`), never split by guess. The 2026-09-29 crawl also has 33
list-typed notes (ICLR 2016–2021) whose list is wrongly split: a last entry starting with `and ` (`r1ISxGZRb`
last entry `"and <name>"`, `HkXKUTVFl`), or two names joined in one entry (`BJij4yg0Z`
`["<name> and <name>"]`, `Hynn8SHOx`). Those were indexed as written: `and <name>` as an author, two people as
one. And `H1JBMVpdx` (ICLR 2017) has its title in `authors`
(`Decoupled "what" and "where" … and equivalent multi-stream network`), which a naive split on ` and ` turns into
"authors".

What makes a split checkable: v1 notes carry `authorids` (one per author), or for early ICLR 2017 an
`author_emails` string. 115 other list-typed notes have fewer or more ids than names but no `and` problem;
their lists are right as far as anyone can tell (ids are often only the corresponding authors).

Options considered:
- (a) Keep refusing every string and index lists as written: loses the two 2017 author lists and keeps 33 wrong
  ones.
- (b) Split on `,` and ` and ` whenever it looks joined, unchecked: turns `H1JBMVpdx`'s title into three authors.
- (c) Split by a fixed rule, and accept it only when the number of names equals the note's id count; refuse
  otherwise and say so.

## Decision

The project owner decided (2026-09-29): for every v1 year, `content.authors` is split by a count-checked rule. A
list with no entry starting with `and ` and none joining names with ` and ` is kept as listed, whatever its
length. Otherwise each entry (the one string, or each list entry) loses a leading `and ` and is split at `, and `,
`,` and ` and `; the split is accepted only if it gives exactly `len(authorids)` names (or the `author_emails`
count when there are no ids). A refused split leaves the authors empty and is counted in `authors_unsplit`; the
raw value stays in the authors claim's evidence either way.

Implementation details (the implementer's, adopted after review; pending owner confirmation): a split is also refused when a
resulting name still needs a split (a guard that keeps a split's output stable when taken again); a bare `and`
entry and a dangling trailing ` and` are dropped like a leading `and ` (`["A", "B", "and"]` is `A`, `B`); only
lowercase `and` is a separator (`And`/`AND` are left as written: every `and` seen live is lowercase); and the
refused notes' ids are listed in the crawl report (`authors_unsplit_ids`, present only when there are any).

## Consequences

- `openreview_v1.split_authors` / `author_count`; the crawl report and manifest gain `authors_split` next to
  `authors_unsplit` (now: refusals) and, when there are any, `authors_unsplit_ids`. On the 2026-09-29 cache the rule splits both 2017 strings and all 33 lists,
  and refuses one note, `H1JBMVpdx` (three pieces for two ids), which is kept out rather than indexed. Correct
  lists are untouched, and a split's output taken again is untouched (a property test holds both).
- Authors are display fields outside `content_hash` (record-schema), so no record's content hash changes; but
  `records.jsonl` changes, so the next snapshot's `snapshot_hash` and `index_version` do. Search membership is
  unchanged: authors are displayed and exported (RIS, BibTeX), never searched.
- Fixtures: `scrub.py` now keeps an authors value's separators and an email string's count, so the recorded
  shapes can be tested with synthetic names.
- Spec 01 §Sources (v1 as-built), the openreview-api and snapshots skills say so. Revisit if a v1 year appears
  whose names contain a lowercase ` and ` (none seen), whose names carry comma-separated suffixes (`<name>, Jr.`
  would split into two pieces and be refused, or mis-split if the count happens to match), whose separators are
  capitalised, or whose ids don't count authors.

