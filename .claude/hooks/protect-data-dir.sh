#!/usr/bin/env bash
# PreToolUse(Write|Edit|MultiEdit|Bash) guard for data/ (docs/specs/01 §Snapshot, 03 §Versioning).
#
# - Snapshots (data/snapshots/) and indexes (data/indexes/) are IMMUTABLE: a search record's
#   reproducibility claim is only as good as the bytes under its index_version. Tools must build a new
#   one (`op snapshot build`, `op index build`), never edit an existing one.
# - data/ is gitignored and never committed (corpus licensing is unresolved; see 00 §Open questions).
#   `git add -f`/`--force` of anything under data/ is refused.
# Exit 2 blocks.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
input=$(cat)
HOOK_INPUT="$input" python3 - "$HOOK_DIR" <<'PY'
import json, os, re, sys
sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
from cmdparse import ParseError, git_subcommand, read_payload, simple_commands

IMMUTABLE = re.compile(r"(^|/)data/(snapshots|indexes)/")
try:
    payload = json.loads(os.environ.get("HOOK_INPUT") or "{}")
except Exception:
    payload = {}
tool = payload.get("tool_name", "")
ti = payload.get("tool_input") or {}

if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if IMMUTABLE.search(path.replace("\\", "/")):
        print("Blocked: data/snapshots/ and data/indexes/ are immutable (reproducibility, spec 03).", file=sys.stderr)
        print("Build a new one with `op snapshot build` / `op index build` instead of editing this.", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)

cmd, cwd = read_payload()
if "data" not in cmd:
    sys.exit(0)
try:
    commands = list(simple_commands(cmd, cwd))
except ParseError:
    sys.exit(0)
for argv, d in commands:
    g = git_subcommand(argv, d)
    if g and g[0] == "add":
        args = g[1]
        forced = any(a in ("-f", "--force") or (a.startswith("-") and not a.startswith("--") and "f" in a) for a in args)
        if forced and any(re.search(r"(^|/)data(/|$)", a) for a in args if not a.startswith("-")):
            print("Blocked: data/ is never committed (corpus licensing unresolved; spec 00). Don't force-add it.", file=sys.stderr)
            sys.exit(2)
    if argv and argv[0] in ("rm", "mv", "sed", "truncate") and any(IMMUTABLE.search(a) for a in argv[1:]):
        if argv[0] == "sed" and not any(a.startswith("-i") for a in argv):
            continue
        print("Blocked: data/snapshots/ and data/indexes/ are immutable. Retire old versions with `op index prune`.", file=sys.stderr)
        sys.exit(2)
sys.exit(0)
PY
