---
name: pmlr-proceedings
description: The PMLR (proceedings.mlr.press) source for ICML — the volume-to-venue/year/track table (`ICML_PMLR_VOLUMES` in ingest/volumes.py, pinned by test_ris.py; a config file comes with task-053), the known ICML volumes, competition and workshop volumes, page structure and parsing gotchas, and why an unfamiliar volume is never coerced into ICML. Use when writing or reviewing the PMLR miner, editing the volume table, or adding an ICML year.
---

# PMLR proceedings (spec 01 §Sources)

PMLR is the **primary** source for ICML 2013–2022 (not on OpenReview as full venues; the crawl starts in
2013, decision-013) and a confirming source for ICML 2023+ (OpenReview v2 is primary there; a paper on
OpenReview but not in PMLR, or the reverse, is a `conflicts.csv` row).

## The volume table is data
As built (task-019): `backend/src/openproceedings/ingest/volumes.py`, `ICML_PMLR_VOLUMES` (volume → year,
track); no other module holds a volume number, and `test_ris.py` pins the table. It holds v119–v267 today;
the rows below marked *add* go in with the PMLR adapter (task-053), whose config file brings
`status_source`/`verified` columns and a check of each row against a recorded index-page fixture. Add them
there, not in a second table.

Every row was verified live on 2026-09-27 against the volume page's heading
(`<h2>Volume N: International Conference on Machine Learning, <dates>, <place></h2>`) and the PMLR index
title; the paper count is the number of `<div class="paper">` entries (evidence:
`docs/research/2026-09-27-openreview-and-proceedings-facts.md`; fixtures `backend/tests/fixtures/http/pmlr/`).

| Volume | Venue | Year | Track | Role | Papers | In `volumes.py` |
|---|---|---|---|---|---|---|
| v28 | ICML | 2013 | `main` | primary | 283 | add |
| v32 | ICML | 2014 | `main` | primary | 310 | add |
| v37 | ICML | 2015 | `main` | primary | 270 | add |
| v48 | ICML | 2016 | `main` | primary | 322 | add |
| v70 | ICML | 2017 | `main` | primary | 434 | add |
| v80 | ICML | 2018 | `main` | primary | 621 | add |
| v97 | ICML | 2019 | `main` | primary | 773 | add |
| v119 | ICML | 2020 | `main` | primary | 1,084 | yes |
| v139 | ICML | 2021 | `main` | primary | 1,183 | yes |
| v162 | ICML | 2022 | `main` | primary | 1,233 | yes |
| v202 | ICML | 2023 | `main` | confirm | 1,828 (= OpenReview accepted) | yes |
| v235 | ICML | 2024 | `unknown` | confirm | 2,610 (= OpenReview, position papers included and unmarked) | yes |
| v267 | ICML | 2025 | `unknown` | confirm | 3,330 (= OpenReview 3,257 main + 73 position) | yes |
| – | ICML | 2026 | – | – | not on PMLR on 2026-09-27 | add when its index page appears |
| v123 | NeurIPS | 2019 | `competition` | primary | 23 (Competition and Demonstration Track) | add (needs a NeurIPS table) |
| v133 | NeurIPS | 2020 | `competition` | primary | 20 | add |
| v176 | NeurIPS | 2021 | `competition` | primary | 36 (sections "Competitions", "Demonstrations") | add |
| v220 | NeurIPS | 2022 | `competition` | primary | 20 | add |

ICML workshop volumes exist and are **out of scope** (never `main`, never ingested unless spec 01 adds
workshops from PMLR): v27 (2011), v184 (ICML 2022 Healthcare AI), v251 (GRaM at ICML 2024), v292
(TerraBytes at ICML 2025). NeurIPS workshop volumes likewise (v116, v136, v137, v163, v181, v187, v210,
v226, v239, v262). v28 and v32 split their papers into "Cycle 1/2/3 Papers" sections, which are not
tracks.

**Position papers:** no ICML volume marks them (v235 and v267 have no section headings), so the track
comes from OpenReview (`ICML.cc/2025/Position_Paper_Track`), and PMLR only confirms acceptance. ICML 2024's
position papers aren't marked on OpenReview either (they carry `ICML.cc/2024/Conference`).
v235's paper entries link the OpenReview forum (`openreview.net/forum?id=…`): use that id to join
PMLR and OpenReview for 2023+, not the title.

## Page structure
- Volume index: `https://proceedings.mlr.press/v<N>/`. Its heading reads `Volume N: <proceedings title>`.
  Some volumes use `<h1>`, others `<h2>` (every ICML volume v28–v267 uses `<h2>`); take the first of
  either and strip the `Volume N: ` prefix. The PMLR index (`https://proceedings.mlr.press/`) lists every
  volume as `<li><a href="vN"><b>Volume N</b></a> <title></li>` (326 on 2026-09-27).
- Per-paper pages: `https://proceedings.mlr.press/v<N>/<key>.html` with a PDF beside it; the abstract is
  `<div id="abstract" class="abstract">`, the title `citation_title` (also repeated in twitter meta tags
  and the BibTeX/Endnote/APA boxes). The `<key>` is
  stable and gives the native id `pmlr-v<N>-<key>` (spec 01 §Record schema).
- Scholar and RIS records sometimes link the GitHub asset host instead
  (`raw.githubusercontent.com/mlresearch/v<N>/…`). Only the `mlresearch` organisation is PMLR.
- Strip HTML from abstracts, keep LaTeX verbatim (spec 03 decides tokenization), and collapse whitespace.

## Rules
1. **Only listed volumes are ingested.** PMLR hosts many unrelated venues (v318 is the Canadian
   Conference on AI). A volume missing from the table is out of scope. It never becomes ICML because its
   title looks similar.
2. **The year comes from the table**, not from the page footer, a PDF date or an arXiv date.
3. **Competition and workshop volumes never become `main`.** The track is a table column, never inferred.
4. Every record gets claims whose evidence is the volume index URL plus the paper URL, with the fetch time
   taken from the cache entry.
5. Every fetch goes through the disk cache (`.claude/skills/openreview-api/SKILL.md` has the retry rules,
   and the same HTTP client serves PMLR).

## Counting check
After a crawl, the paper count per volume must equal the number of paper entries on the volume index.
Put that count in the manifest's source versions so `coverage-auditor` can compare it with the official
accepted count.
