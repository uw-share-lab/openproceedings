# The comparison proxy block on the stack: stalls, memory and refusals (2026-10-16, TASK-183)

What `deploy/smoke-test.sh --compare` and `backend/tests/deploy/compare_probe.py` measured on the Docker stack
with `deploy/compare.yml`'s defaults (`read_body 60s`, `mem_limit 1g` with no swap, `GOMEMLIMIT 800MiB`), for
decision-035's precondition and `deploy/README.md` §Comparisons.

**Setup.** Docker Desktop (engine 24.0.7, older than the 26.0.0 the runbook asks of a real host; the smoke test
warns), compose v2.23.3, on an 8-CPU Mac whose 1-minute load other sessions kept between about 20 and 160;
the VM had 7.7 GiB. Caddy 2.11.7, the image `deploy/caddy.Dockerfile` pins on `dev` since the branch was
rebased onto it; the branch's earlier runs were on 2.11.4 (below). The fixture data directory of
`backend/tests/deploy/fixture_data.py`; the comparison runs against its `small` index (300 records). Ports
bound to 127.0.0.1 only. Each upload goes over TLS to `https://localhost:<port>`. The runs below are on the tree of
`e5f07b53` (the rebased branch before `5299130e`, which changes comments and docs only).

**Method.** An upload declares `Content-Length: 16777216` and sends 16,777,215 bytes, then stops: the proxy
must hold its buffer until `read_body` cuts it. Memory is the caddy container's cgroup v2 `memory.current`
(read once every upload has sent its bytes) and `memory.peak` (since the container started, each run in a
freshly started container). That an upload never reached the API is read from the API's access log: one line
per request to `/api/v1/compare`, so the count of new lines must be exactly the comparisons the test sent.
These stalls are HTTP/1.1; HTTP/2 and HTTP/3 stalls were not run (HTTP/3 is off with comparisons on).

## The smoke test

`OP_HTTP_PORT=127.0.0.1:18080 OP_HTTPS_PORT=127.0.0.1:18443 deploy/smoke-test.sh --compare`, PASS in 158 s
(without `--compare`, PASS in 114 s, with `/meta` offering no comparisons, HTTP/3 advertised and the 64 KiB
cap unconditional in the adapted config). Step 6 of the `--compare` run:

```
/meta limits.compare.max_body_bytes: 16777216
proxy: protocols ['h1', 'h2'] | body caps [([{'not': [{'path': ['/api/v1/compare']}]}], 65536)] | /api/* buffers [65536] | /api/v1/compare [('request_body', 16777216, None), ('static_response', 411, [{'method': ['POST'], 'not': [{'header': {'Content-Length': ['*']}}]}]), ('static_response', 400, [{'expression': {'expr': "!string({http.request.header.Content-Length}).matches('^0*[0-9]{1,18}$')", 'name': 'badlength'}, 'method': ['POST']}]), ('static_response', 413, [{'expression': "int('0' + string({http.request.header.Content-Length})) > 16777216", 'method': ['POST']}]), ('reverse_proxy', 16777216, None)]
Alt-Svc h3 headers: 0
api command: serve --host 0.0.0.0 --port 8000 --trusted-proxy 172.30.80.2 --compare
caddy: read_body 60s, memory limit 1073741824 bytes, GOMEMLIMIT 800MiB
8 uploads stalled a byte short; proxy memory now 460 MiB
a 16 MiB comparison while they stall: records, papers = 282 282
stalled uploads, seconds from each request's start: {"uploads": 8, "cut_min_s": 60.01, "cut_max_s": 60.01, "statuses": ["HTTP/1.1 499 status code 499"]}
proxy memory peak 464 MiB of 1024 MiB; oom_kill 0; restarts 0
API compare requests: 1 (the 16 MiB comparison; no stalled upload reached the API)
16 MiB + 1 byte to /api/v1/compare -> 413: The file is over 16 MiB (16,777,216 bytes), the most this instance compares.
an HTTP/2 file with Content-Length: abc to /api/v1/compare -> 400
a chunked file to /api/v1/compare -> 411
an HTTP/2 file with no content-length to /api/v1/compare -> 411
64 KiB + 1 byte to /api/v1/records -> 413
```

