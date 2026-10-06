---
id: TASK-195
title: 'Comparison: a citable, copyable summary and a place in the search record'
status: Done
assignee: []
created_date: '2026-10-05 08:56'
updated_date: '2026-10-06 00:21'
labels:
  - frontend
  - api
  - ux
milestone: m-3
dependencies: []
ordinal: 139000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A comparison's counts (kept, dropped, not in the index, added) live only on screen and in the downloaded CSVs; nothing nudges Save search record and no record stores that a comparison was made. The gate's usability and methodology reviews (2026-10-05) asked what a methods section may cite: the group counts and comparisons are search-development aids, never flow-diagram numbers, and a comparison figure needs the reviewer's own file hash and date beside the index_version and canonical_hash.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The panel offers a copyable sentence stating the counts, index_version, canonical_hash, the file's sha256 and the date, worded per prisma-reporting; whether a search record should note a comparison is decided and recorded
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Per decision-043: no search-record change. The panel shows the citable sentence (visible, selectable) with a Copy button.
2. sha256 computed in the browser (SubtleCrypto) from the File the reviewer chose, the bytes POSTed: no contract change and decision-035's echo rule untouched. Without SubtleCrypto (not a secure context) the sentence says the hash wasn't computed and how to compute it.
3. Wording per prisma-reporting: search-development aid, not a PRISMA flow count; full index_version, canonical_hash, file sha256, UTC date.
4. Tests in compare.test.ts and compare-records.test.tsx; spec 04/05 and design copy updated.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decided and recorded: decision-043 (owner, 2026-10-05) - a search record never notes a comparison; no record change here. sha256: computed in the browser (Web Crypto, lib/compare.ts fileSha256) from the File POSTed, so no contract change and decision-035's echo list is unchanged; without Web Crypto (not a secure context) the sentence says so. Panel: the sentence is shown as text (selectable) in a labelled figure with the Copy button (native button; 'Copied' in a polite status; CopyButton now announces 'Couldn't copy: select the text and copy it' where the clipboard can't be written instead of doing nothing). Also clamped the 'Next comparison in N s' countdown to the server's wait (the clock could be a tick stale, showing N+1). Docs: spec 04 (methods-section bullet), spec 05 Components 9, design CM-21/USAB-S7/open question, design search-workspace keyboard row, prisma-reporting skill. Tests: npm test --workspace frontend 46 files / 4846 passed; backend selection -k 'compare or meta or serve' 544 passed, 1 skipped; make tooling exit 0.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The compare panel shows the comparison as one citable sentence with a Copy button: search-development check (not a PRISMA count), UTC date, file name and sha256 (computed in the browser from the bytes sent), records read and papers compared, the canonical query and canonical_hash, the full index_version, and the four counts. Per decision-043 the search record is unchanged. Verified by compare.test.ts (exact wording, sha256 of a known vector, no-Web-Crypto fallback) and compare-records.test.tsx (sentence shown with the digest of the file sent, request carries only file and q/mode, keyboard-focusable Copy announces Copied, clipboard-less announcement).
<!-- SECTION:FINAL_SUMMARY:END -->
