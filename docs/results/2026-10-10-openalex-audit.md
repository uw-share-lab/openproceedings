# OpenAlex fidelity audit (2026-10-10)

- Snapshot: `2026-10-10-9efa49481112`
- Code: commit `78b7a6bd53ea`
- Sample: seed 49; every record with an official abstract and a DOI of FAccT 2022, 2025, 2026; AIES 2024, 2025; and 1,000 of 25,124 such AAAI 2010+ records, drawn in id order. Title-route check: 50 attaches.
- Date: 2026-10-10

Reproduce (from the OpenAlex cache, no network):

```
uv run op eval openalex --offline --snapshot 2026-10-10-9efa49481112 --seed 49 --aaai-sample 1000 --date 2026-10-10
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
Works returned for a DOI the batch didn't ask for (not compared): 1.
`differs` examples (the first 10 of 81): `op:facct:2022:doi-3531146.3533069`, `op:facct:2022:doi-3531146.3533070`, `op:facct:2022:doi-3531146.3533082`, `op:facct:2022:doi-3531146.3533083`, `op:facct:2022:doi-3531146.3533088`, `op:facct:2022:doi-3531146.3533089`, `op:facct:2022:doi-3531146.3533091`, `op:facct:2022:doi-3531146.3533092`, `op:facct:2022:doi-3531146.3533094`, `op:facct:2022:doi-3531146.3533097`.

Of 2,122 records compared, OpenAlex's abstract is exact for 1,544 (72.8%) and near-exact for 219 (10.3%): together 1,763 (83.1%) would match every search exactly as the official abstract does.

## The title route (AAAI 1980–2008): wrong-attach check

AAAI 1980–2008 records have no DOI. The fill matches each one by exact title key in the year's OpenAlex listing (`openalex_sources.toml`), attaching only when one listed work and one DOI-less record share the key. The listing source also holds proceedings volumes, other venues' papers and OCR-garbled titles, so an exact title could still name another paper. The fill was replayed over the cached listings (no new listing fetch). A seeded sample of its title-route attaches was then checked against OpenAlex's authors for each work (seed 49; one request per 50 works, `select=id,authorships,biblio`).

- DOI-less AAAI 1980–2008 records with no abstract: 4,709; title-route attaches: 1,061; the fill's refusals: `inverted_gap` 50, `inverted_unreadable` 101, `no_abstract` 119, `title_ambiguous` 21, `title_unmatched` 3,357.
- Sampled: 50 of 1,061 attaches.
- Year: OpenAlex's `publication_year` equals ours in 50 of 50. The listing is filtered by year and the fill requires the year, so this holds by construction.
- Authors: OpenAlex lists authors for 50 of 50; the first-author surname matches ours in 50; the lists share at least one surname in 50.
- Pages: OpenAlex holds a first page for 50 of 50. Our records carry no page field, so pages can't be compared.

**Verdict:** 50 agree (100.0%), 0 look wrong (0.0%), 0 can't be checked (no authors on one side) (0.0%). `agree`: the years match and the author lists share a surname (surnames compared without marks or case, dblp's homonym numbers dropped). `wrong`: OpenAlex lists authors and none of their surnames is any of ours.

No sampled attach looks wrong, so no rule change is indicated by this sample.
