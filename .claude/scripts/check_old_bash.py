#!/usr/bin/env python3
"""Local check (TASK-267 follow-up): every shell script parses with macOS's stock bash 3.2, not only CI's newer one.

    python3 .claude/scripts/check_old_bash.py [--bash PATH] FILE...   # make tooling passes the Makefile's SHELL_FILES

Bash 3.2 misreads some text a newer bash accepts (a heredoc inside `$(…)` whose body has a `(`; a case pattern's
`)` inside `$(…)`), so a case table can pass in CI and still not parse on a Mac. This runs `<bash> -n` on each file
when `<bash>` (default /bin/bash) is bash 3.x, and exits 1 listing every file that fails. When it is missing or
another version (CI's Linux runner, a Mac with a newer /bin/bash) it prints that it skipped and exits 0: CI's own
bash parses every script when it runs it. A version it can't read is a failure, not a skip."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def major(bash: str) -> str | None:
    """`bash`'s major version (`BASH_VERSINFO[0]`), or None when there is no such program."""
    if not os.path.isfile(bash) or not os.access(bash, os.X_OK):
        return None
    r = subprocess.run([bash, "-c", 'echo "${BASH_VERSINFO[0]}"'], capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bash", default="/bin/bash")
    ap.add_argument("files", nargs="*")
    args = ap.parse_args()
    version = major(args.bash)
    if version is None:
        print(f"check_old_bash: skipped ({args.bash} not found)")
        return 0
    if not version.isdigit():
        print(f"check_old_bash: can't read {args.bash}'s version ({version!r})", file=sys.stderr)
        return 1
    if version != "3":
        print(f"check_old_bash: skipped ({args.bash} is bash {version}, not 3.x)")
        return 0
    bad = []
    for f in args.files:
        r = subprocess.run([args.bash, "-n", f], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            bad.append(f"{f}: {r.stderr.strip()}")
    if bad:
        print(f"check_old_bash: {len(bad)} file(s) don't parse with {args.bash} (bash 3.x):", file=sys.stderr)
        print("\n".join(bad), file=sys.stderr)
        return 1
    print(f"check_old_bash: {len(args.files)} files parse with {args.bash} (bash 3.x)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
