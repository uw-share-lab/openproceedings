---
id: TASK-202
title: >-
  Scheduled crawl, snapshot build, verification and index promotion on a hosted
  instance
status: To Do
assignee: []
created_date: '2026-10-06 18:53'
updated_date: '2026-10-16 15:37'
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
- [ ] #4 The schedule runs every source as built (op ingest openreview, iclr, neurips, pmlr, ojs, crossref, then openalex last), each driven by its table; dblp is a pinned XML release and aaai-library a pinned table of Internet Archive captures, so each changes by a reviewed table bump, not by the schedule; a venue's first appearance is not a per-venue-year drop; a new venue-year at an existing source needs a table row, not code
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Gate note (2026-10-06): an auto-promotion threshold of 'no drop in records per venue-year' must exempt drops the takedown list explains (op snapshot diff's abstract_withheld / removed ids on the list), or a legitimate takedown would hold promotion.

Scope note (2026-10-09, decision-049, docs/plans/2026-10-09-new-venues-design.md): AAAI, AIES, FAccT and IASEAI join the corpus. Milestone A built the ojs source (op ingest ojs, replayed last in crawl.replay_all); Crossref, the FAccT site and OpenAlex arrive in milestones B and C. AIES 2026 on OJS needs an ojs_sections.toml row, not code.

Milestone B adds `op ingest crossref` (with the FAccT site pages) and `op ingest dblp --venue AAAI` / `op ingest pmlr --venue FAccT`; a full run orders …, ojs, crossref. CROSSREF_MAILTO is optional (controller's ruling): set it in the scheduled environment to use Crossref's polite pool; without it Crossref is queried through the public pool. A malformed value stops the crawl.

Milestone C adds op ingest openalex (last in a full run; OPENALEX_API_KEY optional) and the post-dedup fill in op snapshot build; promotion needs an index at schema 4.

2026-10-16 refresh: AC#4 rewritten for the as-built sources (decision-049 milestones A to C and decision-051 are merged; the old wording named Crossref, the FAccT site and OpenAlex as later milestones). The FAccT site is fetched inside op ingest crossref. The scheduled OpenAlex fill depends on TASK-135's answer on OpenAlex's terms (the Terms of Service revised 2026-10-02 conflict with the CC0 statement decision-049 relied on). The semantic layer is shelved (decision-017 addendum), so promotion has no embedding build. Host requirements for the schedule are listed in TASK-064's 2026-10-16 note.
<!-- SECTION:NOTES:END -->
