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


def test_loopback_and_unix_sockets_still_work() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect(server.getsockname())  # an in-process test server is fine
    a, b = socket.socketpair()
    a.close()
    b.close()
