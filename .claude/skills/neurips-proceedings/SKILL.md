---
name: neurips-proceedings
description: The proceedings.neurips.cc source — the paper_files URL grammar, the closed track vocabulary (Conference, Datasets_and_Benchmarks_Track, Position_Paper_Track, Creative_AI_Track) and the ≤2023 Datasets_and_Benchmarks alias, abstract-page extraction gotchas, and its role as the only NeurIPS source before 2021 and a cross-check after. Use when writing or reviewing the NeurIPS proceedings miner, its fixtures, or a NeurIPS coverage mismatch.
---

# NeurIPS proceedings (spec 01 §Sources)

## Role
- **The only source** for NeurIPS before 2021 (main track; D&B starts in 2021). The crawl covers 2013 on
  (decision-013); the site index `https://proceedings.neurips.cc/` links every year 1987–2025.
- Published in split volumes: on 2026-09-27 the 2025 base page listed 64 Creative AI papers and linked a
  5,823-paper `vol38-main-conference` page containing main, D&B and position tracks. A year can therefore
  require more than its base URL; follow only a recorded, known companion and never infer absence.
- A **cross-check** for 2021+ (OpenReview v1/v2 is primary for track and status). An OpenReview-accepted
  paper missing from the proceedings, or the reverse, is a `conflicts.csv` row. It never silently flips
  status.
- The proceedings list **accepted papers only** and never host workshop papers. That is why the
  path's track segment discriminates so well. It also means proceedings can never supply
  `status: rejected`.

## URL grammar
```
https://proceedings.neurips.cc/paper_files/paper/<YYYY>/{hash|file}/<sha>-{Abstract|Paper}[-<Track>].{html|pdf}
```
Checked on every year page from 2013 to 2025 (2026-09-27, `docs/research/2026-09-27-openreview-and-proceedings-facts.md`):

| Years | Abstract link | Year-page entry |
|---|---|---|
| 1987–2021 | `<sha>-Abstract.html`: **no track token** (all main track) | `<li class="" data-track="none">` |
| 2022–2023 | `-Abstract-Conference.html`, `-Abstract-Datasets_and_Benchmarks.html` | `<li class="conference">`, `"datasets_and_benchmarks"` |
| 2024 | `-Abstract-Conference.html`, `-Abstract-Datasets_and_Benchmarks_Track.html` | `data-track="datasets_and_benchmarks_track"` |
| 2025 | base: `-Abstract-Creative_AI_Track.html`; vol38 companion: `-Abstract-{Conference,Datasets_and_Benchmarks_Track,Position_Paper_Track}.html` | `data-track="creative_ai_track"`, `"conference"`, `"datasets_and_benchmarks_track"`, `"position_paper_track"` |
| 2021 D&B | `https://datasets-benchmarks-proceedings.neurips.cc/paper/2021` → `/paper_files/paper/2021/hash/<sha>-Abstract-round1.html` / `-round2.html` | `<li class="round1">`, authors in `<i>` |

`classify_proceedings("")` returns track `unknown`, so the miner must give token-less 1987–2021
listings on `proceedings.neurips.cc` track `main` from the host and year (the year page has no other
track), and the 2021 D&B host's `round1`/`round2` listings `datasets_benchmarks`, each as its own
evidence rule with a fixture.
- `papers.nips.cc` is the legacy host with the same papers. Normalize to `proceedings.neurips.cc` in
  `urls.proceedings`.
- The year index `https://proceedings.neurips.cc/paper_files/paper/<YYYY>` lists every paper for that year.
  Crawl from it, not from search.
- `<sha>` is md5 of the paper's number. On `proceedings.neurips.cc` that number never repeats, so the
  native id is `nips-<sha>` (spec 01 §Record schema). **The 2021 D&B host numbers round 1, round 2 and the
  main track separately**: its live page (2026-09-29) had 27 hashes in both rounds and 27 shared with 2021
  main papers, all different papers (`docs/results/2026-09-29-proceedings-dry-runs.md`). There the id is
  `nips-<sha>-round1`/`-round2` (`urls.proceedings_native`), and a link without a round, or dated other than
  2021, is skipped as `no_round` (TASK-118). A listing's `count_ok` compares entries with the stated count,
  before ids exist (and passes when the page states none), so watch `skipped.duplicate` too.
- A PDF URL's abstract page is its `hash/<sha>-Abstract-<Track>.html` sibling by construction.
- Drop the query string (real links carry `?utm_source=…`).
- `proceedings.iclr.cc` uses the same grammar. It is not a spec 01 source today, so don't crawl it
  without a spec change.
- **NeurIPS 2021 D&B is on its own host**, `datasets-benchmarks-proceedings.neurips.cc` (verified
  2026-09-27; its index lists 2021 only): 174 papers, 66 Round 1 + 108 Round 2, equal to OpenReview's
  accepted Round 1 and Round 2. 2022+ D&B is on the main host.
