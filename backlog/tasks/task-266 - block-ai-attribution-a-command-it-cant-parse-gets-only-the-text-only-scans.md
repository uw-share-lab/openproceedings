---
id: TASK-266
title: 'block-ai-attribution: a command it can''t parse gets only the text-only scans'
status: In Progress
assignee:
  - '@jeevanparmar'
created_date: '2026-10-19 11:49'
updated_date: '2026-10-24 07:06'
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
- [ ] #1 Decide: refuse every gh/git write the gate can't parse, or widen the file-option check; record why
- [ ] #2 A case-table row in test-openproceedings-gates.sh fails on the old behaviour
- [ ] #3 make tooling and make mutate-changed: no survivors
<!-- AC:END -->
