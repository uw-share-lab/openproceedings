---
name: track-taxonomy
description: The track and status enums from spec 01 with the source signal that justifies each value, the never-default-to-main and unknown-stays-unknown rules, how evidence claims back every classification, and which tracks and statuses the default query filter includes per spec 02. Use when writing or reviewing backend/src/openproceedings/ingest/classify.py, auditing a snapshot's classifications, or answering why a paper is or is not in a default search.
---

# Track taxonomy (spec 01 §Track taxonomy; spec 02 §Default filters)

## `track`
| Value | Accepted signals (any one, with its claim) | In default filter? |
|---|---|---|
| `main` | a dblp AAAI 1980–2008 main-conference proceedings key (`ingest/dblp_aaai.toml`; its `[[not_paper]]` entries are counted, never records); every paper of an ACM proceedings of FAccT 2019+ and AIES 2018–2023 from Crossref (`ingest/acm_proceedings.toml`) but its `[[not_paper]]` rows (26 FAccT 2020 tutorials and CRAFT sessions): Crossref has no section data, so AIES 2018–2023 student abstracts and keynotes are `main` (OJS labels student abstracts only from 2024); PMLR v81 (FAccT 2018; its `not_papers` are counted, never records); OJS (AAAI 2010+, AIES 2024+, IASEAI 2026): a section whose `ojs_sections.toml` row says `main` (the track comes from the record's section, never the OJS issue; a row may name only `ojs_table.OJS_TRACKS`, so no OJS section can be `position` or `datasets_benchmarks`); venueid `<Org>.cc/<Y>/Conference`; a PMLR volume listed as `main` in the volume table (`ingest/pmlr_volumes.toml`); NeurIPS path `-Conference`; a token-less NeurIPS listing on `proceedings.neurips.cc` up to 2021 (host and year, `classify_neurips_listing`) | **yes** |
| `datasets_benchmarks` | venueid `NeurIPS.cc/<Y>/Track/Datasets_and_Benchmarks` or `…_Track`, and NeurIPS 2026's rename `NeurIPS.cc/2026/Evaluations_and_Datasets_Track` (TASK-094); NeurIPS path `Datasets_and_Benchmarks(_Track)` (≤2023 alias) | **yes** |
| `position` | ICML position-paper track (venueid `ICML.cc/<Y>/Position_Paper_Track`, seen); the proceedings token `Position_Paper_Track` (seen); NeurIPS `NeurIPS.cc/<Y>/Position_Paper_Track` (2025+, verified live 2026-09-27; TASK-094) | **yes** |
| `workshop` | any venueid segment `Workshop` or `Workshop_<City>`; a PMLR workshop volume; a dblp AAAI workshop proceedings key (`dblp_aaai.toml` `[[workshop]]`: 1996w1, 1997ca, 1997w6) | no |
| `competition` | NeurIPS `NeurIPS.cc/<Y>/Competition_Track` (2024+, verified; TASK-094) or `Track/Competition`; PMLR competition volumes (v123, v133, v176, v220) | no |
| `tiny_papers` | ICLR Tiny Papers (2023–2024) | no |
| `blogpost` | ICLR Blogpost track | no |
| `student_abstract` | OJS (ojs.aaai.org) sections of AAAI and AIES student abstracts and posters, by `ingest/ojs_sections.toml` row | no |
| `consortium` | OJS sections of AAAI's doctoral and undergraduate consortia | no |
| `demo` | OJS sections of AAAI's demonstration tracks | no |
| `iaai`, `eaai` | OJS sections printed in the AAAI volumes for IAAI and EAAI; **AAAI only** (the record refuses them on another venue, `record.VENUE_ONLY_TRACKS`) | no |
| `other` | a form that parses but isn't listed above (e.g. `Creative_AI_Track`, `Education_Program`); `venue_id_raw` kept. OJS: Senior Member presentations, New Faculty Highlights, Emerging Trends and the sections the design's mapping does not name (marked "owner decision" in `ojs_sections.toml`). Of these only NeurIPS Creative AI is also in the proceedings, so only it merges with a listing (dedup-rules §Never merge, TASK-137) | no |
| `unknown` | no trustworthy signal | no, but always counted on coverage |

The OJS signal is a table row per journal, volume and OAI set (spec 01 §Sources OJS row; the mapping's reasoning is `docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md`). Exact venueid spellings are in `.claude/skills/openreview-venueids/SKILL.md`, and proceedings path
segments in `.claude/skills/neurips-proceedings/SKILL.md` and `.claude/skills/pmlr-proceedings/SKILL.md`.

## `status`
`accepted` (bare venue path, listed in proceedings, or an accept decision) · `rejected`
(`Rejected_Submission` or a reject decision) · `withdrawn` · `desk_rejected` · `unknown`. The default
filter adds `status:accepted`.

**RIS-imported records** (spec 01 §Sources, the RIS importer row): `status` comes from a claim only. An
OpenReview venueid claim → its status, except that a venueid in an API v1 venue-year (ICLR ≤2023, NeurIPS
2021–2022) gives `unknown`, because v1 puts the bare path on rejected papers too (TASK-095); a
proceedings-page claim → `accepted`; no claim → `unknown`. Never
infer `accepted` from a paper appearing in Scholar (rule 2: unknown stays unknown).

## The default filter (spec 02)
If a query has no top-level `track:` conjunct, the parser adds `track:(main OR datasets_benchmarks OR
position)`. If it has no top-level `status:` conjunct, it adds `status:accepted`. Both are **written into the canonical string**
(guarantee 3), and the per-filter exclusion counts are shown (guarantee 6). Consequences for ingestion:
- A wrong `main` puts a workshop paper into every default search. That is the exact failure the project
  exists to prevent (spec 07 §D: ≥99% workshop vs non-workshop accuracy).
- A wrong `unknown` only hides a paper, and it shows up on coverage. So when in doubt, choose `unknown`.
  The error costs are asymmetric on purpose.
- The default-filter logic belongs to the query layer (`.claude/skills/default-filters/SKILL.md`).
  Ingestion never pre-filters: rejected, withdrawn and workshop papers are all ingested and indexed.

## Rules
1. **Never default to `main`.** The model has no default. Code paths that "fall through" end at `unknown`.
2. **Unknown stays unknown.** No heuristics from title words, author lists, page counts, PDF templates or
   invitation names. A person resolves it with a new evidence rule, which gets a table-test row.
3. **Every value has a claim.** `track` and `status` each carry the claim that produced them (source, URL,
   evidence string). A classification without a claim is a bug, and `track-classifier-auditor` blocks it.
4. **OpenReview venueid beats everything** for venue-years OpenReview hosts. The proceedings may confirm
   acceptance but never override the track.
5. **`presentation` is not a track.** Oral, spotlight and poster are all `main`.
6. Adding an enum value is a spec change (01 and 02 both), a `/meta` vocabulary change (spec 04) and an
   index `SCHEMA_VERSION` question (spec 03).
