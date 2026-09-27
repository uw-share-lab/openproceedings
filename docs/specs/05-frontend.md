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

As built (TASK-039): Next 16.3.6, React 19.2, Tailwind 4.3 (CSS-first `@theme`, no `tailwind.config`),
shadcn/ui via `components.json` (`radix-nova`, CSS variables; components are added with `npx shadcn add`
as pages need them), `next-themes` for the class-based theme, Vitest 5 with Testing Library
(`@testing-library/react`). Node 22. TanStack Query and CodeMirror join with the tasks that use them.

## URL is state (guarantee 3)

`/search?q=<input>&mode=native|scholar&sort=relevance&page=2`. Nothing that affects the result set lives
outside `q` and `mode` (which says how `q` is read). Filters, facet clicks and builder edits all **rewrite
`q`**. Copying the URL copies the search. The result set is keyed on `(q, mode)`; `sort` and `page` only order
and window it. The reducer is `frontend/src/lib/search-state.ts`.

Paging: `PAGE_SIZE = 50` results per page, so `page=n` requests `GET /search?offset=(n-1)×50&limit=50`
(spec 04). `page` is an integer from 1 to 10,000 (`MAX_PAGE`); any other value, and any unknown or repeated
parameter, is shown to the reader as a URL notice and replaced by the default, never used silently.
Notices about `q` and `mode` come first (they say what was searched). Each names the value, why it was not
used and what was used instead, listing the valid values from the reducer's own constants
("`sort=random` is not a sort order — sort orders are `relevance`, `year_desc`, `year_asc`, `title`.
Sorted by `relevance` instead."; a repeated param: "`q` appears more than once; using the first value `""`
and ignoring `trust`.", with `""` marking an empty value). The notice box ends with a **Use corrected
link** (the canonical URL of the state actually shown); the page never redirects on its own.

Facet and include clicks rewrite `q` from the server's `/parse` report of that field's top-level clause
(field, polarity, code-point span, values, and the `(q, mode)` it was parsed from). **Pending TASK-078:**
`/parse` doesn't report these clauses yet, so the reducer takes a `FilterClause` it declares itself
(`search-state.ts`) until the generated schema has one. **"Top-level" is judged
on the flattened canonical tree**, where parenthesised AND groups are flattened: in
`track:workshop "large language model" AND (venue:NeurIPS track:workshop)` both `track:` clauses are
top-level. A field with more than one such clause, or with its only clause inside an OR or NOT, has no
editable clause: `/parse` says so (TASK-078), and splicing over one clause would leave the other ANDed in,
so the edit would silently change nothing. The rewritten clause is `field:v` for one value and
`field:(v1 OR v2 …)` for several. An applied default is written out as `(q) AND field:(…)`; a `q` ending in
an odd run of backslashes is refused, because the last backslash would escape the `)` (spec 02). The wrap
goldens are `frontend/src/lib/wrap-golden.json`, checked against the server parser by
`backend/tests/contract/test_frontend_wrap_golden.py`.

The reducer refuses, with a `SearchStateError` whose `code` the UI branches on and whose message follows
the ux-writing pattern (what happened — why. How to fix): `STALE_CLAUSE` (parsed from another `q` or
`mode`), `WRONG_FIELD`, `NEGATED_CLAUSE`, `NO_EDITABLE_CLAUSE` (the field has no single editable clause),
`BAD_VALUE` (not a bare identifier), `LAST_VALUE` (removing it would exclude every record), `BAD_SPAN`,
`EMPTY_QUERY`, `TRAILING_ESCAPE`, `TOO_LONG` (the new `q` would pass `MAX_QUERY_LENGTH`, 2,000 code points,
which mirrors the API parser's cap until `/meta` serves it; a wrapped `q` that fits but whose canonical form
is over the cap, decision-008, is refused only by the server: `/parse` reporting such a field as not
toggleable is pending TASK-078), `ALREADY_INCLUDED` and `BAD_PAGE`. **Controls
are disabled with the reason, not refused after the click:** a facet toggle or include button calls
`whyBlocked(state, action)` while rendering and, when it returns an error, renders disabled with the
message as its description. `STALE_CLAUSE` is the usual case, while `/parse` catches up with a new `q`.

*M3b design consideration (open).* A facet toggle on an applied default wraps `q` once:
`(trust) AND track:(main OR datasets_benchmarks OR position OR workshop)`. Toggling the value off again
leaves the wrapped form (the clause is now typed, so it is edited in place, not unwrapped), and toggles on
several fields nest a field at a time (`((trust) AND track:(…)) AND status:(…)`) because each wrap
parenthesises the whole `q`. Both are correct but grow `q` and drift from what the reader typed. Before the
sidebar ships, decide whether to unwrap a clause that returns to the default and to append later fields'
clauses to an existing top-level AND instead of re-wrapping.

## Pages

| Route | Content |
|---|---|
| `/` | Search home: the editor, example queries (the review's strings), a coverage summary line |
| `/search` | The main workspace (below) |
| `/paper/[id]` | Full record: abstract with the current query's highlights, all links, provenance table. `GET /papers/{id}` takes no `q` and returns no highlights, so the page needs TASK-087 first |
| `/record/[id]` | Search-record page: the input string as typed, its `mode`, and every translation notice (Scholar mode), the identification string and the default clauses, full index version, search date and the crawl window (`crawl_dates["*"]`, "crawl run <from> to <to>"; only `*` exists until M4 adds per-source windows; when `crawl_dates_kind["*"]` is `scholar_query_dates` it reads "Scholar searches run <from> to <to> (local time)", never "crawl"), total, exclusions (`unknown` on its own line), replay status (`reproduced` / `drifted` with its reason and `+<added_total> / −<removed_total>`, or "membership-identical" on `+0 / −0` / `mismatch`; a replay whose canonical no longer runs reads "could not be re-run: `<refused code>`" with no counts), a "Copy methods text" button, and export buttons that **must** call `/export?record_id=<id>` (the record's stored ids from its own index, never a re-run of `q`). When `identification_citable` is `false` the page shows the CLI's caution, "bootstrap corpus (sources: <sources>): these counts describe that corpus, not a database; they are not PRISMA identification numbers", and **no methods text** (exports stay); when it is null (a v1 record) the caution reads "not recorded whether this index is a bootstrap corpus: these counts may not be PRISMA identification numbers", also with no methods text. On `mismatch` the page is a blocking **"do not cite — replay mismatch"** state with no methods text and no export |
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
   *"We searched openproceedings on 2026-09-25 (index `a1b2c3d4e5f6`, built from a crawl run 2026-09-18 to
   2026-09-20) with the string `<identification_query>`, which identified 716 records within the limits it states
   (`year:2020..2026`). Default filters `track:(main OR datasets_benchmarks OR position)` and
   `status:accepted` removed 304 of them before screening (212 workshop, 4 competition, 88 rejected); that
   count includes 0 unclassified records (track or status unknown), itemised separately. Cross-source
   duplicates were merged at ingest, before indexing (merge counts, and look-alike pairs kept apart by
   track or venue-year, are in the search record). Database scope: coverage
   report for snapshot `<snapshot_hash>`. 412 records were screened. Search record: <url>."*
   The crawl clause is always the window `crawl_dates["*"]` from–to (a crawl spans days), never one date,
   and follows `crawl_dates_kind["*"]`: `crawl` → "built from a crawl run <from> to <to>";
   `scholar_query_dates` → "built from Scholar searches run <from> to <to> (local time)"; `mixed` → "built
   from crawls and Scholar searches run <from> to <to> (Scholar dates in local time)". It never calls
   Scholar's own search dates a crawl (prisma-reporting skill §Bootstrap corpora).
   No methods text is generated unless `identification_citable` is `true` (a bootstrap corpus's counts
   are not identification numbers; prisma-reporting skill).
   If `identification_query` is `""` the text reads "all indexed records"; if it is all-negative, the text
   cites `canonical` instead (prisma-reporting skill). Counts always come from `identification_ast`. The
   text also cites the input string as typed when it differs from the identification string, and when
   `mode` is `scholar` it adds "The string was entered in Google Scholar syntax and translated as
   recorded:" followed by one clause per kind of translation **actually recorded** (never a fixed list):
   `COMPAT_SOURCE_ALIAS` → "`source:` values became `venue:` filters"; `COMPAT_POP_PHRASE` → "unquoted
   multi-word `|` items were read as phrases (openproceedings decision-002), unlike Google Scholar";
   `COMPAT_POP_DOLLAR` → "`$` was read as the Web of Science zero-or-one wildcard"; `COMPAT_NO_STEMMING` →
   "openproceedings does not stem (terms listed in the record)".
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
- Light and dark themes, chosen in the header as System / Light / Dark (a radio group; System follows the
  OS). Layout usable at 360 px wide, and no sideways scroll at 320 px (reading on a phone is allowed;
  writing queries on a phone is not a goal). The focus ring is a solid 2 px `--ring` outline, never
  translucent. Every page has a skip link to `<main id="main">` and a title `<page> · openproceedings`.
- Security headers on every route (`frontend/src/lib/security-headers.ts`, set by `next.config.ts`):
  `Content-Security-Policy` (`default-src 'self'`; scripts and styles `'self' 'unsafe-inline'`, since the
  App Router's streamed payload and the theme script are inline and a nonce would force dynamic rendering;
  `connect-src` adds the API origin when `NEXT_PUBLIC_API_BASE_URL` is set; `object-src 'none'`,
  `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'`; `'unsafe-eval'` only under `next
  dev`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`
  (search URLs carry the query). Because inline scripts are allowed, HTML is never built from strings:
  eslint's `react/no-danger` is an error, and highlights are text nodes cut at the API's spans.

## Testing

- Unit: builder ↔ AST round-trip, and the URL↔state reducer (facet click → exact `q` rewrite).
- e2e (Playwright): type one of the review's strings → see the tree → toggle workshops → count and `q`
  change → export RIS → the file parses and has `total` records → save a record → the record page shows
  `reproduced`.
- Visual regression on the search view (both themes).
