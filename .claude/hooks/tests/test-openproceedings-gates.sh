#!/usr/bin/env bash
# Case table for the openproceedings gates: block-ai-attribution.sh, require-review.sh,
# protect-data-dir.sh, remind-token-contract.sh, load-learnings.sh and .claude/scripts/record-review.py.
# Runs the real hooks against a throwaway repo with a bare "origin", so git resolution is real.
# Every reviewer finding from the 2026-09-25 review round is a row here: a gate bug is fixed only when
# a row that failed before now passes. Usage: ./test-openproceedings-gates.sh
# Never inherit a repo from the caller: git exports GIT_DIR etc. to hooks (e.g. pre-push from a worktree),
# which would point this table's throwaway git calls at the real repository.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
set -u
HOOKS="$(cd "$(dirname "$0")/.." && pwd)"
RECORD="$(cd "$HOOKS/../scripts" && pwd)/record-review.py"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
REPO="$TMP/R&D repo"   # space + '&' in the path, on purpose
ORIGIN="$TMP/origin.git"
pass=0; fail=0

g() { git -C "$REPO" -c user.email=t@t -c user.name=t "$@"; }
git init -q --bare "$ORIGIN"
git init -q -b dev "$REPO"
mkdir -p "$REPO/.claude/learnings" "$REPO/backlog/tasks" "$REPO/data/indexes/abc" "$REPO/data/snapshots/s1" "$REPO/frontend/src/data"
printf '# old\n\n**Key lesson:** k\n' > "$REPO/.claude/learnings/2026-01-01-old.md"
echo x > "$REPO/README.md"
printf '/data/\n' > "$REPO/.gitignore"
g add -A && g commit -q -m init && g remote add origin "$ORIGIN" && g push -q origin dev
g switch -q -c other2 && echo o > "$REPO/other.txt" && g add -A && g commit -q -m other   # a distinct, never-reviewed commit
g switch -q -c feat dev

payload_bash() { python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","cwd":sys.argv[1],"tool_input":{"command":sys.argv[2]}}))' "$REPO" "$1"; }
payload_file() { python3 -c 'import json,sys; print(json.dumps({"tool_name":sys.argv[1],"cwd":sys.argv[3],"tool_input":{"file_path":sys.argv[2]}}))' "$1" "$2" "$REPO"; }

# check <hook> <want: allow|block> <label> <json>
check() {
  local hook="$1" want="$2" label="$3" json="$4" got
  if printf '%s' "$json" | "$HOOKS/$hook" >/dev/null 2>&1; then got=allow; else got=block; fi
  if [ "$got" = "$want" ]; then pass=$((pass+1)); printf '  ok   %-24s %-60s -> %s\n' "$hook" "$label" "$got"
  else fail=$((fail+1)); printf '  FAIL %-24s %-60s -> %s (want %s)\n' "$hook" "$label" "$got" "$want"; fi
}
# check_cmd <want: ok|err> <label> <cmd...>   (for scripts)
check_cmd() {
  local want="$1" label="$2"; shift 2; local got
  if (cd "$REPO" && "$@" >/dev/null 2>&1); then got=ok; else got=err; fi
  if [ "$got" = "$want" ]; then pass=$((pass+1)); printf '  ok   %-24s %-60s -> %s\n' "script" "$label" "$got"
  else fail=$((fail+1)); printf '  FAIL %-24s %-60s -> %s (want %s)\n' "script" "$label" "$got" "$want"; fi
}
approve() { (cd "$REPO" && python3 "$RECORD" APPROVE "$TMP/none.md" >/dev/null 2>&1) || { echo "setup: approve failed"; exit 1; }; }
printf 'No findings.\n' > "$TMP/none.md"
TRAILER='Co-Authored-By: Claude Opus <noreply@anthropic.com>'

echo "== block-ai-attribution.sh"
A=block-ai-attribution.sh
check $A allow "plain commit message"                "$(payload_bash 'git commit -m "feat: add parser"')"
check $A block "Claude co-author trailer in -m"       "$(payload_bash "git commit -m \"feat: x

$TRAILER\"")"
check $A block "heredoc-style -m \"\$(cat <<EOF)\""   "$(payload_bash "git commit -m \"\$(cat <<'EOF'
fix: y

