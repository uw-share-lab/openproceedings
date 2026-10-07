"""Shared helpers for the /dependabot-review scripts (TASK-211, spec 08 §CI "Dependabot").

Every outside call goes through a subprocess (`git`, `curl`, `npm`, `gh`), so the case table
`.claude/scripts/tests/test-dependabot.sh` can put fakes on PATH and no test reaches a live service.
Each checker prints one line per finding, `ok      …`, `FIX     …` (the routine repairs it in the PR) or
`PROBLEM …` (the PR stays open for the owner), then a summary. Exit status: 0 clean; 1 at least one PROBLEM;
2 the check itself could not run (a tool or the network failed: the PR also stays open, and the run log says
why); 3 only FIX findings (fix them, commit, and run the check again).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

TIMEOUT = 120  # seconds for one outside call


class ToolError(Exception):
    """A tool or service call failed: the check could not be completed."""


def run(cmd: list[str], *, ok_codes: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    """Run a command (never through a shell). Raises ToolError on a missing tool, a timeout or a bad exit."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, check=False)
    except FileNotFoundError as e:
        raise ToolError(f"{cmd[0]} is not installed") from e
    except subprocess.TimeoutExpired as e:
        raise ToolError(f"{' '.join(cmd[:3])} timed out after {TIMEOUT}s") from e
    if r.returncode not in ok_codes:
        raise ToolError(f"{' '.join(cmd[:4])} exited {r.returncode}: {r.stderr.strip()[:300]}")
    return r


def run_json(cmd: list[str]) -> Any:
    out = run(cmd).stdout
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise ToolError(f"{' '.join(cmd[:4])} did not print JSON") from e


def git_show(ref: str, path: str) -> str | None:
    """The file at `ref`, or None when it doesn't exist there."""
    r = run(["git", "show", f"{ref}:{path}"], ok_codes=(0, 128))
    return r.stdout if r.returncode == 0 else None


def resolve_refs(base: str | None, head: str) -> tuple[str, str]:
    """`base` defaults to the merge base of origin/dev and `head`, so a branch behind dev shows only its own diff."""
    if base is None:
        base = run(["git", "merge-base", "origin/dev", head]).stdout.strip()
    return base, head


def changed_files(base: str, head: str) -> list[str]:
    return run(["git", "diff", "--name-only", f"{base}..{head}"]).stdout.split()


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as e:
            raise ToolError(f"HTTP {self.status}: response is not JSON") from e


def http(url: str, headers: dict[str, str] | None = None, *, head: bool = False) -> Response:
    """One HTTPS request through curl (https only, no redirects to other schemes, a time limit)."""
    if not url.startswith("https://"):
        raise ToolError(f"refusing a non-https URL: {url}")
    with tempfile.TemporaryDirectory(prefix="op-depbot-") as d:
        hdr, body = Path(d) / "headers", Path(d) / "body"
        cmd = ["curl", "-sS", "--proto", "=https", "--max-time", "60", "-D", str(hdr), "-o", str(body)]
        cmd += ["-w", "%{http_code}"]
        if head:
            cmd.append("-I")
        for k, v in (headers or {}).items():
            cmd += ["-H", f"{k}: {v}"]
        cmd.append(url)
        status_text = run(cmd).stdout.strip()
        if not status_text.isdigit():
            raise ToolError(f"curl printed no status for {url}")
        raw = hdr.read_text(errors="replace") if hdr.exists() else ""
        data = body.read_bytes() if body.exists() else b""
    # the last header block is the final response's
    block = [b for b in re.split(r"\r?\n\r?\n", raw.strip()) if b][-1:] or [""]
    parsed: dict[str, str] = {}
    for line in block[0].splitlines()[1:]:
        k, sep, v = line.partition(":")
        if sep:
            parsed[k.strip().lower()] = v.strip()
    return Response(int(status_text), parsed, data)


def http_json(url: str, headers: dict[str, str] | None = None) -> Any:
    r = http(url, headers)
    if r.status != 200:
        raise ToolError(f"GET {url}: HTTP {r.status}")
    return r.json()


_NUM = re.compile(r"\d+")


def version_tuple(v: str) -> tuple[int, ...]:
    """The leading numeric components: `16.3.8` → (16, 3, 8), `3.12.15-slim-bookworm` → (3, 12, 15)."""
    head = re.match(r"v?(\d+(?:\.\d+)*)", v)
    return tuple(int(n) for n in _NUM.findall(head.group(1))) if head else ()


def is_major(old: str, new: str) -> bool:
    """A semver-major change: the first numeric component differs (or one side has none)."""
    o, n = version_tuple(old), version_tuple(new)
    return not o or not n or o[0] != n[0]


def is_minor_or_more(old: str, new: str) -> bool:
    o, n = version_tuple(old), version_tuple(new)
    return is_major(old, new) or o[:2] != n[:2]


@dataclass
class Report:
    """Collects findings and prints them; `finish` exits with the status the module docstring gives."""

    title: str
    problems: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)

    def ok(self, msg: str) -> None:
        print(f"ok      {msg}", flush=True)

    def problem(self, msg: str) -> None:
        self.problems.append(msg)
        print(f"PROBLEM {msg}", flush=True)

    def fix(self, msg: str) -> None:
        """A finding the routine repairs in the PR itself, then runs the check again."""
        self.fixes.append(msg)
        print(f"FIX     {msg}", flush=True)

    def finish(self) -> NoReturn:
        n, f = len(self.problems), len(self.fixes)
        if n:
            print(f"{self.title}: {n} problem(s), {f} to fix — leave the PR open for the owner")
            sys.exit(1)
        if f:
            print(f"{self.title}: {f} to fix — fix them in the PR, commit, and run this check again")
            sys.exit(3)
        print(f"{self.title}: 0 problems")
        sys.exit(0)


def main_guard(fn: Any) -> NoReturn:
    """Run a checker's main; a ToolError exits 2 with its message, so a failed check never reads as a pass."""
    try:
        fn()
    except ToolError as e:
        print(f"ERROR   {e} — the check did not complete; leave the PR open", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)
