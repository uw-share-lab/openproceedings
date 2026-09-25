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
   (`api-engineer`), then regenerate. The codegen tool and script are pinned in `frontend/package.json`
   (verify at implementation time which one; do not add a second).
3. **The server decides membership, counts, highlights and parsing.** The client never tokenizes, never
   re-matches terms to draw highlights, never filters/sorts/dedups `hits`, never computes a count. A
   second tokenizer in TypeScript is a guarantee-1 bug (`token-contract`). Highlights are slices of the
   string at the API's `highlights` spans, nothing more.

## Layout (proposed; keep it once built)
| Path | Kind |
|---|---|
| `src/app/page.tsx` (`/`), `search/page.tsx` | server shell; the `/search` workspace is a client component |
| `src/app/paper/[id]`, `record/[id]`, `coverage`, `help/syntax` | server components, fetch on request |
| `src/api/schema.ts`, `src/api/client.ts` | generated types; one typed fetch wrapper (base URL from env) |
| `src/lib/search-state.ts` | the URL↔state reducer (pure, unit-tested) |
| `src/editor/`, `src/builder/` | CodeMirror (`codemirror-lezer`) and concept-group builder |
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
- The editor draft is not state until submitted; submitting `router.push`es. Paging uses `replace`.

## TanStack Query
Keys: `["meta"]` (long `staleTime`), `["parse", q, mode]`, `["search", q, mode, sort, page]`,
`["paper", id]`, `["record", id]`. `placeholderData: keepPreviousData` for search so the list doesn't
flash. A 422 is data, not an exception: render its `diagnostics` (spec 04 error shape).

## Gotchas
- API spans are half-open `[start, end)` **code-point** offsets over the raw source string (spec 04
  §Conventions): the stored title/abstract for highlights, `q` for diagnostics. JS strings index UTF-16
  units. Convert exactly once, in the one helper `src/api/spans.ts`, or astral characters (math letters,
  emoji) shift every later highlight.
- Export links carry the same `q`/`mode`; compare `X-Total` and `index_version` with the shown search and
  warn on mismatch (index swapped between the two).
- Next 15+ passes `searchParams` as a Promise to pages — check the pinned version.
