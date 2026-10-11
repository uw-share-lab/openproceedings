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
- **Milestone C (built, 2026-10-10):** the OpenAlex abstract fill (`sources/openalex.py`, `openalex_table.py` with
  `openalex_sources.toml`, `op ingest openalex`, last in a full crawl; `OPENALEX_API_KEY` optional, no contact address
  sent), `abstract_kind` and its `abstract_kind:` filter (index schema 4), the coverage, export and label copy, and the
  fidelity audit (`op eval openalex`).
  - **Record schema 7 → 8:** the `openalex` claim source (an `abstract` claim only, AAAI, AIES and FAccT only) and the
    derived, never-stored `abstract_kind` (`official`, `openalex`, `none`).
  - **Index schema 3 → 4:** `abstract_kind` is a raw fast field, and each engine's facets and combos are its own.
    Schemas 3 and 4 are served; **schema 2 is retired** (its four local indexes were checked with `op index retire
    --dry-run`: 0 pins). A schema-3 index refuses `abstract_kind:` with `FIELD_NOT_INDEXED` and cannot be built from
    a snapshot holding an OpenAlex abstract, so promoting an OpenAlex-filled snapshot needs a schema-4 index.
  - **The fill is a post-dedup step** (after reconcile, before takedowns) replaying a pinned extract, so it only ever
    touches a record whose abstract is still `null`, never an official one, and a takedown still withholds what it
    filled.
  - **No `QUERY_VERSION` change:** a query naming `abstract_kind:` was a `FIELD_UNKNOWN` error before.
  - **Licence:** OpenAlex's data is CC0, but it ships no plaintext abstracts, so serving a rebuilt abstract carries the
    publisher-abstract posture (this decision's fair-dealing basis, the takedown list and the pending copyright-office
    consultation, TASK-135), not a CC0 one. The label and the filter let a review exclude them.
  - **Fidelity:** OpenAlex agrees with the official abstract (exact or near-exact) for 83.1% of 2,122 records audited,
    almost always for AAAI and AIES and far less for FAccT, where it likely carries ACM's published version; every
    title-route attach for AAAI 1980–2008 was checked (1,052 of 1,061 agree; the exact title-key rule stands).
    `docs/results/2026-10-10-openalex-audit.md`; spec 07 §G.
  - **As built (2026-10-10).** Extract sha256 `7fea58b983252594b9ad3fb4788022f81b64adf579ce9cee129abf91a9c5c49c` (5,808
    candidates, 49 lookups, 3,005 works). Snapshot `2026-10-10-22a339940466` (173,253 records), which differs from
    `2026-10-10-9efa49481112` only in 2,158 abstracts (`none` → `openalex`; 1,097 of 1,099 by DOI and 1,061 of 4,709 AAAI
    1980–2008 by title, so 3,648 of those stay without one). Index `9977ed00669f` (schema 4): parity with 0
    differences, and `abstract_kind:openalex` gives 2,158 on both engines. The four schema-2 indexes were deleted on
    2026-10-10. The coverage gate passes (83 of 84 gated cells; ICLR 2013 is the accepted exception). The group-count
    benchmark is within budget on the real corpus (worst p95 76.5 ms) and over it on the synthetic 80k for
    `main-3-sources` (110.7 ms, 65 ms without group counts: TASK-176's counting, not schema 4), recorded in spec 03
    §Performance budgets and followed up in TASK-230.
  - **Gate rows, one independence rule (milestone C review, gate C round 1, 2026-10-11; recorded here because the
    backlog CLI can't edit TASK-219, which is completed; restated in gate C round 2).** A count of AAAI's own
    accepted-paper list backs a gate row only when the list is independent of the proceedings. A list counts as independent of the proceedings when it either states that it is pre-camera-ready, or visibly differs from the proceedings in content (a different count or membership); either shows it was not derived from them. AAAI 2012, 2017, 2020 and 2021 are gated, each row naming its ground: 2020's lists say they were made
    before camera-ready; 2012, 2017 and 2021 differ from the proceedings in count. AAAI 2010 (262), 2014 (398) and
    2016 match the proceedings exactly and are not shown to predate them (2010's and 2014's only archived copies
    were captured after publication, on 2010-08-30 and 2015-09-06), so each is an ungated cell with a cited note. `official_counts.py`, `docs/results/coverage-sources.md` and their tests are
    updated, and the gate is expected at 81 of 82 cells once the coverage report is regenerated after the rebuild.
- Spec 00's venue list says what is indexed now and what is in scope and planned; a venue-year appears in the
  coverage report only once it is crawled.
- Licence posture is the one already used for PMLR and NeurIPS (titles and abstracts with links back; AAAI
  copyright is stated on ojs.aaai.org); the takedown process covers all venues.
- Sections the design did not name are mapped to `other` and listed for owner review in the research note.
