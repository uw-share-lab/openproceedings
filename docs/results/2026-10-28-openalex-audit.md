# OpenAlex fidelity audit (2026-10-28)

- Snapshot: `2026-10-16-03eab0ef56c4`
- Code: commit `52fe3f767fe1`
- Sample: seed 49; every record with an official abstract and a DOI of FAccT 2022, 2025, 2026; AIES 2024, 2025, 2026; and 1,000 of 25,124 such AAAI 2010+ records, sorted by id after a seeded draw. Title-route check: 19 attaches.
- Date: 2026-10-28

Reproduce (from the OpenAlex cache, no network):

```
uv run op eval openalex --offline --snapshot 2026-10-16-03eab0ef56c4 --seed 49 --aaai-sample 1000 --title-sample 19 --date 2026-10-28 --ruling 'Keep the exact title-key and year rule: 18 of the 19 title-route attaches agree on year and an author surname, and the 1 flagged is a spelling or OCR variant of the same first-author surname (controller, 2026-10-11).'
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

The DOI route covers AIES, FAccT and AAAI 2010+. AAAI 1980–2008 has no DOI: its OpenAlex texts are checked by the title-route section and measured by the `aaai_library` section below.

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
| AIES | 2026 | 265 | 262 (98.9%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 1 (0.4%) | 0 (0.0%) | 2 (0.8%) | 0 (0.0%) | 0 (0.0%) |
| FAccT | 2022 | 169 | 25 (14.8%) | 14 (8.3%) | 9 (5.3%) | 64 (37.9%) | 57 (33.7%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| FAccT | 2025 | 206 | 14 (6.8%) | 108 (52.4%) | 10 (4.9%) | 55 (26.7%) | 8 (3.9%) | 11 (5.3%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| FAccT | 2026 | 298 | 66 (22.1%) | 94 (31.5%) | 17 (5.7%) | 80 (26.8%) | 16 (5.4%) | 24 (8.1%) | 0 (0.0%) | 0 (0.0%) | 1 (0.3%) |
| **All** | | **2,387** | 1,806 (75.7%) | 219 (9.2%) | 36 (1.5%) | 204 (8.5%) | 82 (3.4%) | 35 (1.5%) | 2 (0.1%) | 0 (0.0%) | 3 (0.1%) |

Refusals: none.
Works returned for a DOI the batch didn't ask for (not compared): 1; it is in no count above, so no figure changes.
`differs` examples (the first 10 of 82): `op:aies:2026:ojs-43206`, `op:facct:2022:doi-3531146.3533069`, `op:facct:2022:doi-3531146.3533070`, `op:facct:2022:doi-3531146.3533082`, `op:facct:2022:doi-3531146.3533083`, `op:facct:2022:doi-3531146.3533088`, `op:facct:2022:doi-3531146.3533089`, `op:facct:2022:doi-3531146.3533091`, `op:facct:2022:doi-3531146.3533092`, `op:facct:2022:doi-3531146.3533094`.

Of 2,387 records compared, OpenAlex's abstract is exact for 1,806 (75.7%) and near-exact for 219 (9.2%): together 2,025 (84.8%) would match every search exactly as the official abstract does.

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

## AAAI 1980–2008: OpenAlex against AAAI's archived pages (`aaai_library`)

An AAAI 1980–2008 record whose abstract comes from AAAI's own archived aaai.org paper page (`aaai_library`, official) never takes OpenAlex's, but the title route often finds a work for it. The fill was replayed over the cached listings with those abstracts set aside (no new listing fetch), and each text it would attach was compared with AAAI's by the rules above. This is the one measure of OpenAlex's text for these years: on the records OpenAlex does fill, no official text exists. It measures how often two texts agree, not how often OpenAlex is wrong (see Caveats).

- AAAI 1980–2008 records with an `aaai_library` abstract: 4,536 (every one, not a sample; no seed); with an OpenAlex text to compare: 1,131; one work but no abstract in OpenAlex (`no_abstract`): 109; nothing attached, by reason: `inverted_gap` 58, `inverted_unreadable` 2, `title_ambiguous` 20, `title_unmatched` 3,216.

| Venue | Year | Compared | `exact` | `near_exact` | `truncated` | `similar` | `differs` |
|---|---|---|---|---|---|---|---|
| AAAI | 1980 | 36 | 10 (27.8%) | 10 (27.8%) | 0 (0.0%) | 14 (38.9%) | 2 (5.6%) |
| AAAI | 1982 | 52 | 23 (44.2%) | 12 (23.1%) | 0 (0.0%) | 16 (30.8%) | 1 (1.9%) |
| AAAI | 1983 | 49 | 11 (22.4%) | 6 (12.2%) | 0 (0.0%) | 31 (63.3%) | 1 (2.0%) |
| AAAI | 1984 | 29 | 8 (27.6%) | 8 (27.6%) | 0 (0.0%) | 13 (44.8%) | 0 (0.0%) |
| AAAI | 1986 | 56 | 29 (51.8%) | 13 (23.2%) | 0 (0.0%) | 13 (23.2%) | 1 (1.8%) |
| AAAI | 1987 | 90 | 25 (27.8%) | 28 (31.1%) | 0 (0.0%) | 37 (41.1%) | 0 (0.0%) |
| AAAI | 1988 | 71 | 35 (49.3%) | 14 (19.7%) | 0 (0.0%) | 22 (31.0%) | 0 (0.0%) |
| AAAI | 1990 | 65 | 31 (47.7%) | 12 (18.5%) | 0 (0.0%) | 22 (33.8%) | 0 (0.0%) |
| AAAI | 1991 | 66 | 17 (25.8%) | 16 (24.2%) | 0 (0.0%) | 32 (48.5%) | 1 (1.5%) |
| AAAI | 1992 | 56 | 19 (33.9%) | 15 (26.8%) | 0 (0.0%) | 21 (37.5%) | 1 (1.8%) |
| AAAI | 1993 | 44 | 13 (29.5%) | 8 (18.2%) | 1 (2.3%) | 22 (50.0%) | 0 (0.0%) |
| AAAI | 1994 | 85 | 26 (30.6%) | 15 (17.6%) | 1 (1.2%) | 27 (31.8%) | 16 (18.8%) |
| AAAI | 1996 | 69 | 16 (23.2%) | 19 (27.5%) | 0 (0.0%) | 23 (33.3%) | 11 (15.9%) |
| AAAI | 1997 | 52 | 9 (17.3%) | 10 (19.2%) | 0 (0.0%) | 20 (38.5%) | 13 (25.0%) |
| AAAI | 1998 | 36 | 3 (8.3%) | 4 (11.1%) | 0 (0.0%) | 16 (44.4%) | 13 (36.1%) |
| AAAI | 1999 | 35 | 4 (11.4%) | 5 (14.3%) | 0 (0.0%) | 14 (40.0%) | 12 (34.3%) |
| AAAI | 2000 | 34 | 3 (8.8%) | 3 (8.8%) | 0 (0.0%) | 11 (32.4%) | 17 (50.0%) |
| AAAI | 2002 | 26 | 6 (23.1%) | 4 (15.4%) | 0 (0.0%) | 4 (15.4%) | 12 (46.2%) |
| AAAI | 2004 | 26 | 10 (38.5%) | 9 (34.6%) | 0 (0.0%) | 5 (19.2%) | 2 (7.7%) |
| AAAI | 2005 | 33 | 4 (12.1%) | 1 (3.0%) | 12 (36.4%) | 12 (36.4%) | 4 (12.1%) |
| AAAI | 2006 | 42 | 16 (38.1%) | 4 (9.5%) | 0 (0.0%) | 13 (31.0%) | 9 (21.4%) |
| AAAI | 2007 | 30 | 17 (56.7%) | 3 (10.0%) | 1 (3.3%) | 7 (23.3%) | 2 (6.7%) |
| AAAI | 2008 | 49 | 26 (53.1%) | 4 (8.2%) | 1 (2.0%) | 13 (26.5%) | 5 (10.2%) |
| **All** | | **1,131** | 361 (31.9%) | 223 (19.7%) | 16 (1.4%) | 408 (36.1%) | 123 (10.9%) |

`differs` examples (the first 10 of 123): `op:aaai:1980:dblp-Genesereth80`, `op:aaai:1980:dblp-Grinberg80`, `op:aaai:1982:dblp-StolfoS82`, `op:aaai:1983:dblp-BenjaminH83`, `op:aaai:1986:dblp-GuidaGGS86`, `op:aaai:1991:dblp-Vilain91`, `op:aaai:1992:dblp-Sy92`, `op:aaai:1994:dblp-AntonioCN94`, `op:aaai:1994:dblp-Chang94`, `op:aaai:1994:dblp-Franz94`.

Of the 1,131 records with both an `aaai_library` abstract and an OpenAlex text, OpenAlex's is exact for 361 (31.9%), near-exact for 223 (19.7%), truncated for 16 (1.4%), similar for 408 (36.1%) and differs for 123 (10.9%): together 584 (51.6%) would match every search exactly as AAAI's text does.

### The `differs` texts: another paper, or another text?

Each of the 123 `differs` attaches was checked against OpenAlex's authors for the work, as the title route's attaches are above (one request per 50 works, `select=id,authorships,biblio`):

- **Genuinely different texts:** 122 (99.2%). The author lists share a surname, so the work is the same paper and the two texts differ. Of these, 63 open with the same 5 search tokens as AAAI's, and OpenAlex's text is at least 1.5× as long as AAAI's in 86 (median 2.4×); 47 do both, the shape of a text that runs on past the abstract.
- **Look like wrong-paper attaches:** 1 (0.8%). OpenAlex lists authors and none of their surnames is any of ours, so the title route may have attached another paper with the same title key.
- **Can't be told:** 0 (0.0%; no authors on one side).

| Record | OpenAlex work | Our first-author surname | OpenAlex's first-author surname | Near spelling |
|---|---|---|---|---|
| `op:aaai:1998:dblp-Pedersen98a` | `W2164604466` | pedersen | pederson | yes |

1 of the 1 have a first-author surname close to ours (a character ratio of at least 0.75), by the look of them spelling or OCR variants of the same surname; if they are the same authors, 0 are wrong-paper attaches. A text that agrees (`exact` to `similar`) is taken to be the same paper (not author-checked), so of the 1,131 attaches compared, 1 (0.1%) look like another paper, or 0 (0.0%) if the near spellings are the same authors.

## Caveats

- OpenAlex's fidelity for AAAI 1980–2008 is measured only on records `aaai_library` also gives an abstract for (the section above). The records OpenAlex fills are the ones AAAI's archived pages don't cover, so their texts may agree less or more often than these.
- In that comparison AAAI's text is itself read from archived HTML, and OpenAlex's is often text-mined, so a `similar` or `differs` can be an OCR, hyphenation or extraction difference on either side. A `differs` can also be another paper attached by title; the author check above tells which, by surnames, not checked by a person.
- The title route's residual wrong-attach risk is an estimate, not a measured bound: 1 of the 1 attaches that look wrong have a first-author surname close to ours, judged by a character ratio, not checked by a person. If they are the same authors, 0 of the 19 sampled attaches (0.0%) would be wrong.
