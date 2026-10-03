#!/usr/bin/env python3
"""Feed one probe to a hook, or to cmdparse, as data: no shell ever runs it (TASK-169).

    python3 .claude/scripts/probe_hook.py <hook> --file probe.txt [--cwd DIR]   # a probe written with the Write tool
    python3 .claude/scripts/probe_hook.py <hook> --command 'git pu…' [--cwd DIR]
    python3 .claude/scripts/probe_hook.py cmdparse --file probe.txt [--cwd DIR]  # how the gates read it
    python3 .claude/scripts/probe_hook.py sandbox --file probe.txt               # what bash does with it

<hook> is a file name in .claude/hooks/ (`require-review.sh`). The probe is the Bash tool's `command`: this
builds the hook's JSON payload in Python and hands it to the hook on stdin, exactly as Claude Code does, then
prints the verdict (allow: exit 0; block: exit 2; anything else is a crash, which Claude Code lets through) and
what the hook wrote to stderr. `cmdparse` prints each simple command the shared walk reads (argv, directory,
redirects), in both readings (HOME/TMPDIR/USER from the environment and as ''), or the ParseError, and the text
with its line continuations joined (`join_continuations`). Neither runs the probe.

`sandbox` runs it for real, for the one question a parser can't answer (what bash makes of it): in a fresh
mktemp directory that is also HOME and TMPDIR, with only PATH kept, removed afterwards. An absolute path in the
probe still reaches the real filesystem, so read the probe before you run it. Never put a probe in a shell
heredoc or a double-quoted shell string: a heredoc that closes early runs every later line (2026-10-02: a probe's
own `rm -rf data` ran in the home folder), and bash runs a `$(…)` or backquote in double quotes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"


def hook_verdict(hook: str, command: str, cwd: str) -> int:
    path = HOOKS / hook
    if path.parent != HOOKS or not path.is_file():
        print(f"no hook named {hook!r} in {HOOKS}", file=sys.stderr)
        return 64
    payload = json.dumps({"tool_name": "Bash", "cwd": cwd, "tool_input": {"command": command}})
    r = subprocess.run([str(path)], input=payload, capture_output=True, text=True, cwd=cwd)
    verdict = {0: "allow", 2: "block"}.get(r.returncode, f"crash (exit {r.returncode})")
    print(f"{hook}: {verdict}")
    if r.stderr:
        print(r.stderr, end="" if r.stderr.endswith("\n") else "\n")
    return 0


def parse(command: str, cwd: str) -> int:
    sys.path.insert(0, str(HOOKS / "lib"))
    import cmdparse

    print(f"joined: {cmdparse.join_continuations(command)!r}")
    for env_empty in (False, True):
        print("walk, HOME/TMPDIR/USER " + ("read as '':" if env_empty else "from the environment:"))
        try:
            for argv, d, redirects in cmdparse.walk(command, cwd, env_empty):
                print(f"  {list(argv)!r} in {d!r}" + (f" redirects {redirects!r}" if redirects else ""))
        except cmdparse.ParseError as exc:
            print(f"  {type(exc).__name__}: {exc}")
    return 0


def sandbox(command: str) -> int:
    box = tempfile.mkdtemp(prefix="op-probe-")
    try:
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": box, "TMPDIR": box}
        r = subprocess.run(
            ["bash", "-c", command], cwd=box, env=env, capture_output=True, text=True, timeout=30
        )
        print(f"exit {r.returncode} (in {box}, removed)")
        print(f"stdout: {r.stdout!r}\nstderr: {r.stderr!r}")
        return 0
    finally:
        shutil.rmtree(box, ignore_errors=True)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="a hook file name, `cmdparse`, or `sandbox`")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="read the probe from this file (its whole text, as written)")
    src.add_argument("--command", help="the probe itself, as one argument")
    ap.add_argument("--cwd", default=os.getcwd(), help="the payload's cwd (default: this directory)")
    a = ap.parse_args(argv)
    command = Path(a.file).read_text(encoding="utf-8") if a.file is not None else a.command
    if a.target == "cmdparse":
        return parse(command, a.cwd)
    if a.target == "sandbox":
        return sandbox(command)
    return hook_verdict(a.target, command, a.cwd)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
