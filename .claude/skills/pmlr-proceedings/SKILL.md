---
name: pmlr-proceedings
description: The PMLR (proceedings.mlr.press) source for ICML — the volume-to-venue/year/track table that lives in config and is checked in tests, the known ICML volumes, competition and workshop volumes, page structure and parsing gotchas, and why an unfamiliar volume is never coerced into ICML. Use when writing or reviewing the PMLR miner, editing the volume table, or adding an ICML year.
---

# PMLR proceedings (spec 01 §Sources)

PMLR is the **primary** source for ICML 2020–2022 (not on OpenReview as full venues) and a confirming
source for ICML 2023+ (OpenReview v2 is primary there; a paper on OpenReview but not in PMLR, or the
reverse, is a `conflicts.csv` row).

## The volume table is data
It lives in config, e.g. `backend/src/openproceedings/ingest/config/pmlr_volumes.toml`, one row per volume:
`volume`, `venue`, `year`, `track`, `status_source` (`primary` | `confirm`), and `verified` (the date and
how). Code never contains a volume number. `backend/tests/unit/ingest/test_pmlr_volumes.py` checks every
row against a recorded fixture of that volume's index page heading.

| Volume | Venue | Year | Track | Role | Confidence |
|---|---|---|---|---|---|
| v119 | ICML | 2020 | `main` | primary | spec 01 |
| v139 | ICML | 2021 | `main` | primary | spec 01 |
| v162 | ICML | 2022 | `main` | primary | spec 01 |
| v202 | ICML | 2023 | `main` | confirm | spec 01 |
| v235 | ICML | 2024 | `main` | confirm | spec 01 |
| v267 | ICML | 2025 | `main` | confirm | verify (scholarmend notes v267 = ICML 2025) |
| later | ICML | 2026+ | `main` | confirm | verify each from its index heading before adding |
| NeurIPS competition volumes | NeurIPS | per volume | `competition` | primary | verify each volume number |
| ICML workshop volumes (if any) | ICML | per volume | `workshop` | primary | verify; never `main` |

Position papers at ICML 2024+: verify whether PMLR marks them separately. If it doesn't, the track comes
from OpenReview, and PMLR only confirms acceptance.

## Page structure
- Volume index: `https://proceedings.mlr.press/v<N>/`. Its heading reads `Volume N: <proceedings title>`.
  Some volumes use `<h1>`, others `<h2>`; take the first of either and strip the `Volume N: ` prefix.
- Per-paper pages: `https://proceedings.mlr.press/v<N>/<key>.html` with a PDF beside it. The `<key>` is
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
