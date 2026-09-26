---
name: openreview-venueids
description: Every known OpenReview content.venueid form for NeurIPS, ICLR and ICML (main, Datasets & Benchmarks, workshops including satellite-city paths, position, Tiny Papers, Blogposts, and the Rejected/Withdrawn/Desk_Rejected submission suffixes) with the track and status each maps to, plus the parsing rules and which forms still need verifying. Use when writing or reviewing the venueid parser in backend/src/openproceedings/ingest/classify.py or its table test, or when a crawl logs an unparseable venueid.
---

# OpenReview venueid forms (spec 01 §Track taxonomy)

## Grammar
`<Org>.cc/<YYYY>/<rest>` where `<Org>` is `NeurIPS`, `ICLR` or `ICML`. The year is the conference year.
`<rest>` carries the track, and a trailing `…Submission` segment carries the status. OpenReview gives an
accepted paper the bare venue path and keeps a `Submission` suffix on everything else. Parse `<rest>`
**exactly**: match whole path segments against the table, never with `startswith` or `in`.

## The table (T = track, S = status)
| venueid form | T | S | Confidence |
|---|---|---|---|
| `<Org>.cc/<Y>/Conference` | `main` | `accepted` | validated (scholarmend, 90/90 cases) |
| `<Org>.cc/<Y>/Conference/Rejected_Submission` | `main` | `rejected` | validated |
| `<Org>.cc/<Y>/Conference/Withdrawn_Submission` | `main` | `withdrawn` | validated |
| `<Org>.cc/<Y>/Conference/Desk_Rejected_Submission` | `main` | `desk_rejected` | verify exact spelling per year |
| `<Org>.cc/<Y>/Conference/Submission` | `main` | `unknown` (under review or never decided) | verify |
| `NeurIPS.cc/<Y>/Track/Datasets_and_Benchmarks` | `datasets_benchmarks` | `accepted` | seen |
| `NeurIPS.cc/<Y>/Track/Datasets_and_Benchmarks_Track` | `datasets_benchmarks` | `accepted` | seen |
| `NeurIPS.cc/<Y>/Datasets_and_Benchmarks_Track` (no `Track/`) | `datasets_benchmarks` | `accepted` | verify (2024+) |
| D&B path + `/Rejected_Submission` etc. | `datasets_benchmarks` | per suffix | verify |
| `NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round1`, `/Round2` | `datasets_benchmarks` | `accepted` | verify |
| `<Org>.cc/<Y>/Workshop/<name>` | `workshop` | `accepted` | validated |
| `<Org>.cc/<Y>/Workshop_<City>/<name>` (e.g. `NeurIPS.cc/2025/Workshop_Mexico_City/ResponsibleFM`) | `workshop` | `accepted` | validated |
| `<Org>.cc/<Y>/Workshop/<name>/Submission` or `/Rejected_Submission` | `workshop` | per suffix | verify |
| `ICML.cc/<Y>/Position_Paper_Track` | `position` | per suffix | seen (Trust-Evals gold venueids, 2026-09-26) |
| `ICLR.cc/<Y>/TinyPapers` (2023–2024) | `tiny_papers` | `accepted` | verify spelling |
| `ICLR.cc/<Y>/BlogPosts` | `blogpost` | `accepted` | verify spelling |
| NeurIPS Competition Track path | `competition` | per suffix | verify |
| `NeurIPS.cc/<Y>/Track/Creative_AI` | `other` | per suffix | verify (only the proceedings token `Creative_AI_Track` has been seen) |
| any other `<Org>.cc/<Y>/<rest>` that parses | `other` | per suffix | keep `venue_id_raw` |
| anything that does not match the grammar | `unknown` | `unknown` | log, show on coverage |

Rows marked **verify** must be checked against a live note (by forum id, authenticated) before they get a
fixture, and the checked forum id goes in the test's comment.

## Rules
1. **Workshop wins.** Any segment `Workshop` or `Workshop_<anything>` makes the track `workshop`, whatever
   follows. A workshop venueid must never classify as `main`: that is the failure this project exists to
   prevent (spec 07 §D target ≥99%).
2. **Suffix is status, not track.** Strip a trailing `Submission`, `Rejected_Submission`,
   `Withdrawn_Submission` or `Desk_Rejected_Submission` and map it to status; any other status-like last
   segment (`Blind_Submission`, `Rejected_Submissions`, `Withdrawn`, `Desk_Rejected`, `Post_Decision`) is
   stripped with status `unknown`, never `accepted`. A suffix needs a track in front of it; a `-` segment
   (an invitation path) or a year outside 2013–2099 doesn't parse. Keep `venue_id_raw` verbatim.
3. **Venue and year from the venueid must agree with the crawl scope.** A note found while crawling
   ICLR 2024 whose venueid says `ICLR.cc/2023/…` is a conflict, never silently re-yeared.
4. **Aliases collapse to one track.** `Datasets_and_Benchmarks` and `Datasets_and_Benchmarks_Track`
   are the same track; count them once.
5. **Never default.** Unknown stays `unknown`; `other` is only for a form that parses but is not in the
   taxonomy. Neither is ever included by the default filter.
6. **Never from an invitation** (see `.claude/skills/openreview-api/SKILL.md`, `zkNCWtw2fd`).

The code (`classify.py` `_TRACKS`) matches each track path as an **exact tuple per organisation**: only
the rows above reach a default-filter track, and any other path that parses (a different order, another
organisation's track, an unseen spelling) is `other`. Aliases not in the table are not accepted.

## Table test
Code: `backend/src/openproceedings/ingest/classify.py` (`classify_venueid`, `classify_proceedings`).
`backend/tests/unit/ingest/test_venueid.py` is a parametrised table: every validated venueid from
scholarmend's 90 cases plus one row per form above. Add a row for every new form seen in a crawl log;
never delete one.
