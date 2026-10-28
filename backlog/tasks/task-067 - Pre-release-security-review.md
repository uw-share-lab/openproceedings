---
id: TASK-067
title: Pre-release security review
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-10-28 04:51'
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
- [ ] #3 On the chosen host, a per-source connection limit and byte rate in front of Caddy (deploy/connlimit.nft) cover TCP and UDP 443 (QUIC), cap one client's concurrent compare uploads below the OOM point, are measured from another machine (traffic must pass prerouting), with deploy/smoke-test.sh --compare still passing on the host, and are described in spec 08 §Deploy and deploy/README.md §Per-source limits on the host (from TASK-256; owner decisions 2026-10-17, option (c), and 2026-10-28, the byte rate)
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

2026-10-03 code-only main promotion: fresh whole-application security review of main 0b31ebc425c3b27611550c116f1e3907330ff878 to dev 07fe70f0fb6b18202f819149088cfcc54b75ef00 approved with no Must/Should/Nit findings. Fresh make tooling exited 0 and 404 focused security tests passed. The report is summarized in docs/results/2026-10-03-release-preparation.md; full local report and raw evidence are /tmp/main-promotion-security-review.md and /tmp/main-promotion-security-{tooling,tests}.log. This refreshes AC#1 evidence only: AC#2 remains unchecked until rate limits and CORS are verified on an actual deployed instance. No public instance or tag was created.

2026-10-16: AC#2 (rate limits and CORS on the deployed instance) is all that is left; it waits on hosting (TASK-064) and then a deployment. Not added as a dependency: the CLI refuses a list holding the completed TASK-065.

2026-10-28: TASK-256 folded in (owner, 2026-10-28: fewer standalone tasks). Its decision (option (c): a per-source limit at the host, set once TASK-064 picks one; no custom Caddy build, request buffering kept) stays recorded in spec 08 §Deploy and deploy/README.md §Comparisons; its remaining build-and-measure criterion is this task's new last AC.

2026-10-28 (AC #3, per-source limit): the ruleset is in place in deploy/connlimit.nft, run with deploy/connlimit.sh check|apply|show|remove.

What it does: for each IPv4 address or IPv6 /64, TCP and UDP traffic to the host's port 443 is limited to 16 connections at once, and to 1 MiB/s after a 16 MiB burst. Past either limit, packets are dropped. It covers only packets addressed to the host (fib daddr type local). The chain is in prerouting at priority -150, after conntrack and before Docker's DNAT.

Why the byte rate: the connection cap alone bounds uploads only over HTTP/1.1. Caddy 2.11.7 sets no HTTP/2 or HTTP/3 stream limit (Go's default is 250, quic-go's is 100) and has no setting for one. The byte rate bounds what one source can make the proxy buffer. By arithmetic that is about 3 x (16 + 60) MiB, some 230 MiB of the 1 GiB limit. That figure is not measured, and neither is the per-request overhead.

Checked on 2026-10-28, between Docker Desktop containers (Linux 6.5, nftables 1.1.3), with the ruleset in the server's own network namespace and without the fib line, which LinuxKit lacks. Results are in docs/results/2026-10-28-connlimit-container-check.md:
- the ruleset parses and loads, and loading it twice is idempotent;
- 16 of 20 TCP and 16 of 20 UDP flows from one IPv4 address or one /64 got through;
- one /64 shares the 16, and separate /64s don't;
- 40 MiB took 23 s.
backend/tests/deploy/test_connlimit.py pins the rules and numbers, and runs nft -c where it can.

Not measured in front of Caddy, so this AC stays unchecked. That waits on a Linux host (TASK-064). Note for that measurement: deploy/smoke-test.sh --compare on the host must still pass, but the host's own traffic never passes prerouting. The limits themselves have to be measured from another machine, as deploy/README.md §Per-source limits on the host describes. That section, not §Comparisons, documents the limits.

2026-10-28 owner decision (an addendum to TASK-256's option (c)): ship the per-source byte rate as well as the connection cap. That is 1 MiB/s to 443 after a 16 MiB burst per IPv4 address or /64, on TCP and UDP, because a connection cap doesn't bound HTTP/2 or HTTP/3 uploads. The byte rate is its own pair of rules and sets (bytes4, bytes6) and can be dropped without touching the connection cap. NAT: everyone behind one address shares both limits. About 3 concurrent 16 MiB compare uploads fit per shared address (each needs 0.27 MiB/s to beat read_body) before the meter slows them. Recorded in spec 08 §Deploy and deploy/README.md §Per-source limits on the host. AC #3 stays unchecked until a Linux host measures it (TASK-064).

2026-10-28: AC #3 reworded (team lead, who wrote it in the fold-in). The smoke test's traffic is the host's own and never passes prerouting, so the limits are measured from another machine, with deploy/smoke-test.sh --compare still passing on the host. The AC also names the byte rate and the README section the limits now live in. It stays unchecked.

Correction to the first 2026-10-28 note: §Per-source limits on the host is a subsection of deploy/README.md §Comparisons, not a separate section.
<!-- SECTION:NOTES:END -->
