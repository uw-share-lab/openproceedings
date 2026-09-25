---
name: track-taxonomy
description: The track and status enums from spec 01 with the source signal that justifies each value, the never-default-to-main and unknown-stays-unknown rules, how evidence claims back every classification, and which tracks and statuses the default query filter includes per spec 02. Use when writing or reviewing backend/src/openproceedings/ingest/classify.py, auditing a snapshot's classifications, or answering why a paper is or is not in a default search.
---

# Track taxonomy (spec 01 §Track taxonomy; spec 02 §Default filters)

## `track`
| Value | Accepted signals (any one, with its claim) | In default filter? |
|---|---|---|
| `main` | venueid `<Org>.cc/<Y>/Conference`; a PMLR volume listed as `main` in the volume table; NeurIPS path `-Conference` | **yes** |
| `datasets_benchmarks` | venueid `NeurIPS.cc/<Y>/Track/Datasets_and_Benchmarks` or `…_Track`; NeurIPS path `Datasets_and_Benchmarks(_Track)` (≤2023 alias) | **yes** |
| `position` | ICML position-paper track (venueid form: verify); NeurIPS `Position_Paper_Track` (verify mapping) | **yes** |
| `workshop` | any venueid segment `Workshop` or `Workshop_<City>`; a PMLR workshop volume | no |
| `competition` | NeurIPS Competition Track; PMLR competition volumes | no |
| `tiny_papers` | ICLR Tiny Papers (2023–2024) | no |
| `blogpost` | ICLR Blogpost track | no |
| `other` | a form that parses but isn't listed above (e.g. `Creative_AI_Track`); `venue_id_raw` kept | no |
| `unknown` | no trustworthy signal | no, but always counted on coverage |

Exact venueid spellings are in `.claude/skills/openreview-venueids/SKILL.md`, and proceedings path
segments in `.claude/skills/neurips-proceedings/SKILL.md` and `.claude/skills/pmlr-proceedings/SKILL.md`.

## `status`
`accepted` (bare venue path, listed in proceedings, or an accept decision) · `rejected`
(`Rejected_Submission` or a reject decision) · `withdrawn` · `desk_rejected` · `unknown`. The default
filter adds `status:accepted`.

**RIS-imported records** (spec 01 §Sources, the RIS importer row): `status` comes from a claim only. An
OpenReview venueid claim → its status; a proceedings-page claim → `accepted`; no claim → `unknown`. Never
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
