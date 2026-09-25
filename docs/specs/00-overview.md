# openproceedings — system overview

Status: **draft for review** · 2026-09-25 · SHARE Lab, University of Waterloo

## Why this exists

Systematic reviews of ML research need a search they can *report*: a query string, a date, and a hit
count that anyone can re-run. Google Scholar can't give that for NeurIPS, ICLR and ICML:

| Problem with Scholar | What openproceedings does instead |
|---|---|
| Matches anywhere in the **full text** | Searches **title and abstract only**. The corpus never holds full text. |
| **Stems** and fuzzes terms (`benchmarking` also finds `benchmark`) | **No stemming, no synonyms, no stopword removal.** A term matches that exact token. Plural or suffix matching happens only when you write a wildcard. |
| Mixes **workshop** papers in with main-track papers, with no way to filter them out | Every paper has a `track`. Workshops are excluded by default, and the number excluded is reported. |
| Results drift over time and can't be reproduced | Every result carries an **index version**. A saved *search record* can be re-run against the same snapshot. |
| Exports are truncated (snippets, `…` venues) | Exports are RIS, CSV or BibTeX with full abstracts and exact venue/track, ready for Covidence. |

OpenReview hosts most of this corpus but has no Boolean search at all.

The first user is the Trust-Evals systematic review. The system is general to any review over these
venues.

## Scope

**In scope (v1):**
- Venues: NeurIPS (including the Datasets & Benchmarks track), ICLR, ICML (on OpenReview and in PMLR).
- Content: title and abstract, plus metadata (authors, venue, year, track, acceptance status, links).
- Search: exact-token Boolean search with phrases, proximity, explicit wildcards, field scopes, and
  filters written inside the query itself.
- UI: a query editor, a concept-group query builder, filters, highlighted results, export, and search
  records.

**Out of scope (for now):**
- Full text.
- Venues outside the three above. ACL, EMNLP, NAACL, FAccT, CHI and CSCW are a later extension; the
  record schema is designed for it.
- User accounts.
- Citation graphs.
- Any matching that goes beyond the literal query: stemming, synonyms, or embeddings deciding what
  matches.

## Guarantees (the invariants every part must uphold)

1. **Exactness.** A document matches a term only if that exact normalized token appears in the
   searched field. Normalization means case-folding, Unicode NFKC, diacritic folding, and splitting on
   punctuation, as defined in [02](02-query-language.md). No step may add a match that the reference
   matcher in [03](03-search-engine.md) would not.
2. **Title and abstract only.** No other text field is ever searched by default. Metadata is reachable
   only through explicit filter fields (`venue:`, `year:`, `track:`, …).
3. **Filtering is part of the query.** A UI filter and the same filter written in the query compile to
   the same canonical query. A saved query string fully describes its result set.
4. **Reproducibility.** Every search response states `index_version`. Re-running a canonical query on
   the same `index_version` returns the identical ID set.
5. **Ranking never changes membership.** BM25F and the semantic layer only *order* the matched set, or
   *suggest* papers in a clearly separate panel. They never add to or remove from it, or change `total`.
6. **Transparency.** Wildcard expansions, parse warnings, and per-filter exclusion counts are shown to
   the user, never applied silently.

## Architecture

```
            ┌──────────────── ingestion (01) ────────────────┐
 OpenReview │ API v2 / v1 crawlers ─┐                         │
 PMLR       │ proceedings miners ───┼─► normalize ─► dedup ─► │ corpus snapshot
 NeurIPS    │ RIS importer (M2) ────┘   + track/status        │ (JSONL, content-hashed)
            └─────────────────────────────────────────────────┘
                                   │
                                   ▼
   query string ─► query language (02) ─► AST ─► search engine (03) ◄─ index build
   (UI or CLI)      parse · validate ·            Tantivy index + reference   (Tantivy, versioned)
                    canonicalize                  matcher (test oracle)
                                   │
                                   ▼
                          backend API (04)  ◄──── semantic layer (06, phase 2)
                          FastAPI: search · parse · export ·        re-sort + near-miss panel
                          search records · coverage
                                   │
                                   ▼
                          frontend (05) — Next.js + TypeScript
```

