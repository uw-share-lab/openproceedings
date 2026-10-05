---
id: TASK-179
title: >-
  Dedup: an imported RIS copy whose title lost a math symbol, or that shares a
  ris claim, is not merged with its crawled paper
status: Done
assignee: []
created_date: '2026-10-05 05:12'
updated_date: '2026-10-05 08:38'
labels:
  - ingest
  - dedup
milestone: m-4
dependencies: []
references:
  - docs/specs/01-ingestion.md
ordinal: 123000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-178 on snapshot 2026-10-05-47d4e190ca81: 7 accepted records exist only because the Trust-Evals RIS import holds a second copy of a crawled paper that dedup did not merge. Five differ from the crawled title only by a lost math symbol (tau-bench, R2-Guard, Adapt-infinity, RobotArena infinity, A2Search: op:iclr:2025:iclr-1b126cc3… = roNSXZpUDN, iclr-a07e87ec… = CkgKSqZbuC, iclr-a6610efd… = EwFJaXVePU; op:iclr:2026:iclr-2aa3da3c… = OutljIofvS, iclr-dcbdb995… = 3CPzUWIoNf), one has the same title key as its twin but both records hold a ris claim (op:iclr:2024:iclr-c3eb94d1… = QHROe7Mfcb), and one is probably the same paper under an earlier title (op:iclr:2026:iclr-6b41e04c…, perhaps CwoM9T55lG; unconfirmed). They inflate accepted counts (ICLR 2026 main 5,354 instead of 5,351), count a paper twice in the Scholar comparison, and show a paper twice in results.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each of the six confirmed pairs merges into one record under a rule stated in spec 01 and the dedup-rules skill, with merges.csv naming the rule; no never-merge rule is weakened (title alone across venue or year still never merges)
- [x] #2 The retitled seventh case is either merged on evidence the rule can state or left separate and listed as a known duplicate with its reason
- [x] #3 Property and table tests cover a title differing only by a lost math symbol, and two records that each hold a ris claim; the dedup invariants still hold
- [x] #4 A snapshot rebuilt from the same cache shows only these merges as differences from 2026-10-05-47d4e190ca81 (op snapshot diff reviewed), and RIS-only accepted records are 0 or each is explained
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Real causes (snapshot 2026-10-05-47d4e190ca81, merges.csv, conflicts.csv, resolved.json). (1) op:iclr:2024:QHROe7Mfcb and its iclr-c3eb94d1 copy share a title key; the title step refused them as ambiguous_not_merged because the note's cluster already held the RIS row of its forum id and the copy is a RIS row too (two candidates from one source). (2) The five lost-symbol copies and the seventh never met their notes: no shared title key, no conflicts row. The titles are Google Scholar's (resolved.json: clean.ris:TI=-Guard…, {}-bench…), so the math was dropped upstream of scholarmend and of our importer; title_key keeps the symbol where the crawled title has it (r2 guard, tau bench, a 2 search, infty). scholarmend holds no forum id, DOI or title claim for them, only the proceedings.iclr.cc url and that page's abstract. (3) All seven copies have exactly the abstract key of their note (158 to 338 tokens), including iclr-6b41e04c = CwoM9T55lG, which is the same paper under its earlier title (same abstract, same first authors). Rules built: ris is a route, so sharing only ris is no ambiguity (the forum-id and proceedings-id checks judge two RIS rows); and step 3, an imported record (sources ris alone after the title step) merges on (venue, year, abstract key) with the abstract of at least 50 tokens, rule abstract_venue_year, under every refusal of the title step. Rejected: a title key that ignores math (A2Search/ASearch could be two papers), and an abstract rule for every source (it would also merge NeurIPS 2023 D&B 3sRR2u72oQ with its retitled listing nips-39736af1: one more real pair, left for an owner decision). Scratch rebuild from the same cache (2026-10-05-10b5a205a63f, outside the repo): op snapshot diff shows removed 7 (the copies), added 4 (TASK-180), changed 0, display_only 7 (the survivors' urls); merges +7 (1 title_venue_year, 6 abstract_venue_year); conflicts 9,105 to 9,112; RIS-only accepted records 0.

Review fixes (2026-10-05): the import's abstract counts only from its own page; a group holds at most one record that isn't imported; never into a rejected, withdrawn or desk-rejected note; matching on the whole digest; set-aside rivals get their abstract_key row on the output records. Second scratch rebuild: the same snapshot hash as the first (10b5a205a63f), so the same 7 merges and 4 additions and no other record changed; conflicts.csv 9,126 (14 new abstract_key track_not_merged rows: a listing keeping an imported abstract beside a different-track note sharing it). decision-037.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Two dedup changes (spec 01, decision-037): sharing only the ris source is no ambiguity, and a cluster whose only source is ris after the id and title steps merges with the one same-venue-year crawled record that has its abstract (full normalised key, at least 50 tokens), only when the import's abstract claim cites its own proceedings page or forum, never into a rejected, withdrawn or desk-rejected record, never joining two crawled records; refusals and set-aside rivals are conflicts.csv rows. On the real cache the 7 imported second copies merge (1 by title, 6 by abstract; five had lost a math symbol in Google Scholar, one was retitled) and RIS-only accepted records go from 7 to 0, with no other record changed. One review round: no Must, 7 Shoulds, fixed. Abstract matching for crawled listings is deferred to a follow-up.
<!-- SECTION:FINAL_SUMMARY:END -->
