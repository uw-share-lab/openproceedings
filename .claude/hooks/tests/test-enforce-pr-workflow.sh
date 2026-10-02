#!/usr/bin/env bash
# shellcheck disable=SC2016  # commands under test are single-quoted on purpose: $(…), $(( )) and backticks must reach the hooks unexpanded
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

  (cd "$REPO" && printf '%s' "$json" | "$HOOK" >/dev/null 2>&1); local rc=$?
  case $rc in 0) got=allow ;; 2) got=block ;; *) got="crash(rc=$rc)" ;; esac  # only exit 2 blocks

  if [ "$got" = "$expect" ]; then
    pass=$((pass + 1))
    printf '  ok   [%s] %-52.160s -> %s\n' "$on_branch" "$cmd" "$got"
  else
    fail=$((fail + 1))
    printf '  FAIL [%s] %-52.160s -> %s (want %s)\n' "$on_branch" "$cmd" "$got" "$expect"
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

  (cd "$REPO" && printf '%s' "$json" | "$HOOK" >/dev/null 2>&1); local rc=$?
  case $rc in 0) got=allow ;; 2) got=block ;; *) got="crash(rc=$rc)" ;; esac  # only exit 2 blocks

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
  case $rc in 0) got=allow ;; 2) got=block ;; *) got="crash(rc=$rc)" ;; esac
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
check feature/wip block 'git push origin HEAD:heads/dev'          # git reads heads/dev as refs/heads/dev (TASK-067)
check feature/wip allow 'git push origin HEAD:refs/heads/feature/dev' # a feature branch that ends in /dev

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
check feature/x block 'git commit -m "a
see #1" ; git push origin HEAD:dev'                                    # '#1' inside a multi-line quote is not a comment
check feature/x block "git commit -F - <<'EOF' && git push origin HEAD:dev
fix: don't crash
EOF"                                                                    # quoted heredoc delimiter; apostrophe in body
check feature/x block 'git commit -m "x ; git push origin HEAD:dev'     # unparseable: fallback checks push first
check feature/x block 'echo $((1<<n))
git push origin HEAD:dev'                                              # arithmetic << is not a heredoc
check feature/x block "cat <<'EOF'
x \\
EOF
git push origin HEAD:dev"                                              # body ending in a backslash keeps its delimiter
check feature/x block "n=\$((echo a) | wc -l)
# don't worry
git push origin HEAD:dev"                                              # \$((cmd) | …) is not arithmetic: fail closed
check feature/x block "$(printf 'git pu\\\nsh origin HEAD:dev')"      # backslash-newline joins with nothing
check feature/x block "$(printf 'git push origin HEAD:d\\\nev')"     # ... even inside the ref
check feature/x allow 'git push origin feat
echo main'                                                              # separators split commands: 'main' is not a refspec
check main  allow 'bash --norc -c "git status"'            # positive control: long opt + safe cmd
check main  allow 'bash -cx "git status"'                  # positive control: cluster + safe cmd

echo "xargs appends words no gate can see (TASK-067):"
check feature/x block 'echo dev | xargs git push origin'           # xargs supplies the refspec
check feature/x block "echo origin dev | xargs sh -c 'git push \"\$@\"' sh"   # ... also through sh -c "\$@"
check feature/x allow 'echo x | xargs git log -1'                  # positive control

echo "git -c config overrides and aliases are expanded before classifying (TASK-067):"
check feature/x block 'git -c remote.origin.push=HEAD:refs/heads/dev push origin'   # -c picks the destination
check feature/x block 'git -c push.default=matching push origin'
check feature/x allow 'git -c color.ui=never push origin feat'     # positive control: unrelated key
check feature/x block 'git -c alias.p=push p origin HEAD:dev'
check main      block 'git -c alias.ci=commit ci -m x'
check feature/x allow 'git -c alias.ci=commit ci -m x'             # positive control: off main
check feature/x block "git -c 'alias.sp=!git push origin HEAD:dev' sp"   # shell alias: its git commands are read
check feature/x allow "git -c 'alias.sp=!git push origin feat' sp"      # positive control
git -C "$REPO" config alias.mc commit
check main      block 'git mc -m x'                                # alias from the repo's own config
git -C "$REPO" config --unset alias.mc

