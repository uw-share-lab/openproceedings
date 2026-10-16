---
id: TASK-256
title: 'Decide: a per-client connection or upload cap in front of the proxy'
status: To Do
assignee: []
created_date: '2026-10-16 23:07'
updated_date: '2026-10-16 23:07'
labels:
  - ops
  - security
  - decision
dependencies:
  - TASK-064
priority: low
ordinal: 169000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-183 (PR #156): as built, Caddy limits neither connections nor uploads per client. With comparisons on (deploy/compare.yml, caddy mem_limit 1g), about 30 concurrent maximum-size uploads (about 50 MiB each in Caddy) OOM-kill the proxy, which restarts and drops every connection for a few seconds (measured: 24 uploads peak 890 MiB, 32 OOM-killed). A per-client cap belongs in front of or in the proxy, and where depends on the host (TASK-064): a front proxy, a rate-limit module in a custom Caddy build, or the host's firewall. Spec 08 §Deploy and the README mark it open.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The owner decides where the cap lives once the host is chosen (TASK-064), and the decision is recorded
- [ ] #2 If built: concurrent uploads from one client are capped below the OOM point, measured with smoke-test.sh --compare, and spec 08 and deploy/README.md describe it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Options from TASK-183's author (2026-10-16): (a) a custom Caddy build (xcaddy) with a rate-limit or concurrency plugin, returning 429/503 on /api/v1/compare at the limit, so upload memory is capped at limit × about 50 MiB; keeps decision-035, but the image is no longer a stock digest-pinned build Dependabot can bump alone. (b) drop request_buffers and stream bodies to the API: about zero proxy memory per upload, but a slow upload holds the one comparison slot for up to compare_upload_seconds (30 s), reversing decision-035's reason for the block (the per-network cooldown still caps one network at about 7.7% of slot time). (c) a connection limit in front of Caddy (e.g. nftables connlimit per source on 443): host config, waits on TASK-064. The author recommends (a) if the owner wants a bound before hosting; (c) is the natural fit once a host is chosen. Memory is already bounded by mem_limit 1g + memswap_limit (deploy/compare.yml); what is unbounded is availability: past about 30 max-size uploads Caddy is OOM-killed and restarts.
<!-- SECTION:NOTES:END -->
