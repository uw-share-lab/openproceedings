---
id: TASK-099
title: '/parse: a machine-readable reading on WARN_MIXED_AND_OR'
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-27 21:11'
updated_date: '2026-09-30 02:20'
labels:
  - api
  - frontend
milestone: m-3
dependencies: []
ordinal: 96000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-041's 'Load with parentheses' action extracts the parenthesised reading from the warning's message text. Add an additive field on the diagnostic (e.g. reading: the canonical parenthesised query) so the frontend doesn't parse prose; additive under /api/v1.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The warning carries the reading as a field (additive; test_openapi_additive passes)
- [x] #2 The editor uses the field and no longer parses message text
- [x] #3 Golden test pins the reading for the parser's mixed AND/OR cases
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Diagnostic gains reading: str | None (always sent, nullable: additive), set exactly on WARN_MIXED_AND_OR (READING_CODES, model validator); the parser passes the unclipped reading. StoredDiagnostic gains it too (null on older records).
2. make openapi; fix exact-dict contract tests; regenerate record-fixture.json.
3. Goldens: every mixed case in test_parser.py pins (span, reading) and that splicing it keeps canonical and clears one warning; property test over queries() in both modes; validator unit test; /parse contract test.
4. Frontend: ServerDiagnostic/Item carry reading; withParentheses reads the field (regex removed); Vitest for the action; e2e for a >120-code-point reading against the real server.
5. Docs: spec 02/04/05, error-diagnostics and codemirror-lezer skills.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Field: `Diagnostic.reading: str | null`, always sent (required + nullable, so additive under /api/v1; test_openapi_additive passes against origin/dev). Set exactly on WARN_MIXED_AND_OR (`READING_CODES`, enforced by a model validator), null on every other code. Value: the warned level's text at `span` with each AND group parenthesised and branches joined by ` OR ` (`a b OR c` -> `(a b) OR c`), never clipped (the message clips at 120). Chosen over a code-specific payload: one shape everywhere, one nullable key. Not the canonical form: canonical adds defaults/field prefixes, while the action splices the reading over the span in the user's own text. `StoredDiagnostic` got the same key (null on records saved before), so a record returns what it stored.

Frontend: `ServerDiagnostic`/`Item` carry `reading`; `withParentheses` reads it (MIXED_READING regex removed). No version-skew handling exists (frontend and API ship together), so no message fallback; a null reading simply offers no button.

Tests: test_parser.py goldens pin (span, reading) for 16 mixed cases (native + scholar, NEAR, `|`, newline, astral, nested, >120 cp) and that splicing keeps canonical and clears one warning; property test over queries() in both modes; validator unit test; /parse + /search contract test; exact-dict contract tests and record-fixture.json updated; Vitest for the action (field only, never message; long reading; null reading); new e2e against the real server with a 147-cp reading. make test (5361 py + 2594 vitest), make e2e (16), make lint, make tooling green. One first make test run hit a hypothesis DeadlineExceeded in golden/test_reference_200 (untouched, timing under xdist load); passed alone and on the full rerun.

Docs: spec 02 (Precedence rule, ParseResult), 04 (Conventions), 05 (Components 1), error-diagnostics and codemirror-lezer skills; the TASK-041 learning's follow-up ticked.
<!-- SECTION:NOTES:END -->
