---
id: TASK-143
title: API 422 validation message quotes the field path without diagnostics.clip()
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 06:39'
updated_date: '2026-10-01 23:50'
labels:
  - api
  - bug
milestone: m-3
dependencies: []
references:
  - backend/src/openproceedings/api/errors.py
  - backend/src/openproceedings/diagnostics.py
ordinal: 120000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-141's review (PR #48, 2026-09-30). TASK-141 made diagnostics.clip() the one way a message quotes client-supplied text: whitespace runs collapse to one space, and a backtick or a Cc/Cf/Cs character is written as its Python escape, so a message stays one line of visible characters and its backtick quoting holds (the frontend's `Coded` pairs backticks, and it renders API messages too). The API's 422 handler (`_validation`, `backend/src/openproceedings/api/errors.py:185`; the `loc` join at line 191) joins each pydantic error's `loc` into the `API_BAD_PARAM` message raw. `loc` can name a key the client sent (an unexpected body key), so a newline, NUL, ESC, U+202E or backtick in a JSON key reaches the message unescaped. The offending value is already left out and the log gets the code only, so this is message hygiene, not a log leak.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every client-controlled part of a 422 `API_BAD_PARAM` message (each `loc` element, and anything else taken from the request) goes through `diagnostics.clip()` or its escaping, so a key containing a newline, tab, NUL, ESC, U+2028, U+202E or a backtick appears escaped and the message is one line
- [x] #2 An API test posts a body with such keys and asserts the exact message; a property over arbitrary JSON keys asserts the message has no control characters and no unescaped client backtick
- [x] #3 Spec 04 §Error handling (the `API_BAD_PARAM` row) and the error-diagnostics skill's rule that query text is quoted only through `diagnostics.clip` both say request locations are quoted through clip() too
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Pydantic's 422 errors now go through api/errors.py::bad_param_message: each location between backticks with every string part through clip(p, 30) (as deps.strict_query quotes an unknown parameter), pydantic's own text through clip(msg, 200), and at most MAX_NAMED_PARAMS (moved from deps.py to errors.py) named, the rest counted, so the message no longer grows with a body of many unexpected keys. Verified: test_errors.py exact-message test, cap test and a Hypothesis property over arbitrary JSON keys (real ParseRequest validation errors); make test (6087 passed, 2 skipped; vitest 3060 passed), make lint, make tooling.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
API 422 API_BAD_PARAM messages quote each request location through diagnostics.clip between backticks (a body key is client text), escape pydantic's text the same way, and name at most 5 problems. Spec 04 §Error handling and the error-diagnostics skill say so. Verified by an exact-message API test, a cap test and a property over arbitrary JSON keys; full make test, lint and tooling green.
<!-- SECTION:FINAL_SUMMARY:END -->
