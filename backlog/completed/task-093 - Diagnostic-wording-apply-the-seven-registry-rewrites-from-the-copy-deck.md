---
id: TASK-093
title: 'Diagnostic wording: apply the seven registry rewrites from the copy deck'
status: Done
assignee: []
created_date: '2026-09-27 20:29'
updated_date: '2026-09-27 20:55'
labels:
  - query
milestone: m-3
dependencies: []
ordinal: 90000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-033 docs/design/2026-09-27-copy-deck.md: seven diagnostic messages to rewrite (what→why→fix). Update the registry/parser messages and every golden/test that pins them; no code or status changes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The seven registry messages read as the copy deck proposes; codes, statuses and spans unchanged
- [x] #2 Every test that pins the text is updated, and a test pins each new message verbatim with its code and span
- [x] #3 The copy deck marks the seven rewrites applied
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Apply the seven copy-deck section 2 rewrites in query/parser.py and query/lexer.py (codes, statuses, spans unchanged). 2. Pin each new message verbatim with its code and span in backend/tests/unit/test_parser.py. 3. Mark the rewrites applied in the copy deck and update the design docs that quote the old text.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Applied in query/parser.py and query/lexer.py; codes, statuses and spans unchanged. No existing test pinned the old text (grep + full suite); new table test_the_copy_deck_rewrites_are_the_registry_text pins all seven verbatim with code and span (15 rows incl. each field's FIELD_FILTER_SYNTAX example and Scholar source:), plus test_a_canonical_overflow_suggests_shortening_not_splitting for the decision-008 variant. Choices: PARSE_UNBALANCED_PAREN quotes the group from its ( to where the parsed group ends (to the end of q in a filter group), clipped at 40; PARSE_STRAY_COLON quotes a lone colon with the word after it (: model), a joined one as written (:model); FIELD_FILTER_SYNTAX uses each field's own values (venue ICLR OR ICML, year 2020 OR 2024..2026, track main OR position, status accepted OR withdrawn). api/deps.py's own 'split it into several searches' (a different, API-side message) is out of scope and untouched. Copy deck section 2 and its before/after table now say Applied; the syntax-help and search-workspace design mocks quote the new PARSE_UNBALANCED_PAREN text.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Applied the copy deck's seven registry rewrites (what, why, fix) in query/parser.py and query/lexer.py: PARSE_UNBALANCED_PAREN, PARSE_ALL_NEGATIVE, PARSE_TOO_DEEP, PARSE_STRAY_COLON, PARSE_TOO_LONG (both variants), FIELD_FILTER_SYNTAX, WARN_CJK_RUN. Codes, statuses and spans are unchanged. No existing test pinned the old text, so a new table test pins each message verbatim with its code and span. The copy deck marks all seven Applied. Verified: uv run pytest 3835 passed, npm test 348 passed, make lint, make tooling.
<!-- SECTION:FINAL_SUMMARY:END -->
