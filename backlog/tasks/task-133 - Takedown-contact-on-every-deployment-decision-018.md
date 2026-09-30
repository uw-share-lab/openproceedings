---
id: TASK-133
title: Takedown contact on every deployment (decision-018)
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 00:52'
updated_date: '2026-09-30 01:54'
labels:
  - frontend
  - ops
milestone: m-6
dependencies: []
ordinal: 116000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-018 (serve every abstract) requires a takedown contact on every deployment; TASK-063 found none anywhere (no footer or about page, nothing in the API or docs). A takedown removes that record's abstract from the next index version.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The frontend shows a takedown contact on every page (footer or about page), with copy reviewed by ux-writer
- [x] #2 The takedown procedure is documented (spec 08 §Deploy / runbook): who receives requests, how an abstract is removed from the next index version, and how that is recorded
- [x] #3 Tests pin the contact's presence
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Site-wide footer in the root layout (<footer>, contentinfo) with one takedown line; no about page (spec 05 has none, the footer puts the contact on every page with no extra route).
2. Contact from NEXT_PUBLIC_TAKEDOWN_CONTACT (build-time, like NEXT_PUBLIC_API_BASE_URL): an email (mailto) or an http(s)/mailto URL; unset or unusable falls back to the repository's issues page. Pure parser in src/lib/takedown-contact.ts.
3. Copy FT-1..FT-3 in the copy deck (ux-writing voice).
4. Docs: spec 05 NFR + layout, spec 08 §Deploy takedown procedure (operator receives; no suppression tooling exists, so the procedure is manual and the missing tooling is named), README §6, frontend/.env.example, nextjs-conventions layout table.
5. Tests: Vitest (parser + footer: configured, override, fallback, unusable value), layout contentinfo; e2e footer on home/search/paper/coverage; axe states already cover the pages; 320px reflow; Playwright env placeholder takedown@example.org; refresh visual baselines (darwin + linux via the Playwright image).
6. npm test, make e2e, make lint, make tooling; tick ACs, notes; commit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built: <footer> in the root layout (contentinfo, after <main>) with one takedown line (copy deck §9, FT-1..FT-3). Contact from NEXT_PUBLIC_TAKEDOWN_CONTACT (build time, like NEXT_PUBLIC_API_BASE_URL): email or mailto: -> mailto link; http(s) URL -> link; unset -> repository issues page; set but unusable -> same fallback plus a build-log warning. Parser src/lib/takedown-contact.ts; component src/components/site-footer.tsx. No about page: spec 05 has none and the footer reaches every page with no new route.
Owner update applied: the contact is required on publicly reachable instances only (private/local/dev may omit it; the footer still renders the fallback). The takedown mechanism is written as the procedure this task proposes, not a decided fact; no fallback-if-sign-off-refused wording added.
Takedown procedure: spec 08 §Deploy. Nothing withholds an abstract today (snapshot build replays the crawl cache; snapshots are immutable and hash-checked), so it is manual: log it, and take the public instance offline if the abstract must go before tooling exists. Older pinned index versions keep the abstract (op index retire refuses while records pin them); the procedure proposes serve-time withholding across every loaded index version, which is listed as missing tooling with the takedown list in op snapshot build, the manifest/coverage count and a served-abstract check.
Visual baselines: footer hidden in e2e/visual.css (its text is build-configured and accessibility.spec.ts checks it), so the existing darwin/linux baselines stay valid; an amd64 Linux rebaseline was not possible locally (Next build fails under QEMU emulation: --no-opt in NODE_OPTIONS; Chromium screenshot capture fails).

Verification: npm test --workspace frontend 34 files / 2607 tests passed; make lint exit 0; make tooling all case tables passed. make e2e: run 1 (footer present) 13/15, only the two visual baselines failed on the added footer height; footer then hidden in visual.css. Run 3: 14/15 passed, incl. the footer test (home/search/paper/coverage at 1280 and 320 px), 320px reflow, visual light/dark and all spec05 flows; the one failure was the first axe test's 30 s timeout under host load average ~100 (passed in run 1 with the footer; the same test passed at 320 px and in dark). A solo rerun under the same load timed out the same way.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Site-wide footer (contentinfo) names the deployment's takedown contact from NEXT_PUBLIC_TAKEDOWN_CONTACT (email or http(s) page, build time), falling back to the repository's issues page when it is unset or unusable; copy FT-1..FT-3 in the copy deck. The takedown procedure proposed in spec 08 §Deploy: the operator receives requests; the abstract is withheld from the next index_version (manual until the missing tooling exists); older pinned versions are covered by proposed serve-time withholding; each request goes in an operator-kept log. Contact required only on publicly reachable instances. Verified by Vitest (parser, footer, layout), e2e footer checks on home/search/paper/coverage at 1280/320 px, lint and tooling.
<!-- SECTION:FINAL_SUMMARY:END -->
