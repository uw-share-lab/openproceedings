#!/usr/bin/env bash
# Parser probes are Python string data; no probe is executed by a shell.
set -eu
HOOKS="$(cd "$(dirname "$0")/.." && pwd)"
python3 - "$HOOKS" <<'PY'
import ast
import os
from pathlib import Path
import sys

hooks = Path(sys.argv[1])
sys.path.insert(0, str(hooks / "lib"))
from cmdparse import join_continuations

# A later physical delimiter must not hide how the joined delimiter ends the body.
# Quotes after it are command syntax, so their continuations must stay untouched.
cases = [
    ("cat <<EOF\nE\\\nOF\necho 'pu\\\nsh'\nEOF\n", "cat <<EOF\nEOF\necho 'pu\\\nsh'\nEOF\n"),
    ("cat <<-EOF\nx \\\n\tEOF\necho 'pu\\\nsh'\nEOF\n", "cat <<-EOF\nx \\\n\tEOF\necho 'pu\\\nsh'\nEOF\n"),
]
for probe, expected in cases:
    got = join_continuations(probe)
    assert got == expected, (probe, got, expected)
print("passed: joined and tab-stripped delimiters preserve subsequent quote state")

# Exercise the production rel() with git's canonical root spelling and an APFS-style
# realpath spelling deterministically on Linux as well as macOS. No filesystem
# case-folding assumption and no replacement of the comparison under test.
source = (hooks / "protect-data-dir.sh").read_text().split("<<'PY'", 1)[1].split("\n", 1)[1].split("\nPY\n", 1)[0]
tree = ast.parse(source)
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "rel")
namespace = {"os": os, "toplevel": lambda path: "/work/Main"}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(hooks / "protect-data-dir.sh"), "exec"), namespace)
assert namespace["rel"]("/work/MAIN/data/snapshots/s1", "/work/sibling") == "data/snapshots/s1"
assert namespace["rel"]("/work/main-other/data/snapshots/s1", "/work/sibling") is None
print("passed: canonical worktree root comparison folds case and respects the path boundary")
PY
