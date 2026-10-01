#!/usr/bin/env bash
# Case table for cmdparse.GIT_LONG_OPTS (.claude/hooks/lib/cmdparse.py): for every subcommand it lists, the
# installed git's `git <sub> --git-completion-helper-all` is compared with the table. Drift either way is a
# NOTE, never a failure, so the check holds on any git version (CI's runner keeps getting newer gits):
# - an option this git has and the table lacks can't open a bypass: `_long_option` expands an abbreviation only
#   when it is unique in the table, and every option a gate checks is in the table, so an abbreviation git
#   reads as a gated option the hook reads as that option or as ambiguous (FailClosed); one git reads as the
#   new option the hook leaves alone or reads as another (over-blocking at worst). Add it to keep reads exact.
# - an option the table has and this git lacks (an older git) only makes an abbreviation fail closed.
# That argument rests on one premise, which IS checked and fails: every long option a gate hook names (a
# `--option` literal in .claude/hooks/*.sh) that this git lists for a tabled subcommand is in that table. A git
# without the helper passes with a note. Usage: ./test-git-long-opts.sh
set -u
# Never inherit a repo from the caller (git exports GIT_DIR etc. to hooks such as pre-push).
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
LIB="$(cd "$(dirname "$0")/../../hooks/lib" && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git init -q "$TMP/r"   # some helpers (stash) need a repository
python3 - "$LIB" "$TMP/r" <<'PY'
import pathlib, re, subprocess, sys
sys.path.insert(0, sys.argv[1])
from cmdparse import GIT_LONG_OPTS

# the long options the gates name: a `--option` literal anywhere in a hook script
hooks = pathlib.Path(sys.argv[1]).parent
gated = {m for f in hooks.glob("*.sh") for m in re.findall(r"--([a-z][a-z0-9-]+)", f.read_text())}

passed = failed = 0
for key, table in sorted(GIT_LONG_OPTS.items()):
    r = subprocess.run(["git", *key.split(), "--git-completion-helper-all"], cwd=sys.argv[2],
                       capture_output=True, text=True)
    words = r.stdout.split() if r.returncode == 0 else []
    listed = {w[2:].rstrip("=") for w in words if w.startswith("--") and len(w) > 2}
    if not listed:
        print(f"  note git {key}: this git has no --git-completion-helper-all; not checked")
        passed += 1
        continue
    missing, extra = sorted(listed - table), sorted(table - listed)
    if extra:
        print(f"  note git {key}: the table has options this git lacks (a newer git's?): {' '.join(extra)}")
    unread = sorted(set(missing) & gated)
    if unread:  # the premise broken: a gated option this git abbreviates and the hook can't expand
        failed += 1
        print(f"  FAIL git {key}: a gate names options GIT_LONG_OPTS lacks: {' '.join('--' + m for m in unread)}")
        continue
    if missing:  # drift, never a bypass (the header): noted so the table can follow
        passed += 1
        print(f"  note git {key}: this git has options GIT_LONG_OPTS lacks (add them): "
              f"{' '.join('--' + m for m in missing)}")
    else:
        passed += 1
        print(f"  ok   git {key}: every long option is in GIT_LONG_OPTS")
print(f"passed: {passed}  failed: {failed}")
sys.exit(1 if failed else 0)
PY
