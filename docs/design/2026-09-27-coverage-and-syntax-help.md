# Coverage page and syntax help — design

Status: **reviewed**, handed off after the heuristic pre-pass · Backlog: TASK-033 → TASK-045 (tests in TASK-046) · Spec: 05 §Pages (`/coverage`,
`/help/syntax`); 02 §Token semantics, §Grammar, §Fields and filters, §Error handling; 04 `/coverage` ·
Index: [search workspace](2026-09-27-search-workspace.md)

## Problem and job

| Persona | JTBD | Risk removed |
|---|---|---|
| Lead reviewer | When I describe the database in my methods section, I want its exact scope (venues, years, tracks, statuses, missing abstracts, snapshot), so I can state what was and wasn't searchable | citing a count without saying a venue-year has no abstracts |
| Methods peer reviewer | When I check a search, I want to see what the index held, so I can judge whether the search could have found what it claims | — |
| Newcomer student | When a diagnostic tells me something is wrong, I want the rule and a valid example one click away, so I can fix it | a help page that disagrees with the parser |

Evidence: PRISMA-S asks for the database name, its coverage and dates (`prisma-reporting`); spec 07 §C makes the
coverage report the database-scope caveat the methods text cites. The newcomer need is an assumption.

## `/coverage` (TASK-045)

### States
| State | Must show |
|---|---|
| Loaded | snapshot facts, totals, the venue × year table, per-row track × status detail |
| Loading | skeleton of the header lines (no fake numbers) |
| Error | 429/503/non-JSON/500 as `/search` W9–W10 (retry, no auto-retry) |
| A venue-year with 0 abstracts | the missing-abstract count in the row, flagged `⚠` with text "no abstracts: only titles are searchable" |
| Narrow | the table scrolls **inside its own region** (a labelled, focusable scroll container), the page doesn't; the first column is sticky |

### C1 Loaded

```
# Coverage
Index a1b2c3d4e5f6 {index_version} [Copy] · tokenizer 2 · query version 2
Snapshot trust-evals-2026-09-18 {snapshot.name} · {snapshot_hash, whole} [Copy]
Built 2026-09-20 08:14 UTC {built_at} · Collected 2026-09-18 to 2026-09-20 {crawl_dates["*"]}
Sources: openreview, pmlr, neurips_proceedings {snapshot.sources}

1,805 records {totals.records} · 37 without an abstract {totals.abstract_missing} ·
3 of unknown track {totals.unknown_track} · 0 of unknown status {totals.unknown_status}
Only titles and abstracts are indexed. A record without an abstract can be found by its title only.

| Venue   | Year | Records | No abstract | Unknown track | Unknown status |         |
|---------|------|--------:|------------:|--------------:|---------------:|---------|
| ICLR    | 2025 |     412 |           0 |             0 |              0 | Details ▸ |
| ICLR    | 2024 |     388 |           2 |             1 |              0 | Details ▸ |
| ICML    | 2023 |     201 |           0 |             0 |              0 | Details ▸ |
| NeurIPS | 2017 |      96 |           4 |             0 |              0 | Details ▸ |
| NeurIPS | 1988 |      91 |        ⚠ 91 |             0 |              0 | Details ▸ |   (illustrative)
  …
  Details ▾ (ICLR 2024): track × status, from {cells}
  |          | accepted | rejected | withdrawn | desk_rejected | unknown |
  | main     |      301 |       62 |         9 |             2 |       0 |
  | workshop |       14 |        0 |         0 |             0 |       0 |
```
- Every number is an API field; the page never adds cells into row or column totals (the row's Records is
  `venue_years[].records`, from the API). A track × status pair with no cell shows `–` (none), never `0` made up.
- Rows are ordered venue (A–Z), then year (newest first); the table has a caption naming the snapshot, `<th
  scope>` headers, and `tabular-nums`.
- "Collected … to …" is neutral on purpose: `/coverage` doesn't say what kind the window is (a crawl or Scholar
  query dates), and the page must never call Scholar search dates a crawl (prisma-reporting). See API fields.
- No chart in M3b: the table is what a methods section cites. A chart can come with the research-dataviz work.

### Keyboard and screen reader
Details ▸ is a disclosure button per row (`aria-expanded`, `aria-controls` the detail row); the detail table
has its own caption ("ICLR 2024: records by track and status"). The scroll container has `role=region`,
`aria-label="Coverage table"` and `tabindex=0`, so keyboard users can scroll it (1.4.10 allows 2-D scroll for
data tables).

