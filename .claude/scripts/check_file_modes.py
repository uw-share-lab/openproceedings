#!/usr/bin/env python3
"""CI check (TASK-241): every tracked file `scripts/setup-dev.sh` makes executable is committed 100755.

The setup script runs `chmod +x <glob>...` once per clone. A tracked file in one of those globs committed 100644
gets its mode flipped on disk, so a fresh clone's `git status` shows a mode change, and `record-review.py`
refuses the dirty tree. This reads every `chmod` in the script and checks each glob against git's index.
It fails closed: a `chmod` written in any form but `chmod +x <literal glob>...` is refused, and so is a glob
that matches no tracked file (bash would hand it to chmod as written, which fails under `set -e`). Globs are
matched as bash matches them: `*`, `?` and `[...]` within one path segment, and no leading dot unless the
pattern names one. Exits 1 listing every problem."""

from __future__ import annotations

import fnmatch
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETUP = "scripts/setup-dev.sh"
OPERATORS = {";", "&&", "||", "|", "&", "(", ")", ";;"}


def chmod_globs(text: str) -> tuple[list[str], list[str]]:
    """Each glob a `chmod +x` in the script names, and the problems: a chmod it can't read."""
    globs: list[str] = []
    problems: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        lex = shlex.shlex(line, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        try:
            words = list(lex)
        except ValueError as e:
            if "chmod" in line:
                problems.append(f"{SETUP}:{n}: can't read a line with chmod in it ({e})")
            continue
        if "chmod" in line.split("#", 1)[0] and "chmod" not in words:
            problems.append(f"{SETUP}:{n}: chmod in a form this check can't read")
        for i, w in enumerate(words):
            if w != "chmod":
                continue
            args: list[str] = []
            for a in words[i + 1 :]:
                if a in OPERATORS:
                    break
                args.append(a)
            if not args or args[0] != "+x" or len(args) < 2:
                problems.append(
                    f"{SETUP}:{n}: only `chmod +x <glob>...` is checked; found chmod {' '.join(args)}"
                )
                continue
            for g in args[1:]:
                if g.startswith("-") or "$" in g or "`" in g or "{" in g or g.startswith("/"):
                    problems.append(f"{SETUP}:{n}: chmod +x {g}: not a literal repo-relative glob")
                else:
                    globs.append(g)
    return globs, problems


def matches(path: str, glob: str) -> bool:
    """bash's pathname expansion: segment by segment, a leading dot matched only by a literal one."""
    p, g = path.split("/"), glob.split("/")
    if len(p) != len(g):
        return False
    for name, pat in zip(p, g, strict=True):
        if name.startswith(".") and not pat.startswith("."):
            return False
        if not fnmatch.fnmatchcase(name, pat):
            return False
    return True


def index_modes(root: Path) -> dict[str, str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-s", "-z"], capture_output=True, text=True, check=True
    ).stdout
    modes: dict[str, str] = {}
    for entry in filter(None, out.split("\0")):
        meta, path = entry.split("\t", 1)
        modes[path] = meta.split()[0]
    return modes


def main() -> None:
    setup = ROOT / SETUP
    globs, problems = chmod_globs(setup.read_text(encoding="utf-8")) if setup.exists() else ([], [])
    modes = index_modes(ROOT)
    checked = 0
    for g in globs:
        hit = sorted(p for p in modes if matches(p, g))
        if not hit:
            problems.append(f"{SETUP}: chmod +x {g} matches no tracked file")
        for p in hit:
            checked += 1
            if modes[p] != "100755":
                problems.append(
                    f"{p}: committed {modes[p]}, but {SETUP} makes it executable (git add --chmod=+x)"
                )
    for e in problems:
        print(f"✗ {e}", file=sys.stderr)
    print(f"file modes: {checked} files from {len(globs)} chmod globs · {len(problems)} errors")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
