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
# - backlog/ is CLI-managed (task-hygiene skill): only the `backlog` CLI moves a task (e.g. `backlog task
#   complete` into backlog/completed/). Bash mv / git mv / cp / rm / tee / redirects that target files
#   under backlog/ are refused here; enforce-backlog-cli.sh covers editor writes.
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

def glob_base(path):
    """A glob stays literal in the command string, so `rm -rf data/*` must be judged by the directory the
    glob expands inside (`data`) — review round 2 found it wiping every snapshot."""
    for i, ch in enumerate(path):
        if ch in "*?[":
            return os.path.dirname(path[:i]) or "."
    return path

def rel(path, base):
    """Path relative to the repo root that contains `base`, with forward slashes; None if outside."""
    path = glob_base(path)
    root = os.path.realpath(repo_root(base))
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(base, path))
    r = os.path.relpath(full, root).replace("\\", "/")
    return None if r.startswith("..") else r

def inside_immutable(r):
    return r is not None and (r.startswith("data/snapshots/") or r.startswith("data/indexes/"))

def is_or_contains_immutable(r):
    return r is not None and (inside_immutable(r) or r in ("data", "data/snapshots", "data/indexes"))

def in_backlog(r):
    return r is not None and (r == "backlog" or r.startswith("backlog/"))

BACKLOG_MSG = ("Blocked: backlog/ files are CLI-managed — don't move, copy or delete them from the shell. "
               "Use the backlog CLI (e.g. `backlog task complete <id>` moves a Done task to backlog/completed/).")

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
# Fast exit only when nothing in the command could touch data/ or backlog/. `git clean`/`git stash` never
# name data/ but remove it (it is gitignored), so they must reach the checks below.
if not any(k in cmd for k in ("data", "backlog", "clean", "stash")):
    sys.exit(0)
try:
    commands = list(simple_commands(cmd, cwd))
    redirects = list(redirect_targets(cmd, cwd))
except ParseError:
    sys.exit(0)
for op, target, d in redirects:
    if ">" in op and inside_immutable(rel(target, d)):
        refuse(IMMUTABLE_MSG)
    if ">" in op and in_backlog(rel(target, d)):
        refuse(BACKLOG_MSG)

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
    gm = git_subcommand(argv, d)
    if gm and gm[0] == "clean":
        flags = [a for a in gm[1] if a.startswith("-")]
        dry = any(a in ("-n", "--dry-run") or (not a.startswith("--") and "n" in a) for a in flags)
        ignored = any(a in ("-x", "-X") or (not a.startswith("--") and ("x" in a or "X" in a)) for a in flags)
        if ignored and not dry:
            refuse("Blocked: `git clean -x/-X` deletes gitignored files — that is all of data/ (snapshots, indexes, "
                   "search records). Clean specific paths, or add -e data to exclude it.")
    if gm and gm[0] == "stash" and any(a in ("-a", "--all") for a in gm[1]):
        refuse("Blocked: `git stash --all` stashes (and removes) gitignored files, including data/.")
    if gm and gm[0] in ("mv", "rm") and any(in_backlog(rel(p, gm[2])) for p in gm[1] if not p.startswith("-")):
        refuse(BACKLOG_MSG)
    if head in DESTROY | {"mv", "tee"} | DEST_LAST and any(in_backlog(rel(p, d)) for p in paths):
        refuse(BACKLOG_MSG)
    if head in DESTROY and any(is_or_contains_immutable(rel(p, d)) for p in paths):
        refuse(IMMUTABLE_MSG + " To retire an old version use `op index retire <index_version>` (it refuses while a search record pins it).")
    if head == "mv" and paths and (any(is_or_contains_immutable(rel(p, d)) for p in paths[:-1]) or inside_immutable(rel(paths[-1], d))):
        refuse(IMMUTABLE_MSG)
    if head in DEST_LAST and paths and is_or_contains_immutable(rel(paths[-1], d)):
        refuse(IMMUTABLE_MSG)
    if head == "tee" and any(inside_immutable(rel(p, d)) for p in paths):
        refuse(IMMUTABLE_MSG)
    if head == "dd" and any(a.startswith("of=") and inside_immutable(rel(a[3:], d)) for a in args):
        refuse(IMMUTABLE_MSG)
    if head == "find" and ("-delete" in args or "-exec" in args or "-execdir" in args) and paths and is_or_contains_immutable(rel(paths[0], d)):
        refuse(IMMUTABLE_MSG)
    in_place = any(a.startswith("--in-place") or (a.startswith("-") and not a.startswith("--") and "i" in a) for a in args)
    if head == "sed" and in_place and any(inside_immutable(rel(p, d)) for p in paths):
        refuse(IMMUTABLE_MSG)
sys.exit(0)
PY
