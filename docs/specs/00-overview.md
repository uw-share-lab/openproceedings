# openproceedings — system overview

Status: **draft for review** · 2026-09-25 · SHARE Lab, University of Waterloo

## Why this exists

Systematic reviews of ML research need a search they can *report*: a query string, a date, and a hit
count that anyone can re-run. Google Scholar can't give that for these venues (NeurIPS, ICLR and ICML, with AAAI, AIES and IASEAI added by
decision-049 and FAccT planned):

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
- Venues **indexed now**: NeurIPS (including the Datasets & Benchmarks track; from 1987), ICLR (from 2013), ICML
  (from 1988: on OpenReview, in PMLR, and before 2013 from a pinned dblp release; decision-047), AAAI (2010–2026),
  AIES (2024–2025) and IASEAI (2026), the last three from ojs.aaai.org (decision-049, milestone A).
- Venues **in scope and planned** (decision-049; milestones B and C of the
  [design](../plans/2026-10-09-new-venues-design.md), not built): AAAI 1980–2008, AIES 2018–2023 and FAccT
  2018 onward (every paper of every year, as decision-047 did for NeurIPS and ICML), IASEAI 2027 once its accepted
  papers are public, and an OpenAlex fallback for abstracts no official source holds (labelled, with an
  `abstract_kind:` filter). Until a milestone is built its venue-years are absent from the index and the coverage
  page, which says so (copy deck CV-7).
- Content: title and abstract, plus metadata (authors, venue, year, track, acceptance status, links).
- Search: exact-token Boolean search with phrases, proximity, explicit wildcards, field scopes, and
  filters written inside the query itself.
- UI: a query editor, a concept-group query builder, filters, highlighted results, export, and search
  records.

**Out of scope (for now):**
- Full text.
- Venues outside the seven above. ACL, EMNLP, NAACL, CHI and CSCW are a later extension; the record schema is
  designed for it. (FAccT, once listed here, moved into scope in decision-049.)
- User accounts.
- Citation graphs.
- Any matching that goes beyond the literal query: stemming, synonyms, or embeddings deciding what
  matches.
- The semantic layer ([06](06-semantic-layer.md): embedding re-sort and the near-miss panel). v1 is
  Boolean search only; 06 is deferred to phase 2 (decision-017).

## Guarantees (the invariants every part must uphold)

1. **Exactness.** A document matches a term only if that exact normalized token appears in the
   searched field. Normalization means case-folding, Unicode NFKC, mark folding (02 §Token semantics), and splitting on
   punctuation, as defined in [02](02-query-language.md). No step may add a match that the reference
   matcher in [03](03-search-engine.md) would not.
2. **Title and abstract only.** No other text field is ever searched by default. Metadata is reachable
   only through explicit filter fields (`venue:`, `year:`, `track:`, …).
3. **Filtering is part of the query.** A UI filter and the same filter written in the query compile to
   the same canonical query. A saved query string fully describes its result set.
4. **Reproducibility.** Every search response states `index_version`. Re-running a canonical query on
   the same `index_version` returns the identical ID set.
5. **Ranking never changes membership.** Field-weighted BM25 and the semantic layer only *order* the matched set, or
   *suggest* papers in a clearly separate panel. They never add to or remove from it, or change `total`.
6. **Transparency.** Wildcard expansions, parse warnings, and per-filter exclusion counts are shown to
   the user, never applied silently.

## Architecture

