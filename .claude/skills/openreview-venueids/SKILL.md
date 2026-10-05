---
name: openreview-venueids
description: Every known OpenReview content.venueid form for NeurIPS, ICLR and ICML (main, Datasets & Benchmarks, workshops including satellite-city paths, position, Tiny Papers, Blogposts, and the Rejected/Withdrawn/Desk_Rejected submission suffixes) with the track and status each maps to, plus the parsing rules, which forms were verified live (2026-09-27) and why a v1 venueid never gives status. Use when writing or reviewing the venueid parser in backend/src/openproceedings/ingest/classify.py or its table test, or when a crawl logs an unparseable venueid.
---

# OpenReview venueid forms (spec 01 §Track taxonomy)

## Grammar
`<Org>.cc/<YYYY>/<rest>` where `<Org>` is `NeurIPS`, `ICLR` or `ICML`. The year is the conference year.
`<rest>` carries the track, and a trailing `…Submission` segment carries the status. OpenReview gives an
accepted paper the bare venue path and keeps a `Submission` suffix on everything else. Parse `<rest>`
**exactly**: match whole path segments against the table, never with `startswith` or `in`.

## The table (T = track, S = status)
Confidence: **validated** = scholarmend's 90 cases; **live** = checked against live notes on 2026-09-27
(TASK-002; ids, counts and fixtures in `docs/research/2026-09-27-openreview-and-proceedings-facts.md` and
`backend/tests/fixtures/http/openreview/`). **This table is for API v2 notes.** In v1 years (ICLR ≤2023,
NeurIPS 2021–2022) the bare venue path is on rejected papers too, so a v1 venueid never gives status
(`.claude/skills/openreview-api/SKILL.md` §API v1; TASK-095). The code enforces it: `classify_venueid` gives
status `unknown` for every venueid in a v1 venue-year (`classify.is_v1`: ICLR 2013–2023, NeurIPS 2021–2022),
and `classify_v1_venue` maps a v1 note's exact `content.venue` string to track and status.

