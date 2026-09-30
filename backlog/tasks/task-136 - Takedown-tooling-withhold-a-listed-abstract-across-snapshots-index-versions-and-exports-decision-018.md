---
id: TASK-136
title: >-
  Takedown tooling: withhold a listed abstract across snapshots, index versions
  and exports (decision-018)
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 02:11'
updated_date: '2026-09-30 14:14'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Design (spec 08 §Deploy takedown procedure; decision-018/021; owner decisions 2026-09-30 recorded as decision-022):
- List (AC1): <data-dir>/takedowns/withheld.txt, UTF-8, one record id per line, '#' comments and blank lines ignored; a malformed line fails closed (build refused; API load refused, old bundle kept). openproceedings/takedowns.py is the one reader. snapshot_hash covers its effect (listed records lose abstract + abstract claims, so records.jsonl, snapshot_hash and index_version change); the manifest names the withheld ids and counts (written only when non-empty, compared by _holds). The list file itself is not hashed: it is live serve-time state.
- Build (AC2): op snapshot build --takedowns (default <data-dir>/takedowns/withheld.txt) nulls abstract and drops abstract claims for each listed id after dedup/reconcile; a listed id matching no record refuses the build (a rekey or merge can't silently restore it).
- Counts (AC3): manifest abstract_withheld (+ by track, + ids); abstract_missing excludes withheld; RecordFile verifies them; /coverage totals/venue-year/track gain abstract_withheld (serve-time: snapshot-withheld plus listed now); op snapshot diff gains abstract_withheld {added, lifted}.
- Serve (AC4/5): Served bundle carries the list, reloaded on every SIGHUP (even when the index is unchanged). /search hits and /papers/{id}: abstract null, abstract claims dropped, abstract highlight spans empty, abstract_source null, new abstract_withheld: bool (additive). matched/membership unchanged. Exports (served, index_version, record_id; op export): entries() withholds listed ids; marker per format: RIS N1 / BibTeX abstract_withheld takedown sentence, CSV abstract_withheld=true + appended abstract_withheld_reason, JSONL abstract_withheld + abstract_withheld_reason (additive per decision-021). UI: hit and paper page show 'withheld' copy instead of 'No abstract in the index'; coverage shows withheld counts.
- AC6: accepted (owner): pinned versions keep matching; display withheld at serve time.
- AC7: replay stays reproduced on the pinned index; record export withholds; contract tests.
- AC8: op takedown check --api URL [--list] [--data-dir]: for every version /meta lists and each listed id the index holds, requests /papers, /search and every export format and fails on any abstract text, abstract claim, abstract span or missing marker; contract test runs it through TestClient and a mutant with withholding off fails it.
- AC9: deploy/web.Dockerfile with ARG NEXT_PUBLIC_TAKEDOWN_CONTACT and required ARG OPENPROCEEDINGS_INSTANCE=public|private; next.config.ts refuses a public build without a contact.
- AC10: log at <data-dir>/takedowns/log.jsonl, 0600 operator-owned, fields as spec 08; .gitignore + protect-data-dir.sh refuse adding takedowns/ paths; op takedown check fails on a group/world-readable log.
Commits follow the ACs; TDD; make openapi; docs as built (spec 08, 04, 01, 05, skills, README).
<!-- SECTION:PLAN:END -->
