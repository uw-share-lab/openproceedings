---
id: TASK-134
title: Results list names each abstract's source (decision-018 attribution)
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 00:52'
updated_date: '2026-09-30 02:43'
labels:
  - frontend
milestone: m-6
dependencies: []
ordinal: 117000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-018 requires attribution and a source link on every record; PMLR's CC BY 4.0 needs a citation and a hyperlink to PMLR. TASK-063 found the paper page meets it (authors, links, per-field sources), but the results list (hit-item.tsx) shows the abstract with no authors and nothing naming where it came from.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each result shows authors and names the abstract's source with a link, without crowding the dense list (ui-design-system)
- [x] #2 PMLR records carry the citation and PMLR hyperlink wherever their abstract is shown
- [x] #3 Component and e2e tests pin it; exports' provenance noted if attribution must cover them
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. API (additive, /api/v1): Hit.abstract_source {source, origin, url} | null, computed once per record in RecordFile's load pass; the route looks it up per hit.
2. UI: hit-item shows authors (first 3 + et al., toggle) and 'Abstract: <site>' linking the paper's page, '(via RIS import)' for RIS-imported abstracts; link aria-label adds 'abstract source for <title>'; 'Skip to pages' link at the top of the results.
3. Tests: unit (attribution rules, loader), contract (per-site, ris-only, PMLR, null), Vitest, e2e (PMLR, OpenReview, RIS via ICLR Proceedings, skip link, 24px targets); endpoint bench includes attribution.
4. Docs: specs 03/04/05/07, api-contract and ui-design-system skills, copy deck RH-12..14, search-workspace design.
5. Exports: noted only (follow-up by coordinator).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementation (after review round 1, rebased on origin/dev 7f75d09):
- API (additive): Hit.abstract_source = {source: Source (the claim precedence took, open enum), origin: Origin|null (new open enum 'abstract origin': openreview, neurips_proceedings, iclr_proceedings, pmlr, iclr_archive), url: str|null} | null. For a ris claim the evidence prefix names the route: scholarmend:openreview_api -> openreview + urls.forum; scholarmend:proceedings_page -> the site urls.proceedings's host names (NeurIPS/ICLR/PMLR) + that link; no proceedings link -> site from the evidence url's host, unlinked; unknown route -> origin null, no link. ingest/dedup.py::attribution (pure), urls.proceedings_site.
- Served snapshot 2026-09-23-d5ab3d6d444a: 990 ris->neurips_proceedings linked, 639 ris->iclr_proceedings linked, 162 ris->openreview linked, 4 ris->neurips_proceedings unlinked (no urls.proceedings; evidence url cut short), 10 without abstract. Previously all 1,795 showed 'an imported RIS file'.
- Cost: RecordFile computes attributions in its existing load pass (0.06 s for the whole served snapshot load); a 50-hit page is ~95 us of dict lookups + response objects, no file I/O; ~230 B/record. Missing record in the served snapshot stays a 500. Endpoint bench rows (test_search_endpoint_first_page) now run over attributed records and include page_attributions. Spec 03 and 07 §E note it.
- UI: 'Abstract: <site>' (+ ' (via RIS import)'), link aria-label '<site>, abstract source for <title>' (aria-label, not a hidden span: inside the inline-flex link Chrome's name got 'PMLR , abstract…'); 'Skip to pages' link above the results list (sr-only until focused) focuses the Pages nav; keyboard paging e2e uses it and its Tab limit is back to 120. Axe timeout left at 120 s.
- Tests: make test (backend 5453 passed, 2 skipped; Vitest 2603), make e2e 17 passed, make lint, make tooling green. e2e fixture 'attributed' now has ris-only records (every 7th: proceedings_page for all venues, openreview_api for every other ICLR one).
- Linux visual baselines left to the coordinator (from the PR's CI artifact); darwin baselines unchanged by the refresh run (within tolerance).
- Exports (Should 3, follow-up to be filed by the coordinator): RIS N1 and BibTeX note carry only the openproceedings provenance line; RIS UR / BibTeX url give source links, but no export names which source the abstract came from. Not changed here (export mapping is contract).
- decision-018 is stale at lines 64-66 (Consequences, first bullet, 'What exists already…'): it says the result list shows no authors and no statement of the abstract's source (TASK-134, a launch prerequisite). After TASK-134 merges that sentence should say the result list shows authors and 'Abstract: <site>' with a link (and '(via RIS import)'); left for the coordinator/decision owner, not edited here.
<!-- SECTION:NOTES:END -->
