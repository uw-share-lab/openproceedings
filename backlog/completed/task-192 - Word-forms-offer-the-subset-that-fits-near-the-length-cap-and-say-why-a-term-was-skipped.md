---
id: TASK-192
title: >-
  Word forms: offer the subset that fits near the length cap, and say why a term
  was skipped
status: Done
assignee: []
created_date: '2026-10-05 08:39'
updated_date: '2026-10-06 00:18'
labels:
  - frontend
  - query
  - ux
milestone: m-3
dependencies: []
ordinal: 136000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-175 offers no Add $ at all when adding every $ would pass the 2,000-code-point query cap, although some would fit, and a term the notice names but that cannot take a $ gets only a generic sentence in the chooser.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Near the cap the terms that fit are offered and the rest are named as not fitting; each skipped term carries its reason from the server (an additive field); tests and spec 02/05 as built
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
exact.dollar_verdicts splits the rules into offered places and refusals with a reason (too_short, symbol, dollar_nearby, operator_word); wordforms.report adds too_long and unconfirmed. Near the cap (read-back of every edit is exactly PARSE_TOO_LONG) wordforms._fit takes terms in first-written order, each in all its places or none: raw length counted exactly ($ vs '$ ' recounted per choice), canonical counted as +1 per place (the most a $ adds) from the last measured length, up to 3 read-back rounds. A term whose own places dedupe in the canonical form can be passed over by a few code points (spec 02 says so). POST /parse adds word_forms_skipped [{term, reason}] (additive; reason an open enum in OPEN_ENUMS). UI: 'Left as typed:' list per reason under the buttons in both states (replaces the generic NOT_OFFERED sentences); near the cap 'Add $ to the N terms that fit'. e2e word-forms.spec.ts updated (notice helper now :scope > li; the and-reason assertion moved) but not run. Pre-existing, unrelated: test_compare.py::test_the_added_papers_come_as_the_exports_own_ris fails on the clean branch too.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Near the 2,000-code-point cap /parse now offers the terms whose $ fit and names the rest; every named term not offered comes in the additive word_forms_skipped with the server's reason, and the chooser line lists them by reason. Specs 02/04/05, copy deck ED-19, design doc and two skills updated as built; openapi.json, schema.ts, word-forms-golden.json (new near-cap case) and record-fixture.json regenerated.
<!-- SECTION:FINAL_SUMMARY:END -->
