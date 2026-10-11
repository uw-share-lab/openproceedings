# OpenAlex fidelity audit (2026-10-11)

- Snapshot: `2026-10-11-93c2937e2f29`
- Code: commit `dead85b8e326`
- Sample: seed 49; every record with an official abstract and a DOI of FAccT 2022, 2025, 2026; AIES 2024, 2025; and 1,000 of 25,124 such AAAI 2010+ records, sorted by id after a seeded draw. Title-route check: 19 attaches.
- Date: 2026-10-11

Reproduce (from the OpenAlex cache, no network):

```
uv run op eval openalex --offline --snapshot 2026-10-11-93c2937e2f29 --seed 49 --aaai-sample 1000 --title-sample 19 --date 2026-10-11 --ruling 'Keep the exact title-key and year rule: 18 of the 19 title-route attaches agree on year and an author surname, and the 1 flagged is a spelling or OCR variant of the same first-author surname (controller, 2026-10-11).'
```

## Method

Each sampled record has an official abstract (FAccT's from the official FAccT pages, `facct_site`; AIES's and
AAAI's from ojs.aaai.org, `ojs`) and a DOI. Each venue-year's DOIs were looked up in OpenAlex in sorted batches of
50, as `op ingest openalex` looks them up, and each work's `abstract_inverted_index` was rebuilt and cleaned by the
fill's own rules (`openalex.abstract_of`: a gap, two words at one position or any other shape is refused). OpenAlex's
text is then compared with the official one:

- `exact`: equal once whitespace is collapsed.
- `near_exact`: the same search tokens (`dedup.title_key`, the token contract): every search matches both alike.
- `truncated`: OpenAlex's tokens are a strict prefix of the official ones.
- `similar`: a token `SequenceMatcher` ratio of at least 0.9.
- `differs`: anything else.
- `no_abstract`: OpenAlex has the work but no abstract for it.
- `no_openalex`: no OpenAlex work answers for the DOI.
- `refused`: the work's abstract was refused by the rebuild or cleaning (why is listed below the table).
- `duplicate`: several works answer for the DOI with differing texts (several with one text are compared once).

Each rate is of the records compared in that row. No abstract text is quoted here; records are named by id.

## The DOI route: OpenAlex's abstract against the official one

| Venue | Year | Compared | `exact` | `near_exact` | `truncated` | `similar` | `differs` | `no_abstract` | `no_openalex` | `refused` | `duplicate` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AAAI | 2010 | 9 | 8 (88.9%) | 0 (0.0%) | 0 (0.0%) | 1 (11.1%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2011 | 9 | 7 (77.8%) | 0 (0.0%) | 0 (0.0%) | 2 (22.2%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2012 | 17 | 17 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2013 | 9 | 9 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2014 | 25 | 25 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2015 | 28 | 28 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2016 | 31 | 31 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2017 | 31 | 30 (96.8%) | 0 (0.0%) | 0 (0.0%) | 1 (3.2%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2018 | 38 | 37 (97.4%) | 1 (2.6%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2019 | 50 | 50 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2020 | 79 | 79 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2021 | 74 | 73 (98.6%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 1 (1.4%) |
| AAAI | 2022 | 64 | 63 (98.4%) | 0 (0.0%) | 0 (0.0%) | 1 (1.6%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2023 | 72 | 71 (98.6%) | 1 (1.4%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2024 | 112 | 112 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2025 | 154 | 154 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AAAI | 2026 | 198 | 197 (99.5%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 1 (0.5%) |
| AIES | 2024 | 170 | 170 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| AIES | 2025 | 279 | 278 (99.6%) | 1 (0.4%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| FAccT | 2022 | 169 | 25 (14.8%) | 14 (8.3%) | 9 (5.3%) | 64 (37.9%) | 57 (33.7%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| FAccT | 2025 | 206 | 14 (6.8%) | 108 (52.4%) | 10 (4.9%) | 55 (26.7%) | 8 (3.9%) | 11 (5.3%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| FAccT | 2026 | 298 | 66 (22.1%) | 94 (31.5%) | 17 (5.7%) | 80 (26.8%) | 16 (5.4%) | 24 (8.1%) | 0 (0.0%) | 0 (0.0%) | 1 (0.3%) |
| **All** | | **2,122** | 1,544 (72.8%) | 219 (10.3%) | 36 (1.7%) | 204 (9.6%) | 81 (3.8%) | 35 (1.6%) | 0 (0.0%) | 0 (0.0%) | 3 (0.1%) |

Refusals: none.
Works returned for a DOI the batch didn't ask for (not compared): 1; it is in no count above, so no figure changes.
`differs` examples (the first 10 of 81): `op:facct:2022:doi-3531146.3533069`, `op:facct:2022:doi-3531146.3533070`, `op:facct:2022:doi-3531146.3533082`, `op:facct:2022:doi-3531146.3533083`, `op:facct:2022:doi-3531146.3533088`, `op:facct:2022:doi-3531146.3533089`, `op:facct:2022:doi-3531146.3533091`, `op:facct:2022:doi-3531146.3533092`, `op:facct:2022:doi-3531146.3533094`, `op:facct:2022:doi-3531146.3533097`.

Of 2,122 records compared, OpenAlex's abstract is exact for 1,544 (72.8%) and near-exact for 219 (10.3%): together 1,763 (83.1%) would match every search exactly as the official abstract does.

**A note on FAccT.** FAccT agrees far less often than AAAI or AIES, whose official abstracts come from ojs.aaai.org.
FAccT's official abstracts come from the conference's own pages (`facct_site`). Most of FAccT's `similar` and
`differs` cases are about the same length as the official text and mostly open with the same words, so they look
like another version of the same abstract rather than noise: OpenAlex likely carries ACM's published version, not
the conference site's text. A few are entirely different texts. An abstract the fill takes from OpenAlex is labelled
`abstract_kind: openalex`, never `official`, so the label already tells a reader the text is OpenAlex's, which may be
ACM's version rather than the site's.

## The title route (AAAI 1980–2008): wrong-attach check

AAAI 1980–2008 records have no DOI. The fill matches each one by exact title key in the year's OpenAlex listing (`openalex_sources.toml`), attaching only when one listed work and one DOI-less record share the key. The listing source also holds proceedings volumes, other venues' papers and OCR-garbled titles, so an exact title could still name another paper. The fill was replayed over the cached listings (no new listing fetch). A seeded sample of its title-route attaches was then checked against OpenAlex's authors for each work (seed 49; one request per 50 works, `select=id,authorships,biblio`).

- DOI-less AAAI 1980–2008 records with no abstract: 154; title-route attaches: 19; the fill's refusals: `inverted_gap` 2, `no_abstract` 10, `title_ambiguous` 1, `title_unmatched` 141.
- Sampled: 19 of 19 attaches.
- Year: OpenAlex's `publication_year` equals ours in 19 of 19. The listing is filtered by year and the fill requires the year, so this holds by construction.
- Authors: OpenAlex lists authors for 19 of 19; the first-author surname matches ours in 18; the lists share at least one surname in 18.
- Pages: OpenAlex holds a first page for 18 of 19. Our records carry no page field, so pages can't be compared.

**Verdict:** 18 agree (94.7%), 1 look wrong (5.3%), 0 can't be checked (0.0%; no authors on one side). `agree`: the years match and the author lists share a surname (surnames compared without marks or case, dblp's homonym numbers dropped). `wrong`: OpenAlex lists authors and none of their surnames is any of ours.

| Record | OpenAlex work | Our first-author surname | OpenAlex's first-author surname |
|---|---|---|---|
| `op:aaai:1997:dblp-Nournai97` | `W2523563690` | nournai | nourani |

1 of the 1 that look wrong have a first-author surname close to ours (a character ratio of at least 0.75): by the look of them, spelling or OCR variants of the same surname.

Rules that would exclude them:

- **Require at least one shared author surname:** excludes all 1 that look wrong, and also the 0 that can't be checked.
- **Require a matching first-author surname:** excludes all 1 that look wrong, and also 0 that agree on another author and the 0 that can't be checked.

**Ruling:** Keep the exact title-key and year rule: 18 of the 19 title-route attaches agree on year and an author surname, and the 1 flagged is a spelling or OCR variant of the same first-author surname (controller, 2026-10-11).

## Caveats

- OpenAlex's fidelity for AAAI before 2010 is unmeasured. The DOI route compares only records that also have an official abstract, and the title route checks authors, not abstract text. Where AAAI's archived aaai.org pages (`aaai_library`) and OpenAlex both give an abstract for an AAAI 1980–2008 paper, the two can be compared; that measure is a follow-up.
- The title route's residual wrong-attach risk is an estimate, not a measured bound: 1 of the 1 attaches that look wrong have a first-author surname close to ours, judged by a character ratio, not checked by a person. If they are the same authors, 0 of the 19 sampled attaches (0.0%) would be wrong.
