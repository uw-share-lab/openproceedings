---
name: nextjs-conventions
description: The openproceedings Next.js standard — App Router layout, output standalone for the Docker image (never Vercel-bound), server vs client component split, TanStack Query keys, generated API types only, the URL↔state reducer that makes facet clicks rewrite q, and the ban on client-side re-matching of highlights or counts. Use when writing or reviewing anything under frontend/, adding a page or data hook, or touching how the URL maps to a search.
---

# Next.js conventions (spec 05, contract from spec 04)

## Non-negotiables
1. **`output: "standalone"`** in `frontend/next.config.ts`. The app ships in the `web` container
   (`deploy/compose.yml`, spec 08). No `@vercel/*` packages, no edge-only runtime, no ISR/Data-Cache
   features that assume a platform. Search, record and paper fetches use `cache: "no-store"`: the index
   can hot-swap (`index_version` pointer swap, spec 04), and a cached response would show a stale version.
2. **Generated types only.** `frontend/src/api/schema.ts` is generated from the FastAPI OpenAPI schema
   (spec 04 §Conventions); CI fails if it is stale. Never hand-write a response type, never widen one with
   `as`, never add an optional field the schema lacks. Contract change → backend PR first
   (`api-engineer`), then regenerate with `make openapi` (the backend snapshot, then `npm run gen:api`:
   `openapi-typescript` 7.13.0, pinned in `frontend/package.json`; do not add a second codegen tool).
   Fetch through `src/api/client.ts` only: `createApi()` is `openapi-fetch` typed by the generated
   `paths`, `cache: "no-store"`, base URL `NEXT_PUBLIC_API_BASE_URL` (default "" = same origin); it returns
   `{data, error}`, where `error` is the typed `ErrorEnvelope` for every non-2xx (a 422 included).
   `hitHighlightsUtf16(hit)` converts a hit's highlight spans with `spans.ts`.
3. **The server decides membership, counts, highlights and parsing.** The client never tokenizes, never
   re-matches terms to draw highlights, never filters/sorts/dedups `hits`, never computes a count. A
   second tokenizer in TypeScript is a guarantee-1 bug (`token-contract`). Highlights are slices of the
   string at the API's `highlights` spans, nothing more.

