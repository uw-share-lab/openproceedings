---
id: decision-017
title: >-
  v1 is boolean search only; the semantic layer is deferred to phase 2
  (TASK-131)
date: '2026-09-29 23:57'
status: accepted
---
## Context

The plan had six milestones, with M5 (spec 06: SPECTER2 embeddings, `sort=semantic`, the near-miss panel,
the recall@25 evaluation; TASK-058 to 062 and TASK-084) between the full crawl (M4) and hosting and
release (M6). Usability round 2 (TASK-068) was wired to depend on the near-miss panel (TASK-062), and the
public launch (TASK-069) depends on round 2, so the release waited on the semantic layer.

The project owner decided on 2026-09-29 that v1 only needs the Boolean search, and chose to defer the
semantic layer rather than delete it. The owner's decision is those two points. The three reasons below are
the rationale recorded by TASK-131, not the owner's words:
- **Nothing in the Boolean system depends on it.** Spec 00 guarantee 5 (ranking never changes membership)
  means embeddings can only re-order the matched set or suggest papers in a separate panel. `total`,
  `excluded`, exports, search records and `ids_hash` come from the lexical set alone (spec 06 §Purpose,
  spec 04 §Search records), so the search a review cites is complete without 06.
- **The Boolean system is complete.** Query language (M1), index and CLI (M2), API and UI (M3) are merged;
  the full crawl and its coverage gate (M4, TASK-054) are in progress. Field-weighted BM25, the default
  `sort=relevance`, is part of that system (spec 03 §Ranking, built in task-025, M2) and does not need 06.
- **Cost.** The layer adds a model dependency (SPECTER2 base plus the proximity adapter, pinned by
  revision), an offline embedding build per `index_version`, about 120 MB of vectors in RAM per served
  index, a second version (`semantic_version`) in the audit trail, its own endpoint and UI panel, and an
  evaluation (recall@25 against a BM25-OR baseline) that must pass before it ships. That is a milestone of
  work that does not change what a review can find or cite.

Options considered:
- (a) Build M5 before release, as planned. Delays the public instance for a feature spec 06 itself says
  must not ship unless it beats a baseline.
- (b) Drop the semantic layer and delete spec 06. Loses a worked-out design, and the near-miss idea (find
  vocabulary the query lacks) is still the strongest reason to add embeddings later.
- (c) Defer it as a documented phase 2: keep spec 06, the M5 milestone and its tasks, labelled deferred and
  off the v1 path.

## Decision

We release v1 as Boolean search only. The semantic layer (spec 06, milestone M5, TASK-058 to 062 and
TASK-084) is deferred to phase 2: kept, documented and labelled `deferred`, but not built, and nothing on
the path to the v1 release (M6) depends on it.

## Consequences

- **Out of v1:** `sort=semantic`; `GET /near-misses` and the near-miss panel; `op embed build`; `op eval
  near-miss`; `semantic_version` being set on search records (TASK-084). The semantic invariant gate
  (spec 07 §A) and the recall@25 report (spec 07 §F) are not v1 release gates; they become gates when the
  layer is built. The v1 ranking checks stay: the differential compares `total` for every v1 sort
  (`relevance`, `year_desc`, `year_asc`, `title`), and the determinism gate (spec 07 §A) holds.
- **Unchanged:** field-weighted BM25 and every other v1 sort (spec 03 §Ranking); all six guarantees; the
  API contract. `semantic_version` stays in the search-record schema as a nullable field that is always
  `null` in v1 (spec 04 §Search records), so no contract change and no record migration are needed, and
  `ids_hash`, `index_version` and replay are unaffected.
- **Backlog:** TASK-058 to 062 and TASK-084 get the `deferred` label and stay in milestone m-5, renamed
  "M5 Semantic layer (deferred, phase 2)". TASK-068 (usability round 2) no longer depends on TASK-062, so
  TASK-069 (public launch) no longer waits on M5.
- **Docs:** spec 00 (architecture, stack, milestones), spec 06's status line, spec 07 §A and §F, spec 03,
  04 and 08 where they list semantic surface, README's status, and the `embedding-engineer`,
  `near-miss-evaluator` and `specter2-embeddings` roster entries say deferred and link this record.
- **Already merged, left as is:** a `semantic_version: null` field on search records, and `op embed` and
  `op eval near-miss` as stub commands (`cli.py` `PLANNED`, `PLANNED_EVALS`); TASK-131 changed their
  messages to "deferred to phase 2 (decision-017)" (`DEFERRED_TASKS`). `sort=semantic` is refused before
  any semantic code could run: over HTTP, the API's closed `Sort` Literal (`api/models.py`) rejects it with
  422 `API_BAD_PARAM` and pydantic's message; `op search --sort semantic` is an argparse usage error (exit
  2). Only a direct engine call reaches `check_page` in `engine/tantivy_engine.py`, whose hint now says
  "semantic sort is deferred to phase 2 (decision-017)". None of this costs anything to keep.

**What would bring it back** (confirmed by the project owner, 2026-09-29): a v1 release (M6) is out, and either reviewers in usability testing report
missing vocabulary as a real problem that the Boolean tools (wildcards, the concept-group builder, syntax
help) don't solve, or a review team asks for query-revision suggestions. Resuming means a new decision that
supersedes this one, re-checking spec 06 against the as-built API, and starting at TASK-058. The recall@25
rule still applies: the near-miss panel ships only if it beats the BM25-OR baseline.
