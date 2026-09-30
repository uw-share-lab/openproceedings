---
id: TASK-143
title: API 422 validation message quotes the field path without diagnostics.clip()
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 06:39'
updated_date: '2026-09-30 06:39'
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
Found by TASK-141's review (PR #48, 2026-09-30). TASK-141 made diagnostics.clip() the one way a message quotes client-supplied text: whitespace runs collapse to one space, and a backtick or a Cc/Cf/Cs character is written as its Python escape, so a message stays one line of visible characters and its backtick quoting holds (the UI pairs backticks). The API's 422 handler (`backend/src/openproceedings/api/errors.py::_validation`, ~line 191) joins each pydantic error's `loc` into the `API_BAD_PARAM` message raw. `loc` can name a key the client sent (an unexpected body key), so a newline, NUL, ESC, U+202E or backtick in a JSON key reaches the message unescaped. The offending value is already left out; the log gets the code only, so this is message hygiene, not a log leak.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every client-controlled part of a 422 `API_BAD_PARAM` message (each `loc` element, and anything else taken from the request) goes through `diagnostics.clip()` or its escaping, so a key containing a newline, tab, NUL, ESC, U+2028, U+202E or a backtick appears escaped and the message is one line
- [ ] #2 An API test posts a body with such keys and asserts the exact message; a property over arbitrary JSON keys asserts the message has no control characters and no unescaped client backtick
- [ ] #3 The error-diagnostics skill and spec 04 (where it describes the 422 `API_BAD_PARAM` message) say that request locations are quoted through clip()
<!-- AC:END -->
