"""Shared pytest configuration: no network, and Hypothesis profiles (testing-standards, property-testing).

Tests never call real APIs (OpenReview, Semantic Scholar, PMLR, …). Every TCP connection and UDP send other
than a Unix socket or loopback, and every non-loopback name lookup, fails with NetworkBlockedError, for the
whole test session (limits: `pytest_configure`). Crawler tests use recorded HTTP fixtures (01 §Testing); there is no opt-out marker.


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
_real_sendto = socket.socket.sendto
_real_sendmsg = socket.socket.sendmsg
_real_getaddrinfo = socket.getaddrinfo
_real_gethostbyname = socket.gethostbyname
_real_gethostbyname_ex = socket.gethostbyname_ex
_real_gethostbyaddr = socket.gethostbyaddr
_real_getnameinfo = socket.getnameinfo


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


def _sendto(self: socket.socket, data: Any, *rest: Any) -> int:
    address = rest[-1]  # sendto(data, address) or sendto(data, flags, address)
    if not _allowed(self, address):
        raise _refuse(address)
    return _real_sendto(self, data, *rest)


def _sendmsg(self: socket.socket, buffers: Any, *rest: Any) -> int:
    if len(rest) >= 3 and not _allowed(self, rest[2]):  # sendmsg(buffers, ancdata, flags, address)
        raise _refuse(rest[2])
    return _real_sendmsg(self, buffers, *rest)


def _lookup(real: Any) -> Any:
    def guarded(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host in _LOOPBACK or host is None:
            return real(host, *args, **kwargs)
        raise _refuse(host)

    return guarded


def _reverse_lookup(sockaddr: Any, flags: int) -> Any:
    if isinstance(sockaddr, tuple) and sockaddr[0] in _LOOPBACK:
        return _real_getnameinfo(sockaddr, flags)
    raise _refuse(sockaddr)


def pytest_configure(config: pytest.Config) -> None:
    """Installed for the whole session. Covers connect/connect_ex (TCP), sendto/sendmsg (UDP, e.g. DNS) and
    every name lookup. Not covered: subprocesses and `multiprocessing` spawn children (they start a fresh
    interpreter; tests don't spawn network clients), and code calling the C-level `_socket` module directly."""
    socket.socket.connect = _connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _connect_ex  # type: ignore[method-assign]
    socket.socket.sendto = _sendto  # type: ignore[method-assign, assignment]
    socket.socket.sendmsg = _sendmsg  # type: ignore[method-assign]
    socket.getaddrinfo = _lookup(_real_getaddrinfo)
    socket.gethostbyname = _lookup(_real_gethostbyname)
    socket.gethostbyname_ex = _lookup(_real_gethostbyname_ex)
    socket.gethostbyaddr = _lookup(_real_gethostbyaddr)
    socket.getnameinfo = _reverse_lookup
