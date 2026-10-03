---
id: decision-032
title: >-
  A takedown follows twin links: listing either decision-029 twin withholds both
  abstracts, and both ids are listed and logged (TASK-163)
date: '2026-10-03 02:05'
status: accepted
---

## Context

Under [decision-022](decision-022%20-%20A-takedown-withholds-an-abstracts-display-not-its-matching-on-every-loaded-index-version-the-takedown-list-and-log-live-in-the-data-directory-TASK-136.md), a takedown withholds an abstract's display on every loaded index version. Matching stays as it was. `takedowns.same_paper` already follows a listed id to the other ids of the same paper: merges and rekeys (TASK-067).

[decision-029](decision-029%20-%20Link-ICLR-2017-workshop-copies-to-their-conference-twins-as-two-records-with-twin-claims-never-merged-the-RIS-importer-reads-scholarmend-0.1.5s-invitation-by-the-crawlers-twin-rule-TASK-159-TASK-157.md) keeps an ICLR 2017 workshop-listing copy and its conference submission as two records of one paper. They are linked by `twin` claims and never merged. On the 2026-09-29 crawl that is 104 records. So a takedown of one copy left the other copy's abstract on display.

TASK-163 put three options to the owner:
1. No: withhold the listed id and its merges only.
2. Yes: follow the twin claim.
3. No, but `op takedown check` reports a twin that still shows its abstract.

## Decision

The owner chose option 2 on 2026-10-02. A takedown follows twin links. Listing either twin withholds the abstract on both, at serve time and in a snapshot build. Both ids are listed and logged in the operator's takedown log. This applies to every twin a `twin` claim names, not only the 18 pairs that `_bibtex` links.

## Consequences

**Code:**
- `takedowns.same_paper` takes `(record, twin)` pairs and links them both ways and transitively, together with merges and native ids.
- The API (`Served.withheld_in`) reads the pairs from the served snapshot's claims and from the version's own. So a pinned older snapshot built before the claims existed is covered too.
- `op export` reads them from the exported snapshot and from the current index's snapshot. If the current index's snapshot can't be read, it logs one ERROR `takedown_twins_unavailable` and prints a warning.
- `op snapshot build` withholds twins and reports them as `takedowns_twins`, saying what to list and log.
- `op takedown check` reports a listed paper's twin that the list lacks. Since the log check requires a `withheld` entry for every listed id, this also forces both ids into the log.

**Docs:** spec 08 §Deploy and the op rows, spec 01 (twins), spec 04, and the snapshots and logging-standards skills.

**Tests:** `backend/tests/contract/test_twins.py`, `backend/tests/unit/test_takedowns.py` and `backend/tests/unit/ingest/test_snapshot_takedowns.py`.

**Reproducibility:** what matches is unchanged, as under decision-022. A snapshot built with a list naming a twin withholds both abstracts. That gives it a new `snapshot_hash`, the same as for any takedown.

**Revisit** if decision-029's twins are ever merged into one record. A merge already links the two ids, so this rule would then be redundant.