## Layout (skeleton built in TASK-039: app routes, `src/lib/search-state.ts`, `src/api/spans.ts`; `src/api/schema.ts` and `client.ts` in TASK-040; the rest arrives with its task)
| Path | Kind |
|---|---|
| `src/app/page.tsx` (`/`), `search/page.tsx` | server shell; the `/search` workspace is a client component |
| `src/app/paper/[id]`, `record/[id]`, `coverage`, `help/syntax` | server components, fetch on request |
| `src/api/schema.ts`, `src/api/client.ts` | generated types; one typed fetch wrapper (base URL from env) |
| `src/lib/search-state.ts` | the URL↔state reducer (pure, unit-tested) |
| `src/editor/`, `src/builder/` | CodeMirror (`codemirror-lezer`, built in TASK-041) and concept-group builder |
| `src/components/providers.tsx` | `Providers` (in the root layout): the typed API client (`useApi()`) and TanStack Query (`retry: false`, no refetch on focus) |
| `src/components/search/` | the `/search` workspace (TASK-041: editor, diagnostics row, "How we read your query", expansions row, empty state; TASK-042: `search-view.tsx` (runs `/search`, draws the results in `SearchWorkspace`'s `results` slot, `workspace-slot.ts`), `use-search.ts`, `controls.ts` (`blockOf`, `parseViewOf`), `exclusions.ts` (banner and Limits line, pure), `exclusion-banner.tsx`, `filter-sidebar.tsx` (incl. the year control on the TASK-092 actions), `hit-item.tsx`, `search-states.tsx`) |
| `src/components/paper/` | `/paper/[id]` (TASK-042): `GET /papers/{id}?q=&mode=`, key `["paper", id, q, mode]`; a refused `q` falls back to the paper alone |
| `src/components/export/`, `src/lib/export.ts` | the Export menu and a record's exports (TASK-044): `GET /export` pinned to the shown `index_version` (or `record_id` alone), headers read before the body, status/track warnings from `facets` |
| `src/components/compare/`, `src/lib/compare.ts` | "Compare with your records" (TASK-177): `POST /compare` with the chosen `File` as the body (`bodySerializer`; its bytes, never decoded here), drawn only when `/meta`'s `limits.compare` is not null; counts, reasons and each download's text are the response's own (nothing is counted or built in the browser); an answer is keyed by `(q, mode, index_version)` and never shown for another search; tests read `compare-fixture.json` (the API's own answer) through `src/test/compare-fixture.ts` |
| `src/components/record/`, `src/lib/{methods-text,replay-status}.ts` | Save search record and `/record/[id]` (TASK-044): the stored read (`?replay=false`) then the replay; the methods text from the record and `/parse(canonical)`; tests read `record-fixture.json` (the API's own answers) through `src/test/record-fixture.ts` |
| `src/components/{highlighted,paper-badges,paper-links,coded}.tsx`, `src/lib/excerpt.ts`, `src/api/outcome.ts` | shared by results and the paper page: `<mark>` at API spans, badges, links, backticked reducer messages as code; span conversion + excerpt window; every GET answer as data (`Outcome`) |
| `src/components/site-footer.tsx`, `src/lib/takedown-contact.ts` | the footer on every page (TASK-133, decision-018): the takedown contact from `NEXT_PUBLIC_TAKEDOWN_CONTACT` (email or http(s) page, build time; `next.config.ts` fails the build on an unusable value), else the repository's issues page |
| `src/api/hooks.ts` | `useMeta()` (`["meta"]`), `useCoverage()` (`["coverage"]`) |
| `src/test/api-stub.tsx` | tests only: a stubbed fetch behind the real client (each `Call` has `path`, `query`, `body` (JSON parsed; another content type as text) and `contentType`), `renderWithApi`, fake-timer `pass(ms)`, jsdom layout polyfill |
| `e2e/` | Playwright (`e2e-tester`) |

`/help/syntax` is rendered from the 02 golden table data, not hand-written prose, so it cannot drift.

## URL is state (guarantee 3)
`/search?q=&mode=native|scholar&sort=relevance&page=` — the whole state. Rules for `search-state.ts`:
- `fromURL(URLSearchParams) → SearchState`; unknown params dropped; `mode` defaults to `native`.
- Every action (`submit`, `facetToggle`, `includeExcluded`, `builderEdit`, `sort`, `page`) returns a new
  `q` string plus params; any change except `page` resets `page`. No action stores a filter anywhere else.
- Facet / include actions **rewrite the `track:`/`status:`/`venue:`/`year:` clause in `q`** using the spans
  of the parsed input; if the query relies on a default, the action writes the default out explicitly and
  then edits it (`track:(main OR datasets_benchmarks OR position)` → `… OR workshop)`). Verify at
  implementation time that `/parse` returns clause spans; if not, get them added server-side — do not
  re-parse filters on the client.
- Tests pin exact strings: `facetToggle(track=workshop)` on input X yields exactly string Y.
- **As built (TASK-039, `src/lib/search-state.ts`):** `SearchState = {q, mode, sort, page}` and nothing
  else; `resultSetKey` is `[q, mode]`; `toSearchRequest` derives the API's `offset`/`limit` from `page`
  (`PAGE_SIZE` 50, `MAX_PAGE` 10,000). `fromURL` returns `{state, notices}`: unknown, repeated and invalid
  params (including a page over `MAX_PAGE`) are reported, never silently used. Actions: `submit`,
  `builderEdit`, `setMode`, `facetToggle`, `includeExcluded`, `sort`, `page`. Filter actions take a
  `FilterClause {field, negated: false, source, mode, span, values}`, derived from the generated
  `ParsedClause` of `/parse`'s `filters` by `clauseFromParse(filters[field], q, mode)` (TASK-078, decision-011;
  code-point span into `source`; zero-width at the end = applied default or unrestricted field, written out
  as `(q) AND field:(…)`), or `clause: null` plus `/parse`'s `reason`, which words the refusal. They refuse a clause
  whose `(source, mode)` differs from `resultSetKey`, one for another field, a negated one (adding a value
  inside `-track:x` would flip it), and a wrap of a `q` ending in an odd run of backslashes (the escape would
  swallow the `)`; goldens in `src/lib/wrap-golden.json`, checked by the backend parser in
  `backend/tests/contract/test_frontend_wrap_golden.py`). Every refusal throws `SearchStateError` rather than
  no-op, with a `code` (`STALE_CLAUSE`, `WRONG_FIELD`, `NEGATED_CLAUSE`, `NO_EDITABLE_CLAUSE` for
  `clause: null`, `BAD_VALUE`, `LAST_VALUE`, `BAD_SPAN`, `EMPTY_QUERY`, `TRAILING_ESCAPE`, `TOO_LONG` past
  the instance's `max_query_length` (`/meta`'s `limits`, passed as `reduce`/`whyBlocked`'s `limits`; `DEFAULT_LIMITS`
  = 2,000 code points from `src/lib/default-limits.json` until `/meta` is fetched, checked against `/meta` by
  `test_meta_limits.py`) or for `/parse`'s `too_long`, `TOO_DEEP` for its `too_deep`,
  `ALREADY_INCLUDED`, `BAD_PAGE`) and a what — why. fix message. `src/lib/filter-clause-golden.json` pins
  `/parse`'s report and the reducer's result together (backend: `test_clauses.py`, `test_parse_filters.py`).
  Controls call `whyBlocked(state, action, limits)` and render disabled with the reason instead of failing on
  click. "Top-level" clause means top-level on the flattened canonical tree (spec 05 §URL is state).
  `describeNotice`/`noticeText` word the URL notices from the same constants the reducer checks.
