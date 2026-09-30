---
id: TASK-131
title: 'Defer the semantic layer: v1 is boolean search only'
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 23:55'
updated_date: '2026-09-30 00:01'
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
- [x] #1 A decision record states v1 is boolean-only and the semantic layer is deferred, with what would bring it back
- [x] #2 The M5 tasks (058-062, 084) are labelled deferred and out of the v1 path; TASK-068 and TASK-069 no longer depend on TASK-062 (or any M5 task), and any AC that assumes the near-miss panel is reworded
- [x] #3 Spec 00 (architecture, milestone table, M5 row), spec 06's header, spec 07 (recall@25 / membership invariant evals), the README roadmap/status, CLAUDE.md and any skill or agent that presents the semantic layer as planned for v1 say it is deferred
- [x] #4 make lint and make tooling pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
decision-017 (accepted): v1 is Boolean search only; spec 06 / M5 deferred to phase 2, with what would bring it back.
Backlog: TASK-058..062 and TASK-084 labelled deferred with a note citing decision-017; TASK-084 put in m-5 (it had no milestone); m-5 renamed "M5 Semantic layer (deferred, phase 2)" via `backlog milestone rename` (its description still reads "Exit: panel live..." because the CLI cannot edit milestone bodies). TASK-068 no longer depends on TASK-062 (description reworded from "after M5"); TASK-069 depended on M5 only through TASK-068 and is now clear. No other open task references M5 tasks.
Docs: spec 00 (out-of-scope, architecture label, stack row, 06 row, M5 row), 06 status line, 07 §A semantic invariant and §F marked not v1 gates, 03 (sort=semantic refused in v1), 04 (/near-misses, semantic_version always null in v1), 08 (semantic/, op embed, op eval near-miss), README status, CLAUDE.md layout, embedding-engineer / near-miss-evaluator / specter2-embeddings / fastapi-conventions / api-contract / repo-conventions, roster area renamed and .claude/README.md regenerated. Field-weighted BM25 (spec 03, task-025, M2) is unaffected.
Merged code left as is: records.py semantic_version (always None), cli.py PLANNED embed + PLANNED_EVALS near-miss, tantivy_engine.py sort=semantic hint (task-059), search-state.ts comment, schema.ts/openapi semantic_version.
make lint, make tooling and make mutate-changed pass.
<!-- SECTION:NOTES:END -->
