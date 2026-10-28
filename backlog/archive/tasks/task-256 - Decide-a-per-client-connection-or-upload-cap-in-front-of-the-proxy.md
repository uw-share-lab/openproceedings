---
id: TASK-256
title: 'Decide: a per-client connection or upload cap in front of the proxy'
status: To Do
assignee: []
created_date: '2026-10-16 23:07'
updated_date: '2026-10-28 03:59'
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
Found by TASK-183 (PR #156): as built, Caddy limits neither connections nor uploads per client. With comparisons on (deploy/compare.yml, caddy mem_limit 1g), about 30 concurrent maximum-size uploads (about 50 MiB each in Caddy) OOM-kill the proxy, which restarts and drops every connection for a few seconds (measured: 24 uploads peaked at 890 to 998 MiB, 32 OOM-killed). A per-client cap belongs in front of or in the proxy, and where depends on the host (TASK-064): a front proxy, a rate-limit module in a custom Caddy build, or the host's firewall. Spec 08 §Deploy and the README mark it open.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The owner decides where the cap lives once the host is chosen (TASK-064), and the decision is recorded
- [ ] #2 If built: concurrent uploads from one client are capped below the OOM point, measured with smoke-test.sh --compare, and spec 08 and deploy/README.md describe it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Options from TASK-183's author (2026-10-16): (a) a custom Caddy build (xcaddy) with a rate-limit or concurrency plugin, returning 429/503 on /api/v1/compare at the limit, so upload memory is capped at limit × about 50 MiB; keeps decision-035, but the image is no longer a stock digest-pinned build Dependabot can bump alone. (b) drop request_buffers and stream bodies to the API: about zero proxy memory per upload, but a slow upload holds the one comparison slot for up to compare_upload_seconds (30 s), reversing decision-035's reason for the block (the per-network cooldown still caps one network at about 7.7% of slot time). (c) a connection limit in front of Caddy (e.g. nftables connlimit per source on 443): host config, waits on TASK-064. The author recommends (a) if the owner wants a bound before hosting; (c) is the natural fit once a host is chosen. Memory is already bounded by mem_limit 1g + memswap_limit (deploy/compare.yml); what is unbounded is availability: past about 30 max-size uploads Caddy is OOM-killed and restarts.

Owner decision 2026-10-17 (about 03:21 EDT): option (c). The per-client cap will be a per-source connection limit in front of Caddy at the host (for example nftables connlimit on 443), set once TASK-064 chooses a host. No custom Caddy build now (option (a) declined), and request buffering stays (option (b) declined, decision-035). Recorded in spec 08 §Deploy and deploy/README.md §Comparisons. AC #2 waits on the host: build it there and measure with smoke-test.sh --compare.

2026-10-24 (TASK-257): HTTP/3 is now on with comparisons on, so the per-source limit at the host must cover UDP 443 (QUIC) as well as TCP 443.

2026-10-28: folded into TASK-067 (its build-and-measure criterion is now TASK-067's last AC) and archived, at the owner's direction.
<!-- SECTION:NOTES:END -->
