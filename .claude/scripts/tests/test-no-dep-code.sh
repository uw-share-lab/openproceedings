#!/usr/bin/env bash
# Case table for the no-dependency-code marker (decision-048, 2026-10-13): a cloud /dependabot-review run executes
# none of a PR's dependency code, so once `prs.py preflight` has written `op-no-dep-code` in git's common directory
# (its rows are in dependabot_cases.py), the Makefile's dependency targets refuse, scripts/setup-dev.sh skips its
# `uv sync`, and .githooks/pre-push skips its `make lint`. Each row runs the real file in a throwaway repo with
# fake uv, npm, npx and make first on PATH, logging every call. Mutants: .claude/scripts/mutants/gates.json.
set -u
# Never inherit a repo from the caller (git exports GIT_DIR etc. to hooks such as pre-push).
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
SRC="$(cd "$(dirname "$0")/../../.." && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
R="$TMP/r"; LOG="$TMP/calls.log"; BIN="$TMP/bin"
mkdir -p "$BIN"
for tool in uv npm npx make python3; do   # each logs its name and arguments, and succeeds
  printf '#!/bin/sh\necho "%s $*" >> "%s"\n' "$tool" "$LOG" > "$BIN/$tool"; chmod +x "$BIN/$tool"
done
REAL_MAKE=$(command -v make)

fresh() {  # a git repo at $R holding copies of the real files under test, no marker, an empty call log
  rm -rf "$R" && mkdir -p "$R/scripts" "$R/backend" "$R/.githooks" "$R/.claude/hooks/tests" "$R/.claude/scripts/tests" "$R/frontend"
  git init -q "$R"
  cp "$SRC/Makefile" "$R/"; cp "$SRC/scripts/setup-dev.sh" "$R/scripts/"; cp "$SRC/.githooks/pre-push" "$R/.githooks/"
  : > "$R/.claude/hooks/a.sh"; : > "$R/.claude/hooks/tests/a.sh"; : > "$R/.claude/scripts/a.py"   # setup-dev's chmod globs
  : > "$R/.claude/scripts/tests/a.sh"   # make tooling's case-table glob
  printf '{}\n' > "$R/frontend/package.json"; printf '{}\n' > "$R/package-lock.json"; mkdir -p "$R/node_modules"
  : > "$LOG"
}
mark() { : > "$R/.git/op-no-dep-code"; }
# result <label> <condition: a command that succeeds when the row passes>
result() {
  local label="$1"; shift
  if "$@"; then pass=$((pass+1)); printf '  ok   %s\n' "$label"
  else fail=$((fail+1)); printf '  FAIL %s\n       calls: %s\n' "$label" "$(tr '\n' '|' < "$LOG")"; fi
}
logged() { grep -q -- "$1" "$LOG"; }
nothing_ran() { [ ! -s "$LOG" ]; }

echo "== Makefile: the dependency targets refuse while the marker is there"
for target in sync fmt lint test e2e openapi; do
  fresh; mark
  out=$(cd "$R" && PATH="$BIN:$PATH" "$REAL_MAKE" --no-print-directory "$target" 2>&1); rc=$?
  result "make $target refuses with the marker (and runs nothing)" \
    test "$rc" -ne 0 -a -z "$(cat "$LOG")" -a -n "$(printf '%s' "$out" | grep 'refused: .*op-no-dep-code is there')"
done
fresh
out=$(cd "$R" && PATH="$BIN:$PATH" "$REAL_MAKE" --no-print-directory sync 2>&1); rc=$?
result "make sync runs uv sync and npm ci without the marker" test "$rc" -eq 0 -a -n "$(grep 'uv sync --locked' "$LOG")" -a -n "$(grep 'npm ci --ignore-scripts' "$LOG")"
fresh
out=$(cd "$R" && PATH="$BIN:$PATH" "$REAL_MAKE" --no-print-directory test 2>&1); rc=$?
result "make test runs pytest and vitest without the marker" \
  test "$rc" -eq 0 -a -n "$(grep 'uv run --locked pytest' "$LOG")" -a -n "$(grep 'npm test --workspace frontend' "$LOG")"
for target in tooling mutate; do   # the repo's own scripts: they run in a cloud clone (pre-push runs make tooling)
  fresh; mark
  out=$(cd "$R" && PATH="$BIN:$PATH" "$REAL_MAKE" --no-print-directory "$target" 2>&1); rc=$?
  want=$([ "$target" = tooling ] && echo 'python3 .claude/scripts/lint_tooling.py' || echo 'python3 .claude/scripts/mutate.py')
  result "make $target runs with the marker (not refused)" \
    test "$rc" -eq 0 -a -n "$(grep -F "$want" "$LOG")" -a -z "$(printf '%s' "$out" | grep 'refused')"
done
rm -rf "$TMP/nogit"; mkdir -p "$TMP/nogit"; cp "$SRC/Makefile" "$TMP/nogit/"; : > "$LOG"
out=$(cd "$TMP/nogit" && GIT_CEILING_DIRECTORIES="$TMP" PATH="$BIN:$PATH" "$REAL_MAKE" --no-print-directory sync 2>&1); rc=$?
result "make sync outside a git checkout refuses (the marker can't be checked)" \
  test "$rc" -ne 0 -a ! -s "$LOG" -a -n "$(printf '%s' "$out" | grep "refused: git rev-parse failed")"
