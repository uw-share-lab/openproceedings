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
