# Caddy's request_buffers streams the rest of a body past its limit, and each buffered upload costs three times the file

**Key lesson:** Before trusting a proxy setting to keep a slow upload off a backend, run the stall against the real stack and read the proxy's source for the edge: Caddy's `request_buffers` buffers only up to its limit and then streams the rest to the upstream (so an unsized body that reaches or passes it and stalls still holds the backend), a read error falls through to the upstream too, `request_body max_size` never checks a declared length, and a buffered 16 MiB upload costs the proxy about 50 MiB.

- **Date:** 2026-10-16 · **Task:** task-183 · **Area:** ops
- **Artifacts:** `deploy/Caddyfile` (`compare-on`), `deploy/compare.yml`, `deploy/smoke-test.sh --compare`, `backend/tests/deploy/compare_probe.py`, `deploy/README.md` §Comparisons; Caddy v2.11.4 `modules/caddyhttp/reverseproxy/reverseproxy.go` `bufferedBody`

## What we set out to do
Fix the README's untested Caddy block for `POST /api/v1/compare` (decision-035) and run it through the smoke
test: 16 MiB through, a stalled upload cut before it holds the API's one comparison slot, proxy memory
bounded and measured.

## What we learned
- **`request_buffers N` is not "buffer the whole body".** `bufferedBody` does `io.CopyN(buf, body, N)`; if it
  reads exactly N bytes, or the read fails, it returns `MultiReader(buf, body)` and the upstream request is
  opened with the rest streaming (evidence: the v2.11.4 source, unchanged in v2.11.7; on the stack, a chunked upload of 16 MiB + 10
  bytes, then silence, got the API's 408 after its 30 s `compare_upload_seconds`, the API log showing it
  held the slot). A body that declares its length within the cap can't do this; so the comparison path now
  answers 411 to a `POST` with no `Content-Length` (a Chromium `fetch` of a `Blob` sent one over HTTP/2).
- **`request_body max_size` refuses only as it reads.** A declared `Content-Length` one byte over 16 MiB was
  forwarded and refused by the API's own `BodyLimit` from the header (413 `API_BODY_TOO_LARGE`, before any
  slot), not by Caddy. Same for 64 KiB on the other routes. And the refusal races the proxy: the API resets
  the connection while Caddy is still writing the body, so one run in five gave the client a 502
  (`write: connection reset by peer`). The comparison path now answers 413 itself, before reading the body,
  from an `expression` matcher on the declared length (`int('0' + string({http.request.header.Content-Length}))
  > 16777216`; the `'0' +` keeps a missing header from erroring into a 500). Over HTTP/2 Go hands Caddy a
  malformed `Content-Length` (`abc`, `+5`, `5,5`) that HTTP/1.1 would have refused with 400, and `int()` then
  fails into a 500 with two error lines, so a `matches('^0*[0-9]{1,18}$')` route answers 400 first (found by
  the review on a throwaway caddy with h2c).
- **A stall that never reaches the limit is cut by `read_body` and never reaches the upstream**: with the
  declared 16 MiB minus one byte sent, the API logged nothing, a whole 16 MiB comparison ran while 8 such
  uploads were held, and each was cut at `read_body` (60.0 to 60.04 s after its request's start with `60s`: the
  timeout counts from there, sending included). Caddy 2.11.4 then answered the client an empty `200` (its access log said `status: 0`); 2.11.7 answers
  `499`.
- **Memory: about 50 MiB per buffered 16 MiB upload.** cgroup `memory.current` held 412 to 472, 793 and 912 MiB for
  8, 16 and 24 uploads on Caddy 2.11.4 (460, 765 and 883 MiB on 2.11.7); `bytes.Buffer.ReadFrom` doubles to 32 MiB to hold 16 and the outgrown buffers wait
  for GC. With `mem_limit 1g` and `GOMEMLIMIT 800MiB`, 24 reached the edge (peaks 890 to 998 MiB) and 32 got the kernel's OOM kill (Docker's `oom`
  event, exit 137) and a restart: bounded, but a few dozen uploads take the proxy down. `OOMKilled` stayed
  `false` in `docker inspect` (tini is PID 1 and the child was killed); `docker events` showed it.