$TRAILER
EOF
)\"")"
check $A block "git commit -F - <<EOF (stdin heredoc)" "$(payload_bash "git commit -F - <<'EOF'
x

$TRAILER
EOF")"
check $A block "bundled -am"                          "$(payload_bash "git commit -am \"x $TRAILER\"")"
check $A block "bundled -qm"                          "$(payload_bash "git commit -qm \"x $TRAILER\"")"
check $A block "--trailer"                            "$(payload_bash "git commit --trailer \"$TRAILER\" -m x")"
check $A block "gh pr create body footer"             "$(payload_bash 'gh pr create --base dev --title t --body "Summary

🤖 Generated with [Claude Code](https://claude.com/claude-code)"')"
check $A block "gh pr new (alias) with trailer"       "$(payload_bash "gh pr new --body \"$TRAILER\"")"
check $A block "attached short -b\"…\""               "$(payload_bash "gh pr create -t t -b\"$TRAILER\"")"
printf 'msg\n\nCo-authored-by: claude <noreply@anthropic.com>\n' > "$TMP/msg.txt"
check $A block "commit -F file with trailer"          "$(payload_bash "git commit -F '$TMP/msg.txt'")"
check $A allow "-F on a non-regular file is skipped"  "$(payload_bash 'git commit -F /dev/null')"
check $A allow "human co-author is fine"              "$(payload_bash 'git commit -m "x

Co-Authored-By: A Reviewer <reviewer@example.org>"')"
check $A block "inside bash -c wrapper"               "$(payload_bash "bash -c 'git commit -m \"x Co-Authored-By: Claude\"'")"
check $A block "after an unspaced ; separator"        "$(payload_bash "git add .;git commit -m \"x $TRAILER\"")"
check $A block "on the second line of the call"       "$(payload_bash "git add .
git commit -m \"x $TRAILER\"")"
check $A block "🤖 Generated footer alone"             "$(payload_bash 'git commit -m "x

🤖 Generated with some tool"')"
check $A block "noreply@anthropic.com address alone"  "$(payload_bash 'git commit -m "x

Signed-off-by: bot <noreply@anthropic.com>"')"
check $A block "git merge -m with trailer"            "$(payload_bash "git merge feat -m \"merge $TRAILER\"")"
check $A allow "unrelated command"                    "$(payload_bash 'ls -la')"

