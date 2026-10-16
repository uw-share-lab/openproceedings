"""Uploads for the deploy smoke test's comparison checks (`deploy/smoke-test.sh --compare`, TASK-183): a RIS file of
an exact size made from a fixture snapshot, and raw uploads to the proxy that stall, so the test can see where
they are cut and what the proxy holds meanwhile. Standard library only; it talks to the stack over TLS on
localhost and nothing else.

    python3 backend/tests/deploy/compare_probe.py ris <records.jsonl> <bytes> <out.ris>
    python3 backend/tests/deploy/compare_probe.py stall <port> <cacert> <path> <declared bytes> <sent> <uploads>

`ris` writes a file of exactly `<bytes>` bytes: one record per fixture paper with an abstract, by title, venue
and year (the first 400), each padded with `N1` note lines (no field the comparison reads) so the file fits
the API's caps (64 lines a record, 32,768 characters a line). Prints its record count.

`stall` opens `<uploads>` connections at once, each a `POST <path>` (query string included) declaring
`<declared bytes>` and sending `<sent>` bytes of body, then stops sending. It prints `sent` once every upload
has sent its bytes (the moment the proxy holds them all), then waits for each connection to end and prints one
JSON line: how many seconds after its last byte the first and last were cut (-1 for one cut while it was still
sending), and the status lines they got, if any.
"""

from __future__ import annotations

import json
import socket
import ssl
import sys
import threading
import time
from pathlib import Path

RECORDS = 400
MAX_LINE = 30_000  # under the API's 32,768-character line cap, tag included
MAX_LINES = 60  # under its 64 lines a record


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
    """`n` bytes of `N1` lines, none over `MAX_LINE`, at most `MAX_LINES` of them."""
    if n == 0:
        return b""
    lines: list[bytes] = []
    while n > 0:
        if n < 8:  # too short for a line of its own: lengthen the last one
            lines[-1] += b"x" * n
            break
        take = min(n, MAX_LINE)
        if 0 < n - take < 8:
            take = n - 8
        lines.append(b"N1  - " + b"x" * (take - 7) + b"\n")
        n -= take
    if len(lines) > MAX_LINES or any(len(line) > MAX_LINE + 8 for line in lines):
        raise SystemExit("padding over the API's line caps: use a smaller file or more records")
    return b"".join(lines)


def stall(port: int, cacert: str, target: str, declared: int, sent: int, uploads: int) -> None:
    context = ssl.create_default_context(cafile=cacert)
    head = (
        f"POST {target} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
        f"Content-Type: application/x-research-info-systems\r\nContent-Length: {declared}\r\n\r\n"
    ).encode()
    line = b"N1  - " + b"x" * 1017 + b"\n"
    results: list[dict[str, object]] = [{} for _ in range(uploads)]
    ready = threading.Barrier(uploads + 1)

    def one(i: int) -> None:
        s = context.wrap_socket(socket.create_connection(("localhost", port)), server_hostname="localhost")
        try:
            s.sendall(head)
            left = sent
            while left > 0:
                s.sendall(line[: min(left, len(line))])
                left -= min(left, len(line))
        except OSError:  # the proxy cut it before it had sent its bytes (read_body passed while sending)
            results[i] = {"cut_after_s": -1.0, "status": "cut while sending"}
            s.close()
            return
        finally:
            ready.wait()
        stopped = time.monotonic()
        s.settimeout(600)
        got = b""
        try:
            while data := s.recv(4096):
                got += data
        except (OSError, ssl.SSLError):
            pass
        results[i] = {
            "cut_after_s": round(time.monotonic() - stopped, 2),
            "status": got.split(b"\r\n", 1)[0].decode("latin-1") if got else None,
        }
        s.close()

    threads = [threading.Thread(target=one, args=(i,)) for i in range(uploads)]
    for t in threads:
        t.start()
    ready.wait()
    print("sent", flush=True)
    for t in threads:
        t.join()
    cuts = [float(str(r["cut_after_s"])) for r in results]
    statuses = sorted({str(r["status"]) for r in results})
    print(
        json.dumps({"uploads": uploads, "cut_min_s": min(cuts), "cut_max_s": max(cuts), "statuses": statuses})
    )


def main() -> None:
    match sys.argv[1:]:
        case ["ris", records, size, out]:
            print(ris(Path(records), int(size), Path(out)))
        case ["stall", port, cacert, target, declared, sent, uploads]:
            stall(int(port), cacert, target, int(declared), int(sent), int(uploads))
        case _:
            raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