- The editor draft is not state until submitted; submitting `router.push`es. Paging uses `replace`.

## Security headers
`next.config.ts` `headers()` sends `src/lib/security-headers.ts` on every route: a static CSP
(`'self'` everywhere, `'unsafe-inline'` for scripts and styles because the App Router's payload and the
theme script are inline, the API origin in `connect-src` when `NEXT_PUBLIC_API_BASE_URL` is set,
`frame-ancestors 'none'`, `'unsafe-eval'` only in dev), `nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, a `Permissions-Policy` denying camera, microphone and geolocation, and HSTS
outside dev. The set is in spec 05 §Non-functional requirements and pinned by
`security-headers.test.ts`. Since inline scripts run, never build HTML from strings: `react/no-danger` is an
eslint error.

## TanStack Query
Keys: `["meta"]` (long `staleTime`), `["parse", q, mode]`, `["search", q, mode, sort, page]`,
`["paper", id, q, mode]`, `["record", id, "stored"]` (`?replay=false`), `["record", id]` (with its replay),
`["record-diff", id, offset]`. `placeholderData: keepPreviousData` for search so the list doesn't
flash. A 422 is data, not an exception: render its `diagnostics` (spec 04 error shape). `openapi-fetch`'s
`data` type is not `Schemas[...]` (its `Readable<>` widens tuple spans to `number[]`): type a response with
`MethodResponse<Api, method, path>` and validate spans where they are used, never cast.

## Gotchas
- API spans are half-open `[start, end)` **code-point** offsets over the raw source string (spec 04
  §Conventions): the stored title/abstract for highlights, `q` for diagnostics. JS strings index UTF-16
  units. Convert exactly once, in the one helper `src/api/spans.ts`, or astral characters (math letters,
  emoji) shift every later highlight.
- Export links carry the same `q`/`mode`; compare `X-Total` and `index_version` with the shown search and
  warn on mismatch (index swapped between the two).
- Next 16 (pinned 16.3.6) passes `params`/`searchParams` as Promises; type pages with the generated
  `PageProps<"/route">` / `LayoutProps<"/">` globals, which `next typegen` writes (`make lint` runs it
  before `tsc`).
- Dependencies are hoisted to the repo-root `node_modules`, so `next.config.ts` sets
  `outputFileTracingRoot` and `turbopack.root` to the workspace root; the standalone server is
  `.next/standalone/frontend/server.js` and needs `.next/static` copied beside it (`npm start` does this;
  so does `deploy/web.Dockerfile`, TASK-136).
- No `next/font/google`: it fetches at build time, and the image must build offline. System font stacks
  are set in `globals.css`.