echo "== require-review.sh"
R=require-review.sh
check $R block "push with no review record"           "$(payload_bash 'git push -u origin feat')"
check $R block "push after unspaced ;"                "$(payload_bash 'git status;git push origin feat')"
check $R block "push after unspaced &&"               "$(payload_bash 'git status&&git push origin feat')"
check $R block "push on a second line"                "$(payload_bash 'git status
git push origin feat')"
check $R block "push in a (subshell)"                 "$(payload_bash '(git push origin feat)')"
check $R block "FOO=1 git push"                       "$(payload_bash 'FOO=1 git push origin feat')"
check $R block "env X=0 git push"                     "$(payload_bash 'env X=0 git push origin feat')"
check $R block "command git push"                     "$(payload_bash 'command git push origin feat')"
check $R block "time git push"                        "$(payload_bash 'time git push origin feat')"
check $R block "timeout 60 git push"                  "$(payload_bash 'timeout 60 git push origin feat')"
check $R block "if …; then git push; fi"              "$(payload_bash 'if true; then git push origin feat; fi')"
check $R block "{ git push; }"                        "$(payload_bash '{ git push origin feat; }')"
check $R block "for …; do git push; done"             "$(payload_bash 'for b in feat; do git push origin feat; done')"
check $R block "/usr/bin/git push"                    "$(payload_bash '/usr/bin/git push origin feat')"
check $R block "/bin/bash -c \"git push\""            "$(payload_bash '/bin/bash -c "git push origin feat"')"
check $R block "! gh pr create"                       "$(payload_bash '! gh pr create --fill')"
check $R block "sudo -u x nice -n 5 git push"         "$(payload_bash 'sudo -u me nice -n 5 git push origin feat')"
check $R block "push after a <<< herestring line"     "$(payload_bash 'cat <<<x
git push origin feat')"
check $R block "push after a quoted <<EOF mention"    "$(payload_bash 'echo "use <<EOF"
git push origin feat')"
check $R block "--base option injection refused"      "$(payload_bash "gh pr create --fill --base '--upload-pack=touch $TMP/PWNED;false'")"
if [ -e "$TMP/PWNED" ]; then fail=$((fail+1)); echo "  FAIL injected command ran"; else pass=$((pass+1)); echo "  ok   injected command did not run"; fi
check $R allow "deleting a remote branch"             "$(payload_bash 'git push origin --delete feat')"
check $R allow "deleting via :ref only"               "$(payload_bash 'git push origin :old')"
git -C "$REPO" worktree add -q "$TMP/wt-other" other2
(cd "$TMP/wt-other" && printf -- 'No findings.\n' > "$TMP/rc.md" && python3 "$RECORD" REQUEST_CHANGES "$TMP/rc.md" >/dev/null 2>&1)
approve
check $R allow "push after APPROVE of HEAD"           "$(payload_bash 'git push -u origin feat')"
check $R allow "explicit HEAD:refs/heads/feat"        "$(payload_bash 'git push origin HEAD:refs/heads/feat')"
check $R allow "-o ci.skip takes a value"             "$(payload_bash 'git push -o ci.skip origin feat')"
check $R block "-C into an unapproved worktree"       "$(payload_bash "git -C '$TMP/wt-other' push origin HEAD")"
check $R block "cd into an unapproved worktree"       "$(payload_bash "cd '$TMP/wt-other' && git push origin HEAD")"
check $R block "REQUEST_CHANGES record does not count" "$(payload_bash 'git push origin other2')"
check $R block "deletion mixed with unreviewed push"  "$(payload_bash 'git push origin other2 :old')"
check $R block "--all includes an unreviewed branch"  "$(payload_bash 'git push --all origin')"
echo y >> "$REPO/README.md"; g commit -qam "more"
check $R block "new commit invalidates approval"      "$(payload_bash 'git push origin feat')"
check $R block "push hidden in cd && chain"           "$(payload_bash "cd '$REPO' && git push origin feat")"
cdpayload=$(python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","cwd":sys.argv[1],"tool_input":{"command":sys.argv[2]}}))' "$TMP" "cd '$REPO' && git push origin feat")
check $R block "cd from an unrelated cwd is tracked"  "$cdpayload"
approve
check $R block "gh pr create, no learnings entry"     "$(payload_bash 'gh pr create --base dev --fill')"
check $R allow "gh pr create --label no-learning"     "$(payload_bash 'gh pr create --base dev --fill --label no-learning')"
check $R allow "--head owner:feat resolves"           "$(payload_bash 'gh pr create --base dev --head someone:feat --fill --label no-learning')"
check $R allow "dev → main promotion is exempt"       "$(payload_bash 'gh pr create --base main --head dev --fill')"
printf '# t\n\n**Key lesson:** k\n' > "$REPO/.claude/learnings/2026-09-25-x.md"; g add -A; g commit -qm learn
check $R block "learning added but not re-reviewed"   "$(payload_bash 'gh pr create --base dev --fill')"
check $R block "gh pr new (alias) not re-reviewed"    "$(payload_bash 'gh pr new --base dev --fill')"
approve
check $R allow "gh pr create with learning + review"  "$(payload_bash 'gh pr create --base dev --fill')"
check $R allow "-Bdev attached form"                  "$(payload_bash 'gh pr create -Bdev --fill')"
check $R block "--head is honoured (unreviewed head)" "$(payload_bash 'gh pr create --base dev --head other2 --fill --label no-learning')"
check $R block "--base is honoured (no entry vs base)" "$(payload_bash 'gh pr create --base feat --fill')"
g switch -q -c feat-extend dev
printf '\n## Addendum — 2026-09-25\nmore\n' >> "$REPO/.claude/learnings/2026-01-01-old.md"; g commit -qam extend
approve
check $R allow "extending an existing entry counts"   "$(payload_bash 'gh pr create --base dev --fill')"
g switch -q -c feat-readme dev
printf '\nnote\n' >> "$REPO/.claude/learnings/README.md"; printf 'x\n' > "$REPO/.claude/learnings/notes.txt"; g add -A; g commit -qm readme
approve
check $R block "README / non-entry files don't count" "$(payload_bash 'gh pr create --base dev --fill')"
g switch -q feat
printf '# t\n\n**Key lesson:** k\n' > "$REPO/.claude/learnings/README.md"
check_cmd err "record refuses a dirty tree"           python3 "$RECORD" APPROVE "$TMP/none.md"
rm "$REPO/.claude/learnings/README.md"

echo "== record-review.py dispositions"
SHA=$(g rev-parse --short HEAD)
printf -- '- [must] a.py:1 bug\n' > "$TMP/d1.md"
check_cmd err "undispositioned finding"               python3 "$RECORD" APPROVE "$TMP/d1.md"
printf -- '- [Must] a.py:1 wrong results\n' > "$TMP/d1b.md"
check_cmd err "capitalised [Must], undispositioned"   python3 "$RECORD" APPROVE "$TMP/d1b.md"
printf -- '  - [must] b.py:2 also wrong\n' > "$TMP/d1c.md"
check_cmd err "indented finding, undispositioned"     python3 "$RECORD" APPROVE "$TMP/d1c.md"
printf -- '* [must] c.py:3 bug\n' > "$TMP/d1d.md"
check_cmd err "* bullet finding, undispositioned"     python3 "$RECORD" APPROVE "$TMP/d1d.md"
printf -- 'see [must] item above\nNo findings.\n' > "$TMP/d1e.md"
check_cmd err "stray [must] tag outside a bullet"     python3 "$RECORD" APPROVE "$TMP/d1e.md"
printf -- '- [must] a.py:1 bug → rejected: we disagree strongly\n' > "$TMP/d2.md"
check_cmd err "must-fix cannot be rejected"           python3 "$RECORD" APPROVE "$TMP/d2.md"
printf -- '- [must] a.py:1 bug → fixed %s\n- [nit] b.py:2 name → rejected: matches surrounding style\n' "$SHA" > "$TMP/d3.md"
check_cmd ok  "fixed ancestor + reasoned reject"      python3 "$RECORD" APPROVE "$TMP/d3.md"
printf -- '- [should] a.py:1 x -> y mapping wrong -> fixed %s\r\n' "$SHA" > "$TMP/d3b.md"
check_cmd ok  "summary containing -> and CRLF"        python3 "$RECORD" APPROVE "$TMP/d3b.md"
printf -- '- [should] a.py:1 slow → task-999\n' > "$TMP/d4.md"
check_cmd err "task that does not exist"              python3 "$RECORD" APPROVE "$TMP/d4.md"
: > "$REPO/backlog/tasks/task-999 - Speed up.md"; g add -A; g commit -qm task
check_cmd ok  "task that exists"                      python3 "$RECORD" APPROVE "$TMP/d4.md"
printf -- '- [must] a.py:1 bug → fixed deadbeef\n' > "$TMP/d5.md"
check_cmd err "fixed sha that does not exist"         python3 "$RECORD" APPROVE "$TMP/d5.md"
OTHER=$(g rev-parse --short other2)
printf -- '- [must] a.py:1 bug → fixed %s\n' "$OTHER" > "$TMP/d6.md"
check_cmd err "fixed sha reachable but not ancestor"  python3 "$RECORD" APPROVE "$TMP/d6.md"
BASESHA=$(g rev-parse --short origin/dev)
printf -- '- [must] a.py:1 bug → fixed %s\n' "$BASESHA" > "$TMP/d7.md"
check_cmd err "fixed sha already on origin/dev"       python3 "$RECORD" APPROVE "$TMP/d7.md"
printf -- '- [nit] a.py:1 name → rejected: ..........\n' > "$TMP/d8.md"
check_cmd err "rejection without a real reason"       python3 "$RECORD" APPROVE "$TMP/d8.md"
printf -- '- [must] a.py:1 bug → fixed %s\nNo findings.\n' "$SHA" > "$TMP/d9.md"
check_cmd err "'No findings.' alongside a finding"    python3 "$RECORD" APPROVE "$TMP/d9.md"
printf '\xef\xbb\xbf- [ MUST ] a.py:1 bug\n' > "$TMP/d10.md"
check_cmd err "BOM + spaced [ MUST ], undispositioned" python3 "$RECORD" APPROVE "$TMP/d10.md"
: > "$TMP/empty.md"
check_cmd err "empty dispositions file"               python3 "$RECORD" APPROVE "$TMP/empty.md"

echo "== protect-data-dir.sh"
P=protect-data-dir.sh
check $P block "Write into data/indexes/"             "$(payload_file Write "$REPO/data/indexes/abc/meta.json")"
check $P block "Write into a NEW index dir"           "$(payload_file Write "$REPO/data/indexes/new/meta.json")"
check $P block "Edit data/snapshots/ records"         "$(payload_file Edit "$REPO/data/snapshots/s1/records.jsonl")"
check $P allow "Write data/cache/ (mutable)"          "$(payload_file Write "$REPO/data/cache/x.json")"
check $P allow "Write frontend/src/data/ (not data/)" "$(payload_file Write "$REPO/frontend/src/data/indexes/x.ts")"
check $P allow "Write normal source"                  "$(payload_file Write "$REPO/backend/src/openproceedings/cli.py")"
check $P block "git add -f data/"                     "$(payload_bash 'git add -f data/snapshots')"
check $P block "git add -Af data"                     "$(payload_bash 'git add -Af data')"
check $P allow "git add -f frontend/src/data/…"       "$(payload_bash 'git add -f frontend/src/data/fixtures.ts')"
check $P allow "git add docs/data-model.md"           "$(payload_bash 'git add docs/data-model.md')"
check $P block "rm -rf an index"                      "$(payload_bash 'rm -rf data/indexes/abc')"
check $P block "rm -rf data/indexes (the dir)"        "$(payload_bash 'rm -rf data/indexes')"
check $P block "rm -rf data/snapshots"                "$(payload_bash 'rm -rf data/snapshots')"
check $P block "rm -rf data"                          "$(payload_bash 'rm -rf data')"
check $P block "rm after unspaced ;"                  "$(payload_bash 'ls;rm -rf data/indexes/abc')"
check $P block "find data/indexes -delete"            "$(payload_bash 'find data/indexes -name x -delete')"
check $P block "cp over a snapshot file"              "$(payload_bash 'cp /tmp/x data/snapshots/s1/records.jsonl')"
check $P block "mv an index away"                     "$(payload_bash 'mv data/indexes/abc /tmp/abc')"
check $P block "> redirect into an index"             "$(payload_bash 'echo x > data/indexes/abc/meta.json')"
check $P block ">> redirect, no spaces"               "$(payload_bash 'echo x>>data/indexes/abc/meta.json')"
check $P block "sed --in-place on a snapshot"         "$(payload_bash 'sed --in-place s/a/b/ data/snapshots/s1/records.jsonl')"
check $P block "tee into an index"                    "$(payload_bash 'echo x | tee data/indexes/abc/meta.json')"
check $P block "timeout 5 rm -rf data/snapshots"       "$(payload_bash 'timeout 5 rm -rf data/snapshots')"
check $P block "if …; then rm -rf data/snapshots; fi" "$(payload_bash 'if true; then rm -rf data/snapshots; fi')"
check $P block "/bin/rm -rf data/indexes"             "$(payload_bash '/bin/rm -rf data/indexes')"
check $P block "rm after a <<< herestring line"       "$(payload_bash 'cat <<<x
rm -rf data/snapshots')"
check $P block "mv a task file by hand"               "$(payload_bash 'mv "backlog/tasks/task-001 - x.md" backlog/completed/')"
check $P block "git mv a task file"                   "$(payload_bash 'git mv "backlog/tasks/task-001 - x.md" backlog/completed/')"
check $P block "rm a task file"                       "$(payload_bash 'rm "backlog/tasks/task-001 - x.md"')"
check $P block "redirect into backlog/"               "$(payload_bash 'echo x > backlog/tasks/new.md')"
check $P allow "the backlog CLI itself"               "$(payload_bash 'backlog task complete 1')"
check $P allow "reading backlog files"                "$(payload_bash 'cat backlog/tasks/*.md')"
check $P allow "sed read-only on a snapshot"          "$(payload_bash 'sed -n 1p data/snapshots/s1/records.jsonl')"
check $P allow "cp OUT of a snapshot"                 "$(payload_bash 'cp data/snapshots/s1/records.jsonl /tmp/x')"
check $P allow "rm data/cache"                        "$(payload_bash 'rm -rf data/cache')"

echo "== round-2 mutation rows (each row fails if one specific piece of gate logic is removed)"
g switch -q -c mut dev
printf '# m\n\n**Key lesson:** mutation branch\n' > "$REPO/.claude/learnings/2026-09-26-mut.md"; g add -A; g commit -qm mut
approve                                    # HEAD (mut) approved; other2 is never reviewed
check $R allow "heredoc body is not a command"        "$(payload_bash 'cat <<EOF
git push origin other2
EOF')"
check $R allow "2>&1 is not a refspec (fd digit)"     "$(payload_bash 'git push origin mut 2>&1 | tail -5')"
check $R allow "trailing # comment is not a refspec"  "$(payload_bash 'git push -u origin mut  # publish the branch')"
check $R block "sudo -u <value> then git push"        "$(payload_bash 'sudo -u me git push origin other2')"
check $R block "eval recursion"                       "$(payload_bash 'eval "git push origin other2"')"
check $R block "gh -R repo pr create (unreviewed)"    "$(payload_bash 'gh -R me/op pr create --head other2 --fill --label no-learning')"
check $R block "attached -Hother2 is honoured"        "$(payload_bash 'gh pr create -Hother2 --fill --label no-learning')"
check $R block "promotion needs head dev, not feat"   "$(payload_bash 'gh pr create --base main --head other2 --fill')"
check $R block "promotion: owner:dev is not ours"     "$(payload_bash 'gh pr create --base main --head someone:dev --fill')"
check $R block "promotion: --repo other is not ours"  "$(payload_bash 'gh pr create --repo other/fork --base main --head dev --fill')"
check $R block "process substitution <(git push)"     "$(payload_bash 'diff <(git push origin other2) /dev/null')"
check $R block "--base injection, validation only barrier" "$(payload_bash "gh pr create --fill --label no-learning --base '--upload-pack=touch $TMP/PWNED2;false'")"
if [ -e "$TMP/PWNED2" ]; then fail=$((fail+1)); echo "  FAIL injected command ran (approved + no-learning path)"; else pass=$((pass+1)); echo "  ok   injected command did not run (approved + no-learning path)"; fi
check $R allow "-d deletes every named ref"           "$(payload_bash 'git push -d origin other2')"
check $R allow "base defaults to dev"                 "$(payload_bash 'gh pr create --fill')"
check $R allow "comma-split labels (bug,no-learning)" "$(payload_bash 'gh pr create --base dev --head mut --fill -l bug,no-learning')"
g switch -q -c mut-del dev
git -C "$REPO" rm -q ".claude/learnings/2026-01-01-old.md"; g commit -qm del
approve
check $R block "deleting an entry is not a lesson"    "$(payload_bash 'gh pr create --base dev --fill')"
check $R allow "comma-split label bug,no-learning"    "$(payload_bash 'gh pr create --base dev --fill -l bug,no-learning')"
g switch -q -c mut-chmod dev
chmod +x "$REPO/.claude/learnings/2026-01-01-old.md"; g commit -qam chmod
approve
check $R block "chmod-only change is not a lesson"    "$(payload_bash 'gh pr create --base dev --fill')"
g switch -q mut
check $A block "gh pr edit body trailer"              "$(payload_bash "gh pr edit 1 --body \"x $TRAILER\"")"
check $A block "git tag -m trailer"                   "$(payload_bash "git tag -a v1 -m \"rel $TRAILER\"")"
printf 'Summary\n\n%s\n' "$TRAILER" > "$TMP/body.md"
check $A block "--body-file with trailer"             "$(payload_bash "gh pr create --fill --body-file '$TMP/body.md'")"
check $A block "unbalanced quote still scanned"       "$(payload_bash "git commit -m \"x $TRAILER")"
check $A block "-F - < file (stdin redirect)"         "$(payload_bash "git commit -F - < '$TMP/msg.txt'")"
check $A block "cat file | git commit -F -"           "$(payload_bash "cat '$TMP/msg.txt' | git commit -F -")"
check $A block "--trailer Co-authored-by=Claude"      "$(payload_bash 'git commit --trailer "Co-authored-by=Claude <x@y>" -m x')"
check $P block "rm -rf data/* (glob)"                 "$(payload_bash 'rm -rf data/*')"
check $P block "rm -rf data/snap* (glob)"             "$(payload_bash 'rm -rf data/snap*')"
check $P allow "rm -rf data/cache/* (mutable)"        "$(payload_bash 'rm -rf data/cache/*')"
check $P block "git clean -fdx"                       "$(payload_bash 'git clean -fdx')"
check $P block "git clean -fdX"                       "$(payload_bash 'git clean -fdX')"
check $P allow "git clean -ndx (dry run)"             "$(payload_bash 'git clean -ndx')"
check $P allow "git clean -fd (no ignored files)"     "$(payload_bash 'git clean -fd')"
check $P block "git stash --all"                      "$(payload_bash 'git stash --all')"
check $P block "dd of= into an index"                 "$(payload_bash 'dd if=/dev/zero of=data/indexes/abc/x bs=1 count=1')"
check $P block "rsync --delete onto data/indexes/"    "$(payload_bash 'rsync -a --delete empty/ data/indexes/')"
check $P block "cp into data/indexes/ (the dir)"      "$(payload_bash 'cp x data/indexes/')"
check $P block "truncate a snapshot"                  "$(payload_bash 'truncate -s0 data/snapshots/s1/records.jsonl')"
check $P block "find -execdir rm in snapshots"        "$(payload_bash 'find data/snapshots -name x -execdir rm {} \;')"
check $P block "sed -Ei (clustered in-place)"         "$(payload_bash 'sed -Ei s/a/b/ data/snapshots/s1/records.jsonl')"
nb=$(python3 -c 'import json,sys; print(json.dumps({"tool_name":"NotebookEdit","cwd":sys.argv[1],"tool_input":{"notebook_path":sys.argv[1]+"/data/indexes/abc/n.ipynb"}}))' "$REPO")
check $P block "NotebookEdit into an index"           "$nb"
mkdir -p "$REPO/backlog/completed"; : > "$REPO/backlog/completed/task-555 - done.md"
g add -A; g commit -qm completed-task
printf -- '- [should] a.py:1 slow → task-555\n' > "$TMP/d11.md"
check_cmd ok  "task found in backlog/completed/"      python3 "$RECORD" APPROVE "$TMP/d11.md"
printf -- '- [must] a.py:1 wrong → task-555\n' > "$TMP/d12.md"
check_cmd err "APPROVE refused: must → task"          python3 "$RECORD" APPROVE "$TMP/d12.md"
check_cmd ok  "REQUEST_CHANGES with an open must"     python3 "$RECORD" REQUEST_CHANGES "$TMP/d12.md"
check $R block "…and that record does not approve"    "$(payload_bash 'git push origin mut')"