```
            ┌──────────────── ingestion (01) ────────────────┐
 OpenReview │ API v2 / v1 crawlers ─┐                         │
 PMLR, dblp,│ proceedings miners ───┼─► normalize ─► dedup ─► │ corpus snapshot
 ICML sites │                       │                         │
 NeurIPS    │ RIS importer (M2) ────┘   + track/status        │ (JSONL, content-hashed)
            └─────────────────────────────────────────────────┘
                                   │
                                   ▼
   query string ─► query language (02) ─► AST ─► search engine (03) ◄─ index build
   (UI or CLI)      parse · validate ·            Tantivy index + reference   (Tantivy, versioned)
                    canonicalize                  matcher (test oracle)
                                   │
                                   ▼
                          backend API (04)  ◄──── semantic layer (06, deferred: phase 2)
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
| Ingestion, query, index, API | **Python 3.12**, `uv`, FastAPI, pydantic v2 | Matches the lab's tools. The lab's own PyPI packages are pinned dependencies rather than copied code: `scholarmend` (RIS parsing, OpenReview venueid parsing and client, cache, claim ledger) for ingestion, and `refaudit` (BibTeX parser) for export tests. |
| Index | **Tantivy** via `tantivy-py` | Rust speed, positional index, phrase/slop/regex queries, BM25, and custom tokenizers with no stemmer. |
| Frontend | **Next.js (App Router) + TypeScript** | The lab already has Next.js experience. Hosting doesn't depend on Vercel. |
| Semantic (deferred: phase 2, decision-017) | SPECTER2 + a flat in-memory vector index | Built for scientific papers. About 80k vectors fit in RAM, so no vector database is needed. Not in v1. |
| Packaging | Docker Compose (`api`, `web`, `caddy` for TLS; one-off `ops` and `takedown-check`): data read-only but for the search records and the index lock files (`deploy/`, spec 08 §Deploy) | Hosting location is undecided. The index is read-only files, so it can run anywhere. |

## Parts and specs

| # | Spec | Owns |
|---|---|---|
| 01 | [Ingestion](01-ingestion.md) | Sources, record schema, track and status classification, dedup, snapshots |
| 02 | [Query language](02-query-language.md) | Grammar, token semantics, filters in the query, compatibility syntaxes, AST, canonical form |
| 03 | [Search engine](03-search-engine.md) | Tokenizer, index schema, AST→Tantivy compilation, ranking, reference matcher, versioning |
| 04 | [Backend API](04-backend-api.md) | HTTP contract, exports, search records, coverage |
| 05 | [Frontend](05-frontend.md) | Pages, query editor, query builder, filters, results, export |
| 06 | [Semantic layer](06-semantic-layer.md) | Embeddings, semantic re-sort, near-miss panel (deferred: phase 2, decision-017) |
| 07 | [Evaluation](07-evaluation.md) | Exactness fixtures, differential tests, Scholar comparison, coverage and performance |
| 08 | [Ops and tooling](08-ops-and-tooling.md) | Repo layout, CLI, CI, Docker, branch/PR rules, `.claude/` agents and skills roster |

## Milestones

| M | Deliverable | Done when |
|---|---|---|
| M0 | Repo, CI, `.claude/` roster (08) | CI green on an empty skeleton. Agents and skills lint clean. |
| M1 | Query language + tokenizer + reference matcher (02, 03 §oracle) | All exactness fixtures pass. The parser round-trips the review's search strings. |
| M2 | Index + CLI search over the Trust-Evals corpus (RIS import) (01 §RIS, 03) | `op search "<Most Updated string>"` runs. Differential tests against the oracle are green. |
| M3 | API + frontend MVP (04, 05) | The team can run the review's queries in a browser and export RIS into Covidence. |
| M4 | Full crawl of OpenReview and proceedings (01) | Every main-track and D&B cell with an official accepted count is within ±1%, or an owner-accepted exception (07 §C). |
| M5 | Semantic layer (06): **deferred** to phase 2 (decision-017); not on the v1 path | When resumed: near-miss panel live, and the invariant test proves membership never changes. |
| M6 | Hosting + public release | Licensing question resolved, repo made public, instance deployed. |

## Open questions (decide before the milestone named)

1. ~~**Abstract redistribution (M6).**~~ **Closed 2026-09-29 (decision-018):** a public instance serves
   every abstract, each record attributed to its source with a link to it, and a public instance names a
   takedown contact (private, local and development deployments may omit it). For the 2024+ conferences
   OpenReview's terms dedicate the abstracts under CC0; PMLR grants CC BY 4.0, known from ICML 2017 (v70);
   the years with no licence found (NeurIPS before 2021, ICML 2013–2016, earlier OpenReview years) rest on
   Canadian fair dealing alone. Consulting the University of Waterloo copyright office before launch is
   recommended (TASK-135), not a gate: the owner's decision is to show the abstracts whatever the answer.
   Not legal advice. The code is MIT either way. The corpus is never committed to git.
2. ~~**Rejected and withdrawn ICLR submissions (M4).**~~ **Closed 2026-09-27 (decision-012):** every
   public rejected, withdrawn and desk-rejected submission is indexed with `status:rejected`,
   `status:withdrawn` or `status:desk_rejected` and excluded by the default `status:accepted`, counted
   in the exclusion banner. ICLR publishes all of them; NeurIPS and ICML only those whose authors opt in.
3. ~~**Earliest year (M4).**~~ **Closed 2026-09-27 (decision-013), reopened and closed again 2026-10-06
   (decision-047):** every venue is crawled from its first year a spec 01 source holds: NeurIPS from 1987 (its
   proceedings), ICML from 1988 (the pinned dblp snapshot release until 2012, then PMLR and OpenReview; its
   pre-2013 abstracts only where an official ICML page gives one) and ICLR from 2013 (its first year, when it
   was already on OpenReview); the query's `year:` filter narrows it. decision-047 superseded decision-013's
   "years before 2013 stay out" at the owner's request, for the full history of both venues. So per-venue year
   coverage differs before 2013, which the coverage page says. OpenReview cannot establish conference acceptance
   for ICLR 2014–2016, so the public ICLR archive supplies those accepted main-track records (TASK-096).
4. **Planning tool (M0).** Backlog.md CLI (as in Kreate) or GitHub Issues.
5. **Hosting (M6).** A lab VM, a university server, or a PaaS.
