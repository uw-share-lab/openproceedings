---
id: TASK-042
title: 'Filters, exclusion banner, results and paper page'
status: Done
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 22:38'
labels:
  - frontend
milestone: m-3
dependencies:
  - TASK-041
  - TASK-035
  - TASK-087
  - TASK-078
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 05 §Components 4–6.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Filter and facet clicks rewrite q; workshop off by default
- [x] #2 Banner itemises unknown; each include label shows the real facet delta
- [x] #3 Highlights rendered from API spans only; /paper/[id] with provenance
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. SearchView (client) owns the /search query (['search', q, mode, sort, page], keepPreviousData), last good result, refusal -> SearchWorkspace.refusal, openTree on zero results; SearchWorkspace gets one render-prop slot (results) + a context (dirty, select span, edit-year) and nothing else, so TASK-043's editor/builder edits merge cleanly.
2. Results column: header (total, index version + Copy, Searching…, live region), exclusion banner (BN-1..5, include buttons = facet count, adds-0 wording, PRISMA disclosure), Limits line with leave-outs, sort, hits (highlights from API spans only, excerpt rule, badges, links), numbered paging (router.replace, page input, focus to heading), error/wait/stale/index-swapped states (W6-W12), zero results (W8).
3. Sidebar: venue/track/status checkboxes from /parse filters + facets via clauseFromParse/whyBlocked (aria-disabled + describedby, STALE after 500 ms, DRAFT_DIRTY, field notes with Show the clause(s) from blocking_spans/span); year counts + per-year add/remove, from–to set, All years (TASK-092 actions) + Edit year: in the query; narrow Filters (n active) disclosure.
4. /paper/[id]: client PaperView over GET /papers/{id}?q&mode (P1-P5): highlights, match line, status line, links, identifiers, provenance table / dl; refusal fallback without q; not-found.
5. Tests (Vitest + api-stub, no network) for each; docs as-built (spec 05, design, skills); full test/lint/build; smoke against op serve.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Facet/include clicks go through reduce() in src/lib/search-state.ts (TASK-039); its FilterClause input needs per-field clause spans from /parse, which is TASK-078.

TASK-087 done (dependency satisfied): /paper/[id] gets highlights from GET /papers/{id}?q=&mode= (fields matched + highlights, null without q; matched:false = the query incl. default filters doesn't match the paper, lists empty). Result list must link /paper/<id>?q=<q>&mode=<mode>; on a 422/429 for the q, refetch without q and show a one-line notice (spec 05 §Pages).

Design (TASK-033, 2026-09-27): /search sidebar, banner, results, paging and API error states from docs/design/2026-09-27-search-workspace.md §W5, W8-W10, W12-W14; /paper/[id] from docs/design/2026-09-27-export-records-and-paper.md §P1-P5; copy deck §1, §7. Decisions: numbered pages (router.replace, page input, focus to the results heading), not infinite scroll. Banner = standing string 'excluded: …' + its own line 'unclassified: <n> track unknown · <m> status unknown' (never summed) + include buttons labelled with the FACET count (differs from the bucket when a paper fails both defaults). 'Limits you wrote:' line from /parse filters (non-default, non-zero-width span; several clauses listed as such). Every ClauseReason and reducer code has a disabled-with-reason state (W13 table): controls are aria-disabled (focusable) and aria-describedby the whyBlocked message; STALE_CLAUSE text only after 500 ms. NEW component-level refusal DRAFT_DIRTY: while the editor text != searched q, sidebar, include, Export and Save are disabled with copy SB-6 (a facet click would discard unsearched edits). Year: read-only counts + 'Edit year: in the query' (no reducer action yet; decision-011). Proposed follow-ups for the main session: (1) a reducer yearRange action + goldens so Year gets a control; (2) additive per-clause spans for multiple_clauses/nested/mixed_fields (until then 'Show the clauses' walks the server ast). Wrap growth (spec 05 open consideration): keep as built for M3b, revisit after TASK-047.

Pre-pass fixes that land in TASK-042: include button number = facet count in label, accessible name and announcement (M1, test name == label); a field that is a user limit is named on the banner and the Limits line itemises what it leaves out from facets (M2); include that adds 0 is labelled so (S5); zero results show the Limits line + exact-match hint (S6); 'Edit year:' selects the existing clause or inserts a selected year:2020..2026 (S14).

Built as planned. Deviations: 1) one DOM order for both widths: results header, banner and Limits line come before the sidebar (the design keyboard path had the sidebar first; recorded in the design doc). 2) Year got a real control on the TASK-092 actions (per-year add/remove, from-to Set years, All years) plus Edit year: in the query. 3) The paper status line names the venue as venue + year; the full conference name is not in the API. 4) Back to results is always a link (no-referrer policy). SearchWorkspace changed only by a results ReactNode prop, a WorkspaceSlotContext provider (workspace-slot.ts) and a pending-selection effect, to merge cleanly with TASK-043. Verified: uv run pytest 3908 passed, 2 skipped (opt-in); npm test 2026 passed in 20 files; next build OK; make lint and make tooling green; production build smoke-tested against op serve on the local index a7cfd04b656f in headless Chromium: facet toggle, year untick, paging focus, paper highlights, 320 px without sideways scroll, no console errors.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Filters, exclusion banner, results, paging, error states and the paper page (spec 05 components 4-6, design W4-W14 and P1-P5). search-view.tsx runs GET /search (keepPreviousData) and draws into the new results slot of SearchWorkspace; a 422 goes back as the refusal (squiggles) with the last good result kept, marked stale, with Restore it; 429, 503, 500, non-JSON and unreachable answers get blocks with Retry (countdown from Retry-After); index-swap notice; zero-results state. Sidebar: venue, track and status checkboxes from the /parse filters and facet counts, every control checked with whyBlocked plus DRAFT_DIRTY, aria-disabled and described by the reason (STALE only after 500 ms), Show the clause(s) from blocking_spans; year control on yearSet, yearClear, yearAdd and yearRemove. Banner: excluded and unclassified lines, include buttons labelled with the facet count (M1), adds-0 wording (S5), user-limit naming (M2), PRISMA disclosure; Limits you wrote line with leave-outs. Hits: mark plus bold at API spans only, excerpt window, badges, links. Paper page: matched, not matched, direct link, refused-q fallback, not found, provenance table. Tests: search-view.test.tsx (35), exclusions.test.ts, excerpt.test.ts (seeded surrogate sweep), paper-view.test.tsx (13); all suites green; smoke-tested against op serve.
<!-- SECTION:FINAL_SUMMARY:END -->
