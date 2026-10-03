---
id: TASK-039
title: Next.js frontend skeleton in the npm workspace
status: Done
assignee:
  - '@frontend-engineer'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 07:22'
labels:
  - frontend
milestone: m-3
dependencies:
  - TASK-008
ordinal: 38000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 05 §Stack (nextjs-conventions, ui-design-system skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 output: standalone; Tailwind + shadcn tokens for light/dark
- [x] #2 eslint, prettier, tsc wired into make lint and autofix
- [x] #3 URL↔state reducer with tests (q is the only result-set state)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Root npm workspace + frontend/ Next.js App Router (TS strict, output standalone). 2. Tailwind v4 + shadcn tokens (light/dark, project semantic tokens). 3. eslint/prettier/tsc in make lint, fmt, autofix (root node_modules), CI lint + test. 4. src/lib/search-state.ts reducer (q only result-set state) with vitest tests. 5. Docs (CLAUDE.md, README, CONTRIBUTING, skills) same commit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Versions: Next 16.3.6, React 19.2.8, Tailwind 4.3.3 (@tailwindcss/postcss), shadcn via components.json (radix-nova, CSS variables; no components added yet), next-themes 0.4.6, ESLint 9 + eslint-config-next 16.3.6, Prettier 3.9.9 (+tailwind plugin), TypeScript 5, Vitest 5.0.2; Node 22 (.nvmrc). Root npm workspace hoists deps to ./node_modules, so Makefile/autofix/CI now look there (frontend-deps fails make lint/test/fmt if missing). make lint runs next typegen before tsc. CI test job runs vitest + next build (standalone asserted); schema freshness step gated on src/api/schema.ts (TASK-040). Follow-up TASK-078 (/parse clause spans).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Frontend skeleton: root npm workspace (package.json, package-lock.json, .nvmrc 22) with frontend/ as the member. Next 16.3.6 App Router, TS strict (+noUncheckedIndexedAccess, exactOptionalPropertyTypes, noImplicitOverride), output standalone (server at .next/standalone/frontend/server.js). Tailwind 4 + shadcn tokens for light/dark plus the project semantic tokens (hl, warn, excluded, default-clause, track-workshop), contrast-checked by src/app/tokens.test.ts. Placeholder pages for every spec 05 route. src/lib/search-state.ts: SearchState {q, mode, sort, page}, fromURL with visible notices, toURL, resultSetKey [q, mode], toSearchRequest (offset/limit from page), and reduce() whose facet/include actions splice q from a server-supplied FilterClause (code-point span via src/api/spans.ts). 86 vitest tests. prettier/eslint/next typegen+tsc in make lint (CI lint), fmt, autofix (root node_modules, mutant added); CI test adds vitest + build. Docs: CLAUDE.md, CONTRIBUTING, README, specs 05/08, three skills. Follow-up TASK-078.
<!-- SECTION:FINAL_SUMMARY:END -->
