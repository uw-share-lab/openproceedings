---
id: TASK-067
title: Pre-release security review
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-10-02 19:21'
labels:
  - ops
  - security
milestone: m-6
dependencies:
  - TASK-065
ordinal: 66000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Full-tree security-reviewer pass before going public with an instance.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 No open Must/Should findings
- [ ] #2 Rate limits and CORS verified on the deployed instance
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Full-tree security-reviewer pass in five parallel scopes: API and search; ingest and crawlers; takedown tooling (TASK-136); hooks, scripts, githooks and Makefile; CI, deploy, dependencies and frontend.
2. Fix every Must and Should with tests (TDD). Defer only what needs code or a decision that doesn't exist yet.
3. Closing: make lint, make tooling, one full make test, learnings, /review-gate, PR into dev.
4. AC#2 (rate limits and CORS verified on the deployed instance) waits on TASK-065, which waits on TASK-064 (hosting).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-30 review (5 security-reviewer passes, whole tree). Musts: (1) query/normalize.py tokenizer quadratic on runs of combining marks (anonymous CPU DoS via q, or stored in an abstract) - fixed, linear; (2) an older index version served a listed paper's abstract under a pre-rekey id or a merged-away duplicate id, and op takedown check missed it - fixed (takedowns.same_paper, API + op export + check title sweep); (3) protect-data-dir.sh let forced whole-tree git adds stage data/ - fixed in this branch (it was a queued follow-up, not yet filed). Shoulds fixed: pinned-open slot queued without bound (503 API_BUSY after pinned_open_wait_seconds; op serve --pinned-indexes); a missing takedown list failed open (required off loopback, or once any snapshot withheld; build and check refuse too); the check ignored ids the log withholds that the list dropped; the OpenReview token could be echoed via a ValueError; 11 hook evasions (xargs, git -c/aliases, heads/dev, local commits on main, record-review base, forged op-reviews records, $(cat file) attribution, backlog path normalisation, APFS case folding, rm -rf above data/, unlink); Dependabot missing npm; no HSTS. Known follow-ups confirmed and left to their tasks: TASK-148 (CI builds web.Dockerfile), TASK-149 (digest pins), TASK-150 (tantivy Dependabot); api container mounts and user: TASK-065. AC#2 stays open: it needs the deployed instance (TASK-065, which waits on TASK-064).

2026-10-01 review gate, rounds 1 and 2. Round 1 measured the real corpus: NeurIPS proceedings hashes repeat across years (1,281 hashes name two to five papers each in the 2026-09-29 snapshot; ICLR hashes collided in 2026-09-23), so the native-id link now applies only to globally unique ids, OpenReview forum ids and PMLR keys (takedowns.global_native). The same assumption in snapshot._successor and diff's rekey (from TASK-136) was fixed too. Also: a damaged snapshot's merges.csv drops only that snapshot's merges, and the list still applies (ERROR takedown_merges_unavailable per snapshot). op takedown check now reports over-withholding (a merged id whose served title differs) and the damaged merges. The list is also required behind a --trusted-proxy, and op export and op snapshot build --out require it once any snapshot withheld one. Takedown ids must be printable ASCII. The per-version open lock wait is bounded too (503, access line busy: pinned_open), and load lines count takedowns_followed. Hooks: abbreviated git options; config git can read but the gates couldn't (--config-env, include.path, GIT_CONFIG_*, GIT_COMMON_DIR, set -a); repo push config on refspec-less pushes; the matching refspec ':'; glob refspecs; branch -f/checkout -B/switch -C/worktree add -B/fetch into main or dev; git-<sub> programs; brace expansion and $'..' quoting; forged review records via globs and variables; paths through ~, $PWD, $(pwd), pushd; git stash -qa; checkout-then-commit chains. A GIT_LONG_OPTS drift check runs in make tooling. TASK-065 AC#3 now says to mount a directory holding only withheld.txt, required off loopback.

2026-10-01 review gate closed: four rounds plus a capped final pass and a confirmation pass. Every Must and Should is fixed in this branch, deferred to TASK-155 (abstract/mark-run cap, needs an owner decision) or TASK-156 (pre-existing shell-semantics bypasses in the guard hooks; they are guardrails, not an access-control boundary), or cited to an already-filed follow-up (TASK-148 CI image build, TASK-149 digest pins, TASK-150 tantivy Dependabot, TASK-065 AC#3 api container mounts and user). AC#1 is met. AC#2 (rate limits and CORS verified on the deployed instance) waits on TASK-065 (deploy), which waits on TASK-064 (hosting), so the task stays In Progress.

2026-10-02 (TASK-065): the api container's mounts and user are built (deploy/compose.yml): uid 10001, the takedown directory read-only and holding only withheld.txt, indexes/ closed by modes, records/ 0700 uid 10001. For AC#2 on the deployed instance, expect:
- CORS: compose passes no --cors-origin (the web app is on the same origin behind Caddy), so a foreign Origin gets no access-control-allow-origin.
- Rate limit: keyed on X-Forwarded-For, which the API believes only from Caddy's fixed address (--trusted-proxy 172.30.80.2 by default). Caddy replaces an incoming X-Forwarded-For, so a client can't spoof it through the proxy. Check that Caddy's access log shows real client addresses on the host, IPv6 included (deploy/README.md, First start, step 4).
- New privileged surface for security-reviewer: the ops one-off (root, CHOWN, DAC_OVERRIDE, FOWNER, no network; the record store and indexes/). It was reviewed in the TASK-065 PR.
<!-- SECTION:NOTES:END -->
