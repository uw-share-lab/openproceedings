---
id: decision-037
title: >-
  An imported record merges with a same-venue-year record on an identical
  abstract; two ris rows are not an ambiguity (TASK-179)
date: '2026-10-05 07:20'
status: accepted
---
## Context

Snapshot `2026-10-05-47d4e190ca81` held 7 accepted records that existed only because the Trust-Evals RIS import holds a second copy of a crawled ICLR paper, under its `proceedings.iclr.cc` id, that dedup did not merge with the paper's OpenReview note (TASK-178, TASK-179). They inflated accepted counts (ICLR 2026 main 5,354 instead of 5,351), counted a paper twice in the Scholar comparison and showed it twice in results. The causes, read from `merges.csv`, `conflicts.csv` and scholarmend's `resolved.json`:

- One (`op:iclr:2024:QHROe7Mfcb`) shares its title key with its copy and was refused `ambiguous_not_merged`: the note's cluster already held the RIS row of its forum id, the copy is a RIS row too, and the title step refuses two candidates from one source.
- Five lost a math symbol in the title (`$R^2$-Guard` → `-Guard`, `A$^2$Search` → `ASearch`, and τ, ∞ twice). The loss is Google Scholar's (`clean.ris:TI=-Guard…`), upstream of scholarmend and of the importer, so the title keys differ.
- One (`op:iclr:2026:CwoM9T55lG`) is in the import under the paper's earlier title.
- For the last six scholarmend holds no forum id, DOI or title claim, only the proceedings URL and that page's abstract. All seven copies have exactly their note's normalised abstract (158 to 338 tokens).

Options considered:
1. A looser title key that ignores math. Rejected: `A$^2$Search` and `ASearch` can be two papers, and nothing would tell them apart; it also would not find the retitled paper.
2. Abstract matching for every source. It merges the seven and one more pair on this crawl, NeurIPS 2023 D&B `3sRR2u72oQ` with its retitled crawled listing `nips-39736af1…`. A crawled listing's title is the publisher's own, so a difference there is a real retitle, and the merge changes a reconciled status; the owner deferred it.
3. Abstract matching only for import-only clusters, whose title is the one text that is not the publisher's.

## Decision

`ris` is a route, not a publisher: two candidates that share only the `ris` source are judged by the forum id and proceedings id their rows name, not refused as one source's two candidates. And an imported record (a cluster whose only source is `ris` after id, forum-link and title matching) merges with the one record of the same venue and year that keeps an abstract with the same abstract key, under every refusal of the title step. The owner limited abstract matching to import-only clusters (2026-10-05); extending it to crawled listings is deferred to a follow-up (TASK-187).

## Consequences

- `ingest/dedup.py` step 3 (`abstract_venue_year` in `merges.csv`). The abstract key is the SHA-256 of the title key's normalisation of the abstract, from 50 tokens; matching uses the whole digest, `merges.csv` shows 16 hex digits.
- Step 3's own refusals, beyond the title step's (two forum ids, two proceedings ids, the track rule, set-aside rivals):
  - the import's abstract counts only when scholarmend read it from the import's own page (`proceedings_page <url>` naming its proceedings id, or `openreview_api openreview:<forum>` on a forum-id row);
  - a group holds an imported record and at most one record that isn't one, so an abstract never joins two crawled records;
  - an import never merges with a record that is no listing and is rejected, withdrawn or desk-rejected, even a lone one: a note (the merged record would take OpenReview's status) or another import, a forum id's RIS row with no note crawled (both claims are `ris`, so the status would be whichever row was fetched last). Either way an accepted paper would leave accepted-only results. The title step holds the same rule (`_import_would_take_its_status`): such a record never merges on its title with imported records alone; a crawled listing, whose status outranks it, may still take a lone rejected note (decision-005).
- Refused groups and set-aside rivals are `conflicts.csv` rows with field `abstract_key` or `abstract_key_chain`, judged on the output records so every run writes the same rows. A record an import merged into (a listing holding a `ris` claim) is found again by every own-page abstract it keeps, not only its `ris` claim, which a newer RIS row of the note's forum id may have replaced. A pair a title key already reported gets no second, `abstract_key` row.
- On the 2026-10-05 cache: the 7 copies merge (1 `title_venue_year`, 6 `abstract_venue_year`), no other record's content changes, and RIS-only accepted records go from 7 to 0. `conflicts.csv` gains the survivors' title rows and 14 `abstract_key` `track_not_merged` rows, each a listing that keeps an imported abstract beside a different-track note (a workshop version) sharing it. Amended after review: each of those 14 pairs already had its `title_key` row, so the abstract row is no longer written; a rebuild of the same cache gives the same records and `merges.csv` (snapshot hash `10b5a205a63f…`) and 9,112 conflict rows instead of 9,126, those 14 alone removed. The status rule's widening to import-only records and to the title step, and the rows' anchoring on every own abstract, change nothing on this cache.
- No version changes: no tokenizer, index-schema or record-schema input moved. A new snapshot has a new `snapshot_hash`, so `index_version` changes with the rebuild as for any new snapshot; search records pinned to older indexes replay there.
- The dedup-auditor's check that a survivor absorbed at most one record per source now excepts `ris`; its Must list names the abstract rule's violations (`.claude/agents/dedup-auditor.md`). Spec 01 §Pipeline 4 and the `dedup-rules` skill state the rule. Tests: `test_dedup.py` (the seven shapes and each refusal) and `test_dedup_props.py` (the `imports` strategy and the abstract-merge property).
- The build normalises abstracts in every venue-year that holds an import-route abstract, which lengthens it: the build of this cache took 7 min 43 s with the rule, against about 7 minutes reported before it (not measured on the same machine load).
- Known limits: the title step still never consults the abstract, so an import titled `-Guard` beside a different note titled `Guard` would merge on the title (no real instance; TASK-189); and a crawled listing whose paper was retitled stays two records until the deferred follow-up (TASK-187).
- Revisit if scholarmend starts emitting a forum id or DOI for proceedings-page rows (an id would then decide), or if the import gains sources beyond Scholar.

