#!/usr/bin/env bash
# PreToolUse(Write|Edit|MultiEdit|NotebookEdit|Bash) guard for the repo's data/ (specs 01 §Snapshot, 03 §Versioning).
#
# - Snapshots (data/snapshots/) and indexes (data/indexes/) are IMMUTABLE: a search record's
#   reproducibility claim is only as good as the bytes under its index_version. Build a new one
#   (`op snapshot build`, `op index build`); never edit, overwrite, move or delete an existing one.
#   Blocked: editor writes into them; and in Bash, rm/mv/cp/tee/dd/rsync/truncate/shred/find -delete/
#   sed -i/--in-place and >/>> redirects that target them — or that target data/, data/snapshots or
#   data/indexes themselves (`rm -rf data` destroys every snapshot).
# - data/ is gitignored and never committed (corpus licensing is unresolved; spec 00). `git add -f` of
#   anything under the repo-root data/ is refused.
# Paths are resolved against the repo root, so frontend/src/data/… is unaffected. Exit 2 blocks.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
input=$(cat)
HOOK_INPUT="$input" python3 - "$HOOK_DIR" <<'PY'
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
from cmdparse import ParseError, git_subcommand, read_payload, redirect_targets, repo_root, simple_commands

try:
    payload = json.loads(os.environ.get("HOOK_INPUT") or "{}")
except Exception:
    payload = {}
tool = payload.get("tool_name", "")
ti = payload.get("tool_input") or {}
cwd = payload.get("cwd") or os.getcwd()

def rel(path, base):
    """Path relative to the repo root that contains `base`, with forward slashes; None if outside."""
    root = os.path.realpath(repo_root(base))
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(base, path))
    r = os.path.relpath(full, root).replace("\\", "/")
    return None if r.startswith("..") else r

def inside_immutable(r):
    return r is not None and (r.startswith("data/snapshots/") or r.startswith("data/indexes/"))

def is_or_contains_immutable(r):
    return r is not None and (inside_immutable(r) or r in ("data", "data/snapshots", "data/indexes"))

def refuse(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)

IMMUTABLE_MSG = "Blocked: data/snapshots/ and data/indexes/ are immutable (reproducibility, spec 03). Build a new one with `op snapshot build` / `op index build` instead."

if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if path and inside_immutable(rel(path, os.path.dirname(path) if os.path.isabs(path) else cwd)):
        refuse(IMMUTABLE_MSG)
    sys.exit(0)

cmd, cwd = read_payload()
if "data" not in cmd:
    sys.exit(0)
try:
    commands = list(simple_commands(cmd, cwd))
    redirects = list(redirect_targets(cmd, cwd))
except ParseError:
    sys.exit(0)
for op, target, d in redirects:
    if ">" in op and inside_immutable(rel(target, d)):
        refuse(IMMUTABLE_MSG)

DESTROY = {"rm", "shred", "truncate", "rmdir"}          # every path arg is a target
DEST_LAST = {"cp", "rsync", "install", "ln"}          # last path arg is the target
for argv, d in commands:
    if not argv:
        continue
    head, args = argv[0], argv[1:]
    paths = [a for a in args if not a.startswith("-")]
    g = git_subcommand(argv, d)
    if g and g[0] == "add":
        a = g[1]
        forced = any(x in ("-f", "--force") or (x.startswith("-") and not x.startswith("--") and "f" in x) for x in a)
        if forced and any((r := rel(p, g[2])) is not None and (r == "data" or r.startswith("data/")) for p in a if not p.startswith("-")):
            refuse("Blocked: data/ is never committed (corpus licensing unresolved; spec 00). Don't force-add it.")
        continue
    if head in DESTROY and any(is_or_contains_immutable(rel(p, d)) for p in paths):
        refuse(IMMUTABLE_MSG + " To retire an old version use `op index retire <index_version>` (it refuses while a search record pins it).")
    if head == "mv" and paths and (any(is_or_contains_immutable(rel(p, d)) for p in paths[:-1]) or inside_immutable(rel(paths[-1], d))):
        refuse(IMMUTABLE_MSG)
    if head in DEST_LAST and paths and inside_immutable(rel(paths[-1], d)):
        refuse(IMMUTABLE_MSG)
    if head == "tee" and any(inside_immutable(rel(p, d)) for p in paths):
        refuse(IMMUTABLE_MSG)
    if head == "dd" and any(a.startswith("of=") and inside_immutable(rel(a[3:], d)) for a in args):
        refuse(IMMUTABLE_MSG)
    if head == "find" and ("-delete" in args or "-exec" in args or "-execdir" in args) and paths and is_or_contains_immutable(rel(paths[0], d)):
        refuse(IMMUTABLE_MSG)
    if head == "sed" and any(a.startswith("-i") or a.startswith("--in-place") for a in args) and any(inside_immutable(rel(p, d)) for p in paths):
        refuse(IMMUTABLE_MSG)
sys.exit(0)
PY