echo "every other way to make a commit on, or move, a protected branch (TASK-067):"
check main      block 'git cherry-pick x'
check dev       block 'git revert HEAD'
check main      block 'git am fix.patch'
check main      block 'git rebase feat'
check main      block 'git commit-tree HEAD^{tree} -m x'
check main      block 'git reset --hard feat'                      # main now points at feat's commits
check main      block 'git reset --soft HEAD~1'
check main      allow 'git reset --hard origin/main'               # sync with origin
check main      allow 'git reset --hard @{u}'
check main      allow 'git reset --hard'                           # discard local edits, main unmoved
: > "$REPO/notes.txt"                                               # an untracked file to unstage by name
check main      allow 'git reset notes.txt'                        # unstage a path
check main      allow 'git reset -- feat'                          # ... after --, always a path
check main      block 'git update-ref HEAD feat'                   # HEAD is main here: moves it
check feature/x allow 'git update-ref HEAD feat'                   # positive control: off main
check main      allow 'git update-ref --no-deref HEAD feat'        # detaches HEAD; main stays put
check main      block 'git pull --no-ff'                           # a merge commit even when ff is possible
check dev       block 'git pull --no-ff origin dev'
check feature/x allow 'git pull --no-ff'
check feature/x allow 'git cherry-pick x'                          # positive control: off main
check feature/x allow 'git rebase origin/dev'
check feature/x allow 'git reset --hard origin/dev'
check feature/x block 'git update-ref refs/heads/main HEAD'        # moves local main from anywhere
check feature/x block 'git update-ref -d refs/heads/dev'
check feature/x block 'git update-ref -m msg refs/heads/dev HEAD'
check feature/x block 'git update-ref --stdin'                     # refs read from stdin: refuse to guess
check feature/x allow 'git update-ref refs/heads/feature/x HEAD'

echo "abbreviated long options are what git reads them as (TASK-067 review gate):"
check feature/x block 'git push --al origin'                       # --all
check feature/x block 'git push --mirr origin'                     # --mirror
check feature/x block 'git push --a origin'                        # ambiguous (--all, --atomic): fail closed
check main      allow 'git push --dele origin feature/x'           # --delete of a feature ref
check feature/x allow 'git push --force origin feat'               # an exact name wins over its longer siblings
check main      allow 'git merge --ff-o origin/main'               # --ff-only
check main      block 'git merge --ff-o --no-f feat'               # --no-ff overrides it
check main      block 'git pull --no-f'                            # ambiguous (--no-ff, --no-force): fail closed

echo "config this gate can't read: an alias or a refspec-less push fails closed (TASK-067 review gate):"
printf '[alias]\n\tp = push\n' > "$REPO/.git/inc.cfg"
check feature/x block 'P=push git --config-env alias.p=P p origin HEAD:dev'
check feature/x block 'P=push git --config-env=alias.p=P p origin HEAD:dev'
check feature/x block "git -c include.path=$REPO/.git/inc.cfg p origin HEAD:dev"
check feature/x block "git -c includeIf.gitdir:/.path=$REPO/.git/inc.cfg p origin HEAD:dev"
check feature/x block 'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push git p origin HEAD:dev'
check feature/x block "GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\" git p origin HEAD:dev"
check feature/x block "GIT_CONFIG_GLOBAL=$REPO/.git/inc.cfg git p origin HEAD:dev"
check feature/x block 'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=remote.origin.push GIT_CONFIG_VALUE_0=HEAD:refs/heads/dev git push origin'
check feature/x allow "git -c include.path=$REPO/.git/inc.cfg status"   # a builtin: no alias to hide
check feature/x allow 'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=color.ui GIT_CONFIG_VALUE_0=never git push origin feat'
check feature/x block 'git -c remote.origin.mirror=true push origin'    # mirror: every ref, protected ones too

echo "glob refspecs can name a protected branch (TASK-067 review gate):"
check feature/x block "git push origin 'refs/heads/*:refs/heads/*'"
check feature/x block "git push origin '*:*'"
check feature/x allow "git push origin 'refs/heads/feature/x:refs/heads/feature/x'"

