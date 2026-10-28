# A connection cap does not cap multiplexed uploads

**Key lesson:** Over HTTP/2 or HTTP/3, a per-source connection limit doesn't bound concurrent requests. Check the server's stream limit before relying on one. Caddy sets none, so bound bytes per source instead.

- **Date:** 2026-10-28 · **Task:** task-067 (from task-256) · **Area:** deploy
- **Artifacts:** `deploy/connlimit.nft`, `deploy/connlimit.sh`, `backend/tests/deploy/test_connlimit.py`,
  `docs/results/2026-10-28-connlimit-container-check.md`

## What we set out to do
Build the owner's option (c) from TASK-256: a per-source connection limit (nftables `ct count`) on TCP and UDP
443 in front of Caddy. The limit has to keep one client's compare uploads under the proxy's OOM point (24 near
1 GiB, 32 killed).

## What we learned
- **Connections are not uploads.** Caddy 2.11.7 calls `http2.ConfigureServer(srv, new(http2.Server))` and
  leaves quic-go's `MaxIncomingStreams` unset, so the limits are 250 HTTP/2 and 100 HTTP/3 streams per
  connection. Neither the Caddyfile nor the JSON config can lower them. One connection can carry the 32
  uploads that OOM the proxy. A per-source byte rate (`limit rate over 1 mbytes/second burst 16 mbytes`)
  bounds, by arithmetic not yet measured in front of Caddy, what the proxy buffers for one source, because
  `read_body` cuts an upload that is still arriving.
- **Where the chain hooks decides what it sees.** Docker publishes ports by DNAT at prerouting -100. A
  filter at prerouting -150 runs after conntrack (-200) and sees `dport 443` before it is rewritten. An `input`
  chain never sees traffic to a published container port, which takes the forward path. Traffic from the
  host itself never passes prerouting, so a smoke test run on the host isn't limited by the rules. Containers'
  own HTTPS going out does pass it, so the rules also need `fib daddr type local` (Docker's DNAT test), and
  that needs the kernel's `nft_fib_inet`.
- **Docker Desktop can test nftables, mostly.** Its LinuxKit kernel (6.5) loads `ct count`, masked IPv6 set
  keys and byte `limit` meters in a container's own network namespace (`--cap-add NET_ADMIN`). The host is
  unaffected, so rules can be checked between containers without a Linux machine
  (`docs/results/2026-10-28-connlimit-container-check.md`). It has no `nft_fib`, so a `fib` rule fails there.
- **nft's `define` can't name a rate.** `limit rate over $X mbytes/second` is a syntax error, so the numbers
  are literals, pinned by the static test.

## Dead ends — don't repeat these
- `docker run --ip6 fd00:cafe:0:7::1` on a /56 network gave the container `fd00:cafe::1`, so every client
  looked like one /64. Add the extra address in the container (`ip -6 addr add … dev eth0`, then wait for DAD)
  and bind to it.

## Decisions (and what would change them)
- 16 connections and 1 MiB/s after a 16 MiB burst, per IPv4 address or IPv6 /64. A Caddy option for stream
  limits would let the byte rate be relaxed. A different `read_body` or memory limit changes the bound, and
  the test reads both from `compare.yml`.

## Follow-ups
- None filed. The measurement in front of Caddy is TASK-067's last criterion, and it waits on TASK-064.

## Propagated to
- Skill / agent / CLAUDE.md updated? — CLAUDE.md's deploy list; spec 08 §Deploy; deploy/README.md §Per-source limits on the host.
- Test or hook added? — `backend/tests/deploy/test_connlimit.py`.