- Year-page counts (2026-09-27): 2013 360, 2020 1,898, 2021 2,334, 2022 2,671 + 163 D&B, 2023 3,218 +
  322 D&B, 2024 4,034 + 459 D&B. 2022–2023 and 2024 D&B equal OpenReview's accepted counts; 2024 main is
  one short of OpenReview's 4,035, and 2021 main is 296 short of the 2,630 OpenReview v1 venues call
  accepted (TASK-054 resolves both).
- Pre-2022 abstract pages also link `<sha>-Metadata.json` and `<sha>-Reviews.html`.

## Track vocabulary (closed)
| Path `<Track>` | `track` |
|---|---|
| `Conference` | `main` |
| `Datasets_and_Benchmarks_Track` | `datasets_benchmarks` |
| `Datasets_and_Benchmarks` (≤2023 spelling) | alias → `Datasets_and_Benchmarks_Track` → `datasets_benchmarks` |
| `Position_Paper_Track` | `position` (OpenReview and the 2025 vol38 proceedings companion both carry it) |
| `round1`, `round2` (2021 D&B host only) | `datasets_benchmarks` |
| none (1987–2021 on `proceedings.neurips.cc`) | `main`, by host and year (see the grammar table) |
| `Creative_AI_Track` | `other` (keep the raw segment for audit) |
| anything else | `unknown`, counted (`unknown_track` in the import report) and flagged for attention; never a default (as built: `classify_proceedings`) |

The alias means one track never counts as two in the manifest. Mapping an unknown segment to `unknown`
(counted as `unknown_track` and flagged for attention) is deliberate: a new track silently defaulted to
`main` is a confident false keep.

## Abstract extraction (from the abstract page)
- Title: `<meta name="citation_title" content="…">`. Only take the abstract if this title matches the
  record's title (tolerate a leading `$…$` formula that other sources drop).
- Abstract: the `<p class="paper-abstract">` block. Block tags (`p`, `br`, `div`, `li`) become a space;
  inline tags (`<i>`, `<sub>`) vanish, so `<i>k</i>-means` stays `k-means`.
- Some pages are **double-escaped** (`&amp;amp;`; the 2025 year page has an author `&amp;quot;…&amp;quot;`). Unescape once, then decode only complete leftover
  entities. A bare `&` in `R&D` survives. The parsers keep references raw for that one decode, so each is
  re-emitted whole, `;` included: without it `&#x27;Catch` decoded to `⟊tch` and `&mdash;a` stayed `&mdasha`,
  and a garbled title then failed the `citation_title` match and lost its abstract (TASK-128).
- Collapse whitespace. Keep LaTeX verbatim. Reject a string that starts or ends with `…` (a snippet, not
  an abstract); an ellipsis inside a real abstract (`x₁, …, x_n`) is kept (spec 01, record-schema).
- Missing abstract: `abstract=null` and count it in the manifest (the report splits out
  `abstract_title_mismatch` and `page_missing`).

## The miner (as built, task-052)
`backend/src/openproceedings/ingest/sources/neurips.py`, run by `op ingest neurips --year <Y|Y-Y>`
(`--dry-run`, `--offline`, `--refresh`, `--delay`), cache under `<data-dir>/cache/neurips/`. Years before
2013 are refused (decision-013); a year whose index page isn't there (404) is refused as not published,
never read as empty. The track rules above live in `classify.classify_neurips_listing(host, year, token)`,
which returns the rule text that becomes the track claim's evidence; the RIS importer checks a NeurIPS
listing URL with the same function. Claims (source `neurips_proceedings`): venue, year, title, track,
status (`listed on <year index>`) and `urls.proceedings` at the year page's fetch time; abstract, authors
(`citation_author`, else the listing's), `urls.pdf` and `urls.doi` (`citation_doi`, 2024+) at the abstract
page's. From 2021 the report's `role` is `confirm`: dedup's precedence lets the proceedings decide
acceptance and OpenReview the track, and a disagreement is a `conflicts.csv` row. The year page's
`<span class="paper-count">` is the report's `stated` count, compared with the entries parsed (`count_ok`).
- **2025 splits its volumes.** The miner treats the base page and its recorded
  `/paper_files/paper/2025/vol38-main-conference` companion as one crawl. The report contains both listing
  reports and all four tracks. A “See also” URL outside this explicit pair remains in `see_also` and emits
  `listing_see_also_unfollowed`; discovering a link never silently broadens the crawl.

## Presentation
Only set `presentation` (`oral` / `spotlight` / `poster`) when the page or OpenReview states it. Never
infer it from ordering or file names.
