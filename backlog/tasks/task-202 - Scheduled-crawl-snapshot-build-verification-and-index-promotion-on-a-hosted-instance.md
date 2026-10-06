---
id: TASK-202
title: >-
  Scheduled crawl, snapshot build, verification and index promotion on a hosted
  instance
status: To Do
assignee: []
created_date: '2026-10-06 18:53'
labels:
  - ops
  - deploy
  - ingest
milestone: m-6
dependencies:
  - TASK-064
ordinal: 145000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 08's deploy runbook refreshes the index by hand: crawl, op snapshot build (takedown list applied), op index build, verify (op snapshot diff against the served snapshot, op index parity, op eval coverage --check), then promote the new index_version (switch current, SIGHUP) and retire old indexes under retention. A hosted instance needs this on a schedule. The crawlers already pace themselves politely and OpenReview's login comes from the host's .env. Saved search records pin their index, so promotion can't break reproducibility, but a bad crawl (a source changes its HTML, a login lapses) could shrink the index new searches see. Owner direction (2026-10-06): a task for scheduled jobs under hosting/deployment; whether promotion is automatic or waits for a person is still to decide (proposed: automate crawl, build and verify; auto-promote only when the diff stays within thresholds such as no drop in records per venue-year and the M4 gate passing; otherwise hold for a person and alert).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The schedule (crawl, build, verify) runs on the hosting chosen in TASK-064 (cron or a scheduler), with logs and an alert when a step fails
- [ ] #2 Whether promotion is automatic is decided and recorded; if automatic, its thresholds are tested on a shrunk-diff fixture and a failing one holds the index
- [ ] #3 Promotion and retention follow spec 08's runbook, and every promotion is recorded where the next release's Data section can cite it
<!-- AC:END -->