### API fields needed
| Need | Status |
|---|---|
| everything in C1 | exists (`CoverageResponse`) |
| what kind the collection window is (`crawl` / `scholar_query_dates` / `mixed`) and whether the corpus is bootstrap-only | **exists** (TASK-091): `snapshot.crawl_dates_kind` and `snapshot.identification_citable`, derived as a record's. The page can now word the window by its kind and show the citability line |

## `/help/syntax` (TASK-045)

### Structure

Generated, not written (spec 05; nextjs-conventions): every example and every message comes from the same
golden data the parser's tests read, so the page can't drift from the tests.

```
# Query syntax
On this page: Matching · Phrases · AND, OR, NOT · Wildcards · NEAR · Fields · Filters ·
Default filters · Google Scholar syntax · Limits · Messages (A–Z)

## Matching: exact words only
A word matches only that exact word after normalising case, accents and punctuation: no stemming,
no synonyms, no stopwords. `benchmark` does not find `benchmarks`; write `benchmark$` or `benchmark*`.
| You type | Indexed as | Matches |            ← generated from the spec 02 golden token table
| `LLM-as-a-judge` | `llm as a judge` | … |
| `$\alpha$` | `α` | … |
[Search with this example ▸] on each row → /search?q=<example>&mode=<its mode>

## Wildcards
`*` any ending, `$` zero or one character. At least 3 letters or digits before it; at most 200 matching
words; allowed inside a phrase ("large language model$").
…
## Messages
### PARSE_UNBALANCED_PAREN  {id="parse_unbalanced_paren"}
Example: `(trust OR reliance`
Message: This `(` is never closed — add a `)`.
Fix: `(trust OR reliance)`   [Search with this example ▸]
…
### Slow clauses: API_TOO_MANY_VERIFIED_CLAUSES, API_QUERY_TOO_COSTLY  {id="slow-clauses"}
What a position-verified clause is (a phrase with a wildcard item, a NEAR), the instance's limits from
`/meta` `limits` (16 clauses, 300,000 documents), and how to narrow a clause (longer stems, rarer words).
```

- **Anchors** are the diagnostic code in lower case (`#wildcard_stem_too_short`), so the Help ▸ link on every
  diagnostic can be built from its code without a mapping table. The two slow-clause codes share
  `#slow-clauses`; each code also gets its own anchor pointing there.
- The **Messages** section lists every code in `DiagnosticCode` that a reader can meet (the `PARSE_*`,
  `FIELD_*`, `WILDCARD_*`, `WARN_*`, `COMPAT_*` codes and the two slow-clause `API_*` codes), each with an
  example input, the registry message it produces, and a fixed version where one exists. A test fails if a
  code has no entry.
- **Limits** reads `/meta` `limits` at request time (2,000 characters for the canonical form as well as the
  input, and the ranges spec 02 lists; 64 levels; 16 verified clauses; 300,000 candidate documents), so an
  instance with other limits shows its own.
- **Search with this example ▸** opens `/search?q=<example>&mode=<example's mode>`: each golden example
  carries its mode, so the `COMPAT_*`, `WARN_SOURCE_PARTIAL` and `WARN_FILTER_SCOPE` examples open in Scholar
  mode (pre-pass S15). It runs the search at once, so its label says so (the home page's examples only load).

### States
Static apart from the Limits section: if `/meta` fails, that section says "This instance's limits couldn't be
loaded" and shows the defaults from `frontend/src/lib/default-limits.json` labelled "defaults".

### Keyboard and screen reader
A contents list of in-page links (skip-to-section); headings `h2` per section, `h3` per code; examples are
`<code>`; tables have `<th scope>`. Nothing interactive beyond links.

### Generation (TASK-045 implementation note)
Export the golden data (token table, diagnostics examples with their messages) from the backend to a committed
JSON file under `frontend/src/help/`, checked by a backend contract test the way
`frontend/src/lib/wrap-golden.json` is (`backend/tests/contract/test_frontend_wrap_golden.py`), so a changed
message or rule turns a test red until the file is regenerated.

## Copy
Copy deck §Coverage, §Syntax help.

## Heuristic pass
[Pre-pass](2026-09-27-heuristic-prepass.md) S15 and Nit 7 are fixed above; self-check SC-30 to SC-32.

## Open questions
1. Should `/coverage` offer a CSV of the table for supplementary material? Not required by spec 05; add if
   TASK-047 reviewers ask.