| venueid form | T | S | Confidence |
|---|---|---|---|
| `<Org>.cc/<Y>/Conference` | `main` | `accepted` | validated; live (v2) |
| `<Org>.cc/<Y>/Conference/Rejected_Submission` | `main` | `rejected` | validated; live |
| `<Org>.cc/<Y>/Conference/Withdrawn_Submission` | `main` | `withdrawn` | validated; live |
| `<Org>.cc/<Y>/Conference/Desk_Rejected_Submission` | `main` | `desk_rejected` | live (ICLR 2024 `mnyXZBa5dP`; same spelling in every v2 group) |
| `<Org>.cc/<Y>/Conference/Submission` | `main` | `unknown` (under review or never decided) | live: every v2 group's `submission_venue_id`; no decided venue had a public note with it |
| `NeurIPS.cc/<Y>/Track/Datasets_and_Benchmarks` (2022 v1, 2023 v2) | `datasets_benchmarks` | `accepted` | live |
| `NeurIPS.cc/<Y>/Track/Datasets_and_Benchmarks_Track` | `datasets_benchmarks` | `accepted` | seen (scholarmend); not a live group |
| `NeurIPS.cc/<Y>/Datasets_and_Benchmarks_Track` (2024–2025, no `Track/`) | `datasets_benchmarks` | `accepted` | live |
| D&B path + `/Rejected_Submission` etc. | `datasets_benchmarks` | per suffix | live (2023: 16, 2024: 67, 2025: 94 rejected) |
| `NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round1`, `/Round2` (v1) | `datasets_benchmarks` | **not from the venueid**: 78 of Round 1's 144 are rejected (`venue = Submitted to …`) | live (`iBLHqLgbRn`) |
| `NeurIPS.cc/2026/Evaluations_and_Datasets_Track` | `datasets_benchmarks` | per suffix | live group (2026 rename of D&B), no notes yet; TASK-094 |
| `<Org>.cc/<Y>/Workshop/<name>` | `workshop` | `accepted` | validated; live |
| `<Org>.cc/<Y>/Workshop_<City>/<name>` (e.g. `NeurIPS.cc/2025/Workshop_Mexico_City/ResponsibleFM`) | `workshop` | `accepted` | validated; live |
| `<Org>.cc/<Y>/Workshop/<name>/Rejected_Submission` (and the other suffixes) | `workshop` | per suffix | live (`ICLR.cc/2025/Workshop/ICBINB/Rejected_Submission`); 2026 crawl (TASK-178): ICLR 71 rejected, 6 withdrawn (`1lNr7gL71D`), ICML 5 rejected |
| `<Org>.cc/<Y>/Workshop/<name>/Submission` | `workshop` | `unknown` | live on notes: 11 undecided workshop submissions were public in the 2026 crawl (ICLR `LMRL` 1, `KadCjvcLOz`; ICML `CTB` 3, `GenBio` 3, `Mech_Interp` 2, `NExT-Game` 2, `xFNDnnuTSf`; fixture `icml-2026/notes-workshop-submission.json`) |
| `ICML.cc/<Y>/Position_Paper_Track` (2025+) | `position` | per suffix | live (2025: 73; 2026: 213 accepted, 28 opt-in rejected, `thf3e0Ptbf`) |
| `NeurIPS.cc/<Y>/Position_Paper_Track` (2025+) | `position` | per suffix | live (2025: 40 accepted, 55 rejected; `VZnOKzQ5qW`); TASK-094 |
| ICML 2024 position papers | carry `ICML.cc/2024/Conference`, no marker | – | live: indistinguishable from main on OpenReview |
| `ICLR.cc/<Y>/TinyPapers` (2023 v1, 2024 v2) | `tiny_papers` | `accepted` in v2 only (2023's 219 v1 notes all say `Submitted to Tiny Papers @ ICLR 2023`) | live |
| `ICLR.cc/<Y>/BlogPosts` (2023 v1, 2024+ v2) | `blogpost` | `accepted` in v2 only | live (spelling `BlogPosts`) |
| `NeurIPS.cc/<Y>/Competition_Track` (2024+) | `competition` | per suffix | live (2024: 16; `LYvWVFdGZN`); TASK-094 |
| `NeurIPS.cc/<Y>/Creative_AI_Track` | `other` | per suffix, else `unknown` | live (2025: 92; 2026: 95); `classify.is_creative_ai_venueid` names it for dedup's track rule (TASK-137) |
| `ICLR.cc/2017/conference`, `ICLR.cc/2013/conference` (v1, lower case) | `other` (2017 puts it on workshop invitations too; track comes from `content.venue`: in the v1 crawler by its `_NOT_A_TRACK` rule, in the RIS importer only for the exact venueids in `classify.V1_TRACK_FROM_VENUE`, TASK-142). TASK-152: a note on the 2017 **workshop** listing whose string names the main track (`Submitted to ICLR 2017`, 18 notes) is a copy of a rejected conference paper (its `_bibtex` names the conference twin), so the string is the twin's outcome: the crawler gives it the listing's track, `workshop`, and status `unknown` (nothing states the workshop decision; the report's `twin_outcome`), not `main`/`rejected`, which double-counted those rejections. Only where the venueid names no track: one naming a track is checked against the string as before. The RIS importer reads scholarmend 0.1.5's `invitation` claim through the same rule (`openreview_v1.is_twin_outcome`, TASK-157), so a copy imports as `workshop`/`unknown` too; an entry cached before 0.1.5 has no claim and still reads `main`/`rejected`, which the crawl's record outranks once merged by forum id (decision-005). TASK-159 (decision-029): the copies stay records, linked to their conference twins by a `twin` claim (53 copies, 18 by `_bibtex` and title, 35 by title alone; the `Invite to Workshop` copies' `_bibtex` all name one unrelated forum) | never from the venueid | live; only 2017 notes carry it |
| any other `<Org>.cc/<Y>/<rest>` that parses (seen: `High_School_Projects_Track`, `Education_Program`, `Education_Track`, `Competition/LMC`, `Challenge/CellSeg`) | `other` | a mapped suffix's status, else `unknown` (a bare path means `accepted` only for a form in this table) | keep `venue_id_raw` |
| `<Org>.cc/<Y>/Workshop/<name>` whose name looks like a status (`Rejected`, `Data_Submission`) | `workshop` | `accepted` (the segment after `Workshop` is always the name) | rule |
| anything that does not match the grammar | `unknown` | `unknown` | log, show on coverage |

Workshop names contain hyphens and digits (`SCI-FM`, `CLRLC-LLMs`, `7HVU`, `NExT-Game`), and a name can end in
`_Track` (`ICLR.cc/2026/Workshop/ML4RS_Main_Track`, 42 notes): rule 1 still makes it a workshop. A new form gets a live check
(by forum id, authenticated), a recorded fixture, and a table-test row citing the checked id.

## Rules
1. **Workshop wins.** Any segment `Workshop` or `Workshop_<anything>` makes the track `workshop`, whatever
   follows. A workshop venueid must never classify as `main`: that is the failure this project exists to
   prevent (spec 07 §D target ≥99%).
2. **Suffix is status, not track.** Strip a trailing `Submission`, `Rejected_Submission`,
   `Withdrawn_Submission` or `Desk_Rejected_Submission` and map it to status; any other status-like last
   segment (`Blind_Submission`, `Rejected_Submissions`, `Withdrawn`, `Desk_Rejected`, `Post_Decision`) is
   stripped with status `unknown`, never `accepted` (status words match in any case). A suffix needs a
   track in front of it, and the segment right after a `Workshop*` segment is the workshop's name, never a
   status. A bare path is `accepted` only for a form in the table; `other` is `unknown`. A `-` segment
   (an invitation path) or a year outside 2013–2099 doesn't parse. Keep `venue_id_raw` verbatim.
3. **Venue and year from the venueid must agree with the crawl scope.** A note found while crawling
   ICLR 2024 whose venueid says `ICLR.cc/2023/…` is a conflict, never silently re-yeared.
4. **Aliases collapse to one track.** `Datasets_and_Benchmarks` and `Datasets_and_Benchmarks_Track`
   are the same track; count them once.
5. **Never default.** Unknown stays `unknown`; `other` is only for a form that parses but is not in the
   taxonomy. Neither is ever included by the default filter.
6. **Never from an invitation** (see `.claude/skills/openreview-api/SKILL.md`, `zkNCWtw2fd`).

The code (`classify.py` `_TRACKS`) matches each track path as an **exact tuple per organisation and verified
year range**: only the rows above reach a default-filter track in the years shown. In particular D&B's
`Track/...` forms cover 2022–2024, its no-`Track` form 2024–2025, `Evaluations_and_Datasets_Track` 2026+,
`Competition_Track` 2024+, and both position-paper forms 2025+. A different order, another organisation's
track, an unseen spelling, or the right spelling in an adjacent unsupported year is `other`. Aliases and
years not in the table are not accepted.

## Table test
Code: `backend/src/openproceedings/ingest/classify.py` (`classify_venueid`, `classify_proceedings`).
`backend/tests/unit/ingest/test_venueid.py` is a parametrised table: every validated venueid from
scholarmend's 90 cases plus one row per form above (`LIVE` for the 2026-09-27 forms). It also reads every
recorded OpenReview note under `backend/tests/fixtures/http/openreview/` (`V2_NOTES`, `V1_NOTES`): a v2
note's venueid gives its track and status; a v1 note's venueid gives `unknown` status and its
`content.venue` decides. A newly recorded note fixture fails `test_every_recorded_note_has_a_row` until
it gets a row. Add a row for every new form seen in a crawl log;
never delete one.
