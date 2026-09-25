# 05 — Frontend

Status: **draft for review** · depends on: 04 (generated API types) · consumed by: people

## Purpose

A research tool, not a consumer search box. It helps a reviewer write a precise query, see exactly how
it was read, trust the result set, and move that set into screening. Hosting is not tied to Vercel: build
with `output: "standalone"` so it runs in the Docker image (08).

## Stack

Next.js (App Router) + TypeScript (strict). Tailwind + shadcn/ui for components. CodeMirror 6 for the query
editor. TanStack Query for API state. Types are generated from 04's OpenAPI schema, not written by hand.
Tests: Vitest + Testing Library (units), Playwright (e2e against the fixture API).

## URL is state (guarantee 3)

`/search?q=<input>&mode=native|scholar&sort=relevance&page=2`. Nothing that affects the result set lives
outside `q`. Filters, facet clicks and builder edits all **rewrite `q`**. Copying the URL copies the search.

## Pages

| Route | Content |
|---|---|
| `/` | Search home: the editor, example queries (the review's strings), a coverage summary line |
| `/search` | The main workspace (below) |
| `/paper/[id]` | Full record: abstract with the current query's highlights, all links, provenance table |
| `/record/[id]` | Search-record page: the identification string and the default clauses, full index version, search date and crawl date, total, exclusions (`unknown` on its own line), replay status (`reproduced` / `drifted` with its reason / `mismatch`), a "Copy methods text" button, and export buttons pinned to the record's index. On `mismatch` the page is a blocking **"do not cite — replay mismatch"** state with no methods text and no export |
| `/coverage` | Venue × year × track table with source and snapshot date, missing-abstract counts, `unknown` counts |
| `/help/syntax` | Language reference generated from the 02 golden table (it cannot drift from the tests) |

## `/search` layout

```
┌────────────────────────────────────────────────────────────────────────────┐
│ [ Text | Builder ]   mode: [native ▾]                              [Search] │
│ ┌────────────────────────────────────────────────────────────────────────┐ │
│ │ ("foundation model" OR LLM) AND trustworth* AND benchmark …            │ │ ← CodeMirror
│ └────────────────────────────────────────────────────────────────────────┘ │
│ ⚠ AND/OR mixed without parentheses — read as: (A AND B) OR C   [show tree] │ ← diagnostics
│ trustworth* → trustworthy, trustworthiness                                  │ ← expansion chips
├──────────────┬─────────────────────────────────────────────────────────────┤
│ Venue  ☑☑☑   │ 412 papers · index a1b2c3 · excluded: 212 workshop, 88      │
│ Year [2023–] │   rejected [include ▸]      [Export ▾] [Save search record] │
│ Track        │ ─────────────────────────────────────────────────────────── │
│  ☑ main      │ **TrustLLM**: Trustworthiness in Large Language Models       │
│  ☑ D&B       │ ICML 2024 · main · poster                                   │
│  ☐ workshop  │ …evaluate the **trustworthiness** of **LLMs** across six… │
│ Status       │                                                             │
└──────────────┴─────────────────────────────────────────────────────────────┘
```

## Components

1. **Query editor (CodeMirror 6).** Syntax highlighting from a Lezer grammar that mirrors 02. Colour for
   operators, fields, phrases and wildcards. Inline squiggles from `/parse` diagnostics (debounced 250 ms)
   using the spans the server returns. Autocomplete for fields and for the `track:`/`venue:` values from
   `/meta`. The **server's parser is authoritative.** The client grammar only highlights, it never
   decides.
2. **"How we read your query."** A collapsible tree view of the AST, with the default filters shown in grey
   as explicit clauses.
3. **Query builder.** Mirrors how the review's strings are structured: **concept groups** (rows). Terms
   inside a row are ORed, and rows are ANDed, e.g. AI-system terms × trust terms × benchmark terms. Each
   term can be a word, phrase or wildcard, with a per-term field scope. The builder round-trips through the
   AST. Switching from text to builder is allowed only when the AST fits the group shape; otherwise the
   builder shows "this query is too complex for the builder" and stays read-only.
4. **Filter sidebar.** Venue, year range, track, status. Workshop is **off by default**. Each control shows
   its count and **edits the `track:`/`status:` clauses in `q`**.
5. **Exclusion banner.** "212 workshop · 4 competition · 88 rejected excluded by default filters", with
   `unknown` itemised on its own line ("3 unclassified"). Each has an "include" action, and **its label shows
   the number that clicking it will actually add**. That number is the facet count, which differs from the
   bucket count when a paper fails both defaults (for example, a rejected workshop paper). The tooltip explains
   the PRISMA mapping and the fixed bucket order (track, then status; 03). Clicking "include" writes a
   non-default `track:`/`status:` set into `q`. That set is no longer a default, so its exclusions stop
   being automation removals and become user limits in the identification string, and the methods text
   changes to match (03 §Exclusion accounting). The tooltip says so before the click.
6. **Result list.** Title and abstract with highlights taken exactly from the API spans (never re-matched
   on the client). Venue/year/track badges. Links to OpenReview, PDF and proceedings. Uses infinite scroll
   or pages (decided at implementation time; both keep the ordering stable).
7. **Export menu.** RIS (Covidence), CSV, BibTeX, JSONL. Shows the count before downloading.
8. **Save search record.** Creates `/records` and shows the permanent link plus generated methods text
   that says which string reproduces which number:
   *"We searched openproceedings on 2026-09-25 (index `a1b2c3d4e5f6`, built from a crawl of 2026-09-20) with
   the string `<identification_query>`, which identified 716 records within the limits it states
   (`year:2020..2026`). Default filters `track:(main OR datasets_benchmarks OR position)` and
   `status:accepted` removed 304 of them before screening (212 workshop, 4 competition, 88 rejected); that
   count includes 0 unclassified records (track or status unknown), itemised separately. Cross-source
   duplicates were merged at ingest, before indexing (see the coverage report). Database scope: coverage
   report for snapshot `<snapshot_hash>`. 412 records were screened. Search record: <url>."*
   It always gives the **full** `index_version`, never a prefix. The limits clause names every filter the
   user wrote (03 §Exclusion accounting: "identified" is conditional on them) and reads "with no limits"
   when there are none. The coverage report is cited with its snapshot hash as the database-scope caveat
   (07 §C). A review may instead report the default filters as limits, citing the canonical string; the
   record stores both strings, so either framing can be cited.

## Error handling

- API errors are shown from the envelope's `code` and `message` (04 §Error handling), never as a raw
  status or a generic "something went wrong". A parse `422` draws its diagnostics as squiggles at their
  spans, and the search view keeps the last good result set, marked as stale.
- `429 API_RATE_LIMITED` shows the wait from `Retry-After`. `503 API_INDEX_NOT_LOADED` shows a
  "search index is loading" state with a retry.
- A `mismatch` replay is the blocking "do not cite" state of `/record/[id]` (§Pages), not a toast.
- Nothing is retried silently in a way that could change the displayed set without the user seeing it.

## Non-functional requirements

- Accessibility: WCAG 2.2 AA. The editor, builder and results work by keyboard alone. Highlights never rely
  on colour alone (they also use bold or underline).
- Performance: search view interactive in under 1 s on the fixture API. Diagnostics feel instant (≤300 ms
  including the round trip).
- Light and dark themes. Layout usable at 360 px wide (reading on a phone is allowed; writing queries on
  a phone is not a goal).

## Testing

- Unit: builder ↔ AST round-trip, and the URL↔state reducer (facet click → exact `q` rewrite).
- e2e (Playwright): type one of the review's strings → see the tree → toggle workshops → count and `q`
  change → export RIS → the file parses and has `total` records → save a record → the record page shows
  `reproduced`.
- Visual regression on the search view (both themes).