Each stalled upload's `499` is reverse_proxy's answer for a cancelled round trip, after `request_buffers`'
read failed at `read_body` (`modules/caddyhttp/reverseproxy/reverseproxy.go` in 2.11.7), not an answer from the
API (Caddy 2.11.4 wrote an empty `200` instead, its access log saying `status: 0`); the API's access-log count
is the evidence that none reached it.

## Uploads held at once

`compare_probe.py stall 18443 <ca> "/api/v1/compare?q=fairness" 16777216 16777215 <N>`, caddy restarted
before each N (MiB):

| N | before (current, peak) | all sent after | held (current, peak) | after the cut (current, peak) | outcome |
|---|---|---|---|---|---|
| 16 | 14, 15 | 5 s | 765, 804 | 765, 804 | all cut at `read_body` (60.0 s from their start); restarts 0 |
| 24 | 16, 17 | 7 s | 883, 890 | 803, 890 | all cut at `read_body` (60.0 s); restarts 0 |
| 32 | 16, 17 | 11 s | (container gone) | 14, 15 (a new container) | `docker events`: `oom`, then `die` with exit 137; restarted (restarts 1); every connection dropped 10.7 s after it started, as the last bytes arrived |

`docker inspect` reported `OOMKilled=false` for the 32-upload run although the kernel killed Caddy: `init: true`
makes tini PID 1, and the OOM killer took its child. `docker events` is the evidence.

**On Caddy 2.11.4**, before the rebase, the 16, 24 and 32-upload runs (same block, but HTTP/3 still on;
HTTP/1.1 stalls either way): 16 uploads held 793 MiB (peak 794), 24 held 912 MiB (peak 914; 998 MiB in an earlier run on a draft of the
block with a 30 s `read_body`), and 32 were OOM-killed 0.83 s after the last byte. The smoke test's 8 uploads (HTTP/3 off)
held 412 to 472 MiB (peaks 422 to 508) over its four passing 2.11.4 runs (149 to 186 s; 87 to 128 s without
`--compare`). The 24-upload peak varies with how fast the uploads arrive and when Go collects (890 to 998 MiB
over both versions): 24 sits at the edge of the 1 GiB limit, not inside it.

## Why about 50 MiB an upload

Caddy's `bufferedBody` (`modules/caddyhttp/reverseproxy/reverseproxy.go`, the same in v2.11.4 and v2.11.7)
copies the body into a pooled `bytes.Buffer` with `io.CopyN`; `ReadFrom` keeps 512 bytes free and doubles the
buffer as it fills, so 16 MiB ends in a 32 MiB buffer, and the 16, 8, 4, ... MiB buffers it outgrew are garbage
until Go collects them. With the heap near `GOMEMLIMIT`, Go collects harder and the cost falls towards the
32 MiB live buffer (about 36 MiB an upload at 24).

## What it showed besides

- Before the 411, a chunked upload of 16 MiB + 10 bytes followed by silence reached the API and held its slot
  for 30 s (the API's `API_UPLOAD_TIMEOUT` line, `compare_ms` 30009): past `request_buffers` Caddy streams the
  rest of a body, and after a read error it opens the upstream request anyway. With the 411, an unsized `POST`
  never gets that far; a Chromium `fetch` of a `Blob` sent `Content-Length` over HTTP/2 and was compared (200).
- A declared length over the cap was refused by the API from the header (`API_BODY_TOO_LARGE`, before any
  slot), not by Caddy: `request_body max_size` only counts what it reads. In the fifth `--compare` run of the
  smoke test (the four before got 413; `smoke-*--compare.log`) that refusal reached the client as a 502
  (Caddy's error log: `write: connection reset by peer`, the API having closed while the proxy still sent the
  file), so the comparison path now answers 413 itself from the declared length, before reading any of it.
- Over HTTP/2 Go passes a malformed `Content-Length` on to Caddy (HTTP/1.1 refuses it with 400 itself), and the
  413 matcher's `int()` then failed into a 500 (found by the review on a throwaway caddy with h2c), so a
  length that isn't 1 to 18 digits now gets 400 first.
- A cut upload got an empty `200` from Caddy 2.11.4 (its access log: `status: 0`, `size: 0`) and gets `499`
  from 2.11.7; the web app reads an empty 2xx, or a 4xx without the API's error envelope, as no answer
  (`frontend/src/api/outcome.ts`).
