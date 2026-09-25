#!/usr/bin/env bash
# Case table for enforce-pr-workflow.sh. Runs the real hook against a throwaway git repo so the
# branch check exercises real `git rev-parse` rather than a mock. Usage: ./test-enforce-pr-workflow.sh
# Never inherit a repo from the caller: git exports GIT_DIR etc. to hooks (e.g. pre-push from a worktree),
# which would point this table's throwaway git calls at the real repository.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
set -u

HOOK="$(cd "$(dirname "$0")/.." && pwd)/enforce-pr-workflow.sh"
REPO=$(mktemp -d)
WT=""
trap 'git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1; rm -rf "$REPO" "$WT"' EXIT

git -C "$REPO" init -q -b main
git -C "$REPO" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init

pass=0
fail=0

# check <branch> <expected: allow|block> <command>
# Runs the hook with its ambient CWD == $REPO checked out on <branch> and no "cwd" in the JSON
# payload — exercises the plain (non-worktree) path.
check() {
  local on_branch="$1" expect="$2" cmd="$3" got
  git -C "$REPO" checkout -q "$on_branch" 2>/dev/null || git -C "$REPO" checkout -q -b "$on_branch"

  local json
  json=$(python3 -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.argv[1]}}))' "$cmd")

  if (cd "$REPO" && printf '%s' "$json" | "$HOOK" >/dev/null 2>&1); then got=allow; else got=block; fi

  if [ "$got" = "$expect" ]; then
    pass=$((pass + 1))
    printf '  ok   [%s] %-52s -> %s\n' "$on_branch" "$cmd" "$got"
  else
    fail=$((fail + 1))
    printf '  FAIL [%s] %-52s -> %s (want %s)\n' "$on_branch" "$cmd" "$got" "$expect"
  fi
}

# check_cwd <ambient_branch> <json_cwd_dir> <expect> <command>
# Simulates the pinned-subagent scenario: the hook subprocess's ambient CWD is $REPO on
# <ambient_branch>, but the tool call's JSON payload carries its own "cwd" (e.g. a worktree). Also
# exercises `-C`/`cd` overrides embedded directly in <command>, which must win over both.
check_cwd() {
  local ambient_branch="$1" json_cwd="$2" expect="$3" cmd="$4" got
  git -C "$REPO" checkout -q "$ambient_branch" 2>/dev/null || git -C "$REPO" checkout -q -b "$ambient_branch"

  local json
  json=$(python3 -c 'import json,sys; print(json.dumps({"cwd": sys.argv[1], "tool_input":{"command":sys.argv[2]}}))' "$json_cwd" "$cmd")

  if (cd "$REPO" && printf '%s' "$json" | "$HOOK" >/dev/null 2>&1); then got=allow; else got=block; fi

  if [ "$got" = "$expect" ]; then
    pass=$((pass + 1))
    printf '  ok   [ambient=%s cwd=%s] %-40s -> %s\n' "$ambient_branch" "$(basename "$json_cwd")" "$cmd" "$got"
  else
    fail=$((fail + 1))
    printf '  FAIL [ambient=%s cwd=%s] %-40s -> %s (want %s)\n' "$ambient_branch" "$(basename "$json_cwd")" "$cmd" "$got" "$expect"
  fi
}

# check_warn <branch> <command> -- expects allow AND a "Review gate warning" on stderr.
check_warn() {
  local on_branch="$1" cmd="$2" out got warned
  git -C "$REPO" checkout -q "$on_branch" 2>/dev/null || git -C "$REPO" checkout -q -b "$on_branch"

  local json
  json=$(python3 -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.argv[1]}}))' "$cmd")

  out=$(cd "$REPO" && printf '%s' "$json" | "$HOOK" 2>&1); local rc=$?
  [ "$rc" -eq 0 ] && got=allow || got=block
  case "$out" in *"Review gate warning"*) warned=yes ;; *) warned=no ;; esac

  if [ "$got" = "allow" ] && [ "$warned" = "yes" ]; then
    pass=$((pass + 1))
    printf '  ok   [%s] %-52s -> allow+warn\n' "$on_branch" "$cmd"
  else
    fail=$((fail + 1))
    printf '  FAIL [%s] %-52s -> got=%s warned=%s (want allow+warn)\n' "$on_branch" "$cmd" "$got" "$warned"
  fi
}

echo "main is protected:"
check main block 'git commit -m "x"'
check main block 'git push'
check main block 'git push origin main'
check main block 'git merge feature/x'
check main block 'git push -u origin feature/x'

