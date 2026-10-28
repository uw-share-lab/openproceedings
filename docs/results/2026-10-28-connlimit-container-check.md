# The host's per-source limits, checked between containers (2026-10-28)

`deploy/connlimit.nft` (TASK-067's last criterion; spec 08 §Deploy, `deploy/README.md` §Per-source limits on
the host), loaded in one container's own network namespace and probed from others on a Docker network. This
checks that nftables accepts the rules and that they count and limit as specified. It is **not** the
measurement in front of Caddy on a host: that waits on TASK-064, and TASK-067's last criterion stays
unchecked.

**Setup.** Docker Desktop (engine 24.0.7) on a Mac. Its LinuxKit kernel is 6.5.11, and the server container
ran nftables 1.1.3 (Alpine 3.22) with `--cap-add NET_ADMIN`. The rules were in that container's network
namespace only, so the host and other containers were untouched. A user network `cl-test` had subnets
172.31.250.0/24 and fd00:cafe::/56. The server was 172.31.250.10 and fd00:cafe::10. It ran a small Python
server that accepts and drains TCP 443 (v4 and v6) and answers UDP 443 (v4 and v6). The clients were
`python:3.12-alpine` containers:

- `conns <host> <n> [<hold s>]` opens `n` TCP connections one after another, each with a 3 s connect timeout,
  and holds the ones that connect.
- `udp <host> <n>` sends one datagram from each of `n` sockets and counts the answers (2 s timeout).
- `bytes <host> <MiB>` sends that much on one connection and times it until the server reports what it read.

An IPv6 client in another /64 added its address in the container (`ip -6 addr add <a>/56 dev eth0`, then
waited 3 s for DAD) and bound to it. Docker's `--ip6` gave the container `fd00:cafe::<host part>`, so it
couldn't place a client in another /64.

**What differs from the shipped file.** The `fib daddr type != local accept` line was taken out. LinuxKit
has no `nft_fib` support, and `deploy/connlimit.sh check` refuses the file there with "Could not process
rule: No such file or directory". Stock distribution kernels (Debian, Ubuntu, RHEL) build `nft_fib_inet`.
That line only stops the rules applying to packets not addressed to the host, such as containers' HTTPS
going out, so it can't change the results below, which are all to the server's own address. The server ran
`deploy/connlimit.sh check`, then `apply` twice, which shows that reloading is idempotent.

**Raw output:**

```text
== server: 6.5.11-linuxkit nftables v1.1.3 (Commodore Bullmoose #4) 
/tmp/connlimit.nft parses
applied twice
ready
== v4 one source, 20 tcp
tcp 16/20 connected
== v4 two sources at once, 12 each (expect 12+12)
tcp 12/12 connected
tcp 12/12 connected
== v4 udp 20 flows
udp 16/20 answered
== v4 bytes: 40 MiB one connection (expect ~24 s at 1 MiB/s after a 16 MiB burst)
bytes 40 MiB sent, server read 40 MiB in 23.4 s
== same /64 (fd00:cafe:0:7::/64): A holds 10, B 8s later (expect 10, 6)
tcp 10/10 connected
tcp 6/10 connected
== different /64s (0:8 and 0:9): (expect 10, 10)
tcp 10/10 connected
tcp 10/10 connected
== v6 udp 20 (expect 16)
udp 16/20 answered
== v6 bytes 40 MiB (expect ~24 s)
bytes 40 MiB sent, server read 40 MiB in 23.4 s
== drop counters
		th dport != 443 accept
		ct state new add @conns4 { ip saddr ct count over 16 } counter packets 16 bytes 836 drop comment "connections"
		ct state new add @conns6 { ip6 saddr & ffff:ffff:ffff:ffff:: ct count over 16 } counter packets 16 bytes 1156 drop comment "connections"
		update @bytes4 { ip saddr limit rate over 1 mbytes/second burst 16 mbytes } counter packets 380 bytes 4946080 drop comment "bytes"
		update @bytes6 { ip6 saddr & ffff:ffff:ffff:ffff:: limit rate over 1 mbytes/second burst 16 mbytes } counter packets 388 bytes 4383336 drop comment "bytes"
```

**Reading it:**

- One IPv4 source got 16 of 20 TCP connections and 16 of 20 UDP flows. Two IPv4 sources each got 12 of 12.
- In one /64, a second address got the 6 of 16 the first address left. Addresses in two /64s each got 10 of 10.
- 40 MiB on one connection took 23.4 s from either family: the 16 MiB burst, then 24 MiB at 1 MiB/s.
- The drop counters count packets: 16 for the 4 refused connections of each family, each SYN and its
  retries.

**Not checked here:**

- Caddy's memory under the limits, from one source over HTTP/1.1 and over HTTP/2 or HTTP/3 with many
  streams.
- The per-request overhead of many stalled streams.
- The `fib` line.
- Docker's DNAT path on a host.

Those wait on the host (`deploy/README.md` §Per-source limits on the host).
