---
id: TASK-266
title: 'block-ai-attribution: a command it can''t parse gets only the text-only scans'
status: In Progress
assignee:
  - '@jeevanparmar'
created_date: '2026-10-19 11:49'
updated_date: '2026-10-25 15:16'
labels:
  - hooks
  - security
dependencies: []
priority: medium
ordinal: 173000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
On ParseError (.claude/hooks/block-ai-attribution.sh ~line 271) the hook runs the raw-text and tokenize scans, refuses only a gh/git command whose text matches its file-option regex, then exits 0. A gh/git write it can't parse whose file option the regex misses (a flag held in a variable, say) is let through unread. Found during the 0.4.0 work.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decide: refuse every gh/git write the gate can't parse, or widen the file-option check; record why
- [x] #2 A case-table row in test-openproceedings-gates.sh fails on the old behaviour
- [x] #3 make tooling and make mutate-changed: no survivors
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24: refuse, not widen: a command the gate can't parse has no readable options, so no file-option regex can be complete (a flag in a variable). may_write() on the joined text refuses git message verbs, gh pr/issue/release writes and any gh api; other unparseable commands stay allowed. 22 rows (the $OPT_266 row fails on dev), 2 rows flipped allow->block on purpose. 13 mutants KILLED; narrowed mutate runs (TASK-253/248/wrapper/unparseable/266/269) 0 problems; full mutate-changed stopped at 199/455, all killed (load ~270); qa-auditor reruns it in the gate.

2026-10-25 (review round 1): an unparseable command is read three ways (as written; with quotes, backslashes and the $ of $'…'/$"…" removed, so g$''it reads git; as tokenize's words, so $'\x67'it reads git), both checks run on them, and gh/git match case-blind; the parsed walk case-folds command names (GIT commit runs git on macOS). 13 rows, 7 new mutants; full mutate-changed 529 mutants, all killed after one new row.
<!-- SECTION:NOTES:END -->
