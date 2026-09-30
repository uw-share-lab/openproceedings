---
id: TASK-136
title: >-
  Takedown tooling: withhold a listed abstract across snapshots, index versions
  and exports (decision-018)
status: To Do
assignee: []
created_date: '2026-09-30 02:11'
updated_date: '2026-09-30 02:19'
labels:
  - ops
milestone: m-6
dependencies: []
ordinal: 119000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-018 requires a takedown contact on every public instance; TASK-133 added it and proposed a takedown procedure (spec 08 §Deploy) that nothing implements yet. From the TASK-133 review:
(a) the takedown list's file, format and location, and whether snapshot_hash and the manifest cover it;
(b) op snapshot build nulls listed abstracts, and a recrawl can't restore them;
(c) a withheld count in the manifest, on /coverage and in the snapshot diff;
(d) serve-time withholding across every loaded index version: hits, excerpts and highlights, /papers/{id} and its provenance, and every export format;
(e) a withheld marker distinct from missing (guarantee 6);
(f) the oracle leak: pinned versions still match on the withheld text; decide whether to accept it or drop the field from matching;
(g) replay and record-page behaviour under guarantee 4;
(h) a check that no listed abstract is served;
(i) a web-image build ARG for NEXT_PUBLIC_TAKEDOWN_CONTACT, plus a required-var gate for public deploys;
(j) where the operator's takedown log lives and who can access it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The takedown list's file, format and location are specified, and whether snapshot_hash and the manifest cover it is decided and documented
- [ ] #2 op snapshot build nulls every listed abstract, and a recrawl followed by a rebuild cannot restore one
- [ ] #3 The withheld count appears in the snapshot manifest, on /coverage and in op snapshot diff
- [ ] #4 Every index version the API loads withholds listed abstracts in hits, excerpts and highlights, /papers/{id} and its provenance, and every export format
- [ ] #5 A withheld abstract carries a marker distinct from a missing one, in the API and the UI (guarantee 6)
- [ ] #6 The oracle leak (pinned versions still match on withheld text) is decided: accepted with a written reason, or the field dropped from matching
- [ ] #7 Search-record replay and the record page behave per guarantee 4 with listed abstracts, with tests
- [ ] #8 A check fails when any listed abstract is served by any loaded index version
- [ ] #9 Public deploys cannot build the web image without NEXT_PUBLIC_TAKEDOWN_CONTACT (a build ARG and a required-var gate)
- [ ] #10 Where the operator's takedown log lives and who can access it is documented, and it stays out of git
<!-- AC:END -->
