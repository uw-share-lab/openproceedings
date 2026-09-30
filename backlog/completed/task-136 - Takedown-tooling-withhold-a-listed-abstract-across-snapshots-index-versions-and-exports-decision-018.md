---
id: TASK-136
title: >-
  Takedown tooling: withhold a listed abstract across snapshots, index versions
  and exports (decision-018)
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 02:11'
updated_date: '2026-09-30 19:43'
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
- [x] #1 The takedown list's file, format and location are specified, and whether snapshot_hash and the manifest cover it is decided and documented
- [x] #2 op snapshot build nulls every listed abstract, and a recrawl followed by a rebuild cannot restore one
- [x] #3 The withheld count appears in the snapshot manifest, on /coverage and in op snapshot diff
- [x] #4 Every index version the API loads withholds listed abstracts in hits, excerpts and highlights, /papers/{id} and its provenance, and every export format
- [x] #5 A withheld abstract carries a marker distinct from a missing one, in the API and the UI (guarantee 6)
- [x] #6 The oracle leak (pinned versions still match on withheld text) is decided: accepted with a written reason, or the field dropped from matching
- [x] #7 Search-record replay and the record page behave per guarantee 4 with listed abstracts, with tests
- [x] #8 A check fails when any listed abstract is served by any loaded index version
- [x] #9 Public deploys cannot build the web image without NEXT_PUBLIC_TAKEDOWN_CONTACT (a build ARG and a required-var gate)
- [x] #10 Where the operator's takedown log lives and who can access it is documented, and it stays out of git
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Design (spec 08 §Deploy takedown procedure; decision-018/021; owner decisions 2026-09-30 recorded as decision-022):
- List (AC1): <data-dir>/takedowns/withheld.txt, UTF-8, one record id per line, '#' comments and blank lines ignored; a malformed line fails closed (build refused; API load refused, old bundle kept); missing = empty unless named, already applied, or the loaded snapshot withheld abstracts (then takedowns_missing). openproceedings/takedowns.py is the one reader. snapshot_hash covers its effect; the manifest names the withheld ids and counts (keys only when something was withheld; withheld in AUDITED). The list file itself is not hashed: it is live serve-time state.
- Build (AC2): op snapshot build --takedowns withholds each listed abstract (abstract, abstract claims, conflicts.csv texts) after dedup/reconcile; a listed id merged or rekeyed is followed to its successor, withheld too (takedowns_followed); a listed id with no record is reported (takedowns_unmatched), never refused (refusing would push operators to drop the line and re-expose older versions).
- Counts (AC3): manifest abstract_withheld (+ by track, + ids); abstract_missing excludes withheld; /coverage abstract_withheld (serve-time); op snapshot diff abstract_withheld {added, lifted}; op eval coverage notes it.
- Serve (AC4/5): the bundle carries the list, re-read on every load/SIGHUP. /search, /papers (+provenance, spans), every export (served, index_version, record_id; op export) withhold; markers: abstract_withheld (API), RIS N1/BibTeX sentence, CSV/JSONL abstract_withheld_reason, X-Abstracts-Withheld header; UI RH-15, PA-8, CV-6, EX-E9.
- AC6: accepted (owner). AC7: replay reproduced on the pinned index; record exports withhold.
- AC8: op takedown check --api (HTTP; versions outermost, one export per version/format/cell).
- AC9: deploy/web.Dockerfile + web-build-gate.sh (OPENPROCEEDINGS_INSTANCE required; public needs a contact) + next.config.ts gate.
- AC10: log <data-dir>/takedowns/log.jsonl, operator-owned 0600; .gitignore, protect-data-dir.sh, .dockerignore; op takedown check checks owner, mode, latest entry.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built in 8a97b40..HEAD. AC1: list <data-dir>/takedowns/withheld.txt (ids, # comments; malformed refuses; missing = empty unless named/applied/snapshot-withheld). AC2: op snapshot build withholds after dedup/reconcile (abstract, abstract claims, conflicts.csv texts); follows merged/rekeyed listed ids (takedowns_followed) and reports unmatched ones (takedowns_unmatched), never refusing; only records it took something from are named (listing an abstract-less record changes nothing); takedown_differs for same records / other withheld ids; recrawl test. AC3: manifest abstract_withheld(+by_track, ids), /coverage abstract_withheld (serve-time), op snapshot diff abstract_withheld{added,lifted}, op eval coverage note. AC4: served bundle carries the list, re-read on every load/SIGHUP (even an unchanged index; a failed promotion still applies it; a missing list once applied fails the reload); /search, /papers (+provenance, spans), every export format on served/index_version/record_id, op export. AC5: abstract_withheld on Hit and PaperResponse, CSV/JSONL abstract_withheld_reason, X-Abstracts-Withheld; UI RH-15/PA-8/CV-6/EX-E9. AC6: decision-022 (owner: accept). AC7: contract tests: replay reproduced with identical ids on the pinned old index after the list and a rebuild; record exports withheld. AC8: op takedown check --api (HTTP; unit tests break each sub-check against a fake API; contract mutants of the real routes fail it). AC9: deploy/web.Dockerfile + web-build-gate.sh (OPENPROCEEDINGS_INSTANCE required; public needs contact) + next.config.ts gate; the image was not built locally (Docker daemon not running). AC10: log <data-dir>/takedowns/log.jsonl, operator-owned 0600, fields in decision-022/spec 08; .gitignore, protect-data-dir.sh (forced/glob/case/parent-dir adds; case rows, mutants), .dockerignore; op takedown check checks owner, mode and each id's latest entry.
Review gate: round 1 (11 reviewer roles) and round 2 findings fixed; see the PR's dispositions.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Takedown tooling (decision-018, decision-022). The list is <data-dir>/takedowns/withheld.txt: record ids with # comments. A malformed list fails closed. A missing list is refused once one is applied or once the loaded snapshot has withheld abstracts. op snapshot build withholds each listed abstract after dedup and reconcile: the abstract, its abstract claims and its conflicts.csv texts. A merged or rekeyed listed paper is followed to its new id, and an id with no record is reported, never refused. The manifest names and counts the withheld abstracts apart from missing ones, and op snapshot diff and /coverage report them. The API re-reads the list on every load and SIGHUP and withholds at serve time on every loaded index version: /search hits, /papers and its provenance and highlights, and every export (served, index_version, record_id, and op export). Marking is abstract_withheld in the API, abstract_withheld_reason in CSV and JSONL, the takedown sentence in RIS and BibTeX, the X-Abstracts-Withheld header, and the UI copy RH-15, PA-8, CV-6 and EX-E9. The oracle leak is accepted (the owner's decision): pinned versions keep matching the withheld text, so replays reproduce. op takedown check --api checks a running instance and the log. The web image has a required OPENPROCEEDINGS_INSTANCE, and a public build needs a takedown contact. The log (<data-dir>/takedowns/log.jsonl, operator-owned 0600) is kept out of git and out of the docker build context. Verified: make test (5959 passed, 2 skipped; vitest 3052 passed), make e2e 19/19, make lint, make tooling, and mutate --changed with 31 mutants and 0 problems. Three review rounds closed.
<!-- SECTION:FINAL_SUMMARY:END -->