echo "a protected local branch moved without update-ref (TASK-067 review gate):"
check feature/x block 'git branch -f main HEAD'
check feature/x block 'git branch --force dev HEAD'
check feature/x block 'git branch -fq main HEAD'
check feature/x block 'git branch -M x main'
check feature/x block 'git branch -C x dev'
check feature/x block 'git branch --move --force x main'
check feature/x allow 'git branch -f feature/y HEAD'
check feature/x allow 'git branch -c main backup'                  # copies main elsewhere; main unmoved
check feature/x allow 'git branch -u origin/main feature/x'        # -u takes a value
check feature/x allow 'git branch --list main'
check main      block 'git checkout -B main feature/x'
check feature/x block 'git checkout -B dev feature/x'
check feature/x block 'git checkout -Bdev feature/x'
check feature/x allow 'git checkout -B feature/y'
check feature/x block 'git switch -C main feature/x'
check feature/x block 'git switch --force-create=dev feature/x'
check feature/x block 'git switch --force-c dev feature/x'          # abbreviated --force-create
check feature/x allow 'git switch -C feature/y'
check feature/x block 'git worktree add -B main /tmp/wt-x'
check feature/x block 'git fetch . feature/x:dev'
check feature/x block 'git fetch origin feature/x:refs/heads/main'
check feature/x block 'git fetch origin +dev:dev'                  # forced: not a sync
check feature/x block "git fetch origin 'refs/heads/*:refs/heads/*'"
check feature/x block 'git fetch --stdin origin'                   # refspecs from stdin: refuse to guess
check feature/x allow 'git fetch origin dev:dev'                   # fast-forwards local dev from origin's dev
check feature/x allow 'git fetch origin'
check feature/x allow 'git fetch --depth 5 origin dev:dev'           # --depth takes a value: origin is the remote
check feature/x block 'git fetch upstream dev:dev'                 # another remote's dev is not a sync
check feature/x block 'git fetch -f origin dev:dev'
check feature/x allow 'git fetch . feature/x:feature/y'

echo "git-<sub> programs are git <sub> (TASK-067 review gate):"
check feature/x block '$(git --exec-path)/git-push origin HEAD:dev'
check main      block '/usr/libexec/git-core/git-commit -m x'
check feature/x allow '/usr/libexec/git-core/git-push origin feat'
check feature/x block 'caffeinate -i /usr/libexec/git-core/git-push origin HEAD:dev'   # behind a wrapper cmdparse doesn't know

echo "an unparseable command with a git write word is refused (TASK-067 final review gate):"
check main      block 'git cherry-pick x "'
check main      block 'git revert x "'
check main      block 'git am x "'
check main      block 'git rebase x "'
check main      block 'git reset --hard x "'
check feature/x block 'git cherry-pick x "'   # unparseable with a git write word: refused on any branch (final review gate)

