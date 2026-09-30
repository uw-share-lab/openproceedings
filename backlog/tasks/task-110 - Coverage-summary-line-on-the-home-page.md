---
id: TASK-110
title: Coverage summary line on the home page
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-27 22:46'
updated_date: '2026-09-30 00:45'
labels:
  - frontend
milestone: m-3
dependencies: []
ordinal: 107000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-045 proposal: the home page's coverage line (TASK-041) should use the same /coverage facts and wording as the coverage page.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Home coverage line from GET /coverage with the coverage page's window wording,Test pins it to the coverage fixture
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Home coverage line is now frontend/src/components/coverage/coverage-line.tsx (EmptyState renders it): one GET /coverage answer via useCoverage() (TanStack key ["coverage"], generated types), no GET /meta. Shows index_version, totals.records ("records indexed", CV-1), the venues of venue_years in API order (A-Z, as /coverage lists them) and the corpus-wide window through corpusWindow() in coverage/format.ts, the same function the /coverage header now uses (ALL_SOURCES, windowText, corpusWindow moved there; the report's Window component removed), so the window sentence has one home. Loading and failure (non-2xx or network error) render nothing, never a placeholder number (design W1). Owner-accepted exceptions are not mentioned: GET /coverage reports raw +/-1% and does not expose them (spec 07 section C), and the line shows only facts the API serves. Fixture line: 'Index c60faee23898 · 39 records indexed · ICLR, ICML, NeurIPS · Google Scholar searches run 2026-09-26 to 2026-09-26 · Coverage ▸'. Tests: coverage-line.test.tsx (6: exact fixture line, same window sentence as CoverageReport renders, Crawled kind, missing * window, loading, 502 and network failure); search-workspace and concept-builder stubs now serve coverage-fixture.json (the builder stub's partial body crashed the new line). e2e: home line matches /coverage's records and window (spec05.spec.ts); axe and 320px home states wait for the line. Docs: design W1 + API table, copy deck CV-1, CLAUDE.md layout, testing-standards stub rule; learnings entry 2026-09-29-partial-api-stubs-break-the-next-reader.

Verified 2026-09-29: npm test --workspace frontend 33 files / 2590 tests passed; make lint clean; make tooling all case tables passed; make e2e 15/15 passed (run twice, second after the final component edit).

Review round 1 closed (1 Should, 5 Nits, all fixed): windowText writes a same-day window as '<label> on <day>' on both pages and the per-source list (fixture line now '... Google Scholar searches run on 2026-09-26 ...'; copy deck CV-1 and design W1 updated); a distinct-window clone pins from/to order ('Crawled 2026-09-20 to 2026-09-26') and a served total that isn't a venue-year sum ('1,805 records indexed'); comments on venue order, on the pages fetching separately, and useCoverage's docstring. npm test --workspace frontend 2592 passed; make lint, make tooling, make e2e 15/15 green.
<!-- SECTION:NOTES:END -->