- **Caddy units:** `16MB` is 16,000,000 and `64KB` 64,000 (`caddy adapt` shows the bytes); the API's caps are
  16,777,216 and 65,536, so write `16MiB` / `64KiB`.
- **A site-level directive wraps a `handle`**: the site's `request_body` ran before the path's handle, so it
  is scoped with `@rest not path /api/v1/compare` inside an imported snippet chosen by `{$OP_COMPARE:off}`; an
  unknown value names a missing snippet and `caddy validate` fails ("File to import not found").

## Dead ends — don't repeat these
- Reading `cut_after_s` without checking the API log: an upload that streamed through and was refused there
  also "ends", so the proof is the API's access lines (and a concurrent comparison that gets 200).
- Measuring under a 1-minute load above 100 (other sessions' suites): 32 uploads couldn't be sent within a
  30 s `read_body`, and the run measured nothing. Wait for the load, or lengthen `read_body` for the run.
- `curl -T -` is a `PUT`: a 411 check needs `-X POST`.

## Decisions (and what would change them)
- 411 for an unsized `POST` to the comparison path instead of a buffer one byte over the cap → it closes the
  stream-through for every unsized body, over HTTP/2 as well as chunked → reverse if a client that must
  stream (no known length) needs comparisons.
- No HTTP/3 with comparisons on (`protocols h1 h2` from a `protocols-on` snippet) → Caddy builds its HTTP/3
  server with no timeout but `IdleTimeout` (`modules/caddyhttp/server.go`, `http3.Server{...}`, in v2.11.4 and
  v2.11.7). In 2.11.4 nothing else gave a QUIC stream a read deadline; since 2.11.6 Caddy sets a per-request
  one through `http.ResponseController` (read idle, `read_body` as its ceiling), which quic-go's HTTP/3 writer
  honours (`SetReadDeadline`), so it is probably cut now. Not measured: this Mac's curl has no HTTP/3 →
  re-enable HTTP/3 once a QUIC stall is shown to be cut.
- The overlay `deploy/compare.yml` instead of README edits → one switch that the smoke test runs exactly as
  an operator would → a deploy that templated its Caddyfile could fold it in.

## Follow-ups
- [ ] (reported to the lead for filing) the other API routes have the same stream-through at 64 KiB (an
  unsized body that reaches the cap and stalls holds a uvicorn connection until `read_body`, which
  `compare.yml` raises to 60 s); and a cap on concurrent uploads or connections per client in front of the
  proxy, the one thing that would keep an upload flood from OOM-killing it.

## Propagated to
- `deploy/README.md` §Comparisons (the measurements and the enable steps), spec 08 §Deploy, the
  `Caddyfile`'s and `compare.yml`'s comments, decision-035's as-built note, and the raw measurements in
  `docs/results/2026-10-16-compare-proxy.md`.
- Test: `deploy/smoke-test.sh --compare` checks the stall, the memory peak, 413, 411 and the 64 KiB cap; no
  skill change (no skill covers Caddy).

## Addendum — 2026-10-24 (TASK-255, TASK-259, TASK-257, TASK-268: the other API routes, the 413 race, HTTP/3)
Measured on the Docker stack (Caddy 2.11.7, Go 1.26.8); numbers in `docs/results/2026-10-24-proxy-body-limits.md`,
the as-built config in `deploy/Caddyfile`, `deploy/README.md` §Comparisons and spec 08 §Deploy (commits 5888f841,
2d4d8aa8).
- **A cap that refuses only as it reads lets the upstream refuse first, and that becomes a 502 under load.** The
  fix above was made for `/api/v1/compare` only; the 64 KiB routes kept forwarding a declared length over the cap.
  With 8 busy-loop containers, 150 requests of 65,537 bytes per protocol gave three different answers: Caddy's
  empty 413 (most), the API's JSON 413, and 9 × 502 (`write: broken pipe`: the API refused from the header and
  closed while the proxy was still sending its buffer). Refusing a declared over-cap length before reading the
  body (`error 413` from an `expression` matcher) and answering every proxy 413 from the 64 KiB cap in the API's
  exact envelope, `Content-Type`, `Cache-Control`, and `Connection: close` over HTTP/1.x only (`handle_errors 413`;
  on HTTP/3 the header made the 413 malformed, RFC 9114 §4.2: review round 1) gave 150 × the API's 413
  on each protocol. Lesson: when a race is fixed on one route, apply it to every route behind the same cap; and
  make the proxy's refusal indistinguishable from the upstream's, so a client gets one answer.