echo "without python3, the text fallback still refuses commit makers on a protected branch, push first:"
NOPY="$(mktemp -d)"
for tool in bash git cat dirname; do ln -s "$(command -v "$tool")" "$NOPY/$tool"; done
# check_nopy <branch> <expect> <command>: the hook run with a PATH that has no python3
check_nopy() {
  local on_branch="$1" expect="$2" cmd="$3" json got
  git -C "$REPO" checkout -q "$on_branch" 2>/dev/null || git -C "$REPO" checkout -q -b "$on_branch"
  json=$(python3 -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.argv[1]}}))' "$cmd")
  (cd "$REPO" && printf '%s' "$json" | PATH="$NOPY" "$HOOK" >/dev/null 2>&1); local rc=$?
  case $rc in 0) got=allow ;; 2) got=block ;; *) got="crash(rc=$rc)" ;; esac
  if [ "$got" = "$expect" ]; then pass=$((pass + 1)); printf '  ok   [%s, no python3] %-40s -> %s\n' "$on_branch" "$cmd" "$got"
  else fail=$((fail + 1)); printf '  FAIL [%s, no python3] %-40s -> %s (want %s)\n' "$on_branch" "$cmd" "$got" "$expect"; fi
}
check_nopy main      block 'git cherry-pick x'
check_nopy main      block 'git revert x'
check_nopy main      block 'git am x'
check_nopy main      block 'git rebase x'
check_nopy main      block 'git reset --hard x'
check_nopy main      block 'git commit -m x'
check_nopy main      allow 'git status'
check_nopy feature/x allow 'git commit -m x'
check_nopy feature/x block 'git commit -m x; git push origin HEAD:dev'   # push is checked first
check_nopy feature/x block 'git -C ../other commit -m x'                 # -C: the branch can't be placed
rm -rf "$NOPY"

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
echo "--git-dir / GIT_DIR point git at another worktree's branch (TASK-067):"
check_cwd main "$WT" block "GIT_DIR=\"$REPO/.git\" git commit -m x"          # json cwd = feature worktree
check_cwd main "$WT" block "git --git-dir=\"$REPO/.git\" commit -m x"
check_cwd main "$WT" block "git --git-dir \"$REPO/.git\" cherry-pick x"
check_cwd main "$WT" block "env GIT_DIR=\"$REPO/.git\" git merge x"
check_cwd main "$WT" allow "GIT_DIR=\"$WT/.git\" git commit -m x"            # positive control: its own gitfile
check_cwd main "$REPO" allow "git --git-dir=\"$WT/.git\" commit -m x"        # ... and the other way round
check_cwd main "$WT" block "export GIT_DIR=\"$REPO/.git\"; git commit -m x"  # exported for every later command
check_cwd main "$WT" block "GIT_DIR=\"$REPO/.git\"; export GIT_DIR; git commit -m x"
check_cwd main "$WT" block "declare -x GIT_DIR=\"$REPO/.git\" && git commit -m x"
check_cwd main "$WT" allow "GIT_DIR=\"$REPO/.git\"; git commit -m x"         # a shell variable git never sees
check_cwd main "$WT" allow "export GIT_DIR=\"$REPO/.git\"; unset GIT_DIR; git commit -m x"
check_cwd main "$WT" block "GIT_DIR=\"$REPO/.git\" git branch -f main HEAD"  # moves the main worktree's branch

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

echo "review gate round 2: brace expansion and ANSI-C quoting are what bash runs (TASK-067):"
check feature/x block 'git push origin HEAD:d{e,}v'                # bash: HEAD:dev HEAD:dv
check feature/x block 'git push origin HEAD:{feat,dev}'
check feature/x block 'git push origin HEAD:{d..e}ev'               # a letter sequence: dev eev
check feature/x block 'git push origin HEAD:d{x,{e,y}}v'            # nested
check feature/x block "git push origin HEAD:\$'\\x64ev'"            # \$'\x64ev' is dev
check feature/x block "git push origin \$'HEAD:\\144ev'"            # octal escape
check feature/x block "git push origin HEAD:d\$'\\u0065'v"          # mid-word, \u escape
check feature/x block "git push origin HEAD:\$\"dev\""              # \$\"…\" is a plain quoted string
check feature/x block "git push origin HEAD:\$'dev\\0x'"           # a NUL ends the \$'…' value: dev
check feature/x block 'git branch -f d{e,}v HEAD'
check feature/x allow 'git push origin "HEAD:d{e,}v"'               # quoted: no expansion, a literal ref
check feature/x allow 'git push origin HEAD:feature/{a,b}'          # positive control
check feature/x allow 'echo {a,b} ${HOME} @{u} && git push origin feat'
check main      block '{ git commit -m x; }'                         # `{` alone is still a reserved word

echo "review gate round 2: GIT_COMMON_DIR points git at another repo's config (TASK-067):"
mkdir -p "$REPO/evil" && printf '[alias]\n\tp = push\n' > "$REPO/evil/config"
check feature/x block "GIT_COMMON_DIR=\"$REPO/evil\" git p origin HEAD:dev"
check feature/x block "export GIT_COMMON_DIR=\"$REPO/evil\"; git p origin HEAD:dev"
check feature/x block "GIT_COMMON_DIR=\"$REPO/evil\" git push origin"   # refspec-less: config decides
check feature/x allow "GIT_COMMON_DIR=\"$REPO/evil\" git status"        # a builtin: no alias to hide

