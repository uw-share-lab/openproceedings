---
id: TASK-228
title: >-
  v0.3.0 release Data note: default-search sets shrank, earlier records replay
  as drifted
status: Done
assignee: []
created_date: '2026-10-10 16:33'
updated_date: '2026-10-11 11:38'
labels:
  - release
dependencies: []
ordinal: 158000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the fix/aaai-aies-tracks review gate (review-methodologist S3, 2026-10-10). The v0.3.0 docs/releases.toml entry (written on the release branch with the verified index's hashes, spec 08 §Release) must say that AAAI 1980-2008 and AIES 2018-2023 entries outside the technical program left the default search (decision-050: 1,197 track changes, 39 not-paper removals), that OpenAlex abstracts were added (decision-049), and that records saved on an earlier index replay as drifted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The v0.3.0 releases.toml notes and CHANGELOG state the changed default-search sets and the drifted replay, with the figures
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The v0.3.0 docs/releases.toml notes and the generated CHANGELOG Data section state the changed default-search sets (decision-050: 1,197 track changes, 39 not-paper removals), the new abstracts (4,536 AAAI official from archived pages, 1,117 OpenAlex), the SCHEMA_VERSION 3->4 change, and that records saved on an earlier index replay as drifted with each removed paper's cause.
<!-- SECTION:FINAL_SUMMARY:END -->
