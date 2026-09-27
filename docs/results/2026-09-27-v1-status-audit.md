# API v1 venueid status audit of the RIS corpus (TASK-095 AC#2), 2026-09-27

**Result: no record in the M2 corpus took its status or track from an API v1 venueid.** Nothing in the
snapshot is a rejected v1 paper marked accepted, and re-ingesting with the TASK-094/095 classifier gives a
byte-identical snapshot.

## The question
OpenReview API v1 gives the bare venue path to rejected submissions as well as accepted ones: ICLR 2017
(`ICLR.cc/2017/conference`), ICLR 2022 and 2023, NeurIPS 2021–2022 and NeurIPS 2021 D&B
(`…/Round1`, `…/Round2`), plus ICLR 2023 Tiny Papers and Blogposts
(`docs/research/2026-09-27-openreview-and-proceedings-facts.md` §How status is represented). Before
TASK-095, `classify_venueid("ICLR.cc/2022/Conference")` returned `main`/`accepted`. The RIS importer
accepts scholarmend's venueid claims as given, so a rejected ICLR 2022/2023 paper could have entered
the M2 corpus as accepted.

## What was checked (read-only)
- **Snapshot** `data/snapshots/2026-09-23-d5ab3d6d444a` (1,805 records; `snapshot_hash`
  `d5ab3d6d…9bc4`). For every record, the `status` and `track` provenance claims and `venue_id_raw`.
- **Its inputs**, the two scholarmend outputs the manifest pins (`out-covidence` 1,391 entries,
  `out-covidence-2020-2024` 443; the sha256 of each `mended.ris` and `resolved.json` matches the
  manifest). Every entry was checked, the 29 skipped ones included, for a `venue_id` claim in a v1
  venue-year (`is_v1`: ICLR 2013–2023, NeurIPS 2021–2022) or one of the bare v1 forms above.
- **The live review's triage** (`Trust-Evals-LitReview/out/decisions.csv`, 2,293 rows) was checked by
  venue-year and publisher. It has no record ids, so it gives counts only.

## Counts

| Check | v1 venue-years in scope | Records |
|---|---|---|
| Snapshot records with `venue_id_raw` in a v1 venue-year | ICLR 2017/2022/2023, NeurIPS 2021–22, D&B 2021 (and every other v1 year) | **0** of 1,805 |
| Snapshot records whose `status` claim cites a v1 venueid | same | **0** |
| Snapshot records whose `track` claim cites a v1 venueid | same | **0** |
| Snapshot records in any v1 venue-year, whatever the evidence | ICLR ≤2023, NeurIPS 2021–2022 | **0** |
| scholarmend `venue_id` claims in a v1 venue-year, skipped entries included | same | **0** of 169 claims |
| Live-review `MAIN` rows from `openreview.net` in 2017–2023 | same | **0** (the 8 `openreview.net` rows from 2022–2023 are all `WORKSHOP`) |

The snapshot's earliest venue-years are ICLR 2024 (v2), ICML 2022–2023 (PMLR) and NeurIPS 2023 (v2 and
proceedings). All 169 venueid claims in the inputs are v2 forms: `ICLR.cc/2024/Conference` (1),
`ICLR.cc/2026/Conference` (34), `ICML.cc/2024/Conference` (11), `ICML.cc/2025/Conference` (10),
`ICML.cc/2025/Position_Paper_Track` (1), `ICML.cc/2026/Conference` (111),
`NeurIPS.cc/2025/Workshop/AiForAnimalComms` (1), plus 7 `PMLR v…` claims from `pmlr_index`, which are
not OpenReview venueids. Status evidence in the snapshot: 1,633 records from a `proceedings_url`
listing, 3 from a `pmlr_url`, and 169 from a v2 venueid.

Why the 2020–24 search has no v1-year papers: its 443 entries are mostly 2024 (1,187 year claims for
2024, 91 for 2023, 5 for 2022, 1 for 2021). The four 2021–2022 entries were all skipped: three
`out_of_scope` (`oecd.ai` 2021; `sciengine.com` and `link.springer.com` 2022) and one `unresolved`
NeurIPS 2022 entry (2020–24 file, entry index 441). That last one is a NeurIPS 2022 slide deck (`neurips.cc/media/…/Slides/…`),
not a paper, and has no venueid. The live review's triage lists it as `MAIN` (publisher `neurips.cc`,
2022). That is a Scholar/venuetriage question, not a v1 status one, and it's worth one look in screening.

**Ids.** No snapshot record id qualifies, so none is listed.

## What re-ingest would change (dry run)
The same two inputs were copied into the scratchpad and run through `op ingest ris` and
`op snapshot build` with this branch's code (`--data-dir` in the scratchpad; nothing under `data/`
written):
- Import reports: the same as the manifest's (`imported` 1,377 + 428; skip reasons, `track_status` and
  `status_overrides` 0, all unchanged).
- The rebuilt snapshot is **`2026-09-23-d5ab3d6d444a`, the same hash**, and its `records.jsonl` has the
  same sha256 (`d5ab3d6d…9bc4`). No record's `status`, `track` or `content_hash` changes, so the
  `index_version` doesn't change either and saved search records replay as `reproduced`.
- TASK-094's new rows (NeurIPS `Position_Paper_Track` → `position`, `Competition_Track` →
  `competition`, `Evaluations_and_Datasets_Track` → `datasets_benchmarks`) change nothing here either.
  The corpus's 15 NeurIPS 2025 position papers already came from the proceedings token
  `Position_Paper_Track`, and no record carries a NeurIPS position or competition venueid.

## What changes going forward
- `classify_venueid` now returns status `unknown` for every venueid in a v1 venue-year. Track, venue and
  year are unchanged.
- The RIS importer records a v1 venueid's status claim as
  `venueid=… (API v1 venue-year: not status evidence)`. A proceedings listing for the same venue, year
  and track still makes the record `accepted` (counted in `status_overrides`). Without a listing, the
  record is `unknown`, which the default `status:accepted` filter excludes and counts. scholarmend's claims
  don't include `content.venue`, so the importer has no v1 venue string to use.
- The M4 v1 adapters (TASK-051) take status from `content.venue` through `classify_v1_venue` (a table of
  the exact strings seen live), from the decision note, or from the withdrawn or desk-rejected invitation.
- A future RIS import (a new Scholar search reaching 2017–2023) can't bring in a rejected v1 paper as
  accepted.