echo "review gate round 2: set -a / set -o allexport export every later assignment (TASK-067):"
check feature/x block 'set -a; GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push; git p origin HEAD:dev'
check feature/x block 'set -o allexport; GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push; git p origin HEAD:dev'
check feature/x block 'set -euax; GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push; git p origin HEAD:dev'
check feature/x allow 'set -a; set +a; GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push; git p origin HEAD:dev'
check feature/x allow 'set -o allexport; set +o allexport; GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push; git p origin HEAD:dev'
check feature/x allow 'set -euo pipefail; GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push; git p origin HEAD:dev'

echo "review gate round 2: a refspec-less push reads the repo's push config (TASK-067):"
check feature/x allow 'git push origin'                              # no push config: the branch itself
check feature/x block 'git config remote.origin.push HEAD:refs/heads/dev; git push origin'
check feature/x block 'git config alias.p push && git p origin HEAD:dev'   # the alias is written mid-command
check feature/x block 'git config --add include.path /tmp/x.cfg; git p origin HEAD:dev'
check feature/x allow 'git config user.name t && git commit -m x'   # an unrelated key
check feature/x allow 'git config --get-regexp alias.p push; git status'   # reading config writes nothing
git -C "$REPO" config remote.origin.push HEAD:refs/heads/dev
check feature/x block 'git push origin'                              # ... set by an earlier call
check feature/x allow 'git push origin feat'                         # a refspec named: config unused
git -C "$REPO" config --unset remote.origin.push
git -C "$REPO" config remote.origin.mirror true
check feature/x block 'git push origin'
git -C "$REPO" config remote.origin.mirror false
check feature/x allow 'git push origin'                              # mirror=false: not a mirror
git -C "$REPO" config --unset remote.origin.mirror
git -C "$REPO" config push.default matching
check feature/x block 'git push origin'                              # every branch with a same-named remote one
git -C "$REPO" config push.default upstream
git -C "$REPO" config branch.feature/x.remote origin
git -C "$REPO" config branch.feature/x.merge refs/heads/dev
check feature/x block 'git push'                                     # upstream: pushes feature/x to dev
git -C "$REPO" config branch.feature/x.merge refs/heads/feature/x
check feature/x allow 'git push'                                     # its upstream is itself
git -C "$REPO" config push.default current
check feature/x allow 'git push origin'
git -C "$REPO" config --unset push.default
git -C "$REPO" config --remove-section branch.feature/x

echo "review gate round 2: the matching refspec ':' pushes every same-named branch (TASK-067):"
check feature/x block 'git push origin :'
check feature/x block 'git push -f origin :'
check feature/x block 'git push origin +:'
check feature/x allow 'git push origin :feature/old'                 # positive control: a deletion

echo "review gate round 2: a checkout/switch earlier in the command decides the branch (TASK-067):"
check feature/x block 'git checkout main && git commit -m x'
check feature/x block 'git switch main; git merge feature'
check feature/x block 'git switch dev && git cherry-pick x'
check feature/x block 'git checkout -q main && git reset --hard feature/x'
check feature/x allow 'git checkout main && git checkout feature/x && git commit -m x'
check feature/x allow 'git checkout main -- README && git commit -m x'   # restores a file, stays put
check main      allow 'git switch -c feature/y && git commit -m x'   # off main before the commit
check main      allow 'git checkout -b feature/z && git commit -m x'
check main      allow 'git switch --detach && git commit -m x'
check main      allow "git checkout $(git -C "$REPO" rev-parse HEAD) && git commit -m x"   # a commit: detached
check main      block 'git checkout HEAD && git commit -m x'          # HEAD: still on main
check main      block 'git checkout notes.txt && git commit -m x'     # a path: still on main

echo "review gate round 2: set -a reaches GIT_DIR too (TASK-067):"
check_cwd main "$WT" block "set -a; GIT_DIR=\"$REPO/.git\"; git commit -m x"
check_cwd main "$WT" allow "set -a; set +a; GIT_DIR=\"$REPO/.git\"; git commit -m x"

