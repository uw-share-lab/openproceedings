---
id: TASK-131
title: 'Defer the semantic layer: v1 is boolean search only'
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 23:55'
updated_date: '2026-09-29 23:55'
labels:
  - docs
  - scope
dependencies: []
ordinal: 115000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner's decision (2026-09-29): v1 only needs the boolean search; the semantic layer (M5: SPECTER2 embeddings, sort=semantic, the near-miss panel, recall@25 — spec 06, TASK-058 to 062 and 084) is deferred as a documented phase 2, not deleted. Nothing in the boolean system depends on it (spec 00 rule 5: ranking never changes membership), but usability round 2 (TASK-068) and the public launch (TASK-069) are wired to depend on the near-miss panel (TASK-062).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision record states v1 is boolean-only and the semantic layer is deferred, with what would bring it back
- [ ] #2 The M5 tasks (058-062, 084) are labelled deferred and out of the v1 path; TASK-068 and TASK-069 no longer depend on TASK-062 (or any M5 task), and any AC that assumes the near-miss panel is reworded
- [ ] #3 Spec 00 (architecture, milestone table, M5 row), spec 06's header, spec 07 (recall@25 / membership invariant evals), the README roadmap/status, CLAUDE.md and any skill or agent that presents the semantic layer as planned for v1 say it is deferred
- [ ] #4 make lint and make tooling pass
<!-- AC:END -->