echo "== remind-token-contract.sh (non-blocking; must emit context on contract files only)"
out=$(payload_file Edit "$REPO/backend/src/openproceedings/query/normalize.py" | "$HOOKS/remind-token-contract.sh")
case "$out" in *TOKENIZER_VERSION*) pass=$((pass+1)); echo "  ok   reminder on normalize.py";; *) fail=$((fail+1)); echo "  FAIL no reminder on normalize.py";; esac
out=$(payload_file Edit "$REPO/backend/src/openproceedings/api/app.py" | "$HOOKS/remind-token-contract.sh")
if [ -z "$out" ]; then pass=$((pass+1)); echo "  ok   silent on api/app.py"; else fail=$((fail+1)); echo "  FAIL spoke on api/app.py"; fi

echo "== autofix.sh (non-blocking; fixes in place, reports what it can't)"
cp "$HOOKS/../../pyproject.toml" "$REPO/pyproject.toml" 2>/dev/null
ln -s "$(cd "$HOOKS/../.." && pwd)/.venv" "$REPO/.venv" 2>/dev/null   # autofix runs ruff from the workspace venv, never via uv run
printf 'import os,sys\nx=1\n' > "$REPO/fmt_me.py"
( cd "$REPO" && payload_file Edit "$REPO/fmt_me.py" | CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1 ); rc=$?
if [ $rc -eq 0 ] && grep -q '^x = 1$' "$REPO/fmt_me.py"; then pass=$((pass+1)); echo "  ok   python file formatted in place (exit 0)"; else fail=$((fail+1)); echo "  FAIL python not formatted / nonzero exit ($rc)"; fi
printf 'def f(:\n' > "$REPO/broken.py"
out=$(payload_file Edit "$REPO/broken.py" | CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" 2>/dev/null)
case "$out" in *additionalContext*) pass=$((pass+1)); echo "  ok   unfixable python reported back";; *) fail=$((fail+1)); echo "  FAIL unfixable python not reported";; esac
printf 'x = 1\n' > "$REPO/data/cache.py" 2>/dev/null || { mkdir -p "$REPO/data"; printf 'x=1\n' > "$REPO/data/cache.py"; }
printf 'x=1\n' > "$REPO/data/cache.py"
payload_file Edit "$REPO/data/cache.py" | CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1
if grep -q '^x=1$' "$REPO/data/cache.py"; then pass=$((pass+1)); echo "  ok   data/ is never touched"; else fail=$((fail+1)); echo "  FAIL autofix rewrote a file under data/"; fi