- **Caddy's `handle_errors` skips the site's `header` directive.** A 502 with `web` stopped carried `server: Caddy`
  and no HSTS; the site `header` runs only on routes that answer normally. A site-wide `handle_errors` that
  imports the same header operations (snippet `error-headers`, imported by the 413 block too) fixes every response
  the proxy writes from an error (`smoke-test.sh` checks a 413 on `/` and the 502).
- **A chunked body over the cap that then stalls holds the API anyway, because Go drains a closed body.**
  `request_buffers` one byte over the cap (65537) stops the at-cap stream-through (4 stalls of 65,536 bytes held 0
  API connections), but 4 chunked stalls of 70,000 bytes still held 4 for the whole `read_body`: `bufferedBody`
  opens the upstream request after the cap's error, the transport fails and closes the body, and Go's HTTP/1.1
  server reads up to 256 KiB of a body being closed to reuse the connection, blocking on the silent client
  (Go 1.26 `net/http` `transfer.go`, read from the source, consistent with the 59.98 s roundtrip). HTTP/2 does not
  drain (an unsized 200,000-byte HTTP/2 stall held 0 and got 413). So every chunked `/api/*` request gets 411
  (`header Transfer-Encoding *` sees the coding Go removes from the header map); neither the web app nor `op` sends one.
- **It was every method, not only POST.** The API's `BodyLimit` reads any body before routing, so a stalled
  chunked `GET /api/v1/search` held a connection too; and the compare handle took every method while its length
  checks were `POST`-only, so a chunked `PUT` reached the 16 MiB buffer. Only a `POST` enters it now (`PUT` → the
  API's 405). Lesson: scope a matcher's checks to exactly what enters the handle, or a method the checks skip
  inherits the handle's looser limits.
- **HTTP/3 back on: `read_body` cuts a trickling QUIC upload, but the cut upload is forwarded.** With a
  Debian curl 8.14.1 built with HTTP/3 (`deploy/smoke-h3.Dockerfile`; macOS's curl, `curlimages/curl` and Alpine's
  have none), 16 trickles were cut at `read_body` 60s (504); a stall was cut there only at `read_body 20s` (16 at
  20.0-20.5 s). At 60 s a client that sends nothing is closed first by QUIC's 30 s idle timeout (30.89 s). Unlike HTTP/1.1 (499, context cancelled, the API never sees it), the HTTP/3 deadline
  leaves the context alive and `bufferedBody` forwards what it read: 10 of 16 reached the API, which refused each
  within half a second (408/429), never comparing it. Accepted and documented; a memory check of HTTP/3 after an
  HTTP/1.1 batch measures the two protocols' buffers, so the smoke test compares a second HTTP/3 batch with a first.
- **Pin an apt-installed tool through the base image's Debian snapshot.** An exact `curl=` pin against
  deb.debian.org would break at the next security update (the security archive keeps only the latest version);
  `smoke-h3.Dockerfile` points apt at the snapshot named in the image's own `debian.sources`.
- Propagated to: `deploy/README.md` §Comparisons, spec 08 §Deploy, the `Caddyfile`'s comments, decision-035's
  as-built note (6378d5f8), and `deploy/smoke-test.sh` (411s, 405, the API envelope on 413 under 20 tries per
  protocol, HTTP/3 batches, error headers, a stalled web body). Still no skill: none covers Caddy.
