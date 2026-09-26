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
| ICML position-paper track | `position` | per suffix | verify: whether it is its own path (e.g. `…/Position_Paper_Track`) or `Conference` + a `content.venue` label |
| `ICLR.cc/<Y>/TinyPapers` (2023–2024) | `tiny_papers` | `accepted` | verify spelling |
| `ICLR.cc/<Y>/BlogPosts` | `blogpost` | `accepted` | verify spelling |
| NeurIPS Competition Track path | `competition` | per suffix | verify |
| any other `<Org>.cc/<Y>/<rest>` that parses | `other` | per suffix | keep `venue_id_raw` |
| anything that does not match the grammar | `unknown` | `unknown` | log, show on coverage |

Rows marked **verify** must be checked against a live note (by forum id, authenticated) before they get a
fixture, and the checked forum id goes in the test's comment.

## Rules
1. **Workshop wins.** Any segment `Workshop` or `Workshop_<anything>` makes the track `workshop`, whatever
   follows. A workshop venueid must never classify as `main`: that is the failure this project exists to
   prevent (spec 07 §D target ≥99%).
2. **Suffix is status, not track.** Strip the trailing `*_Submission` / `Submission` to get the track
   path; map the suffix to status. Keep `venue_id_raw` verbatim either way.
3. **Venue and year from the venueid must agree with the crawl scope.** A note found while crawling
   ICLR 2024 whose venueid says `ICLR.cc/2023/…` is a conflict, never silently re-yeared.
4. **Aliases collapse to one track.** `Datasets_and_Benchmarks` and `Datasets_and_Benchmarks_Track`
   are the same track; count them once.
5. **Never default.** Unknown stays `unknown`; `other` is only for a form that parses but is not in the
   taxonomy. Neither is ever included by the default filter.
6. **Never from an invitation** (see `.claude/skills/openreview-api/SKILL.md`, `zkNCWtw2fd`).

## Table test
`backend/tests/unit/ingest/test_venueid.py` is a parametrised table: every validated venueid from
scholarmend's 90 cases plus one row per form above. Add a row for every new form seen in a crawl log;
never delete one.