rm -f "$REPO/.venv"
printf 'x=1\n' > "$REPO/novenv.py"
out=$(payload_file Edit "$REPO/novenv.py" | CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" 2>/dev/null)
case "$out" in *".venv/bin/ruff not found"*) pass=$((pass+1)); echo "  ok   no venv → skipped with a note, never uv run";; *) fail=$((fail+1)); echo "  FAIL no-venv case: $out";; esac
mkdir -p "$TMP/outside"; printf 'x=1\n' > "$TMP/outside/o.py"; ln -s "$TMP/outside/o.py" "$REPO/link.py"
ln -s "$(cd "$HOOKS/../.." && pwd)/.venv" "$REPO/.venv" 2>/dev/null
mkdir -p "$REPO/sub"; printf 'x=1\n' > "$TMP/outside/dots.py"
payload_file Edit "$REPO/sub/../../outside/dots.py" | CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1
if grep -q '^x=1$' "$TMP/outside/dots.py"; then pass=$((pass+1)); echo "  ok   a ../ path out of the repo is not touched"; else fail=$((fail+1)); echo "  FAIL autofix followed ../ out of the repo"; fi
rm -f "$REPO/.venv"
payload_file Edit "$REPO/link.py" | CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1
if grep -q '^x=1$' "$TMP/outside/o.py"; then pass=$((pass+1)); echo "  ok   symlink to a file outside the repo is not touched"; else fail=$((fail+1)); echo "  FAIL autofix followed a symlink out of the repo"; fi

