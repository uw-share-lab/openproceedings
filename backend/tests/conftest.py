"""Shared pytest configuration: no network, and Hypothesis profiles (testing-standards, property-testing).

Tests never call real APIs (OpenReview, Semantic Scholar, PMLR, …). Every socket connection other than a
Unix socket or loopback fails with NetworkBlockedError, and name lookups fail too, for the whole test
session. Crawler tests use recorded HTTP fixtures (01 §Testing); there is no opt-out marker.


Select with HYPOTHESIS_PROFILE or `--hypothesis-profile`: `dev` (local default), `ci` (2,000 examples, the
`test` workflow) and `nightly` (50,000, the `nightly` workflow). `print_blob=True` so a CI failure prints a
`@reproduce_failure` blob; the example database (`.hypothesis/`) is gitignored.
"""

import os
import socket
from typing import Any

import pytest
from hypothesis import settings

settings.register_profile("dev", max_examples=200, deadline=500, print_blob=True)
settings.register_profile("ci", max_examples=2_000, deadline=2_000, print_blob=True)
settings.register_profile("nightly", max_examples=50_000, deadline=None, print_blob=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


class NetworkBlockedError(RuntimeError):
    """A test tried to reach the network."""


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _refuse(what: object) -> NetworkBlockedError:
    return NetworkBlockedError(
        f"tests never call real APIs (tried {what!r}); use a recorded fixture — testing-standards skill"
    )


def _allowed(sock: socket.socket, address: Any) -> bool:
    return sock.family == socket.AF_UNIX or (isinstance(address, tuple) and address[0] in _LOOPBACK)


def _connect(self: socket.socket, address: Any) -> None:
    if not _allowed(self, address):
        raise _refuse(address)
    _real_connect(self, address)


def _connect_ex(self: socket.socket, address: Any) -> int:
    if not _allowed(self, address):
        raise _refuse(address)
    return _real_connect_ex(self, address)


def _no_lookup(host: Any, *args: Any, **kwargs: Any) -> Any:
    if host in _LOOPBACK or host is None:
        return _real_getaddrinfo(host, *args, **kwargs)
    raise _refuse(host)


_real_getaddrinfo = socket.getaddrinfo


def pytest_configure(config: pytest.Config) -> None:
    socket.socket.connect = _connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _connect_ex  # type: ignore[method-assign]
    socket.getaddrinfo = _no_lookup
