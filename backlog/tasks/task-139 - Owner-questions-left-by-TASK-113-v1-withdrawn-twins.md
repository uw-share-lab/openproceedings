---
id: TASK-139
title: Owner questions left by TASK-113 (v1 withdrawn twins)
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 02:40'
updated_date: '2026-09-30 03:28'
labels:
  - decision
milestone: m-4
dependencies: []
ordinal: 122000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-113 implemented the owner's rule (an accepted Blind note with a withdrawn twin becomes unknown) and left three questions for the owner: (1) should a Blind note with no decision plus a withdrawn twin become withdrawn (would clear ICLR 2018 main's 12 unknowns)? (2) 10 ICLR 2018 rejected Blind notes have withdrawn twins and stay rejected: correct? (3) should desk-rejected twins count too (none in the 2026-09-29 cache)? Also confirm the implementer's limits recorded in decisions 019/020 (withdrawn-only, same track, and the author-split guards).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The owner's answers are recorded in decision-020 (and 019 for the author guards)
- [x] #2 Any rule change is implemented with tests and a real-data check; the coverage gate still passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner's answers (2026-09-29) recorded in decision-020 (new 'owner's answers' list; limits now 'confirmed by the owner on 2026-09-29') and decision-019 (author guards confirmed).

Implemented answer (1) in openreview_v1.withdrawn_twins, which now returns Twins(conflicts, withdrawn): a record whose status is unknown with evidence exactly NO_DECISION_NOTE ('no decision note in the forum', decision-note years ICLR 2018-2021 only) and a withdrawn same-track same-pdf twin becomes withdrawn. Its status claim cites the first twin's listing page and reads 'no decision note in the forum; withdrawn twin <id> shares the pdf (invitation=...)', naming every twin in id order. Choice: no conflicts.csv row (the accepted case has one because its signals disagree; here the twin's withdrawal is the only signal). Records the rule touched (conflicted or withdrawn) are exempt from rule 5's collapse, so the rule never changes which records exist (pinned with an identical-content twin). Twins are the records withdrawn by their listing before the rule runs: order-free, and a second run is a no-op. Answers (2) and (3) were already the behaviour; now pinned by table rows. A DEBUG openreview_v1_withdrawn_twin line per converted record.

Tests (test_openreview_v1.py): crawl-level table by decision (accepted/oral -> unknown+row, no decision -> withdrawn, no decision + other pdf -> unknown, reject -> rejected, workshop invite -> unchanged); record-level table (undecided, rejected, desk-rejected twin for undecided and accepted, accepted, other track, unknown for conflict/unmapped/dry-run, both withdrawn); evidence/url/log test; order/idempotence with accepted+undecided+withdrawn; every twin named; no collapse; a content.venue year (NeurIPS 2021) note without a venue stays unknown beside a withdrawn twin (non-overlap with TASK-132's silent-notes rule).

Real data (scratch OP_DATA_DIR scratchpad/task139, cache symlinked, snapshot 2026-09-29-5f920d29c5b2, index 94658c86c9e1): ICLR 2018 main before accepted 336 / rejected 496 / unknown 13 / withdrawn 83; after 336 / 496 / 1 (S1p31z-Ab) / 95. Exactly 12 ICLR 2018 records changed (status only), record count 1,018 unchanged, conflicts.csv row count unchanged (7,818 lines). No other v1 year has a blind/withdrawn pdf pair. op eval coverage --check: PASS (43 of 44 within 1%, ICLR 2013 accepted exception).

Docs: spec 01 (v1 as-built), openreview-api skill, module docstring rule 4. coverage-sources.md unaffected (accepted counts unchanged).

Checks: full backend suite 5534 passed, 1 failed (test_clauses Hypothesis FailedHealthCheck while a snapshot build ran alongside; rerun alone: 143 passed); test_openreview_v1.py 95 passed after the last test additions; make lint and make tooling pass.

Review round 1 (Close TASK-139 review findings): decision-020 now separates the owner's answer 1 (withdrawn, evidence naming the twin(s) and the listing page) from the implementer's details (first twin's page, no conflicts row, never collapsed, only the found absence of a decision note, withdrawn_by_twin), marked pending owner confirmation; replay wording corrected (saved searches reproduce on their pinned index_version; drifted only once it is gone; any status:withdrawn/unknown search that can include these records). The crawl report moves each note made withdrawn out of unmapped into withdrawn_by_twin (manifest key only when non-zero; ICLR 2018: unmapped {} and withdrawn_by_twin 12), documented in spec 01, decision-020, openreview-api and snapshots skills.

Open owner question (not implemented): should an anonymous blind copy of a withdrawn paper fold into its named withdrawn twin (one record instead of two withdrawn records of the same pdf)? Today both stay, and the twin rule never changes which records exist.
<!-- SECTION:NOTES:END -->
