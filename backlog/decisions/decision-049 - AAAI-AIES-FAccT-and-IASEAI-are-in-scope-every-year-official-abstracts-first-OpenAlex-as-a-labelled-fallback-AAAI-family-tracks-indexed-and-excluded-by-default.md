---
id: decision-049
title: >-
  AAAI, AIES, FAccT and IASEAI are in scope, every year; official abstracts
  first, OpenAlex as a labelled fallback; AAAI-family tracks indexed and
  excluded by default
date: '2026-10-10 01:56'
status: accepted
---
## Context

On 2026-10-09 the owner asked for AAAI, AIES, FAccT and IASEAI to join the corpus. Spec 00 §Scope listed three
venues (NeurIPS, ICLR, ICML) and named FAccT, among others, as a later extension. The design is
`docs/plans/2026-10-09-new-venues-design.md`; the sources were checked live on 2026-10-09
(`docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md`).

## Decision

The owner's seven decisions of 2026-10-09:
1. AAAI, AIES, FAccT and IASEAI join the corpus scope.
2. Every paper of every year, as decision-047 did for NeurIPS and ICML: AAAI from 1980, AIES and FAccT from 2018,
   IASEAI from 2026 (IASEAI '25 published no papers).
3. Abstracts are searched for every paper that has one. Precedence: the official source's abstract, else
   OpenAlex's (these four venues only), else `null`. The abstract's origin is labelled, filterable
   (`abstract_kind:`) and counted.
4. Everything is indexed with its real track. The default filter (`track:(datasets_benchmarks OR main OR
   position)`, `status:accepted`) is unchanged, so the new non-main tracks are excluded by default and counted
   in the exclusion buckets, as `competition` and `tiny_papers` are; one `track:` clause brings them back.
5. IAAI and EAAI, printed in the AAAI volumes, are `venue:AAAI` with tracks `iaai` and `eaai`.
6. One source module per official host plus an OpenAlex abstract-fill step. Rejected: dblp for everything (its
   release lags new years and has no AAAI sections) and OpenAlex for everything (truncated and duplicate DOIs, no
   tracks).
7. TASK-202 (the scheduled crawl) covers every source in scope, and every doc is updated as built.

## Supersedes

Spec 00 §Scope's venue list ("the three above") and its "later extension" line, which named FAccT. ACL, EMNLP,
NAACL, CHI and CSCW remain out of scope for now.

## Consequences

- `RECORD_SCHEMA_VERSION` 5 → 6 (five new track values, four new venues, the `ojs` claim source, the `ojs-`
  native id), then 6 → 7 in milestone B (the `crossref` and `facct_site` claim sources, the `doi-<toc>.<n>` native id,
  `dblp-` ids for AAAI 1980–2008). The corpus grows from about 141k to about 173k records (173,292 after milestone B's build).
- **Milestone A (built):** vocab, record schema 6, the `ojs` source (`sources/ojs.py`, `ojs_harvest.py`,
  `ojs_table.py` with `ojs_sections.toml`, `op ingest ojs`), the HTTP layer's XML responses and the research
  note. It brings AAAI 2010–2026 (25,126 records; 25,128 before the 2023 Errata were ruled front matter), AIES 2024–2025 (449) and IASEAI 2026 (57) from
  ojs.aaai.org.
- **Milestone B (built, 2026-10-10):** AAAI 1980–2008 from the pinned dblp release (`dblp_aaai.toml`,
  `sources/dblp_aaai.py`, `op ingest dblp --venue AAAI`: 4,730 records in 23 held years, none in 1981, 1985, 1989,
  1995, 2001, 2003 or 2009), ACM proceedings through Crossref (`acm_proceedings.toml`, `sources/crossref.py`,
  `op ingest crossref`: FAccT 2019–2026 1,213 records, AIES 2018–2023 575), PMLR v81 (FAccT 2018: 17, so FAccT is
  1,230 records; `op ingest pmlr --venue FAccT`) and the FAccT site's official abstracts for 2022, 2025 and 2026
  (169 of 181, 206 of 206, 298 of 314; `facct_site.toml`, `sources/facct_site.py`). Schema 7. `CROSSREF_MAILTO` is
  optional (the public pool without it). Crossref carries no section data, so AIES 2018–2023's student abstracts and
  keynotes are in `main`. No source was added for the scheduled crawl's `facct-site` target: it is folded into
  `crossref`. Spec 01 §Sources has the rows; the design's "Milestone B as built" note records where the build
  departs from the plan.
- **Milestone C (planned):** the OpenAlex abstract fill, `abstract_kind` and its filter (index schema 4),
  the coverage and abstract-origin copy, the snapshot and index build, and the benchmarks at the larger size.
- Spec 00's venue list says what is indexed now and what is in scope and planned; a venue-year appears in the
  coverage report only once it is crawled.
- Licence posture is the one already used for PMLR and NeurIPS (titles and abstracts with links back; AAAI
  copyright is stated on ojs.aaai.org); the takedown process covers all venues.
- Sections the design did not name are mapped to `other` and listed for owner review in the research note.
