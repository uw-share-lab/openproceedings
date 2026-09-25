#!/usr/bin/env bash
# Never inherit a repo from the caller: git exports GIT_DIR etc. to hooks (e.g. pre-push from a worktree),
# which would point this table's throwaway git calls at the real repository.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
set -u

# Case table for enforce-backlog-cli.sh — the hook that gates WRITES to Backlog.md-managed files.
#
# Two things here are subtle enough to be worth pinning:
#   1. The decisions/ carve-out is Edit-only. `backlog decision` exposes only `create`, so a decision's
#      Context/Decision/Consequences body has no other author than a hand-Edit — but the FILE must still be
#      CLI-created so it gets id/date/status frontmatter. Write -> blocked, Edit/MultiEdit -> allowed.
#   2. The hook FAILS CLOSED, but only for payloads that mention a backlog path. It runs on every Write/Edit
#      in the repo, so a python3 outage must not block unrelated edits.
#
# Run after touching the hook, then re-sync the mirrors: scripts/sync-codex-mirror.sh
#
# Resolve beside this test so each mirror exercises its own hook implementation.
HOOK_DIR=$(cd "$(dirname "$0")/.." && pwd)
HOOK="$HOOK_DIR/enforce-backlog-cli.sh"
failures=0
checks=0

# The repo path contains a space and an '&' — exercise that, since it has broken hooks before.
REPO='/Users/x/school/R&D Lab/openproceedings'

payload() { # tool, file_path -> tool-call JSON
  python3 -c 'import json,sys; print(json.dumps({"tool_name": sys.argv[1], "tool_input": {"file_path": sys.argv[2]}}))' "$1" "$2"
}

check() { # name, expected_rc, input
  local name="$1" want="$2" input="$3" rc
  checks=$((checks + 1))
  printf "%s" "$input" | "$HOOK" >/dev/null 2>&1
  rc=$?
  if [[ $rc -eq $want ]]; then
    printf "  ok   %-62s -> %s\n" "$name" "$([ "$want" -eq 0 ] && echo allow || echo block)"
  else
    printf "  FAIL %-62s (rc=%s, wanted %s)\n" "$name" "$rc" "$want"
    failures=$((failures + 1))
  fi
}

echo "enforce-backlog-cli.sh"

# --- CLI-managed trees: every tool is blocked ---
for dir in tasks drafts docs milestones completed archive; do
  check "Write $dir/"  2 "$(payload Write "$REPO/backlog/$dir/task-001 - x.md")"
  check "Edit  $dir/"  2 "$(payload Edit  "$REPO/backlog/$dir/task-001 - x.md")"
done

# --- CLI-owned state files (not under a subdir) ---
check "Write backlog/config.yml"   2 "$(payload Write "$REPO/backlog/config.yml")"
check "Edit  backlog/config.yml"   2 "$(payload Edit  "$REPO/backlog/config.yml")"
check "Edit  backlog/Backlog.md"   2 "$(payload Edit  "$REPO/backlog/Backlog.md")"

# --- decisions/: the carve-out. Write blocked, Edit/MultiEdit allowed. ---
check "Write decisions/ (must be CLI-created)" 2 "$(payload Write     "$REPO/backlog/decisions/decision-009 - x.md")"
check "Edit  decisions/ (body has no other author)" 0 "$(payload Edit      "$REPO/backlog/decisions/decision-009 - x.md")"
check "MultiEdit decisions/"                   0 "$(payload MultiEdit "$REPO/backlog/decisions/decision-009 - x.md")"

# --- every backlog scope, root and any nested one ---
check "root backlog/tasks/"          2 "$(payload Edit "$REPO/backlog/tasks/task-006 - x.md")"
check "nested backend backlog/tasks/" 2 "$(payload Edit "$REPO/backend/backlog/tasks/task-009 - x.md")"
check "nested frontend backlog/tasks/" 2 "$(payload Edit "$REPO/frontend/backlog/tasks/task-008 - x.md")"

# --- ordinary files are untouched (this hook runs on EVERY Write/Edit) ---
check "ordinary source file"            0 "$(payload Edit  "$REPO/backend/src/openproceedings/query/parser.py")"
check "ordinary doc"                    0 "$(payload Write "$REPO/README.md")"
check "path merely containing 'backlog'" 0 "$(payload Edit "$REPO/docs/backlog-notes.md")"

# --- fail-closed behaviour ---
check "malformed JSON mentioning backlog/" 2 '{"tool_name":"Edit","tool_input":{"file_path":"/x/backlog/tasks/a.md"'
check "malformed JSON, no backlog path"    0 '{"tool_name":"Edit","tool_input":{"file_path":"/x/src/a.py"'
check "empty payload"                      0 ''

# --- $path/$tool/$parsed must not leak in from the environment on a parse failure ---
# `parsed=1` MUST be exported too, or this test is vacuous: without it the hook exits at the fail-closed
# branch and never evaluates `case "$path"`, so it returns 0 whether or not the guard exists. Verified by
# mutation — deleting the path=''/tool=''/parsed='' init makes this case return 2 (the leaked backlog path
# is matched) while the real hook returns 0.
checks=$((checks + 1))
rc=$(printf '%s' '{"tool_name":"Edit","tool_input":{"file_path":"/x/src/a.py"' \
     | env path="$REPO/backlog/tasks/x.md" tool=Edit parsed=1 "$HOOK" >/dev/null 2>&1; echo $?)
if [[ $rc -eq 0 ]]; then
  printf "  ok   %-62s -> allow\n" "env \$path/\$tool/\$parsed don't leak in"
else
  printf "  FAIL %-62s (rc=%s, wanted 0)\n" "env \$path/\$tool/\$parsed don't leak in" "$rc"
  failures=$((failures + 1))
fi

echo
echo "passed: $((checks - failures))  failed: $failures"
[[ $failures -eq 0 ]] || exit 1