echo "sync carve-out: pull/ff-only-merge on main is allowed, plain merge/push stay blocked:"
check main allow 'git pull'
check main allow 'git pull origin main'
check main allow 'git pull --ff-only'
check main allow 'git merge --ff-only origin/main'
check main block 'git merge feature'
check main block 'git merge --no-ff x'
check main block 'git merge --ff-only --no-ff feat'   # --no-ff overrides --ff-only -> real merge commit
check main block 'git merge --ff-only --ff feat'      # --ff can also produce a merge commit
check main block 'git push'
check main block 'git push origin main'
check main block 'git push --ff-only origin main'   # --ff-only never carves out push
check feature/wip allow 'git pull'
check feature/wip allow 'git merge x'

echo "read-only lookalikes are not merges:"
check main allow 'git merge-base origin/main feature/x'
# shellcheck disable=SC2016  # the $(...) must reach the hook unexpanded — that is the case under test
check main allow 'git diff $(git merge-base main feat) HEAD'
check main allow 'git status'
check main allow 'git log --oneline -3'

echo "deleting a remote feature branch cannot rewrite main:"
check main allow 'git push origin --delete feature/x'
check main allow 'git push -d origin feature/x'
check main allow 'git push origin :feature/x'
check main allow 'git push origin --delete feature/main-fix'

echo "the remote main ref is never writable or deletable, from any branch:"
check main       block 'git push origin --delete main'
check main       block 'git push --delete origin main'
check main       block 'git push origin :main'
check main       block 'git push origin --delete refs/heads/main'
check feature/wip block 'git push origin --delete main'
check feature/wip block 'git push origin +:main'          # force-delete refspec
check feature/wip block 'git push origin HEAD:main'        # write main from a feature branch
check feature/wip block 'git push origin +main:main'
check feature/wip block 'git push origin feature/wip:main --force'
check feature/wip block 'git push --mirror origin'         # mirror can delete main
check feature/wip block 'git push --all origin'            # --all writes remote main

echo "dev is protected too (integration branch in the feature->dev->main flow):"
check dev block 'git commit -m "x"'
check dev block 'git push'
check dev block 'git push origin dev'
check dev block 'git merge feature/x'
check dev block 'git push -u origin feature/x'             # standing on dev, push blocked
check dev allow 'git pull'                                 # sync carve-out applies to dev
check dev allow 'git pull origin dev'
check dev allow 'git merge --ff-only origin/dev'
check dev block 'git merge feature'                        # plain merge on dev -> merge commit
check dev allow 'git status'                               # read-only lookalike
check dev allow 'git push origin --delete feature/x'       # deleting a feature ref is fine from dev

echo "the remote dev ref is never writable or deletable, from any branch:"
check main       block 'git push origin --delete dev'
check main       block 'git push origin :dev'
check feature/wip block 'git push origin HEAD:dev'         # write dev from a feature branch
check feature/wip block 'git push origin +dev:dev'
check feature/wip block 'git push origin --delete refs/heads/dev'

echo "shell wrappers do not launder the command:"
check main block 'bash -c "git push origin main"'
check main block "sh -lc 'git push origin main'"
check main block 'bash -c "git commit -m x"'
check main block 'zsh -ic "git merge feature/x"'
check feature/wip block 'bash -c "git push origin HEAD:main"'
check main block 'bash --norc -c "git push origin main"'   # --norc must not be read as the -c flag
check main block 'bash --rcfile foo -c "git push origin main"'
check main block 'bash --noprofile --norc -c "git push origin main"'
check main block 'zsh --no-rcs -c "git merge x"'
check main block 'bash -cl "git push origin main"'         # -c anywhere in a short cluster
check main block 'bash -cx "git push origin main"'
check main block 'bash -icl "git push origin main"'
check main block 'sh -cx "git commit -m x"'
check main block 'dash -cx "git push origin main"'
check main  allow 'bash -c "git status"'                   # positive control: wrapper != auto-block
# openproceedings round 2 (security review): shapes a whitespace-only split missed
check feature/x block 'if true; then git push origin HEAD:dev; fi'      # reserved words + unspaced ;
check feature/x block 'git push origin HEAD:dev;'                       # trailing ; must not become part of the ref
check feature/x block '/usr/bin/git push origin HEAD:main'              # absolute path to git
check feature/x block 'git status;git push origin HEAD:main'            # unspaced ; between commands
check feature/x block 'git status
git push origin HEAD:main'                                             # newline between commands
check main  block 'timeout 60 git commit -m x'                          # wrapper prefix
check main  block '{ git commit -m x; }'                                # brace group
check main  allow 'bash --norc -c "git status"'            # positive control: long opt + safe cmd
check main  allow 'bash -cx "git status"'                  # positive control: cluster + safe cmd