fresh; mkdir -p "$R/sub"; mark
out=$(cd "$R/sub" && PATH="$BIN:$PATH" "$REAL_MAKE" --no-print-directory -f ../Makefile test 2>&1); rc=$?
result "make test from a subdirectory still refuses" test "$rc" -ne 0 -a ! -s "$LOG" -a -n "$(printf '%s' "$out" | grep 'refused: ')"
fresh; mark; git -C "$R" -c user.email=t@t -c user.name=t commit -q --allow-empty -m i; git -C "$R" worktree add -q "$TMP/wt" 2>/dev/null
cp "$SRC/Makefile" "$TMP/wt/"
out=$(cd "$TMP/wt" && PATH="$BIN:$PATH" "$REAL_MAKE" --no-print-directory test 2>&1); rc=$?
result "make test in a linked worktree refuses (the marker is in the common git directory)" \
  test "$rc" -ne 0 -a ! -s "$LOG" -a -n "$(printf '%s' "$out" | grep 'refused: .*/r/\.git/op-no-dep-code')"
git -C "$R" worktree remove --force "$TMP/wt" 2>/dev/null; rm -rf "$TMP/wt"

echo "== .githooks/pre-push: make lint stands down while the marker is there; make tooling still runs"
fresh; mark
out=$(cd "$R" && PATH="$BIN:$PATH" bash .githooks/pre-push 2>&1); rc=$?
result "pre-push with the marker runs make tooling only" \
  test "$rc" -eq 0 -a "$(grep -c '^make ' "$LOG")" = 1 -a -n "$(grep '^make --no-print-directory tooling' "$LOG")"
result "pre-push with the marker says why lint was skipped" test -n "$(printf '%s' "$out" | grep 'make lint skipped: .*op-no-dep-code is there')"
fresh
out=$(cd "$R" && PATH="$BIN:$PATH" bash .githooks/pre-push 2>&1); rc=$?
result "pre-push without the marker runs make lint and make tooling" \
  test "$rc" -eq 0 -a -n "$(grep '^make --no-print-directory lint' "$LOG")" -a -n "$(grep '^make --no-print-directory tooling' "$LOG")"

# a linked worktree: git's common directory holds the marker, not the worktree's own git directory
linked() {  # fresh repo with the marker, a commit, and a linked worktree at $TMP/wt holding copies of the files
  fresh; mark; git -C "$R" -c user.email=t@t -c user.name=t commit -q --allow-empty -m i
  rm -rf "$TMP/wt"; git -C "$R" worktree add -q "$TMP/wt" 2>/dev/null
  mkdir -p "$TMP/wt/scripts" "$TMP/wt/.githooks" "$TMP/wt/.claude/hooks/tests" "$TMP/wt/.claude/scripts"
  cp "$SRC/scripts/setup-dev.sh" "$TMP/wt/scripts/"; cp "$SRC/.githooks/pre-push" "$TMP/wt/.githooks/"
  : > "$TMP/wt/.claude/hooks/a.sh"; : > "$TMP/wt/.claude/hooks/tests/a.sh"; : > "$TMP/wt/.claude/scripts/a.py"
}
linked
out=$(cd "$TMP/wt" && PATH="$BIN:$PATH" bash .githooks/pre-push 2>&1); rc=$?
result "pre-push in a linked worktree skips make lint" test "$rc" -eq 0 -a -z "$(grep 'make --no-print-directory lint' "$LOG")"
git -C "$R" worktree remove --force "$TMP/wt" 2>/dev/null; rm -rf "$TMP/wt"

fresh; mkdir -p "$TMP/badgit"; printf '#!/bin/sh\nexit 128\n' > "$TMP/badgit/git"; chmod +x "$TMP/badgit/git"
out=$(cd "$R" && PATH="$TMP/badgit:$BIN:$PATH" bash .githooks/pre-push 2>&1); rc=$?
result "pre-push fails, running nothing, when git can't name the git directory" test "$rc" -ne 0 -a ! -s "$LOG"

echo "== scripts/setup-dev.sh: uv sync is skipped while the marker is there"
fresh; mark
out=$(cd "$R" && PATH="$BIN:$PATH" bash scripts/setup-dev.sh 2>&1); rc=$?
result "setup-dev.sh with the marker installs nothing" test "$rc" -eq 0 -a ! -s "$LOG"
result "setup-dev.sh with the marker says it skipped uv sync" test -n "$(printf '%s' "$out" | grep 'skipped uv sync: .*op-no-dep-code is there')"
fresh
out=$(cd "$R" && PATH="$BIN:$PATH" bash scripts/setup-dev.sh 2>&1); rc=$?
result "setup-dev.sh without the marker runs uv sync --locked" test "$rc" -eq 0 -a -n "$(grep '^uv sync --locked' "$LOG")"

linked
out=$(cd "$TMP/wt" && PATH="$BIN:$PATH" bash scripts/setup-dev.sh 2>&1); rc=$?
result "setup-dev.sh in a linked worktree skips uv sync" test "$rc" -eq 0 -a -z "$(grep '^uv ' "$LOG")"
git -C "$R" worktree remove --force "$TMP/wt" 2>/dev/null; rm -rf "$TMP/wt"

echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
