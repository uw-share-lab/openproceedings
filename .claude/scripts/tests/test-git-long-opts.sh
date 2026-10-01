#!/usr/bin/env bash
# Case table for cmdparse.GIT_LONG_OPTS (.claude/hooks/lib/cmdparse.py): for every subcommand it lists, the
# installed git's `git <sub> --git-completion-helper-all` must name no long option the table lacks. git takes
# any unique prefix of a long option, so a missing option can make an abbreviation read as the wrong one
# (`--forc` must be --force). An option the table has and this git lacks (a newer git's) only makes an
# abbreviation fail closed, so it is printed as a note, not a failure. A git without the helper (no output)
# passes with a note. Usage: ./test-git-long-opts.sh
set -u
# Never inherit a repo from the caller (git exports GIT_DIR etc. to hooks such as pre-push).
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
LIB="$(cd "$(dirname "$0")/../../hooks/lib" && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git init -q "$TMP/r"   # some helpers (stash) need a repository
python3 - "$LIB" "$TMP/r" <<'PY'
import subprocess, sys
sys.path.insert(0, sys.argv[1])
from cmdparse import GIT_LONG_OPTS

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
    if missing:
        failed += 1
        print(f"  FAIL git {key}: GIT_LONG_OPTS lacks {' '.join('--' + m for m in missing)}")
    else:
        passed += 1
        print(f"  ok   git {key}: every long option is in GIT_LONG_OPTS")
print(f"passed: {passed}  failed: {failed}")
sys.exit(1 if failed else 0)
PY
