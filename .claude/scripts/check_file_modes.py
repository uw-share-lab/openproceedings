#!/usr/bin/env python3
"""CI check (TASK-241): every tracked file `scripts/setup-dev.sh` makes executable is committed 100755.

The setup script runs `chmod +x <glob>...` once per clone. A tracked file in one of those globs committed 100644
gets its mode flipped on disk, so a fresh clone's `git status` shows a mode change, and `record-review.py`
refuses the dirty tree. This reads every `chmod` in the script and checks each glob against git's index.
It fails closed: a `chmod` written in any form but `chmod +x <literal glob>...` is refused, and so is a glob
that matches no tracked file (bash would hand it to chmod as written, which fails under `set -e`). Globs are
matched as bash matches them: `*`, `?` and `[...]` within one path segment, and no leading dot unless the
pattern names one; a glob whose bash meaning fnmatch doesn't share (`[^...]`, `[[:class:]]` and the other `[[`
forms) is refused. bash's default glob options and the repo root as working directory are assumed, so `shopt`,
`GLOBIGNORE` and any `cd`/`pushd`/`popd` but `cd "$(git rev-parse --show-toplevel)"` are refused. A missing setup
script is an error too, so moving it can't switch the check off. Exits 1 listing every problem."""

from __future__ import annotations

import fnmatch
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETUP = "scripts/setup-dev.sh"
OPERATORS = {";", "&&", "||", "|", "&", "(", ")", ";;"}


def logical_lines(text: str) -> tuple[list[tuple[int, str]], list[str]]:
    """Each line as bash reads it, a backslash-newline joined away (so `ch\\` + `mod` is still chmod), with the
    number of the line it starts on; and the problems: a continued line with a `#` in it, since a comment is
    never continued and this check can't tell a comment from a quoted `#` (that line and the next are each
    still read on their own)."""
    out: list[tuple[int, str]] = []
    problems: list[str] = []
    start, buf = 1, ""
    for n, raw in enumerate(text.split("\n"), 1):
        if not buf:
            start = n
        continued = (len(raw) - len(raw.rstrip("\\"))) % 2 == 1  # an odd run of trailing backslashes
        if continued and "#" in raw:
            problems.append(f"{SETUP}:{n}: a continued line with # in it (comment or not?) can't be read")
        elif continued:
            buf += raw[:-1]
            continue
        out.append((start, buf + raw))
        buf = ""
    if buf:
        out.append((start, buf))
    return out, problems


TOPLEVEL = (
    "$(git rev-parse --show-toplevel)"  # the one directory change allowed: globs resolve from the repo root
)
GLOB_STATE = ("shopt", "GLOBIGNORE")  # these change what bash's globs match


def chmod_globs(text: str) -> tuple[list[str], list[str]]:
    """Each glob a `chmod +x` in the script names, and the problems: a chmod it can't read."""
    globs: list[str] = []
    lines, problems = logical_lines(text)
    for n, line in lines:
        if line.lstrip().startswith("#"):  # a comment line: bash runs none of it
            continue
        lex = shlex.shlex(line, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""  # shlex starts a comment at any `#`, bash only at one that begins a word
        try:
            words = list(lex)
        except ValueError as e:
            if "chmod" in line:
                problems.append(f"{SETUP}:{n}: can't read a line with chmod in it ({e})")
            continue
        # A word that begins with `#` starts a trailing comment, unless the `#` was quoted, which shlex no longer
        # shows; so a chmod after one is refused rather than skipped.
        cut = next((i for i, w in enumerate(words) if w.startswith("#")), len(words))
        code, rest = words[:cut], words[cut:]
        if any("chmod" in w for w in rest):
            problems.append(f"{SETUP}:{n}: chmod after a # (a comment, or a quoted #?) can't be read")
        if any("chmod" in w and w != "chmod" for w in code):
            problems.append(f"{SETUP}:{n}: chmod in a form this check can't read")
        for i, w in enumerate(code):
            if any(x in w for x in GLOB_STATE):
                problems.append(
                    f"{SETUP}:{n}: {w} changes what globs match; this check assumes bash's defaults"
                )
            if w in ("cd", "pushd", "popd") and code[i + 1 : i + 2] != [TOPLEVEL]:
                problems.append(f'{SETUP}:{n}: {w} other than `cd "{TOPLEVEL}"` moves where globs resolve')
            if w != "chmod":
                continue
            args: list[str] = []
            for a in code[i + 1 :]:
                if a in OPERATORS:
                    break
                args.append(a)
            if not args or args[0] != "+x" or len(args) < 2:
                problems.append(
                    f"{SETUP}:{n}: only `chmod +x <glob>...` is checked; found chmod {' '.join(args)}"
                )
                continue
            for g in args[1:]:
                if (
                    g.startswith(("-", "/"))
                    or any(c in g for c in "$`{")
                    or "[^" in g  # bash negates with ^, fnmatch reads it as a literal
                    or "[[" in g  # POSIX [:class:], [.coll.] and [=equiv=], which fnmatch doesn't know
                ):
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
    if not setup.is_file():  # moved or renamed, the check would otherwise guard nothing
        print(f"✗ {SETUP} not found: nothing to check the file modes against", file=sys.stderr)
        sys.exit(1)
    globs, problems = chmod_globs(setup.read_text(encoding="utf-8"))
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
