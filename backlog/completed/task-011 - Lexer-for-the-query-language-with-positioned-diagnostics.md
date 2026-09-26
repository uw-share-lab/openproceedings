---
id: TASK-011
title: Lexer for the query language with positioned diagnostics
status: Done
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 03:33'
labels:
  - query
milestone: m-1
dependencies:
  - TASK-010
  - TASK-001
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Tokens for uppercase operators, |, -, phrases, fields, ranges, * and $ wildcards, NEAR/n (spec 02 §Grammar).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Lowercase and/or/not are terms; WARN_LOWERCASE_OPERATOR emitted
- [x] #2 Every error carries a half-open code-point span over q and a fix hint
- [x] #3 Property test: random strings never raise, only return diagnostics
- [x] #4 Golden (decision-001): `a$`/`ab*` → stem-too-short error; `"large language model$"` lexes a wildcard inside a phrase
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Registry: add PARSE_UNTERMINATED_PHRASE, PARSE_BAD_NEAR, PARSE_WILDCARD_NOT_SUFFIX.
2. Tests first: golden lex table (operators, | and -, fields, ranges, NEAR/n, phrases incl. curly quotes, escapes, wildcards incl. inside phrases and LaTeX $…$ words), every error code with its span, WARN_LOWERCASE_OPERATOR only between terms; Hypothesis: never raises, spans ordered and within q, every non-space char covered.
3. query/lexer.py: lex(q) -> LexResult(lexemes, warnings, errors); one frozen Lexeme type; pure, stdlib + normalize.
4. Spec 02 §Grammar lexical rules as built; query-grammar skill; decision-001 stem wording (letters and digits after normalisation).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review dispositions: 'split Lexeme into per-kind types' (task-011 and task-013 reviews, Nit) → rejected: Lexeme is internal to lexer.py/parser.py and built in one place; a union would add isinstance ceremony to every parser branch without catching any bug the reviews found. Everything else from both reviews is fixed (commits 106811f and the task-013 review round).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
query/lexer.py: lexemes with code-point spans; nothing silently reinterpreted (ambiguous minus, mid-word/detached wildcards, stray colon, bare NEAR are errors; look-alike operators, lowercase operators, dropped symbols warn); NFKC look-alikes act as syntax (table re-derived from Unicode); LaTeX math regions come from the tokenizer. Three review rounds; mutants killed or documented equivalent; properties clean at 50k.
<!-- SECTION:FINAL_SUMMARY:END -->
