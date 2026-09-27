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
(`@testing-library/react`). Node 22. TASK-041 added CodeMirror 6 (`@codemirror/*`, `@lezer/*`) and TanStack
Query 5; the editor's Lezer grammar is token-only, fed by a mirror of the server lexer whose character tables
and golden cases are generated from `lexer.py` (codemirror-lezer skill).

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
(field, polarity, code-point span, values, and the `(q, mode)` it was parsed from): `/parse`'s `filters`
(02 §Filter clauses, decision-011). `clauseFromParse(filters[field], q, mode)` turns the generated
`ParsedClause` into the reducer's `FilterClause` (a positive, toggleable clause with a span) or `clause: null`
with the server's `reason`, which the action carries so the refusal says why. **"Top-level" is judged
on the flattened canonical tree**, where parenthesised AND groups are flattened: in
`track:workshop "large language model" AND (venue:NeurIPS track:workshop)` both `track:` clauses are
top-level. A field with more than one such clause, or with its only clause inside an OR or NOT, has no
editable clause: `/parse` says so (`multiple_clauses`, `nested`, `mixed_fields`), and splicing over one clause would leave the other ANDed in,
so the edit would silently change nothing. The rewritten clause is always grouped, `field:(v1 OR v2 …)`, and
`field:(v)` for one value: a bare `field:v` spliced before a group would touch it (`trust
track:workshop(x OR y)` is `PARSE_PAREN_TOUCHES_WORD`), while the group's `)` never touches what follows, so
`/parse`'s check of the widest edit covers every edit a click makes. The canonical form, and so the search
record's hash, is the same as the bare form's. An applied default is written out as `(q) AND field:(…)`; a `q` ending in
an odd run of backslashes is refused, because the last backslash would escape the `)` (spec 02). The wrap
goldens are `frontend/src/lib/wrap-golden.json`, checked against the server parser by
`backend/tests/contract/test_frontend_wrap_golden.py`.

