---
id: TASK-163
title: >-
  Decide: should a takedown treat a decision-029 twin as the same paper, so the
  twin's abstract is withheld too? (decision-029 deferral)
status: Done
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-03 02:13'
labels:
  - decision
  - ops
  - dedup
  - deferred
dependencies:
  - TASK-159
references:
  - >-
    backlog/decisions/decision-022 -
    A-takedown-withholds-an-abstracts-display-not-its-matching-on-every-loaded-index-version-the-takedown-list-and-log-live-in-the-data-directory-TASK-136.md
  - >-
    backlog/decisions/decision-029 -
    Link-ICLR-2017-workshop-copies-to-their-conference-twins-as-two-records-with-twin-claims-never-merged-the-RIS-importer-reads-scholarmend-0.1.5s-invitation-by-the-crawlers-twin-rule-TASK-159-TASK-157.md
  - backend/src/openproceedings/takedowns.py
priority: low
ordinal: 133000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: decision-029 (TASK-159), Consequences, Deferred: owner decision needed. Under decision-022 a takedown withholds an abstract's display; the record and its matching stay. decision-022 already follows a listed id to other ids that are the same paper (merges and rekeys, `takedowns.same_paper`). decision-029 keeps an ICLR 2017 workshop copy and its conference twin as two records linked by a `twin` claim, never merged, so a takedown of one copy today leaves the other copy's abstract displayed. Question: should `same_paper` treat a `twin` claim as the same paper? Options: (1) no, the listed id and its merges only; (2) yes, follow the twin claim; (3) no, but `op takedown check` reports that a twin still shows its abstract.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The owner picks an option; a decision record (`backlog decision create`) states it with the options considered and cites decision-022 and decision-029
- [x] #2 The owner chose option 2 (follow the twin claim), so the behaviour is implemented in this task's PR (the owner asked for one PR, 2026-10-02): `takedowns.same_paper` follows twin pairs (API serve time on every loaded version, `op export`), `op snapshot build` withholds twins (`takedowns_twins`), `op takedown check` asks for each twin to be listed and logged, with tests, and spec 08 §Deploy describes it
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Follow twin identities at API and CLI export time and snapshot withholding; independently union served and all pinned twin links in the checker; preserve preferred metadata; verify cross-version tests and document decision-032.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner decision 2026-10-02 (via team-lead): option 2. A takedown follows twin links: listing either twin (ICLR 2017 workshop copy or conference submission, and any decision-029 twin, not only the 18 bibtex pairs) withholds the abstract on both, and both ids are listed and logged in the operator log.
Built: takedowns.same_paper(listed, merges, ids, twins=pairs) links (record, twin) pairs both ways and transitively, together with merges and native ids. RecordFile.twins/twin_pairs read the claims at load. API Served.withheld_in uses the served snapshot's pairs plus the version's own, so an older snapshot without claims is covered. op export uses the exported snapshot's pairs plus the current index's (_current_twin_pairs; if that snapshot can't be read: one ERROR takedown_twins_unavailable and a stderr warning). snapshot.withhold withholds twins of listed/followed ids (Withholding.twins, BuildResult.takedowns_twins, JSON and stderr). op takedown check reports a listed paper's twin the list lacks, so both ids get listed and logged.
Tests: tests/contract/test_twins.py (every twin withheld in /papers, /search and all four exports, plus op export, for any listed twin; pinned older version, record export and op export --index on a snapshot without claims; the unreadable-current warning; the check), tests/unit/test_takedowns.py, test_snapshot_takedowns.py. Spec 08 §Deploy and the op rows, spec 01, spec 04, and the snapshots and logging-standards skills are updated.

Final production review Should fixed: the checker now unions every served and pinned twin link independently of the preferred title/authors record. Regressions cover current metadata without links, an older version with links, and two pinned versions with distinct and repeated links. Focused pytest test_takedown_check.py and test_takedowns.py: 82 passed; focused ruff format/check and git diff --check passed. Spec 08 clarified; learning addendum records the fallback-versus-union trap. Full final gates remain required before closure.

Final integration cdb68cdb6fc12bd0ae9c23bed1788e1fd1c78511 on merged dev9152ecb: make test PASS6386backend/2optional skips and3217frontend; make lint/tooling PASS; make e2e PASS19. Fresh focused index/dedup/twins/checker/takedown tests PASS289. Logs /tmp/twins-finalization-{test,lint,tooling,e2e,focused}.log. Independent integrated all-role review APPROVE /tmp/twins-integrated-all-role-review.md. Final metadata commit and its fresh fulltest/lint/tooling remain required before publication.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Owner option2 recorded by CLI as decision-032: takedowns follow all twin links and require both ids listed/logged. Served/pinned API, CLI export, snapshot and checker paths verified by cross-version contracts and full suite; checker unions links independently of metadata fallback.
<!-- SECTION:FINAL_SUMMARY:END -->