The evaluation suite ([07](07-evaluation.md)) checks every layer. Operations and repo tooling
([08](08-ops-and-tooling.md)) wrap the whole thing.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Ingestion, query, index, API | **Python 3.12**, `uv`, FastAPI, pydantic v2 | Matches the lab's tools. We can reuse scholarmend's OpenReview client and cache patterns. |
| Index | **Tantivy** via `tantivy-py` | Rust speed, positional index, phrase/slop/regex queries, BM25, and custom tokenizers with no stemmer. |
| Frontend | **Next.js (App Router) + TypeScript** | The lab already has Next.js experience. Hosting doesn't depend on Vercel. |
| Semantic (phase 2) | SPECTER2 + a flat in-memory vector index | Built for scientific papers. About 80k vectors fit in RAM, so no vector database is needed. |
| Packaging | Docker Compose (`api`, `web`, read-only data volume) | Hosting location is undecided. The index is read-only files, so it can run anywhere. |

## Parts and specs

| # | Spec | Owns |
|---|---|---|
| 01 | [Ingestion](01-ingestion.md) | Sources, record schema, track and status classification, dedup, snapshots |
| 02 | [Query language](02-query-language.md) | Grammar, token semantics, filters in the query, compatibility syntaxes, AST, canonical form |
| 03 | [Search engine](03-search-engine.md) | Tokenizer, index schema, AST→Tantivy compilation, ranking, reference matcher, versioning |
| 04 | [Backend API](04-backend-api.md) | HTTP contract, exports, search records, coverage |
| 05 | [Frontend](05-frontend.md) | Pages, query editor, query builder, filters, results, export |
| 06 | [Semantic layer](06-semantic-layer.md) | Embeddings, semantic re-sort, near-miss panel (phase 2) |
| 07 | [Evaluation](07-evaluation.md) | Exactness fixtures, differential tests, Scholar comparison, coverage and performance |
| 08 | [Ops and tooling](08-ops-and-tooling.md) | Repo layout, CLI, CI, Docker, branch/PR rules, `.claude/` agents and skills roster |

## Milestones

| M | Deliverable | Done when |
|---|---|---|
| M0 | Repo, CI, `.claude/` roster (08) | CI green on an empty skeleton. Agents and skills lint clean. |
| M1 | Query language + tokenizer + reference matcher (02, 03 §oracle) | All exactness fixtures pass. The parser round-trips the review's search strings. |
| M2 | Index + CLI search over the Trust-Evals corpus (RIS import) (01 §RIS, 03) | `op search "<Most Updated string>"` runs. Differential tests against the oracle are green. |
| M3 | API + frontend MVP (04, 05) | The team can run the review's queries in a browser and export RIS into Covidence. |
| M4 | Full crawl of OpenReview and proceedings (01) | Coverage page within ±1% of official accepted counts for each venue-year. |
| M5 | Semantic layer (06) | Near-miss panel live. The invariant test proves membership never changes. |
| M6 | Hosting + public release | Licensing question resolved, repo made public, instance deployed. |

## Open questions (decide before the milestone named)

1. **Abstract redistribution (M6).** Can a public instance serve abstracts? OpenReview's terms and the
   NeurIPS and PMLR proceedings terms differ. The code is MIT either way. The corpus is never committed
   to git.
2. **Rejected and withdrawn ICLR submissions (M4).** They are public on OpenReview. Proposal: index them
   with `status:rejected` / `status:withdrawn` and apply `status:accepted` by default, the same pattern
   as workshops.
3. **Earliest year (M4).** The review uses 2020–2026. Proposal: crawl from 2018 (ICLR's first year on
   OpenReview) and filter by year in the query.
4. **Planning tool (M0).** Backlog.md CLI (as in Kreate) or GitHub Issues.
5. **Hosting (M6).** A lab VM, a university server, or a PaaS.