The reducer refuses, with a `SearchStateError` whose `code` the UI branches on and whose message follows
the ux-writing pattern (what happened — why. How to fix): `STALE_CLAUSE` (parsed from another `q` or
`mode`), `WRONG_FIELD`, `NEGATED_CLAUSE` (also for `/parse`'s reason `negated`), `NO_EDITABLE_CLAUSE` (the
field has no single editable clause: `multiple_clauses`, `nested`, `mixed_fields`, `unparsable_edit`, or a
reason this code doesn't know, each worded in the message), `BAD_VALUE` (not a bare identifier), `LAST_VALUE`
(removing it would exclude every record), `BAD_SPAN`, `EMPTY_QUERY`, `TRAILING_ESCAPE`, `TOO_LONG` (the new
`q` would pass the instance's `max_query_length`, which `/meta` serves in `limits` (TASK-089) and `reduce` and
`whyBlocked` take as an argument; until `/meta` is fetched (TASK-041/042) they use `DEFAULT_LIMITS`, 2,000 code
points, from `frontend/src/lib/default-limits.json`, which the backend's `test_meta_limits.py` checks equals the
cap `/meta` serves; or `/parse` reported `too_long`: the widest edit's canonical form would be over the cap,
decision-008),
`TOO_DEEP` (`/parse` reported `too_deep`: the wrap would nest `q` past the instance's `max_query_depth`, 64,
also from `/meta`'s `limits` and `default-limits.json`),
`ALREADY_INCLUDED` and `BAD_PAGE`. The golden cases in `frontend/src/lib/filter-clause-golden.json` pin
`/parse`'s report and the reducer's result together.

**Year** has its own actions (TASK-092), since a year clause is ranges, not values:
`yearClauseFromParse(filters.year, q, mode)` narrows `/parse`'s `ParsedYearClause` as `clauseFromParse` does,
and `yearSet` (exactly one range), `yearClear` (every year: `year:(1000..9999)`, rewritten in place, never
deleted), `yearAdd` and `yearRemove` (a range added to or taken out of the clause's ranges) write the whole
clause, grouped and merged as the canonical form keeps it (`year:(2018..2020 OR 2022..2024)`, one year bare:
`year:(2024)`), over the clause's span or as `(q) AND year:(…)`. They refuse as the other fields do
(`STALE_CLAUSE`, `WRONG_FIELD`, `NEGATED_CLAUSE`, `/parse`'s reasons, `TOO_LONG`, `TOO_DEEP`, `BAD_SPAN`,
`EMPTY_QUERY`, `TRAILING_ESCAPE`), with `BAD_VALUE` for a range that is not two four-digit years from 1000 to
9999 in order, `ALREADY_INCLUDED` (the clause already admits the years, or already is the range set),
`NOT_INCLUDED` (removing years it doesn't admit), `LAST_VALUE` (removing its last year) and
`TOO_MANY_RANGES` (more than `MAX_YEAR_RANGES`, 4, the most `/parse`'s widest year edit covers: 02 §Filter
clauses). Their goldens are `frontend/src/lib/year-clause-golden.json`, shared with the backend's `/parse`
tests, which also parse every expected string and check that only the year clause changed. **Controls
are disabled with the reason, not refused after the click:** a facet toggle, include button or year control calls
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
| `/paper/[id]` | Full record: abstract with the current query's highlights, all links, provenance table. The result list links to `/paper/<id>?q=<q>&mode=<mode>` (the query rides in the URL, so a shared or reloaded link shows the same highlights), and the page calls `GET /papers/{id}?q=…&mode=…` (04 §Endpoints, task-087): it draws `highlights` exactly as the result list does (API spans only, never re-matched), and when `matched` is false it says the paper doesn't match that query (e.g. the default filters remove it) with nothing lit. A link without `q` (a direct link) calls `GET /papers/{id}` alone and shows the record with no highlights and no match line. If the `q` in the URL is refused (a 422 or 429), the page fetches the paper without `q` and shows it unhighlighted with a one-line notice that the query in the link couldn't be run; a 404, or a 422 `API_BAD_PARAM` for the id, is the not-found state |
| `/record/[id]` | Search-record page: the input string as typed, its `mode`, and every translation notice (Scholar mode), the identification string and the default clauses, full index version, search date and the crawl window (`crawl_dates["*"]`, "crawl run <from> to <to>"; only `*` exists until M4 adds per-source windows; when `crawl_dates_kind["*"]` is `scholar_query_dates` it reads "Scholar searches run <from> to <to> (local time)", never "crawl"), total, exclusions (`unknown` on its own line), replay status (`reproduced` / `drifted` with its reason and `+<added_total> / −<removed_total>`, or "membership-identical" on `+0 / −0` / `mismatch`; a replay whose canonical no longer runs reads "could not be re-run: `<refused code>`" with no counts; a replay this instance withholds (04 §Search records: `refused` `API_TOO_MANY_VERIFIED_CLAUSES` or `API_QUERY_TOO_COSTLY`, status `drifted`, `changed` empty) reads "could not be re-run: `API_TOO_MANY_VERIFIED_CLAUSES` — this instance's limit is below the record's <verified_clauses> position-verified clauses", or for `API_QUERY_TOO_COSTLY` "— its position checks would read more documents than this instance allows in one query", never as reproduced, as membership-identical or as a drift with no reason; its exports stay, the record's stored ids), a "Copy methods text" button, and export buttons that **must** call `/export?record_id=<id>` (the record's stored ids from its own index, never a re-run of `q`). When `identification_citable` is `false` the page shows the CLI's caution, "bootstrap corpus (sources: <sources>): these counts describe that corpus, not a database; they are not PRISMA identification numbers", and **no methods text** (exports stay); when it is null (a v1 record) the caution reads "not recorded whether this index is a bootstrap corpus: these counts may not be PRISMA identification numbers", also with no methods text. On `mismatch` the page is a blocking **"do not cite — replay mismatch"** state with no methods text and no export |
| `/coverage` | Venue × year × track table with source and snapshot date, missing-abstract counts, `unknown` counts. As built (TASK-045): `GET /coverage` fetched on each visit (`components/coverage/`, client-side, so no server-side API address is needed); the window is worded by `crawl_dates_kind` ("Google Scholar searches run", never "crawled", for a bootstrap source), a citability note when `identification_citable` is false, a statuses-indexed column, and a disclosure per venue-year with track × status (`–` for no cell) and each track against its official count (difference, gate verdict, citation). Every number is an API field; its tests render `coverage-fixture.json`, a real `GET /coverage` answer kept current by `test_frontend_coverage_fixture.py` |
| `/help/syntax` | Language reference generated from the 02 golden table (it cannot drift from the tests). As built (TASK-045): rendered from `src/help/syntax-golden.json`, which `backend/tests/contract/help_golden.py` builds from the parser (an example, mode, registry message and fix per reader-facing code), the token goldens, spec 02's consequences table, the vocabularies, the default clauses and the limit constants; `test_frontend_help_golden.py` fails while it is stale or a code lacks an entry. Anchors are the code in lower case (`#slow-clauses` holds both slow-clause codes); Limits reads `/meta` at request time, else shows the defaults, said to be defaults |

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

Designs (TASK-033, wireframes, every state, interaction and copy): `docs/design/2026-09-27-search-workspace.md`
indexes them; the heuristic pre-pass and its dispositions are in `docs/design/2026-09-27-heuristic-prepass.md`.
Where a design adds to this spec (the `(text, mode)` draft and `DRAFT_DIRTY`, the export's status and track
warnings, the save's index check), the design doc says so; its open questions list what would change this spec.

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
   *As built (TASK-043, `frontend/src/builder/`):* the Text/Builder tabs share one draft string, which stays
   canonical. The builder reads the server's `ast` (`read.ts`: groups, one optional Exclude row, and the
   top-level filters as read-only limits kept as written) and writes the draft back only after an edit
   (`write.ts`: fully parenthesised, uppercase operators, each term exactly one lexeme, checked with the
   editor's mirror of the server lexer). Two goldens tie it to the parser:
   `builder-read-golden.json` (the backend's own reading of 300+ queries, which `read.ts` must equal) and
   `builder-write-golden.json` (what the builder writes, unedited and after seeded random edits, which
   `backend/tests/contract/test_frontend_builder_golden.py` parses: an unedited rewrite keeps the
   `canonical`, and an edited query means exactly what its chips say). At run time the builder checks the
   server's reading of each query it wrote and says so if it differs.
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
   on the client). Venue/year/track badges. Links to OpenReview, PDF and proceedings. **Numbered pages**
   (TASK-042): `◂ Previous · Page n of m · Next ▸` and a "Go to page" input, `router.replace` (Back leaves
   the search), focus to the results heading after a change.

   *As built (TASK-042).* `src/components/search/search-view.tsx` runs `GET /search` (TanStack key
   `["search", q, mode, sort, page]`, `keepPreviousData`) and draws the results in `SearchWorkspace`'s
   `results` slot (`workspace-slot.ts`: `dirty`, and the editor for "Show the clause"). A 422 for the searched
   query goes back to the workspace as `refusal` (squiggles); the last good answer stays on screen, dimmed and
   marked stale, with **Restore it**. The sidebar and banner read `/parse`'s `filters` for the searched query
   (`controls.ts`: `parseViewOf`, and `blockOf` = `whyBlocked` + `DRAFT_DIRTY` + "no report yet", which is the
   reducer's `STALE_CLAUSE`). Banner and Limits line are computed in `exclusions.ts` from `excluded`, `facets`
   and `/parse` only (no client arithmetic beyond reading them). Highlights and the abstract excerpt:
   `src/lib/excerpt.ts`. `/paper/[id]`: `src/components/paper/paper-view.tsx`.
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

   *As built (TASK-044).* The methods text is `frontend/src/lib/methods-text.ts` (`methodsText`), pure: every
   number is a field of the record the API sent (`identified_total`, `excluded`, `unclassified_total`,
   `total`), and the default and limit clauses are slices of `canonical` at the spans of `POST /parse`'s report
   of that same string (`clausesOf`: a field in `defaults` is a default clause; any other field with a clause
   of its own is a limit, and one written more than once is each clause behind it; a filter nested in an OR or
   NOT is part of the string, not a limit). Its test renders this section's example sentence from the spec
   file itself and requires an exact match, and runs the API's own records (`record-fixture.json`, kept
   current by `backend/tests/contract/test_frontend_record_fixture.py`) through it, checking that the prose
   holds no number the record didn't send. Wording this section leaves open, now pinned by those tests: an
   empty identification string reads "with no search string (all indexed records)"; an all-negative one
   (`/parse` of it reports `PARSE_ALL_NEGATIVE`) "with the string `<canonical>`, which without its default
   filters identified …"; one default filter reads "Default filter `status:accepted`"; none applied reads "No
   default filter applied, so no records were removed before screening."; the input as typed is "The input as
   typed was `<input>`."; a Scholar record with no translation recorded says so; a translation code this
   version doesn't word is given by its recorded message; a crawl kind it doesn't know (or a v1 record's null)
   reads "records collected <from> to <to>"; a count of one is singular. When `/parse` answers under another
   `query_version` than the record's, the clauses aren't separated: the limits read "within any limits it
   states" and the defaults "The default filters (written out in the canonical query `<canonical>`)".

   *As built (TASK-044): export, save and the record page.* The Export menu (`components/export/export-menu.tsx`)
   and Save (`components/record/save-record.tsx`) sit in the results header, both disabled with the reason
   while the draft is dirty or the results are stale. An export is `GET /export?format&q&mode&index_version=<shown>`
   (`lib/export.ts`): its headers are read before the body, and a different `X-Index-Version` ("the index
   changed") or, on the same index, a different `X-Total` (a bug) abandons it with nothing saved. The menu's
   status and track warnings list `facets[field][value]` for each value the searched clause admits beyond the
   default (`fieldWarning`; zeros left out, never summed), or name the reason with no numbers when the clause is
   negated, nested or written more than once; the formats wait until `/parse` has reported on the shown
   query. Save posts `{q, mode, index_version}` (a moved index is 409 with nothing saved), then reads the record
   back for its status and methods text; `API_RECORDS_STORE_FULL` turns saving off for the session
   (`sessionStorage`). `/record/[id]` (`components/record/record-view.tsx`) reads the stored record first
   (`?replay=false`), then its replay; the methods text and the exports appear once the replay has answered (or
   couldn't run: "Replay: waiting" on a 429 or `API_BUSY`), so a `mismatch` never shows either.

## Error handling

- API errors are shown from the envelope's `code` and `message` (04 §Error handling), never as a raw
  status or a generic "something went wrong". A parse `422` draws its diagnostics as squiggles at their
  spans, and the search view keeps the last good result set, marked as stale.
- `429 API_RATE_LIMITED` shows the wait from `Retry-After`. `503 API_BUSY` is shown the same way: "the
  server is busy with slow phrase checks; try again in N s", the wait from `Retry-After`. `503
  API_INDEX_NOT_LOADED` shows a "search index is loading" state with a retry. `503 API_RECORDS_STORE_FULL`
  turns saving off ("saving search records is paused on this instance"); searching, reading records and
  exporting work as before. `413 API_BODY_TOO_LARGE` says the query is far too long to send (a valid one
  always fits). A `422 API_TOO_MANY_VERIFIED_CLAUSES` or `422 API_QUERY_TOO_COSTLY` draws its
  diagnostics as squiggles on each slow clause, like a parse error (the latter's say how many documents
  each clause's check would read).
- A `422 API_BAD_PARAM` on `/paper/[id]` or `/record/[id]` (a malformed id in the URL) renders as that
  page's not-found state, the same as a 404.
- A 5xx whose body isn't JSON comes from in front of the app (uvicorn's `limit_concurrency` 503, or the
  reverse proxy; 04 §Error handling): it means "busy, retry", shown as a retry state, never as an error in
  the user's query.
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