echo "review gate round 3: a multi-line \$'…' message is read, and a leftover parse error fails closed (TASK-067):"
check_cwd main "$WT" block "git -C \"$WT_TO_REPO\" commit -m \$'feat: x\n\nbody'"
check_cwd main "$WT" block "git -C \"$WT_TO_REPO\" commit -m \$'feat: x

body'"
check_cwd main "$WT" block "cd \"$WT_TO_REPO\" && git commit -m \$'feat: x

body'"
check_cwd main "$WT" allow "git commit -m \$'feat: x

body'"                                                                  # the worktree's own feature branch
check_cwd main "$WT" block "git -C \"$WT_TO_REPO\" commit -m \"x"       # unparseable: the fallback can't place -C
check_cwd main "$WT" block "cd \"$WT_TO_REPO\" && git commit -m \"x"
check_cwd main "$WT" block "git -C \"$WT_TO_REPO\" push origin feature/wt-branch \""

echo "review gate round 3: the gate follows cd/pushd like the other gates, and resolves \$ words (TASK-067):"
check_cwd main "$WT" block "pushd \"$WT_TO_REPO\" && git commit -m x"
check_cwd main "$WT" block "W=\"$WT_TO_REPO\"; cd \$W && git commit -m x"
check_cwd main "$WT" block "cd \"\$PWD/$WT_TO_REPO\" && git commit -m x"
check_cwd main "$WT" block "cd ~+/\"$WT_TO_REPO\" && git commit -m x"
check_cwd main "$WT" block 'cd "$OP_UNSET_DIR" && git commit -m x'      # a directory this gate can't tell
check_cwd main "$WT" allow "pushd \"$WT_TO_REPO\" && popd && git commit -m x"
check_cwd main "$WT" allow "cd \"\$OP_UNSET_DIR\" && git -C \"$WT\" commit -m x"   # an absolute -C places it
check feature/x block 'caffeinate git -c alias.p=push p origin HEAD:dev'   # an alias behind an unknown wrapper
check feature/x block 'B=dev; git push origin HEAD:$B'
check feature/x block 'git push origin HEAD:$OP_UNSET_REF'                # a destination this gate can't tell
check feature/x allow 'B=feat; git push origin HEAD:$B'

echo "review gate round 3: assignments before a shell wrapper reach the commands inside it (TASK-067):"
check_cwd main "$WT" block "GIT_DIR=\"$REPO/.git\" bash -c 'git commit -m x'"
check feature/x block "GIT_CONFIG_GLOBAL=/tmp/op-g bash -c 'git push'"
check feature/x allow "X=1 bash -c 'git push origin feat'"

echo "review gate round 3: checkout/switch with redirects, --track, -p, and a GIT_DIR= spelling (TASK-067):"
check feature/x block 'git checkout main 2>/dev/null && git commit -m x'
check feature/x block 'git checkout main >/dev/null && git commit -m x'
check feature/x block 'git checkout main &>/dev/null && git commit -m x'
check feature/x block 'git checkout main 2>/dev/null && git push origin HEAD'
check feature/x block 'git checkout --track origin/main && git commit -m x'
check feature/x block 'for b in dev feat; do git checkout $b; break; done; git commit -m y'
check feature/x block 'for b in dev feat; do break; done; git push origin HEAD:$b'
check feature/x block 'git checkout -t origin/dev && git commit -m x'
check feature/x block 'git switch --track origin/main && git commit -m x'
check feature/x block 'git switch -t origin/main && git commit -m x'
check feature/x block 'git checkout --track refs/remotes/origin/dev && git commit -m x'
check feature/x allow 'git checkout --no-track -b feature/q origin/main && git commit -m x'
check feature/x allow 'git checkout -p main && git commit -m x'        # patches files; stays on feature/x
check feature/x allow 'git checkout --patch main && git commit -m x'
check feature/x block 'GIT_DIR=.git git checkout main && git commit -m x'

