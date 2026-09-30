---
id: TASK-140
title: WARN_MIXED_AND_OR message text drops a branch that failed to parse
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 02:40'
updated_date: '2026-09-30 04:19'
labels:
  - query
milestone: m-3
dependencies:
  - TASK-099
ordinal: 123000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Since TASK-099 (not yet merged when this was filed), a mixed AND/OR level with a branch that failed to parse (e.g. 'a b OR () OR c') gets reading: null, so the editor offers no button, but the warning's message still quotes '(a b) OR c', silently dropping the failed branch in the prose. Spec 02 §diagnostics.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The message matches the reading rule (quotes the level faithfully or omits the parenthesised reading when a branch failed)
- [x] #2 Parser golden rows pin it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Choice: OMIT the parenthesised reading (not quote the level from source text). A faithful quote of a broken level (e.g. `(a b) OR () OR c`) would show a reading the diagnostic's `reading` field doesn't carry, and suggests a grouping the user can't load; the fix-first message follows error-diagnostics (fix hint) and ux-writing (what happened, then why, then fix). New message, when part of the level doesn't parse: "AND and OR are mixed here without parentheses, and part of it doesn't parse — fix the errors here first, then add parentheses to choose how it groups (AND binds tighter than OR)." (plus the Scholar note in Scholar mode). The normal message and its 120-char clip are unchanged.

Rule widened (the new property found it): the reading is withheld when any error falls inside the level's token range (parser.reported), not only when a branch has no node. Old code also gave lossy readings for `a b () OR c` → `(a b) OR c` and `a b OR c ()` → `(a b) OR (c)` (the AND group's node span stops before the failed part). On those levels the span is now the whole level (was the node spans, e.g. `() OR a b` spanned only `a b`); normal levels' spans unchanged. `a b OR c)` (the error is outside the level) keeps its reading.

Tests: test_parser.py FAILED table (11 rows: `()`, `""`, lone `-`, `NOT`, `title:`, failed-first, errors inside an AND group, trailing OR, Scholar) + exact normal message; test_properties.py test_the_mixed_message_quotes_only_the_reading_it_carries (queries() plus a broken-piece variant: the message quotes exactly clip(reading, 120) or nothing, and a reading is never lossy vs the text at its span); verified it fails on origin/dev's parser. Frontend: nothing parses the message (diagnostics-row/editor use `reading`); copy deck row added. Docs: spec 02 Precedence, spec 04 Conventions, error-diagnostics skill, Diagnostic.reading description (make openapi regenerated).

Verification: backend unit+golden+contract 5547 passed, 1 failed (test_a_facet_of_a_field_the_query_never_filters_counts_its_matches: hypothesis deadline under load avg ~90; passes on 3 seeded reruns, unrelated); Vitest editor + search 112 passed; make lint and make tooling green. Full make test not run (load avg 66-93).

Found, not fixed: 'Show how it was read' is still offered on WARN_MIXED_AND_OR when the query has errors, but QueryTree renders only when effective_ast is non-null, so the button opens nothing (search-workspace.tsx / diagnostics-row.tsx).

Review round (approved; 2 Shoulds, 3 Nits fixed): (S1) a level with errors now quotes itself as typed, clipped at 120 like a reading (not a reading), so the message stands alone and nested levels read differently: "`a b OR () OR c` mixes AND and OR without parentheses, and it has errors — fix them first, then add parentheses to choose how it groups (AND binds tighter than OR)." Property expects the clipped span text when reading is null (nothing on the summary); goldens for nested and long levels. (S2) the 'Show how it was read' dead button is fixed: DiagnosticsRow takes treeAvailable (effective_ast non-null) and offers it only then; Vitest covers both states (verified the new case fails without the fix). Nits: spec 02 / skill say 'an error raised while parsing the level'; 'has errors' wording; BROKEN comment lists OR. Design doc search-workspace updated (Load with parentheses reads the reading field). Verification: parser/properties/diagnostics/compat + contract 1916 passed, 1 skipped; Vitest search+editor 1596 passed; make lint, make tooling green.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
WARN_MIXED_AND_OR no longer quotes a reading its `reading` field doesn't carry. When parsing the level raises an error (a failed branch like `a b OR () OR c`, or an error inside an AND group like `a b () OR c`, which used to give lossy readings), `reading` is null, the span covers the whole level, and the message quotes the level as typed (clipped at 120) and says to fix the errors first, then add parentheses. The normal message is unchanged. The frontend no longer offers 'Show how it was read' when the query has errors (no tree renders). Pinned by parser golden rows (`()`, `""`, lone `-`, `NOT`, `title:`, nested, long, Scholar), a property (message quotes exactly clip(reading) or the clipped level text; readings never lossy), and Vitest for both button states. Spec 02, spec 04, error-diagnostics skill, copy deck, search-workspace design and the OpenAPI description updated. Verified: backend parser/properties/diagnostics/contract 1916 passed; Vitest 1596 passed; make lint, make tooling.
<!-- SECTION:FINAL_SUMMARY:END -->
