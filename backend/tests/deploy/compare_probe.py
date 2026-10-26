"""Uploads for the deploy smoke test's comparison checks (`deploy/smoke-test.sh --compare`, TASK-183): a RIS file of
an exact size made from a fixture snapshot, and raw uploads to the proxy that stall, so the test can see where
they are cut and what the proxy holds meanwhile. Standard library only; it talks to the stack over TLS on
localhost and nothing else.

    python3 backend/tests/deploy/compare_probe.py ris <records.jsonl> <bytes> <out.ris>
    python3 backend/tests/deploy/compare_probe.py stall <port> <cacert> <path> <declared bytes> <sent> <uploads> [<method>]

`ris` writes a file of exactly `<bytes>` bytes: one record per fixture paper with an abstract, by title, venue
and year (the first 400), each padded with `N1` note lines (no field the comparison reads) so the file fits
the API's caps (64 lines a record, 32,768 characters a line). Prints its record count.

`stall` opens `<uploads>` connections at once, each a `<method> <path>` (`POST` unless given; query string
included) declaring `<declared bytes>` (or `chunked`: sent chunked, with no length, the last chunk never sent;
TASK-255, TASK-268) and sending `<sent>` bytes of body, then stops sending. It prints `sent` once every upload
has sent its bytes (the moment the proxy holds them all), then waits for each connection to end and prints one
JSON line: how many seconds after its request's first byte the first and last were cut (read_body counts from
there; -1 for one that failed to connect or was cut while still sending), and the status lines they got.
"""

from __future__ import annotations

import json
import socket
import ssl
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

RECORDS = 400
MAX_LINE = 30_000  # under the API's 32,768-character line cap, tag included
MAX_LINES = 60  # under its 64 lines a record
WAIT = 600  # seconds: the longest any upload waits for the others, or for the proxy to end it


def ris(records: Path, size: int, out: Path) -> int:
    papers = [
        r for r in map(json.loads, records.read_text(encoding="utf-8").splitlines()) if r.get("abstract")
    ]
    heads = [
        f"TY  - CONF\nTI  - {' '.join(p['title'].split())}\nJF  - {p['venue']}\nPY  - {p['year']}///\n".encode()
        for p in papers[:RECORDS]
    ]
    tail = b"ER  - \n"
    room = size - sum(len(h) + len(tail) for h in heads)
    if room < 0:
        raise SystemExit(f"{size} bytes is too small for {len(heads)} records")
    share, extra = divmod(room, len(heads))
    with out.open("wb") as f:
        for i, head in enumerate(heads):
            f.write(head + _padding(share + (1 if i < extra else 0)) + tail)
    if out.stat().st_size != size:
        raise SystemExit(f"wrote {out.stat().st_size} bytes, not {size}")
    return len(heads)


def _padding(n: int) -> bytes:
    """`n` bytes of `N1` lines (8 bytes at least, `MAX_LINE` at most, `MAX_LINES` of them at most)."""
    if 0 < n < 8:
        raise SystemExit(f"{n} bytes of padding is too short for a line: use another size")
    lines: list[bytes] = []
    while n > 0:
        take = min(n, MAX_LINE)
        if 0 < n - take < 8:  # leave the last line room for its tag
            take = n - 8
        lines.append(b"N1  - " + b"x" * (take - 7) + b"\n")
        n -= take
    if len(lines) > MAX_LINES:
        raise SystemExit("padding over the API's line caps: use a smaller file or more records")
    return b"".join(lines)


@dataclass
class Cut:
    """How one stalled upload ended: seconds from its request's first byte (-1 if it never got to stall, or
    nothing ended it within `WAIT`), and the status line it got, if any."""

    after_start_s: float
    status: str | None


def stall(
    port: int, cacert: str, target: str, declared: int | None, sent: int, uploads: int, method: str = "POST"
) -> None:
    """`declared` None: the body is sent chunked."""
    context = ssl.create_default_context(cafile=cacert)
    length = "Transfer-Encoding: chunked" if declared is None else f"Content-Length: {declared}"
    kind = (
        "application/x-research-info-systems" if target.startswith("/api/v1/compare") else "application/json"
    )
    head = (
        f"{method} {target} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
        f"Content-Type: {kind}\r\n{length}\r\n\r\n"
    ).encode()
    line = b"N1  - " + b"x" * 1017 + b"\n"

    def framed(piece: bytes) -> bytes:  # a chunk of a chunked body, or the bytes themselves
        return piece if declared is not None else f"{len(piece):x}\r\n".encode() + piece + b"\r\n"

    cuts = [Cut(-1.0, "not finished") for _ in range(uploads)]
    ready = threading.Barrier(uploads + 1, timeout=WAIT)

    def one(i: int) -> None:
        try:
            s = context.wrap_socket(
                socket.create_connection(("localhost", port), timeout=WAIT), server_hostname="localhost"
            )
        except OSError:
            cuts[i] = Cut(-1.0, "connect failed")
            _wait(ready)
            return
        with s:
            began = time.monotonic()  # read_body counts from the request's start
            try:
                s.sendall(head)
                left = sent
                while left > 0:
                    s.sendall(framed(line[: min(left, len(line))]))
                    left -= min(left, len(line))
            except OSError:  # the proxy cut it before it had sent its bytes (read_body passed while sending)
                cuts[i] = Cut(-1.0, "cut while sending")
                return
            finally:
                _wait(ready)
            got = b""
            try:
                while data := s.recv(4096):
                    got += data
            except TimeoutError:  # the proxy never ended it: not a cut
                cuts[i] = Cut(-1.0, "timed out")
                return
            except OSError:
                pass
            status = got.split(b"\r\n", 1)[0].decode("latin-1") if got else None
            cuts[i] = Cut(round(time.monotonic() - began, 2), status)

    threads = [threading.Thread(target=one, args=(i,), daemon=True) for i in range(uploads)]
    for t in threads:
        t.start()
    if not _wait(ready):
        raise SystemExit(f"the uploads didn't all send their bytes within {WAIT} s")
    print("sent", flush=True)
    deadline = time.monotonic() + WAIT
    for t in threads:
        t.join(max(0.0, deadline - time.monotonic()))
    after = [c.after_start_s for c in cuts]
    statuses = sorted({str(c.status) for c in cuts})
    print(
        json.dumps(
            {"uploads": uploads, "cut_min_s": min(after), "cut_max_s": max(after), "statuses": statuses}
        )
    )


def _wait(barrier: threading.Barrier) -> bool:
    """Wait at `barrier`; False once it has waited `WAIT` (it is then broken for every thread)."""
    try:
        barrier.wait()
    except threading.BrokenBarrierError:
        return False
    return True


def main() -> None:
    match sys.argv[1:]:
        case ["ris", records, size, out]:
            print(ris(Path(records), int(size), Path(out)))
        case ["stall", port, cacert, target, declared, sent, uploads, *method] if len(method) <= 1:
            length = None if declared == "chunked" else int(declared)
            stall(int(port), cacert, target, length, int(sent), int(uploads), *method)
        case _:
            raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