echo "review gate round 3: config written other than by git config, then a push (TASK-067):"
check feature/x block 'git remote add --mirror=push o3 /tmp/op-o3.git && git push o3'
check feature/x block "echo '[alias] p = push' >> .git/config; git p origin HEAD:dev"
check feature/x block "printf '[remote \"origin\"]\\n\\tpush = HEAD:refs/heads/dev\\n' >> .git/config; git push"
check feature/x block 'echo x | tee -a .git/config && git push origin'
check feature/x block 'git remote set-branches origin dev && git push origin'
check feature/x allow 'echo x >> notes.txt; git push origin feat'
git -C "$REPO" config push.default upstream
check feature/x block 'git branch -u origin/dev && git push origin'
check feature/x block 'git branch --set-upstream-to=origin/dev && git push origin'
check feature/x block 'git config branch.feature/x.merge refs/heads/dev && git push origin'
git -C "$REPO" config --unset push.default

echo "review gate round 3: an empty or unresolvable refspec word leaves a refspec-less push (TASK-067):"
git -C "$REPO" config remote.origin.push HEAD:refs/heads/dev
check feature/x block 'git push origin {,}'
check feature/x block 'git push origin $OP_UNSET_REF'
check feature/x allow 'git push origin feat{,}'                          # one word: feat feat
git -C "$REPO" config --unset remote.origin.push

echo "final review gate: crashes and parse failures fail closed (TASK-067):"
BR="echo $(python3 -c 'print("{x," * 1100 + "x" + "}" * 1100)')"
check feature/x block "$BR; git push origin HEAD:d''ev"                 # deep braces: no crash (exit 1 is a pass)
check feature/x block "git push origin HEAD:d''ev <<EOF"                # unclosed heredoc: bash still runs the push
check feature/x block "git commit -m x <<EOF"
check feature/x allow 'echo "unbalanced'                                # a parse failure with no git write in it
check feature/x block 'git push origin {x{1..4096},HEAD:dev}'          # past the brace limit: a parse error

echo "final review gate: bundled -t and a trailing -- still switch branches (TASK-067):"
check feature/x block 'git checkout -qt origin/dev && git commit -m x'
check feature/x block 'git checkout main -- && git commit -m x'
check feature/x block 'git checkout -t origin/dev -- && git commit -m x'
check feature/x allow 'git checkout main -- README && git commit -m x'   # restores a file; stays put

echo "final review gate: branch creation that writes an upstream, then a push (TASK-067):"
git -C "$REPO" config push.default upstream
git -C "$REPO" update-ref refs/remotes/origin/dev HEAD               # a remote-tracking start point
check feature/x block 'git checkout -b x9 -t origin/dev && git push'
check feature/x block 'git checkout -b feature/q origin/dev && git push'   # branch.autoSetupMerge's default
check feature/x allow 'git checkout -b x9 main && git push origin x9'      # a local start point: no upstream
check feature/x block 'git switch -c x9 --track origin/dev && git push'
check feature/x block 'git checkout -qb x9 --track=direct origin/dev && git push'
check feature/x block 'git worktree add -b x9 /tmp/op-wt-x9 origin/dev && git push'
check feature/x allow 'git switch -c x9 && git push origin x9'           # no start point: no upstream
check feature/x allow 'git checkout --no-track -b x9 origin/dev && git push origin x9'
git -C "$REPO" config --unset push.default
git -C "$REPO" update-ref -d refs/remotes/origin/dev

echo "final review gate: a word that expands to nothing is no refspec (TASK-067):"
git -C "$REPO" config remote.origin.push HEAD:refs/heads/dev
check feature/x block 'E=; git push origin $E'
check feature/x block 'unset E; git push origin $E'
check feature/x block 'git push origin $TMPDIR'
check feature/x block 'git push origin "$TMPDIR"'
check feature/x allow 'E=feat; git push origin $E'
check feature/x block 'B=main; git checkout $B && git commit -m x'          # a checkout target is resolved too
check feature/x allow 'cd "$HOME" && cd - && git commit -m x'          # read with HOME '' too: cd - is here
git -C "$REPO" config --unset remote.origin.push

echo "TASK-156: a quoted command substitution is a command, and every git command is read with HOME '' too:"
check dev       block 'x="$(git commit -m x)"'
check dev       block 'cd ~ && git commit -m x'                             # HOME '': the cd stays on dev
HOME="$(dirname "$REPO")" check feature/x allow "cd ~/$(basename "$REPO") && git commit -m x"   # HOME '': a failed cd stays

echo
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
