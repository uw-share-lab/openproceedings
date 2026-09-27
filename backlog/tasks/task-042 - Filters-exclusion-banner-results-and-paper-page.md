---
id: TASK-042
title: 'Filters, exclusion banner, results and paper page'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 20:27'
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
- [ ] #1 Filter and facet clicks rewrite q; workshop off by default
- [ ] #2 Banner itemises unknown; each include label shows the real facet delta
- [ ] #3 Highlights rendered from API spans only; /paper/[id] with provenance
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Facet/include clicks go through reduce() in src/lib/search-state.ts (TASK-039); its FilterClause input needs per-field clause spans from /parse, which is TASK-078.

TASK-087 done (dependency satisfied): /paper/[id] gets highlights from GET /papers/{id}?q=&mode= (fields matched + highlights, null without q; matched:false = the query incl. default filters doesn't match the paper, lists empty). Result list must link /paper/<id>?q=<q>&mode=<mode>; on a 422/429 for the q, refetch without q and show a one-line notice (spec 05 §Pages).

Design (TASK-033, 2026-09-27): /search sidebar, banner, results, paging and API error states from docs/design/2026-09-27-search-workspace.md §W5, W8-W10, W12-W14; /paper/[id] from docs/design/2026-09-27-export-records-and-paper.md §P1-P5; copy deck §1, §7. Decisions: numbered pages (router.replace, page input, focus to the results heading), not infinite scroll. Banner = standing string 'excluded: …' + its own line 'unclassified: <n> track unknown · <m> status unknown' (never summed) + include buttons labelled with the FACET count (differs from the bucket when a paper fails both defaults). 'Limits you wrote:' line from /parse filters (non-default, non-zero-width span; several clauses listed as such). Every ClauseReason and reducer code has a disabled-with-reason state (W13 table): controls are aria-disabled (focusable) and aria-describedby the whyBlocked message; STALE_CLAUSE text only after 500 ms. NEW component-level refusal DRAFT_DIRTY: while the editor text != searched q, sidebar, include, Export and Save are disabled with copy SB-6 (a facet click would discard unsearched edits). Year: read-only counts + 'Edit year: in the query' (no reducer action yet; decision-011). Proposed follow-ups for the main session: (1) a reducer yearRange action + goldens so Year gets a control; (2) additive per-clause spans for multiple_clauses/nested/mixed_fields (until then 'Show the clauses' walks the server ast). Wrap growth (spec 05 open consideration): keep as built for M3b, revisit after TASK-047.

Pre-pass fixes that land in TASK-042: include button number = facet count in label, accessible name and announcement (M1, test name == label); a field that is a user limit is named on the banner and the Limits line itemises what it leaves out from facets (M2); include that adds 0 is labelled so (S5); zero results show the Limits line + exact-match hint (S6); 'Edit year:' selects the existing clause or inserts a selected year:2020..2026 (S14).
<!-- SECTION:NOTES:END -->
