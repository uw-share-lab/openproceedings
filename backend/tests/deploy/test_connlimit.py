"""The host's per-source limits in front of Caddy (`deploy/connlimit.nft`, TASK-067): the rules cover TCP and UDP
443 for IPv4 addresses and IPv6 /64s at a hook that sees Docker's published port, and their numbers stay under
what the proxy was measured to hold with `compare.yml`'s defaults (deploy/README.md §Comparisons). Where `nft`
can check a ruleset here (Linux, with CAP_NET_ADMIN) the file is also parsed by it; elsewhere only these
static checks run. Measuring the limits on a host is TASK-067's last criterion."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[3] / "deploy"
RULESET = DEPLOY / "connlimit.nft"
V6_64 = "ffff:ffff:ffff:ffff::"

# measured on this stack with compare.yml's defaults (docs/results/2026-10-16-compare-proxy.md): 16 HTTP/1.1
# uploads held at once peaked at 804 MiB of the 1 GiB limit, 32 were OOM-killed; an upload costs the proxy
# about three times what has arrived
MEASURED_HELD = 16
PROXY_FACTOR = 3


def _rules() -> list[str]:
    text = RULESET.read_text(encoding="utf-8")
    chain = text[text.index("chain prerouting {") :]
    return [line.strip() for line in chain.splitlines() if " drop" in line]


def _compare_default(name: str) -> str:
    found = re.search(rf"\${{{name}:-([^}}]+)}}", (DEPLOY / "compare.yml").read_text(encoding="utf-8"))
    assert found, f"compare.yml has no default for {name}"
    return found.group(1)


def test_chain_sees_the_published_port_after_conntrack() -> None:
    text = RULESET.read_text(encoding="utf-8")
    # after conntrack (-200), before Docker's DNAT (-100), which would turn 443 into the container's port
    assert "type filter hook prerouting priority -150; policy accept;" in text
    assert "meta l4proto != { tcp, udp } accept" in text  # TCP and UDP (QUIC: HTTP/3 is on)
    assert "th dport != 443 accept" in text
    # only this table is replaced on a reload, never Docker's
    assert re.search(
        r"^table inet openproceedings_limits\ndelete table inet openproceedings_limits$", text, re.M
    )
    assert "flush ruleset" not in text


def test_each_limit_covers_ipv4_addresses_and_ipv6_64s() -> None:
    rules = _rules()
    assert len(rules) == 4
    conns = [r for r in rules if r.startswith("ct state new add @conns")]
    rates = [r for r in rules if r.startswith("update @bytes")]
    assert len(conns) == 2 and len(rates) == 2
    for pair in (conns, rates):
        v4 = [r.split("{ ip saddr ", 1)[1] for r in pair if "{ ip saddr " in r]
        v6 = [r.split(f"{{ ip6 saddr and {V6_64} ", 1)[1] for r in pair if f"{{ ip6 saddr and {V6_64} " in r]
        assert len(v4) == 1 and len(v6) == 1
        assert v4 == v6  # the same limit for both families


def test_connection_cap_is_at_most_what_the_proxy_was_measured_to_hold() -> None:
    caps = {int(m) for r in _rules() for m in re.findall(r"ct count over (\d+)", r)}
    assert len(caps) == 1
    assert 6 <= caps.pop() <= MEASURED_HELD  # a browser's six HTTP/1.1 connections fit


def test_byte_rate_bounds_one_sources_buffered_uploads() -> None:
    rates = {
        m for r in _rules() for m in re.findall(r"limit rate over (\d+) mbytes/second burst (\d+) mbytes", r)
    }
    assert len(rates) == 1
    rate, burst = (int(x) for x in rates.pop())
    read_body = _compare_default("OP_READ_BODY")
    assert read_body.endswith("s")
    seconds = int(read_body[:-1])
    mem_limit = _compare_default("OP_CADDY_MEM_LIMIT")
    assert mem_limit == "1g"
    # a 16 MiB file fits in read_body at the rate (the burst aside) ...
    assert rate * seconds >= 16
    # ... and what one source can have in flight before read_body cuts it costs at most a quarter of the limit
    assert PROXY_FACTOR * (burst + rate * seconds) <= 1024 // 4


def test_nft_parses_the_ruleset_where_it_can() -> None:
    nft = shutil.which("nft")
    if nft is None:
        pytest.skip("no nft here (it needs Linux with nftables); the static checks above still ran")
    done = subprocess.run([nft, "-c", "-f", str(RULESET)], capture_output=True, text=True, check=False)
    if done.returncode != 0 and "Operation not permitted" in done.stderr:
        pytest.skip("nft -c needs CAP_NET_ADMIN here")
    assert done.returncode == 0, done.stderr
