---
name: neurips-proceedings
description: The proceedings.neurips.cc source — the paper_files URL grammar, the closed track vocabulary (Conference, Datasets_and_Benchmarks_Track, Position_Paper_Track, Creative_AI_Track) and the ≤2023 Datasets_and_Benchmarks alias, abstract-page extraction gotchas, and its role as the only NeurIPS source before 2021 and a cross-check after. Use when writing or reviewing the NeurIPS proceedings miner, its fixtures, or a NeurIPS coverage mismatch.
---

# NeurIPS proceedings (spec 01 §Sources)

## Role
- **The only source** for NeurIPS before 2021 (main track; D&B starts in 2021).
- A **cross-check** for 2021+ (OpenReview v1/v2 is primary for track and status). An OpenReview-accepted
  paper missing from the proceedings, or the reverse, is a `conflicts.csv` row. It never silently flips
  status.
- The proceedings list **accepted papers only** and never host workshop papers. That is why the
  path's track segment discriminates so well. It also means proceedings can never supply
  `status: rejected`.

## URL grammar
```
https://proceedings.neurips.cc/paper_files/paper/<YYYY>/{hash|file}/<sha>-{Abstract|Paper}-<Track>.{html|pdf}
```
- `papers.nips.cc` is the legacy host with the same papers. Normalize to `proceedings.neurips.cc` in
  `urls.proceedings`.
- The year index `https://proceedings.neurips.cc/paper_files/paper/<YYYY>` lists every paper for that year.
  Crawl from it, not from search.
- `<sha>` is stable per paper, so the native id is `nips-<sha>` (spec 01 §Record schema).
- A PDF URL's abstract page is its `hash/<sha>-Abstract-<Track>.html` sibling by construction.
- Drop the query string (real links carry `?utm_source=…`).
- `proceedings.iclr.cc` uses the same grammar. It is not a spec 01 source today, so don't crawl it
  without a spec change.
- NeurIPS 2021 D&B may be on a separate host (`datasets-benchmarks-proceedings.neurips.cc`). Verify at
  implementation time and record the answer in the miner's docstring.

## Track vocabulary (closed)
| Path `<Track>` | `track` |
|---|---|
| `Conference` | `main` |
| `Datasets_and_Benchmarks_Track` | `datasets_benchmarks` |
| `Datasets_and_Benchmarks` (≤2023 spelling) | alias → `Datasets_and_Benchmarks_Track` → `datasets_benchmarks` |
| `Position_Paper_Track` | `position` (verify with the spec owner: spec 01 names only ICML's position track) |
| `Creative_AI_Track` | `other` (keep the raw segment for audit) |
| anything else | **raise `UnknownTrack`**, never default |

The alias means one track never counts as two in the manifest. Raising on an unknown segment is
deliberate: a new track silently defaulted to `main` is a confident false keep, which is much harder to
notice than a crash.

## Abstract extraction (from the abstract page)
- Title: `<meta name="citation_title" content="…">`. Only take the abstract if this title matches the
  record's title (tolerate a leading `$…$` formula that other sources drop).
- Abstract: the `<p class="paper-abstract">` block. Block tags (`p`, `br`, `div`, `li`) become a space;
  inline tags (`<i>`, `<sub>`) vanish, so `<i>k</i>-means` stays `k-means`.
- Some pages are **double-escaped** (`&amp;amp;`). Unescape once, then decode only complete leftover
  entities. A bare `&` in `R&D` survives.
- Collapse whitespace. Keep LaTeX verbatim. Reject any string containing `…`, which is a snippet and not
  an abstract.
- Missing abstract: `abstract=null` and count it in the manifest.

## Presentation
Only set `presentation` (`oral` / `spotlight` / `poster`) when the page or OpenReview states it. Never
infer it from ordering or file names.
