---
name: typescript-standards
description: The frontend TypeScript standard for openproceedings — strict tsconfig, API types generated from the backend OpenAPI schema into frontend/src/api/schema.ts (never hand-written), eslint/tsc/prettier gates, no client-side re-matching or re-parsing, and URL-as-state typing. Use when writing or reviewing code under frontend/, touching API calls or response types, or fixing the lint/tsc/freshness checks in CI.
---

# TypeScript standards (frontend/)

## Compiler and lint
- `tsconfig.json`: `"strict": true` plus `noUncheckedIndexedAccess`, `noImplicitOverride`,
  `exactOptionalPropertyTypes` (verify at implementation time that the Next.js/shadcn setup tolerates the
  last one; if not, record why in the PR).
- CI `lint` runs `eslint`, `tsc --noEmit`, `prettier --check`. Run `npm run lint && npx tsc --noEmit`
  before committing.
- No `any`. `unknown` + a narrowing function at trust boundaries. No `as` casts on API data; no non-null
  `!` on values that can be absent in a response.
- No `// @ts-ignore`; `// @ts-expect-error <reason>` only in tests.

## API types are generated — never hand-written
- Source of truth: the pydantic v2 models in `backend/src/openproceedings/api/` → OpenAPI →
  `frontend/src/api/schema.ts` via codegen (spec 04 §Conventions). Regenerate with the project script
  (verify the exact command at implementation time, e.g. `npm run gen:api`) after any backend model change,
  and commit the result in the same PR.
- CI `test` fails if `schema.ts` is stale. Don't edit it by hand to make CI pass.
- Derive component prop types from the generated ones (`Pick<components["schemas"]["SearchResponse"],
  "total" | "excluded">`), never parallel interfaces like `interface Hit { title: string }`. A hand-written
  API type is a Must in review — it is how the two sides drift.
- The `Diagnostic` shape (`{code, message, span}`) comes from the schema too (`error-diagnostics`).

## The server is authoritative
- **Parsing:** the Lezer grammar only highlights. Diagnostics, the AST tree and canonical form come from
  `POST /parse`. Never decide validity in the client.
- **Matching:** highlights are the API's `highlights` spans applied to the API's text — never re-matched,
  re-tokenized or regex-searched on the client (guarantee 1). A second tokenizer in TS is a bug
  (`token-contract`).
- **Counts:** `total`, `excluded` and facet counts are displayed as returned, never recomputed.

## URL is state (guarantee 3)
- Everything that affects the result set lives in `q`. The URL↔state reducer is a pure, typed function
  with unit tests: a facet click produces an exact, predictable rewrite of `q`.
- `mode`, `sort`, `page` are typed unions (`"native" | "scholar"`), parsed and validated from
  `searchParams`, with invalid values falling back visibly, not silently.

## Data fetching and components
- TanStack Query for server state; keys include `q`, `mode`, `sort`, and `index_version` where relevant.
- Server components by default; `"use client"` only where interaction needs it (the editor, builder).
- Accessibility is not optional (`accessibility` skill): keyboard paths, highlights not colour-only.

## Tests
Vitest + Testing Library for units (builder↔AST round-trip, URL reducer), Playwright for e2e against the
fixture API (`testing-standards`).