echo "eval re-parses its argument:"
check main       block 'eval "git push origin main"'
check main       block 'eval "git commit -m x"'
check feature/wip block 'eval "git push origin +:main"'
check main       allow 'eval "git status"'                 # positive control

echo "env / sudo prefixes still expose the git call:"
check main block 'env GIT_PAGER=cat git push origin main'
check main block 'env X=1 git commit -m x'
check main allow 'env X=1 git status'                      # positive control

echo "feature branches are unrestricted (non-main targets):"
check feature/wip allow 'git commit -m "x"'
check feature/wip allow 'git push -u origin feature/wip'
check feature/wip allow 'git push origin HEAD:feature/other'

echo "compound commands are caught:"
check main block 'git add -A && git commit -m "x"'
check main block 'echo hi && git push origin main'
check feature/wip block 'echo hi && git push origin +:main'

# A real worktree, checked out on a feature branch, off the same $REPO — for the pinned-cwd cases.
WT="$(mktemp -u)"
git -C "$REPO" checkout -q main
git -C "$REPO" worktree add -q -b feature/wt-branch "$WT" main >/dev/null 2>&1

echo "worktree-aware branch detection (defect 1 -- pinned subagent cwd):"
# Ambient hook CWD is $REPO on main throughout this block (check_cwd checks it out each call) --
# simulating a subagent pinned to the superproject root.
check_cwd main "$WT"   allow 'git commit -m "x"'                 # JSON cwd = worktree (feature branch)
check_cwd main "$WT"   allow 'git push -u origin feature/wt-branch'
check_cwd main "$REPO" block 'git commit -m "x"'                 # JSON cwd = the repo itself: still main
check_cwd main "$REPO" allow "git -C \"$WT\" commit -m x"         # explicit -C wins over json cwd
check_cwd main "$REPO" allow "cd \"$WT\" && git commit -m x"      # leading cd wins over json cwd
check_cwd main "$WT"   block "cd \"$REPO\" && git commit -m x"    # leading cd overrides json cwd the other way
check_cwd main "$REPO" block 'git commit -m x'                    # positive control: no override at all

# Multiple -C chain left-to-right per real git: each relative -C resolves against the prior one.
# Compute the relative hop from $WT -> $REPO (chained result must land on main and block) and the
# reverse ($REPO -> $WT, must chain into the feature worktree and allow), plus an absolute-reset case.
WT_TO_REPO=$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$REPO" "$WT")
REPO_TO_WT=$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$WT" "$REPO")
echo "multiple -C flags chain like real git (defect 1 -- HIGH bypass fix):"
# ambient/json cwd is an unrelated dir (the OTHER worktree/repo); the chain, not the cwd, decides.
check_cwd main "$WT"   block "git -C \"$WT\" -C \"$WT_TO_REPO\" commit -m x"   # rel chain -> main worktree
check_cwd main "$REPO" allow "git -C \"$REPO\" -C \"$REPO_TO_WT\" commit -m x" # rel chain -> feature worktree
check_cwd main "$WT"   block "git -C \"$REPO\" -C . commit -m x"               # absolute-then-relative -> main
check_cwd main "$WT"   allow "git -C /nonexistent -C \"$WT\" commit -m x"      # absolute 2nd -C resets base -> feature
check_cwd main "$REPO" allow 'git -C /a -C ../../nowhere commit -m x'          # chain misses git repo -> "" != main (git would fail anyway)

echo "opaque script wrappers are flagged, not silently laundered (defect 2):"
check_warn main 'bash script.sh'                                 # git hidden inside a file we can't read
check_warn main 'sh deploy.sh'
check_warn main '. ./setup.sh'
check_warn main 'source setup.sh'
check_warn main 'zsh script.zsh'
check_warn dev  'bash deploy.sh'                                   # opaque wrapper on dev is flagged too
check main  allow 'bash -c "git status"'                          # -c form is still parsed, not opaque
check feature/wip allow 'bash script.sh'                          # off main: no main-mutation at risk, no warn
check main  allow 'bash script.sh --no-op'                        # positional flags still count as opaque
if out=$(cd "$REPO" && printf '%s' "$(python3 -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.argv[1]}}))' 'bash')" | "$HOOK" 2>&1) \
   && ! printf '%s' "$out" | grep -q "Review gate warning"; then
  pass=$((pass + 1)); printf '  ok   [main] %-52s -> allow, no warn (no script arg)\n' 'bash'
else
  fail=$((fail + 1)); printf '  FAIL [main] %-52s -> unexpected warn/block\n' 'bash'
fi

echo
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
