"""Tests never call real APIs: the session-wide guard in conftest.py refuses every network connection."""

from __future__ import annotations

import socket
import urllib.request

import pytest

from tests.conftest import NetworkBlockedError


def test_http_request_is_refused() -> None:
    with pytest.raises(NetworkBlockedError, match="recorded fixture"):
        urllib.request.urlopen("https://api2.openreview.net/notes", timeout=1)


def test_name_lookup_is_refused() -> None:
    with pytest.raises(NetworkBlockedError):
        socket.getaddrinfo("api.semanticscholar.org", 443)


def test_raw_socket_to_the_internet_is_refused() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s, pytest.raises(NetworkBlockedError):
        s.connect(("1.1.1.1", 443))


def test_connect_ex_is_refused() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s, pytest.raises(NetworkBlockedError):
        s.connect_ex(("1.1.1.1", 443))


def test_ipv6_is_refused() -> None:
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s, pytest.raises(NetworkBlockedError):
        s.connect(("2606:4700:4700::1111", 443, 0, 0))


@pytest.mark.parametrize(
    "lookup",
    [
        lambda: socket.gethostbyname("example.com"),
        lambda: socket.gethostbyname_ex("example.com"),
        lambda: socket.gethostbyaddr("1.1.1.1"),
        lambda: socket.create_connection(("example.com", 443), timeout=1),
    ],
    ids=["gethostbyname", "gethostbyname_ex", "gethostbyaddr", "create_connection"],
)
def test_every_name_lookup_is_refused(lookup: object) -> None:
    with pytest.raises(NetworkBlockedError):
        lookup()  # type: ignore[operator]


def test_udp_sends_are_refused() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        with pytest.raises(NetworkBlockedError):
            s.sendto(b"\x00", ("1.1.1.1", 53))  # a DNS query
        with pytest.raises(NetworkBlockedError):
            s.sendto(b"\x00", 0, ("1.1.1.1", 53))
        with pytest.raises(NetworkBlockedError):
            s.sendmsg([b"\x00"], [], 0, ("1.1.1.1", 53))


def test_loopback_and_unix_sockets_still_work() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect(server.getsockname())  # an in-process test server is fine
    a, b = socket.socketpair()
    a.close()
    b.close()
    assert socket.gethostbyname("localhost")
    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_server,
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_client,
    ):
        udp_server.bind(("127.0.0.1", 0))
        assert udp_client.sendto(b"x", udp_server.getsockname()) == 1
        assert (
            udp_client.sendto(b"x", 0, udp_server.getsockname()) == 1
        )  # the flags form reads the address last
