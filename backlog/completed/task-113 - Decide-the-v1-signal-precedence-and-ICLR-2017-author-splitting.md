---
id: TASK-113
title: Decide the v1 signal precedence and ICLR 2017 author splitting
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-27 22:46'
updated_date: '2026-09-30 02:23'
labels:
  - ingest
  - docs
milestone: m-4
dependencies: []
ordinal: 110000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-051 leaves a field unknown when two v1 signals disagree (e.g. a withdrawn invitation vs an accepting venue string), and leaves ICLR 2017 single-string authors empty. Decide whether one signal outranks another, and how to split the author strings once a real one is recorded. Also document the new unresolved conflict type in the manifest's conflict counts (spec 01/07).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A decision records the precedence (or that unknown stays),A decision or spec rule for ICLR 2017 authors,Spec 01/07 document the unresolved conflict type
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-29 (owner decision, same day): implemented and documented.
- decision-020 (status): v1 signals that disagree stay unknown, no ranking; also flags an accepted record whose pdf a withdrawn/desk-rejected record of the crawl shares (`openreview_v1.withdrawn_twins`, after the listings, before the duplicate collapse). Evidence: ICLR 2021 xGZG2kS5bFk withdrawn yet presented vs ICLR 2018 S1p31z-Ab (ELMo) accepted yet withdrawn as SJTCsqMUf and not presented. decision-019 (authors): count-checked split for every v1 year (`split_authors`, `author_count`); lists with no `and`-joined/`and `-prefixed entry are untouched; report gains `authors_split`, `authors_unsplit` now counts refusals; raw value kept in the authors claim's evidence. (decision-018 was taken by the TASK-063 branch: the unused 018 file I created was deleted uncommitted; these are 019 and 020.)
- `op eval coverage` now lists every `unresolved:*` conflicts.csv row by record id with the cell it would count in and whether it is gated (`load_unresolved` checks conflicts.csv against the manifest hash). Spec 01 §Pipeline 5 documents the manifest `conflicts` keys; spec 04 says `unresolved` is deliberately not in `dedup`; spec 07 §C the new report section; snapshots, openreview-api, dedup-rules, coverage-reporting skills updated.
- Fixtures: 8 trimmed from the 2026-09-29 crawl cache via scrub.py (which now keeps author separators and email-string counts, and trims a listing to `keep_ids`): ELMo blind/withdrawn/forum; author shapes S1HEBe_Jl, HkXKUTVFl, Hynn8SHOx, H1JBMVpdx, r1ISxGZRb, BJij4yg0Z, Hy3MvSlRW, HklCmaVtPS, RepN5K31PT3. Tests: twin table + order/idempotence; author table, report counts, split table, 3 Hypothesis properties (split count == id count; output re-split is listed unchanged; correct lists untouched); coverage report unresolved section, loader hash check, CLI end to end. test_combined_snapshot FILES_HASH re-recorded (manifest gained `authors_split`; SNAPSHOT_HASH unchanged).
- Real-data check (scratch snapshot 2026-09-29-9f3c65db8cf8, index 43141d9dec4d, cache symlinked): unresolved 2 (S1p31z-Ab, xGZG2kS5bFk); ICLR 2018 main 336/336 (was 337); ICLR 2021 main 859/860; authors split 34 (ICLR 2016 1, 2017 8, 2018 3, 2019 9, 2020 12, 2021 1), refused 1 (H1JBMVpdx, title in authors); records 95,938 unchanged, unknown status 863→864; `op eval coverage` M4 gate PASS, 43/44 within ±1% + ICLR 2013 accepted exception; the only report diffs are the ICLR 2018 row, its crawl's `conflicts 1`, the new unresolved section and the total.
- Possible follow-up (not in the owner's decision, not implemented): a Blind note with NO decision plus a withdrawn twin could be marked withdrawn, which would clear ICLR 2018's 12 such unknowns. Also observed and left as is: 10 ICLR 2018 blind notes rejected with a withdrawn twin keep `rejected` (decision-020 names only the accepting case). Per-paper overrides / an ICLR accepted-list source remain later work.

2026-09-29 review round 1 (all findings fixed):
- MUST: real author names and a profile id removed from the test, decision-019 and the learnings addendum (note id + shape instead, e.g. `S1HEBe_Jl`: "<name>, <name>"; `~and_<Name>1`); the diff outside the scrubbed fixtures was grepped for names, profile ids and emails: none left.
- Twin rule: only a withdrawn twin counts (desk_rejected dropped; possible follow-up: whether a desk-rejected twin should, none on the 2026-09-29 cache), and it must be in the same track; the conflict row names every twin. Tests: desk-rejected twin, another track, no pdf, arXiv link, two twins, order/idempotence.
- Coverage report: each unresolved row shows the record's track / status now and flags a field no longer unknown.
- Authors: a bare `and` entry and a dangling ` and` are dropped like a leading `and `; lowercase-only separators documented; decision-019 marks the implementer's guard and adds suffixes (`, Jr.`) to "Revisit if". Refused notes are listed in the crawl report as `authors_unsplit_ids` (only when any): on the 2026-09-29 cache, ICLR 2017 `H1JBMVpdx`.
- Real-data rerun: same snapshot 2026-09-29-9f3c65db8cf8 / index 43141d9dec4d; unresolved 2 (S1p31z-Ab, xGZG2kS5bFk, both main / unknown); ICLR 2018 main 336/336; ICLR 2021 main 859/860; authors split 34, refused 1; `op eval coverage` PASS (43/44 + ICLR 2013 exception).

Review round 2 (d0164ad): approved; implementation limits in decisions 019/020 are marked 'the implementer's, adopted after review; pending owner confirmation'; the unresolved table puts a dash in 'would count in' when the record is missing. split_authors('and', 0) counting as a split is left: harmless.
<!-- SECTION:NOTES:END -->
