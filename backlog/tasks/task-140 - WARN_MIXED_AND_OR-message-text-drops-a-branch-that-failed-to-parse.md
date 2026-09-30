---
id: TASK-140
title: WARN_MIXED_AND_OR message text drops a branch that failed to parse
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 02:40'
updated_date: '2026-09-30 04:00'
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
<!-- SECTION:NOTES:END -->
