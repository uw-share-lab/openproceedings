---
id: TASK-175
title: >-
  One-click word forms: apply the $ suggestion from the Scholar-mode no-stemming
  notice
status: In Progress
assignee: []
created_date: '2026-10-05 01:47'
updated_date: '2026-10-05 02:16'
labels:
  - frontend
  - query
  - ux
milestone: m-3
dependencies: []
references:
  - docs/specs/05-frontend.md
  - docs/specs/02-query-language.md
ordinal: 119000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A reviewer who pastes a Google Scholar string gets far fewer papers than the same string means in Scholar, because Scholar stems and openproceedings matches exactly (guarantee 1). On 2026-10-04 the Trust-Evals primary string returned 27 papers as typed and 67 once $ was added by hand to five terms. The COMPAT_NO_STEMMING notice says to add $ but leaves the typing to the user, who may not know which terms it names. Stemming in the engine is ruled out by guarantee 1; the fix is an explicit rewrite of the query text that the user triggers and sees (guarantees 3 and 6).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The no-stemming notice offers an action that rewrites the query text, adding $ to the terms the notice names; the engine, tokenizer and index are unchanged and nothing is expanded unless the rewritten text says so (00 guarantee 1)
- [x] #2 The rewrite is visible in the editor and the URL before or as the search runs, is undoable, and the saved query string alone reproduces the result set (00 guarantees 3, 4)
- [x] #3 Every expansion the added wildcards produce is shown as existing wildcard expansions are (00 guarantee 6)
- [x] #4 Terms where $ is invalid or already present (phrases' inner words per spec 02, filter values, terms with a wildcard) are left alone, with tests for each case
- [x] #5 Spec 05 and the syntax help describe the action as built
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Server reports where a $ can go: query/wordforms.py::word_forms(q, parse(q, mode)), served as POST /parse word_forms ({term, at, insert}); rules from the lexer's own stem conditions, read back by parsing the edited query.
2. Tests first: test_wordforms.py table (each AC4 case) + property (each edit alone and all together change only the named terms); contract test for /parse and for /search expansions of the edited query.
3. Frontend: src/lib/word-forms.ts splices (checked against a backend-generated golden); the COMPAT_NO_STEMMING line in diagnostics-row.tsx offers Add $ to all N terms and Choose terms; an edit of the draft, never a search.
4. Specs 02 (Word forms), 04 (/parse), 05 (Components 1), copy deck ED-19, syntax help, skills, README, CLAUDE.md as built; make openapi; regenerate record-fixture.json.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built on task-175-word-forms (off feat/review-comparison-tools).
Design: POST /parse reports word_forms ({term, at, insert}) from query/wordforms.py; the UI splices them into the draft (src/lib/word-forms.ts) from the COMPAT_NO_STEMMING line (Add $ to all N terms / Choose terms). Rejected: the client finding terms (re-parsing), a field on Diagnostic (parse would recurse for the read-back; records and /search would carry it), any server-side stem flag (guarantee 1).
AC1: no engine/tokenizer/index change; test_parse_word_forms.py shows the unedited query expands nothing. AC2: draft edit (one undoable change, Revert edits), URL on Search; canonical replays natively to the same ids. AC3: /search query.expansions has a key per added $. AC4: test_wordforms.py table (phrase inner words, filter and source: values, existing wildcards, short stems, symbols, LaTeX runs) + property. AC5: spec 05 Components 1, spec 02 Word forms, spec 04, copy deck ED-19, /help/syntax Scholar section.
Not done: no Playwright step for the action (e2e not run under machine load); nothing offered when all edits together would exceed the 2,000-code-point cap.
<!-- SECTION:NOTES:END -->
