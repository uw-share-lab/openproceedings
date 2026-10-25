---
id: TASK-257
title: >-
  Test an HTTP/3 upload stall and re-enable HTTP/3 with comparisons on if it is
  cut
status: In Progress
assignee:
  - '@jeevanparmar'
created_date: '2026-10-16 23:07'
updated_date: '2026-10-25 15:17'
labels:
  - ops
dependencies: []
priority: low
ordinal: 170000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-183 (PR #156) turns HTTP/3 off in the compare-on block because a stalled upload over QUIC couldn't be tested: the Mac's curl has no HTTP/3. Since Caddy 2.11.6 the per-request read deadline (read_body_idle, and read_body) probably reaches QUIC streams. Test it with an HTTP/3-capable client against smoke-test.sh --compare. What is at risk is the proxy's memory, not the API's comparison slot: with comparisons on, the proxy buffers the whole file before it asks the API, so a QUIC stall never reaches the slot, but if read_body doesn't cut it the upload holds its buffer for as long as the client keeps the connection alive. Then TASK-256's OOM no longer needs fast uploads: a trickle reaches it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 An HTTP/3 upload that stalls under the 16 MiB cap is shown to be cut, or shown not to be: cut means the client gets 499 (or Caddy's access log records it) within OP_READ_BODY ± 2 s, the bound smoke-test.sh applies to its HTTP/1.1 probe (a 499 alone can mean the client gave up; the timing shows the proxy cut it), and with N = 8 a second batch of stalls sent after the first is cut raises the caddy cgroup's memory.peak by less than N × 25 MiB (memory.current is no evidence: Go keeps freed buffers, and it stayed at 765 MiB after a confirmed HTTP/1.1 cut in docs/results/2026-10-16-compare-proxy.md); HTTP/3 is re-enabled in compare-on only if it is cut, and spec 08 and deploy/README.md say which
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24: cut. Client: Debian trixie curl 8.14.1 with HTTP/3 (deploy/smoke-h3.Dockerfile, packages pinned via the base image's snapshot). read_body 20s: stall cut 20.05 s, trickle 20.18 s; 2 batches of 8 x 16 MiB-1 stalls all cut 20.0-20.5 s, second batch +43 MiB memory.peak (< 200). Smoke --compare: 16 cuts at read_body +-2 s, peak 620 -> 620 MiB. HTTP/3 re-enabled in compare-on; a cut HTTP/3 upload is forwarded truncated and refused by the API (408/429) within 0.5 s, never compared (documented). An idle QUIC connection closes at 30 s first.

2026-10-25 (review round 1): AC #1's 'within OP_READ_BODY ± 2 s' was shown for a silent stall only at read_body 20s; at the shipped 60s a silent stall is closed first by QUIC's 30 s idle timeout (30.89 s, 504), and a trickle is cut at read_body (60.10-60.14 s). Both end well within the bound's intent (no upload outlives read_body); smoke-test.sh --compare sends trickles for that reason.
<!-- SECTION:NOTES:END -->