echo "== load-learnings.sh"
mkdir -p "$TMP/empty/.claude/learnings"; printf '# Learnings index\n\n_No entries yet._\n' > "$TMP/empty/.claude/learnings/INDEX.md"
out=$(CLAUDE_PROJECT_DIR="$TMP/empty" "$HOOKS/load-learnings.sh" 2>&1)
case "$out" in *"(0 entries)"*) case "$out" in *"integer expected"*) fail=$((fail+1)); echo "  FAIL empty index errors";; *) pass=$((pass+1)); echo "  ok   empty index reports 0 cleanly";; esac;; *) fail=$((fail+1)); echo "  FAIL empty index: $out";; esac

mkdir -p "$TMP/big/.claude/learnings"
{ printf '# Learnings index\n\n'; for i in $(seq 1 45); do printf -- '- 2026-01-%02d [t%d](x.md) — k\n' $(( (i % 28) + 1 )) "$i"; done; } > "$TMP/big/.claude/learnings/INDEX.md"
out=$(CLAUDE_PROJECT_DIR="$TMP/big" "$HOOKS/load-learnings.sh" 2>&1)
lines=$(printf '%s\n' "$out" | grep -c '^- ')
case "$out" in *"5 older entries"*) if [ "$lines" -eq 40 ]; then pass=$((pass+1)); echo "  ok   index capped at 40 lines with an 'older entries' note"; else fail=$((fail+1)); echo "  FAIL cap printed $lines lines"; fi;; *) fail=$((fail+1)); echo "  FAIL no older-entries note";; esac

echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
