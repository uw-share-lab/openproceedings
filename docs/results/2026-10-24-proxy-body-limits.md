# The proxy's body limits on the other API routes, the 413 race, and HTTP/3 stalls (2026-10-24)

What was measured on the Docker stack for TASK-255 (unsized bodies that stall on the non-compare API routes),
TASK-259 (the API's early 413 reaching the client as Caddy's 502), TASK-257 (does `read_body` cut a stalled
HTTP/3 upload) and TASK-268 (a non-`POST` to `/api/v1/compare` skipping the length checks), before and after
the `deploy/Caddyfile` changes that close them. `deploy/README.md` §Comparisons and spec 08 §Deploy state the
outcome; this note keeps the numbers.

**Setup.** Docker Desktop (engine 24.0.7) on an 8-CPU Mac shared with other sessions: the host's 1-minute load
was 4 to 5 at the start and 230 to 240 later (other sessions' suites and file syncs), as noted per run. Caddy
2.11.7 (`deploy/caddy.Dockerfile`, built with Go 1.26.8). A stack of `deploy/compose.yml` +
`deploy/compare.yml` (`read_body 60s`) over `backend/tests/deploy/fixture_data.py`'s data, as its own Compose
project on its own ports and internal network (172.30.82.0/24), beside a running private deployment that was
left alone. Configurations were swapped with `caddy reload` inside the running caddy container. "API
connections" are the api container's established TCP connections on port 8000 (`/proc/net/tcp`), sampled
while the uploads were held. Chunked HTTP/1.1 stalls are `backend/tests/deploy/compare_probe.py stall <port>
<ca> <path> chunked <bytes> <n> [<method>]`; unsized HTTP/2 bodies are `curl --http2 -X POST -T -` reading a
pipe that stops after the bytes and stays open.

## TASK-255: an unsized body that reaches the 64 KiB cap and stalls

Before (`request_buffers 64KiB` on `/api/*`), with `read_body 60s`:

| Request (then silence) | API connections while held | Ended |
|---|---|---|
| 4 × chunked `POST /api/v1/records`, 65,536 bytes | 4, the whole 60 s | 60.02 s (499, 504) |
| 4 × chunked `POST /api/v1/records`, 65,535 bytes (control) | 0 | 60.02 s (499) |
| 4 × chunked `GET /api/v1/search`, 65,536 bytes | 4, the whole 60 s (the API logged 200 after 60,028 ms) | 60.02 s (499, 504) |
| 2 × chunked `POST /api/v1/records`, 200,000 bytes | 2 | 60.03 to 60.05 s (413, 499) |
| unsized HTTP/2 `POST /api/v1/records`, 65,536 bytes | 1 | |

So it was every method, not only `POST`: the API's `BodyLimit` reads any request's body before routing, a
`GET`'s included. A body that reaches `request_buffers` exactly is streamed on (Caddy's `bufferedBody`
returns the buffer plus the rest of the client's body when `io.CopyN` reads its whole limit).

`request_buffers` one byte over the cap (65,537) alone fixed the at-cap stall: 4 chunked stalls of 65,536 bytes
to `POST /api/v1/records`, `GET /api/v1/search` and `PUT /api/v1/compare` each held 0 API connections and were
cut at read_body (60.01 to 60.08 s, 499). It did not fix a chunked body that went past the cap and then
stalled: 4 of 70,000 bytes held 4 API connections for 60 s. Caddy's debug log for one of 200,000 bytes: the
`upstream roundtrip` took 59.98 s, then `http: request body too large` (`requestbody.errorWrapper.Read`). The
cap's error comes back from `io.CopyN` at once, but `bufferedBody` opens the upstream request anyway; the
transport writes the 65,536 buffered bytes, fails on the next read and closes the request body, and Go's
HTTP/1.1 server reads up to 256 KiB of a body being closed so it can reuse the connection, which blocks on the
silent client until read_body (Go 1.26 `net/http` `transfer.go` `writeBody` and `body.Close`; read from the
source, consistent with the timing). Over HTTP/2 a server-side body closes without reading on, and an unsized
HTTP/2 body of 200,000 bytes held 0 API connections (at 15 s) and got 413.

As built: `request_buffers 65537`, plus a 411 for any `/api/*` request sent chunked (Caddy's `header
Transfer-Encoding *` matcher sees the chunked coding Go removes from the header map). Chunked stalls of 65,536
and 200,000 bytes to `POST /api/v1/records`, `PUT /api/v1/compare` and `GET /api/v1/search` then got 411 and
never reached the API; an unsized HTTP/2 body that stops at 65,536 bytes held 0 API connections at 15 s (1
before). Neither the web app nor `op` sends a chunked API request: the app's bodies are JSON strings or the
file's `Blob`, both sent with a length, and `op takedown check` only reads.

## TASK-259: 64 KiB + 1 byte to `/api/v1/records` under load

Step 6's request (`curl --data-binary` of 65,537 bytes, declared), 150 times per protocol, with 8 busy-loop
containers in the Docker VM (about 128% CPU each) and a host 1-minute load of 14 to 35:

| Config | HTTP/1.1 | HTTP/2 |
|---|---|---|
| before | 133 × 413 empty (Caddy's), 12 × 413 the API's JSON, **5 × 502** | 141 × 413 empty, 5 × 413 JSON, **4 × 502** |
| as built | 150 × 413, the API's JSON | 150 × 413, the API's JSON |

(as built with the same 8 busy loops and a host load of 230.) Each 502 was Caddy's `write tcp …->…:8000: write:
broken pipe`: the API refused from the header, closed, and the proxy was still writing the 64 KiB it had
buffered. Most clients got neither the API's answer nor a 502 but Caddy's own empty 413 (the transport's next
body read failing at the cap): three answers to one request. As built the proxy refuses a declared length over
65,536 bytes before reading any of the body (`error 413` from an `expression` matcher), and `handle_errors 413`
answers every proxy 413 from the 64 KiB cap with the API's own envelope, `Content-Type`, `Cache-Control` and, over
HTTP/1.x only, `Connection: close` (see Review round 1 below). The smoke test compares that body with the API's own refusal, read from the API directly.

## TASK-268: other methods to `/api/v1/compare` with comparisons on

Before, the `compare-on` handle took every method on the path; its 411, 400 and 413 matchers were `POST` only,
so a chunked `PUT` passed straight to `request_body`/`request_buffers` of 16 MiB. As built, only a `POST` enters
the handle; any other method is an ordinary API request under the 64 KiB cap. A `PUT` with a length gets the
API's own 405 (`API_METHOD_NOT_ALLOWED`, `Allow: POST`), a chunked one 411, and a CORS preflight reaches the API
as before.

## TASK-257: a stalled HTTP/3 upload

The client: curl 8.14.1 with HTTP/3 (nghttp3 1.8.0 over OpenSSL 3.5's QUIC), from Debian trixie
(`deploy/smoke-h3.Dockerfile`, `debian:trixie-slim@sha256:62bd423a…`; neither macOS's curl, `curlimages/curl`
8.17.0 or 8.23.0, nor Alpine 3.22's or edge's has HTTP/3), run on the stack's edge network against
`caddy:443` over UDP with `--http3-only`. Each upload is a `POST /api/v1/compare` declaring 16,777,216 bytes,
its body from a pipe: 16,777,215 bytes then silence (a stall), or 16,776,000 then a byte a second (a trickle).
HTTP/3 was turned on in the compare-on block for these runs.

| `read_body` | Upload | Ended (Caddy's access log) |
|---|---|---|
| 60s | 1 stall | 30.89 s, 504: QUIC's idle timeout (Caddy sets no `MaxIdleTimeout`, so quic-go's 30 s), not read_body |
| 20s | 1 stall | 20.05 s, 504 |
| 20s | 1 trickle | 20.18 s, 504 (16,776,019 bytes read: the trickle kept the connection alive) |
| 20s | 8 stalls, then 8 more once those were cut (caddy freshly started) | all 16 at 20.0 to 20.5 s, 504 |
| 60s | 8 trickles in `smoke-test.sh --compare`, after its 8 HTTP/1.1 stalls were cut, then 8 more | 60.10 to 60.14 s, 504 (the logged runs: 2, 3, the follow-up and review round 1; run 1's times weren't kept) |

So `read_body` reaches an HTTP/3 upload through the per-request read deadline Caddy sets since 2.11.6. At the
shipped `read_body 60s`, an upload that stalls (sends nothing at all) is closed first by QUIC's 30 s idle
timeout, at 30.89 s; one that trickles is cut at `read_body`. A stall was cut at `read_body` only when that was
shorter than the idle timeout (20 s). That is why `smoke-test.sh` sends trickles.

Memory (caddy cgroup, MiB): the two batches of 8 stalls held 259 (current) with the peak going 28 → 278, then
308 with the peak 278 → 321: the second batch raised the peak by 43 MiB, under 8 × 25 = 200. In the smoke
test's third run the first batch of 8 trickles raised the peak from 430 (after the HTTP/1.1 batch) to 696 MiB,
and the second by nothing (696 → 696). An HTTP/3 upload held about 31 MiB in a fresh proxy (259 MiB for 8, less
the 14 MiB `memory.current` of the freshly started container before the first batch; its peak was already 28), and
about 33 MiB on top of an HTTP/1.1 batch (smoke run 3, 430 → 696), against about 50 for HTTP/1.1 (`deploy/README.md`'s
2026-10-16 table).

One difference from HTTP/1.1: a cut HTTP/3 upload is forwarded. An HTTP/1.1 upload cut at read_body ends as
499 (the request's context is cancelled) and the API never sees it. Over HTTP/3 the deadline's error leaves
the context alive, and `bufferedBody` falls through to the upstream request with what it read: 10 of the 16
cut uploads above reached the API, which refused each within half a second (408 `API_UPLOAD_TIMEOUT`, 165 to
436 ms; 429 `API_RATE_LIMITED`, or with `busy: compare_running`); in the smoke runs 6 of 8 and 12 of 16. None
was compared. The API's slot
is held for that half second, not for read_body, and the refusal is debited from the client's bucket.

As built: HTTP/3 is on with comparisons on, as with them off (`protocols h1 h2 h3`), and `smoke-test.sh
--compare` runs two batches of 8 trickles after its HTTP/1.1 stalls.

## The web app's paths, and the proxy's own error responses (follow-ups, same day)

**The web paths** (`reverse_proxy web:3000`, no `request_buffers`). The frontend has no server actions, no route
handlers and no middleware (`"use server"`, `route.ts`, `middleware.ts`/`proxy.ts`: none under
`frontend/src`), so it takes no request body. Measured on the same kind of stack (`read_body 60s`), with the
web container's established connections from the proxy read from its `/proc/net/tcp`:

- a small body: `POST /` 405, `PUT /` 405, `GET /` 200, `POST /search` 200 (the page), and a `POST` with a
  `Next-Action` header 400, each within 0.1 s, the body unread;
- 4 stalled bodies each (chunked 1,000 bytes to `/` and `/search`, a declared 2,000 with 1,000 sent, as `POST`
  and as `GET`), with `Connection: close`: answered in 0.06 to 0.11 s and closed; 0 web connections at 15 s.
  `Next-Action` stalls over HTTP/1.1 and HTTP/2: 400 in 0.01 to 0.03 s, 0 web connections at 8 s;
- with keep-alive clients that keep the body open for 30 s: one connection per stall, held 6 s and then
  dropped by the web server (4 stalls: 4 4 4 4 4 4 0 0 …, sampled each second), the same as the idle
  keep-alive connection a plain `GET /search` leaves for 5 s (1 1 1 1 1 0 …);
- a chunked body of 200,000 bytes to `/search`: 413 (the site's 64 KiB `request_body` cap); a declared length
  over the cap: the proxy's 413 before reading it.

So a body sent to the web app, slow, stalled or large, holds nothing there beyond an ordinary request's
keep-alive, and nothing was changed for it; `smoke-test.sh` now checks that a stalled chunked `POST /search`
holds no web connection at 9 s, which a route that read bodies would fail. (The check was not shown failing:
there is no such route to try it on.)

**Error responses.** The site's `header` directive (HSTS, `-Server`) runs only on the routes that answer
normally, not on a response Caddy writes from an error. With the committed config, `GET /` while `web` was
stopped got `502` with `server: Caddy` and no `strict-transport-security`. A site-wide `handle_errors` that
imports the same two header operations (an `error-headers` snippet the 413 block imports too) gives every
such response both: the 502 (HTTP/1.1 and HTTP/2) and the web path's empty 413 now carry
`Strict-Transport-Security: max-age=63072000` and no `Server` header, and the 413 on `/api/*` keeps the API's
envelope.

**The HTTP/3 client's packages.** `deploy/smoke-h3.Dockerfile` now points apt at the Debian snapshot its base
image was built from (`20261020T213255Z`, named in the image's own `debian.sources`), for both trixie and
trixie-security, with `Check-Valid-Until: no`, and asks for `curl=8.14.1-2+deb13u7` and the same
`libcurl4t64`: every package it installs is then fixed (with them `libnghttp3-9 1.8.0-1`, `openssl
3.5.7-1~deb13u3`). A `--no-cache` build took 13 s, and the `HTTP3` feature check passed. An exact-version pin
against deb.debian.org alone would break at the next curl security update, since the security archive keeps
only the latest version.

## The smoke test

`OP_HTTP_PORT=127.0.0.1:28080 OP_HTTPS_PORT=127.0.0.1:28443 deploy/smoke-test.sh`: PASS in 165 s (host load
about 230). With `--compare`, three runs:

1. PASS in 277 s (load about 230), with one batch of 8 HTTP/3 trickles after the HTTP/1.1 stalls, checked by
   how much it raised the memory peak: 444 → 555 MiB.
2. FAIL in 229 s on that check: 439 → 657 MiB (+217, over 8 × 25). An HTTP/3 batch run after an HTTP/1.1 batch
   measures the two protocols' different buffers, not whether a cut upload lets its memory go, so the test now
   sends two HTTP/3 batches and checks the second against the first, as TASK-257's criterion says. Everything
   else in the run passed (the 8 trickles cut at 60.11 to 60.14 s; one 408 and five 429 from the API).
3. PASS in 292 s (load 6 to 66), two HTTP/3 batches. Step 6 (the adapted-config line left out; the access-log
   line, which lists all 16 cuts at 60.10 to 60.14 s, shortened):

```
== 6. comparisons
/meta limits.compare.max_body_bytes: 16777216
Alt-Svc h3 headers: 1
api command: serve --host 0.0.0.0 --port 8000 --trusted-proxy 172.30.81.2 --compare
caddy: read_body 60s, memory limit 1073741824 bytes, GOMEMLIMIT 800MiB
8 uploads stalled a byte short; proxy memory now 394 MiB
a 16 MiB comparison while they stall: records, papers = 282 282
stalled uploads, seconds from each request's start: {"uploads": 8, "cut_min_s": 60.01, "cut_max_s": 60.02, "statuses": ["HTTP/1.1 499 status code 499"]}
proxy memory peak 430 MiB of 1024 MiB; oom_kill 0; restarts 0
API compare requests: 1 (the 16 MiB comparison; no stalled upload reached the API)
HTTP/3 batch 1, version and status each client saw:  8 3 504 
HTTP/3 batch 2, version and status each client saw:  8 3 504 
HTTP/3 uploads in the access log (seconds, status, bytes read): [(60.1, 504, 16776060), (60.1, 504, 16776060), … 16 in all, the last (60.14, 504, 16776060)]
the API's answers to them after the cut:  2 "status": 408 10 "status": 429 
proxy memory peak 696 MiB after the first HTTP/3 batch, 696 MiB after the second
16 MiB + 1 byte to /api/v1/compare -> 413: The file is over 16 MiB (16,777,216 bytes), the most this instance compares.
an HTTP/2 file with Content-Length: abc to /api/v1/compare -> 400
a chunked file to /api/v1/compare -> 411
an HTTP/2 file with no content-length to /api/v1/compare -> 411
64 KiB + 1 byte to /api/v1/records, 20 times over HTTP/1.1 and over HTTP/2 -> 413: {"error":{"code":"API_BODY_TOO_LARGE","message":"The request body is over 65,536 bytes; a query fits in far less."}}
a chunked search record to /api/v1/records -> 411
a chunked PUT to /api/v1/compare -> 411
a PUT with a length to /api/v1/compare -> 405: {"error":{"code":"API_METHOD_NOT_ALLOWED","message":"This endpoint doesn't take that method; use POST."}}
an unsized HTTP/2 body of 64 KiB + 1 byte to /api/v1/records -> 413
an unsized HTTP/2 body that stops at 64 KiB and stays open: API connections from the proxy after 5 s: 0
```

After the follow-ups (the error headers, the web-path check, the pinned HTTP/3 client), both runs passed again:
`deploy/smoke-test.sh` in 111 s and `--compare` in 299 s. The new lines, the same in both:

```
a chunked POST to /search that stalls: 200; web connections from the proxy after 9 s: 0
64 KiB + 1 byte to / -> 413; 1 HSTS, 0 Server header(s)
GET / with web stopped -> 502; 1 HSTS, 0 Server header(s)
```

The `--compare` run's HTTP/3 batches: 16 cut at 60.10 to 60.11 s (504), the API answering 2 × 408 and 10 × 429,
and the memory peak 620 MiB after the first batch and 620 MiB after the second.

## Review round 1 (2026-10-25)

**The proxy's 413 over HTTP/3.** `handle_errors 413` set `Connection: close` on every protocol. A new smoke row
sends 64 KiB + 1 byte to `/api/v1/records` from the HTTP/3 client with `--http3-only`. With the header on every
protocol, curl failed: `(95) HTTP/3 stream 0 was closed cleanly, but before getting all response header fields,
treated as error`. So an HTTP/3 client got no 413 at all. RFC 9114 §4.2 makes a connection-specific header a
malformed response. With the header limited to HTTP/1.x (`not protocol http/2+`), the same row gets `3 413`, the
API's own words and no `Connection` header, and HTTP/1.1 still gets `Connection: close` (also checked now).

**The zero-count rows.** The two rows that count connections held by a stalled body now check, at each sample,
that the stalled curl is still running (`kill -0`). Afterwards they check how each request ended:
- the 64 KiB HTTP/2 body, once its producer ends it at 10 s, gets 422, and the API's line for it shows 422 in
  2.3 ms: the API got it whole and never waited for it;
- the stalled `POST /search` gets 200.

Both runs passed after these changes: `deploy/smoke-test.sh --compare` in 333 s, then `deploy/smoke-test.sh` in
156 s. (The only later change to `smoke-test.sh` is a line in its header comment.)
