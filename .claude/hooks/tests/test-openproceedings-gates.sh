#!/usr/bin/env bash
# shellcheck disable=SC2016  # commands under test are single-quoted on purpose: $(…), $(( )) and backticks must reach the hooks unexpanded
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
payload_at() { python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","cwd":sys.argv[1],"tool_input":{"command":sys.argv[2]}}))' "$1" "$2"; }
payload_file() { python3 -c 'import json,sys; print(json.dumps({"tool_name":sys.argv[1],"cwd":sys.argv[3],"tool_input":{"file_path":sys.argv[2]}}))' "$1" "$2" "$REPO"; }

# check <hook> <want: allow|block> <label> <json>
check() {
  local hook="$1" want="$2" label="$3" json="$4" got
  # a block is exit 2 exactly: any other non-zero exit is a crash, which Claude Code lets through (fail open)
  printf '%s' "$json" | "$HOOKS/$hook" >/dev/null 2>&1; local rc=$?
  case $rc in 0) got=allow ;; 2) got=block ;; *) got="crash(rc=$rc)" ;; esac
  if [ "$got" = "$want" ]; then pass=$((pass+1)); printf '  ok   %-24s %-60s -> %s\n' "$hook" "$label" "$got"
  else fail=$((fail+1)); printf '  FAIL %-24s %-60s -> %s (want %s)\n' "$hook" "$label" "$got" "$want"; fi
}
# check_no_tmpdir: `check`, with TMPDIR absent from the hook's environment (CI's runner has none)
check_no_tmpdir() {
  local saved="${TMPDIR-}" had="${TMPDIR+x}"
  unset TMPDIR
  check "$@"
  if [ -n "$had" ]; then export TMPDIR="$saved"; fi
}
# check_no_home: `check`, with HOME absent from the hook's environment (bash's `~` is then the passwd home)
check_no_home() {
  local saved="${HOME-}" had="${HOME+x}"
  unset HOME
  check "$@"
  if [ -n "$had" ]; then export HOME="$saved"; fi
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
check $A block "gh release create --notes footer"     "$(payload_bash 'gh release create v0.1.0 --target abc --notes "x

🤖 Generated with [Claude Code](https://claude.com/claude-code)"')"
check $A block "gh release create --notes-file"       "$(payload_bash "gh release create v0.1.0 --notes-file '$TMP/msg.txt'")"
check $A block "gh release edit -F file"              "$(payload_bash "gh release edit v0.1.0 -F '$TMP/msg.txt'")"
printf 'clean notes\n' > "$TMP/notes.md"
check $A allow "gh release create, clean notes file"  "$(payload_bash "gh release create v0.1.0 --notes-file '$TMP/notes.md'")"
check $A allow "gh release view is not a write"       "$(payload_bash "gh release view v0.1.0 --json body")"
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
# an unresolvable base must refuse, not read merge-base's exit 128 as "not on the base" (TASK-067)
check_cmd err "fixed <base sha>, OP_REVIEW_BASE=nope"  env OP_REVIEW_BASE=nope python3 "$RECORD" APPROVE "$TMP/d7.md"
check_cmd err "fixed <new sha>, OP_REVIEW_BASE=nope"   env OP_REVIEW_BASE=nope python3 "$RECORD" APPROVE "$TMP/d3.md"
BASEFULL=$(g rev-parse origin/dev); g update-ref -d refs/remotes/origin/dev
check_cmd err "fixed <base sha>, origin/dev deleted"   python3 "$RECORD" APPROVE "$TMP/d7.md"
g update-ref refs/remotes/origin/dev "$BASEFULL"
check_cmd ok  "fixed <new sha> with the base restored" python3 "$RECORD" APPROVE "$TMP/d3.md"
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
check $P block "git add a takedown log"               "$(payload_bash 'git add /srv/op/data/takedowns/log.jsonl')"
check $P block "git add -f takedowns/ elsewhere"      "$(payload_bash 'git add -f ops/takedowns')"
check $P block "git add ./takedowns/withheld.txt"     "$(payload_bash 'cd /tmp && git add ./takedowns/withheld.txt')"
check $P allow "git add takedowns.py (a module)"      "$(payload_bash 'git add backend/src/openproceedings/takedowns.py')"
mkdir -p "$REPO/ops/Takedowns"   # a data directory's takedowns/, in another case (APFS folds it)
check $P block "git add -f . over a takedowns/ dir"    "$(payload_bash 'git add -f .')"
check $P block "git add -f a parent of takedowns/"     "$(payload_bash 'git add -f ops')"
check $P block "git add -f a globbed takedowns path"   "$(payload_bash "git add -f 'ops/Takedown[s]/log.jsonl'")"
check $P block "git add -f Takedowns/ in another case" "$(payload_bash 'git add -f ops/Takedowns/log.jsonl')"
check $P allow "git add . (ignored files stay out)"    "$(payload_bash 'git add .')"
check $P allow "git add 'ops/*' unforced"             "$(payload_bash "git add 'ops/*'")"
check $P block "git add -fA with a takedowns/ dir"    "$(payload_bash 'git add -fA')"
check $P block "git add --force --all"                "$(payload_bash 'git add --force --all')"
check $P block "git add -f with no path"              "$(payload_bash 'git add -f')"
check $P block "git add -f ':/' (magic pathspec)"     "$(payload_bash "git add -f ':/'")"
check $P block "git add -f '*.jsonl' (git's * crosses /)" "$(payload_bash "git add -f '*.jsonl'")"
check $P block "git stage -f ops"                     "$(payload_bash 'git stage -f ops')"
check $P block "git add -f --pathspec-from-file=x"    "$(payload_bash 'git add -f --pathspec-from-file=list.txt')"
check $P block "git add -f --pathspec-from-file x"    "$(payload_bash 'git add -f --pathspec-from-file list.txt')"
check $P allow "git add -A unforced"                  "$(payload_bash 'git add -A')"
check $P allow "git add -f a dir with no takedowns/"   "$(payload_bash 'git add -f backend')"
rm -rf "$REPO/ops"
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

echo "== protect-data-dir.sh, TASK-067 security review (a repo with data/ files and no takedowns/ dir)"
# The rows above that refuse `git add -fA` pass because ops/Takedowns existed; here only data/ can be staged.
mkdir -p "$REPO/backend" && echo b > "$REPO/backend/a.py"
echo r > "$REPO/data/snapshots/s1/records.jsonl"; echo s > "$REPO/data/secret.jsonl"
check $P block "git add -fA stages data/"             "$(payload_bash 'git add -fA')"
check $P block "git add -f . stages data/"            "$(payload_bash 'git add -f .')"
check $P block "git add --force --all stages data/"   "$(payload_bash 'git add --force --all')"
check $P block "git add -A -f stages data/"           "$(payload_bash 'git add -A -f')"
check $P block "git add -f (no path)"                 "$(payload_bash 'git add -f')"
check $P block "git add -f ':/data'"                  "$(payload_bash "git add -f ':/data'")"
check $P block "git add -f ':(glob)data/**'"          "$(payload_bash "git add -f ':(glob)data/**'")"
check $P block "git add -f '*.jsonl' (dry run sees data/)" "$(payload_bash "git add -f '*.jsonl'")"
check $P block "git add -f d* (git's glob)"           "$(payload_bash 'git add -f d*')"
check $P block "git add -f DATA/secret.jsonl (APFS)"  "$(payload_bash 'git add -f DATA/secret.jsonl')"
check $P block "cd frontend && git add -f '../d*'"    "$(payload_bash "cd frontend && git add -f '../d*'")"
check $P block "git stage -f '*.jsonl'"               "$(payload_bash "git stage -f '*.jsonl'")"
check $P block "git add -f --pathspec-from-file, no takedowns" "$(payload_bash 'git add -f --pathspec-from-file=list.txt')"
check $P block "git add -f -p: git refuses the dry run" "$(payload_bash 'git add -f -p backend')"
check $P allow "git add -f backend (dry run: no data/)" "$(payload_bash 'git add -f backend')"
check $P allow "git add -f a missing file"            "$(payload_bash 'git add -f frontend/src/data/fixtures.ts')"
check $P allow "git add -A unforced (data/ ignored)"  "$(payload_bash 'git add -A')"
check $P allow "git add '*.jsonl' unforced"           "$(payload_bash "git add '*.jsonl'")"
check $P block "--pathspec-from-file, repo without data/" "$(payload_bash "cd '$TMP/wt-other' && git add -f --pathspec-from-file=/dev/null")"
check $P allow "git -C frontend add -f ../backend"    "$(payload_bash 'git -C frontend add -f ../backend')"
check $P allow "git -c core.fsmonitor=… add -f backend" "$(payload_bash "git -c core.fsmonitor='touch $TMP/FSMON' add -f backend")"
if [ -e "$TMP/FSMON" ]; then fail=$((fail+1)); echo "  FAIL the dry run ran a -c core.fsmonitor program"; else pass=$((pass+1)); echo "  ok   the dry run drops -c (never runs a -c core.fsmonitor program)"; fi
mkdir -p "$REPO/ops2/cache/takedowns" && echo l > "$REPO/ops2/cache/takedowns/log.jsonl"   # the walk skips cache/
check $P block "git add -f a dir with cache/takedowns/ (dry run)" "$(payload_bash 'git add -f ops2')"
rm -rf "$REPO/ops2"
check $P block "update-index --add --cacheinfo …,data/x" "$(payload_bash 'git update-index --add --cacheinfo 100644,e69de29bb2d1d6434b8b29ae775ad8c2e48c5391,data/x')"
check $P block "git update-index --add data/…"        "$(payload_bash 'git update-index --add data/secret.jsonl')"
check $P block "git update-index --add a takedowns log" "$(payload_bash 'git update-index --add ops/takedowns/log.jsonl')"
check $P block "git update-index --add DATA/… (APFS)" "$(payload_bash 'git update-index --add DATA/secret.jsonl')"
check $P block "git update-index --add --stdin (unseen)" "$(payload_bash 'git update-index --add --stdin')"
check $P block "git update-index --index-info (unseen)" "$(payload_bash 'git update-index --index-info')"
check $P allow "git update-index --add backend/a.py"  "$(payload_bash 'git update-index --add backend/a.py')"
check $P allow "git update-index data/… without --add" "$(payload_bash 'git update-index --assume-unchanged data/secret.jsonl')"
# case folding (APFS): Data, DATA and Backlog name the same directories
check $P block "rm -rf Data"                          "$(payload_bash 'rm -rf Data')"
check $P block "rm -rf DATA/snapshots/s1"             "$(payload_bash 'rm -rf DATA/snapshots/s1')"
check $P block "> redirect into Data/snapshots/"      "$(payload_bash 'echo x > Data/snapshots/s1/x')"
check $P block "Write into DATA/snapshots/"           "$(payload_file Write "$REPO/DATA/snapshots/s1/x")"
check $P block "mv Backlog/tasks/… out"               "$(payload_bash 'mv Backlog/tasks/a.md /tmp')"
check $P block "git add -f Data (literal check folds)" "$(payload_bash 'git add -f Data/nothere')"
check $P allow "rm -rf frontend/src/Data (not data/)" "$(payload_bash 'rm -rf frontend/src/Data')"
# a directory ABOVE data/ holds the snapshots too
check $P block "rm -rf . (the repo root)"             "$(payload_bash 'rm -rf .')"
check $P block "rm -rf ../<repo>"                     "$(payload_bash 'rm -rf "../R&D repo"')"
check $P block "rm -rf a directory above the repo"       "$(payload_bash "rm -rf '$TMP'")"
check $P block "mv . away"                            "$(payload_bash 'mv . /tmp/elsewhere')"
check $P block "find . -name s1 -delete"              "$(payload_bash 'find . -name s1 -delete')"
check $P block "find . -name '*.pyc' -delete (conservative)" "$(payload_bash "find . -name '*.pyc' -delete")"
check $P block "find frontend . -delete (2nd start path)" "$(payload_bash 'find frontend . -name x -delete')"
check $P block "find -name s1 -delete (start defaults to .)" "$(payload_bash 'find -name s1 -delete')"
check $P block "find . -ok rm"                        "$(payload_bash 'find . -name s1 -ok rm -rf {} \;')"
check $P block "rsync --delete onto the repo root"    "$(payload_bash 'rsync -a --delete empty/ ./')"
check $P allow "rm -rf a worktree (no data/)"         "$(payload_bash "rm -rf '$TMP/wt-other'")"
mkdir -p "$TMP/clone2/data/indexes/x"   # another checkout's data/, not above this repo
check $P block "rm -rf another checkout with data/indexes" "$(payload_bash "rm -rf '$TMP/clone2'")"
check $P allow "find -L frontend -delete (-L is no start)" "$(payload_bash 'find -L frontend -name x -delete')"
check $P allow "find frontend -name '*.pyc' -delete"  "$(payload_bash "find frontend -name '*.pyc' -delete")"
check $P allow "find . -name x (no delete)"           "$(payload_bash 'find . -name x -print')"
check $P allow "cp into the repo root"                "$(payload_bash 'cp /tmp/x .')"
check $P allow "rsync onto the repo root, no --delete" "$(payload_bash 'rsync -a empty/ ./')"
# unlink
check $P block "unlink a snapshot file"               "$(payload_bash 'unlink data/snapshots/s1/records.jsonl')"
check $P block "unlink a task file"                   "$(payload_bash 'unlink backlog/tasks/a.md')"
check $P allow "unlink /tmp/x"                        "$(payload_bash 'unlink /tmp/x')"
# xargs appends paths the hook cannot see
check $P block "echo data | xargs rm -rf"             "$(payload_bash 'echo data | xargs rm -rf')"
check $P block "ls | xargs unlink"                    "$(payload_bash 'ls | xargs unlink')"
check $P block "ls | xargs mv -t /tmp"                "$(payload_bash 'ls | xargs mv -t /tmp')"
check $P block "echo data | xargs git add -f"         "$(payload_bash 'echo data | xargs git add -f')"
check $P block "ls | xargs git rm"                    "$(payload_bash 'ls | xargs git rm')"
check $P block "ls | xargs sed -i s/a/b/"             "$(payload_bash 'ls | xargs sed -i s/a/b/')"
check $P allow "ls | xargs sed -n 1p (read-only)"     "$(payload_bash 'ls | xargs sed -n 1p')"
check $P allow "ls | xargs wc -l"                     "$(payload_bash 'ls | xargs wc -l')"
check $P allow "xargs rm outside a data/backlog repo" "$(payload_bash "cd '$TMP/wt-other' && ls | xargs rm")"
# in-place edits of backlog tasks (decision bodies are the one editable part: enforce-backlog-cli.sh)
check $P block "sed -i \"\" on a backlog task"        "$(payload_bash 'sed -i "" s/a/b/ backlog/tasks/a.md')"
check $P block "sed -i on a backlog task"             "$(payload_bash 'sed -i s/a/b/ backlog/tasks/a.md')"
check $P block "perl -pi -e on a backlog task"        "$(payload_bash "perl -pi -e 's/a/b/' backlog/tasks/a.md")"
check $P block "perl -i.bak -pe on a snapshot"        "$(payload_bash "perl -i.bak -pe 's/a/b/' data/snapshots/s1/records.jsonl")"
check $P allow "sed -i on a decision body"            "$(payload_bash 'sed -i s/a/b/ backlog/decisions/decision-1.md')"
check $P allow "sed -n on a backlog task (read)"      "$(payload_bash 'sed -n 1p backlog/tasks/a.md')"
check $P allow "perl -Mstrict -ne (M's value has an i)" "$(payload_bash "perl -Mstrict -ne 'print' backlog/tasks/a.md")"
check $P allow "perl -ne on a backlog task (read)"    "$(payload_bash "perl -ne 'print' backlog/tasks/a.md")"
check $P block "unparseable, DATA in capitals"        "$(payload_bash 'rm -rf DATA "')"
rm -rf "$REPO/backend" "$REPO/data/secret.jsonl" "$REPO/data/snapshots/s1/records.jsonl"

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
check $P block "rsync into data/snapshots/, no --delete" "$(payload_bash 'rsync -a empty/x data/snapshots/s1/x')"
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

echo "== round-3 rows (parser regressions, fail-closed, globs, and the mutation survivors)"
g switch -q mut
approve
# multi-line quoted messages keep their quotes (a '#' line inside must not become a comment)
check $R block "quoted body with #12, unreviewed PR"   "$(payload_bash 'gh pr create --base dev --head other2 --label no-learning --body "Summary

Closes #12"')"
check $P block "quoted #1 line then rm -rf data"      "$(payload_bash 'echo "note
#1" ; rm -rf data')"
# quoted heredoc delimiters are recognised; apostrophes in bodies are inert
check $R block "<<'EOF' body with apostrophe, then push" "$(payload_bash "cat > n.md <<'EOF'
It's a note
EOF
git push origin other2")"
check $P block "<<'EOF' body with apostrophe, then rm" "$(payload_bash "cat > n.md <<'EOF'
don't
EOF
rm -rf data")"
check $R allow "<<'EOF' body line 'then git push' inert" "$(payload_bash "cat <<'EOF'
then git push origin other2
EOF")"
# the same quoting must not crash the parser on APPROVED work (a crash fails closed and would block it)
check $R allow "approved push after a #12 quoted line"  "$(payload_bash 'echo "fix
Closes #12" && git push origin mut')"
check $R allow "approved push after \"x # y\" quoted"   "$(payload_bash 'echo "x # y" && git push origin mut')"
check $R block "push after a commit in the same call"  "$(payload_bash 'git commit -m "x # y" && git push origin mut')"
# comment rule: '#' starts a comment only at the start of a word, and never inside quotes
check $P block "a#b is a word, not a comment"          "$(payload_bash 'echo a#b; rm -rf data')"
check $P block "quoted \"x # y\" is not a comment"     "$(payload_bash 'echo "x # y"; rm -rf data')"
check $P block "# <<EOF inside a comment is no heredoc" "$(payload_bash 'git log -1 # <<EOF
rm -rf data')"
# fail closed on unparseable commands
check $R block "unparseable push fails closed"        "$(payload_bash 'git push origin other2 "')"
check $P block "unparseable rm of data fails closed"  "$(payload_bash 'rm -rf data "')"
# globs are expanded against the filesystem
check $P block "rm -rf data* (glob)"                  "$(payload_bash 'rm -rf data*')"
check $P block "rm -rf dat? (glob)"                   "$(payload_bash 'rm -rf dat?')"
check $P block "rm -rf * in the repo root"            "$(payload_bash 'rm -rf *')"
check $P block "cd frontend && rm -rf ../*"           "$(payload_bash 'cd frontend && rm -rf ../*')"
check $P block "rm -r da\"\"ta (quotes split the word)" "$(payload_bash 'rm -r da""ta')"
check $P allow "rm -rf frontend/src/data/* (not data/)" "$(payload_bash 'rm -rf frontend/src/data/*')"
# git clean / stash precision
check $P allow "git clean -fdx -e data"               "$(payload_bash 'git clean -fdx -e data')"
check $P allow "git clean -fdx --exclude=data/"       "$(payload_bash 'git clean -fdx --exclude=data/')"
check $P allow "git clean -fdx -- frontend/"          "$(payload_bash 'git clean -fdx -- frontend/')"
check $P block "git clean -fdx -- . (covers data)"    "$(payload_bash 'git clean -fdx -- .')"
check $P block "git stash -a"                         "$(payload_bash 'git stash -a')"
check $P allow "git stash list --all is read-only"    "$(payload_bash 'git stash list --all')"
check $P block "git stash push --all"                 "$(payload_bash 'git stash push --all')"
# backlog: copying OUT is fine, into is not
check $P allow "cp a task OUT of backlog/"            "$(payload_bash 'cp "backlog/tasks/task-999 - Speed up.md" /tmp/')"
check $P allow "rsync backlog/ out"                   "$(payload_bash 'rsync -a backlog/ /tmp/bk/')"
check $P block "cp INTO backlog/"                     "$(payload_bash 'cp x.md backlog/tasks/')"
# wrappers: long options and env -S
check $R block "sudo --user root git push"            "$(payload_bash 'sudo --user root git push origin other2')"
check $R block "env -S 'git push'"                    "$(payload_bash "env -S 'git push origin other2'")"
# --head must be a real branch name even when it resolves (mut@{0} is a reflog entry of an approved sha)
check $R block "--head mut@{0} is not a branch name"  "$(payload_bash 'gh pr create --base dev --head "mut@{0}" --fill --label no-learning')"
# learnings: rename + extend counts
g switch -q -c mut-rename dev
git -C "$REPO" mv ".claude/learnings/2026-01-01-old.md" ".claude/learnings/2026-01-01-old-renamed.md"
printf '\n## Addendum\nmore\n' >> "$REPO/.claude/learnings/2026-01-01-old-renamed.md"; g add -A; g commit -qm rename
approve
check $R allow "rename + extend of an entry counts"   "$(payload_bash 'gh pr create --base dev --fill')"
g switch -q mut
# record-review: a rejection needs >= 3 words
printf -- '- [nit] a.py:1 name → rejected: too noisy\n' > "$TMP/d13.md"
check_cmd err "two-word rejection reason refused"     python3 "$RECORD" APPROVE "$TMP/d13.md"
# autofix: eslint never runs while its config is new/untracked (a fake npx records calls)
mkdir -p "$TMP/bin" "$REPO/frontend" "$REPO/node_modules"
printf '#!/bin/sh\necho "$@" >> "%s/npx.log"\n' "$TMP" > "$TMP/bin/npx"; chmod +x "$TMP/bin/npx"
printf 'x\n' > "$REPO/frontend/a.ts"; : > "$TMP/npx.log"
payload_file Edit "$REPO/frontend/a.ts" | PATH="$TMP/bin:$PATH" CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1
if grep -q eslint "$TMP/npx.log"; then pass=$((pass+1)); echo "  ok   eslint runs when its config is unchanged"; else fail=$((fail+1)); echo "  FAIL eslint did not run with a clean config"; fi
printf 'export default []\n' > "$REPO/frontend/eslint.config.js"; : > "$TMP/npx.log"
payload_file Edit "$REPO/frontend/a.ts" | PATH="$TMP/bin:$PATH" CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1
if grep -q eslint "$TMP/npx.log"; then fail=$((fail+1)); echo "  FAIL eslint ran with a new untracked config"; else pass=$((pass+1)); echo "  ok   eslint skipped while its config is untracked"; fi
# prettier loads its config's plugins (code) too: same guard (TASK-067)
: > "$TMP/npx.log"
payload_file Edit "$REPO/frontend/a.ts" | PATH="$TMP/bin:$PATH" CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1
if grep -q prettier "$TMP/npx.log"; then fail=$((fail+1)); echo "  FAIL prettier ran with an untracked eslint config"; else pass=$((pass+1)); echo "  ok   prettier skipped while a formatter config is untracked"; fi
rm -f "$REPO/frontend/eslint.config.js"; printf '{"plugins":["./x.js"]}\n' > "$REPO/frontend/.prettierrc.json"; : > "$TMP/npx.log"
payload_file Edit "$REPO/frontend/a.ts" | PATH="$TMP/bin:$PATH" CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1
if grep -q prettier "$TMP/npx.log"; then fail=$((fail+1)); echo "  FAIL prettier ran with a new untracked .prettierrc"; else pass=$((pass+1)); echo "  ok   prettier skipped while .prettierrc is untracked"; fi
rm -f "$REPO/frontend/.prettierrc.json"; : > "$TMP/npx.log"
payload_file Edit "$REPO/frontend/a.ts" | PATH="$TMP/bin:$PATH" CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1
if grep -q prettier "$TMP/npx.log"; then pass=$((pass+1)); echo "  ok   prettier runs when its config is unchanged"; else fail=$((fail+1)); echo "  FAIL prettier did not run with a clean config"; fi
rm -rf "$REPO/node_modules" "$REPO/frontend/eslint.config.js" "$REPO/frontend/a.ts"

echo "== round-4 rows (git clean precision, arithmetic, heredoc edges)"
g switch -q mut
approve
check $P block "git clean -fdX -e data (X deletes it)"  "$(payload_bash 'git clean -fdX -e data')"
check $P block "git clean -fdx :/ (repo-root pathspec)" "$(payload_bash 'git clean -fdx :/')"
check $P block "git clean -fdx -enode_modules (not dry)" "$(payload_bash 'git clean -fdx -enode_modules')"
check $P block "git clean -fdx data"                   "$(payload_bash 'git clean -fdx data')"
check $P block "git clean -fdx data/snapshots"         "$(payload_bash 'git clean -fdx data/snapshots')"
check $P block "arithmetic << then rm on the next line" "$(payload_bash 'echo $((x<<y))
rm -rf data/snapshots')"
check $R block "arithmetic << then push"                "$(payload_bash 'echo $((1<<n))
git push origin other2')"
check $R allow "arithmetic << before an approved push"  "$(payload_bash 'echo $((1<<2)) && git push origin mut')"
check $R block "heredoc body ending in \\ keeps its end" "$(payload_bash "cat <<'EOF'
x \\
EOF
git push origin other2")"
check $R allow "<<\\EOF body with apostrophe, approved"  "$(payload_bash "cat <<\\EOF
it's
EOF
git push origin mut")"
check $R allow "'EOF ' (trailing space) is not the end" "$(payload_bash "$(printf 'cat <<EOF\nEOF \ngit push origin other2\nEOF')")"  # printf keeps the trailing space editors strip
check $R block "line continuation joins a push"        "$(payload_bash 'git push origin \
other2')"

echo "== round-5 rows (arithmetic depth, clustered -e, partly quoted delimiters, continuation parity)"
g switch -q mut
approve
check $R block "\$((cmd) | …) is a subst, not arithmetic" "$(payload_bash "n=\$((echo a) | wc -l)
# don't worry
git push origin other2
echo '")"  # the closing quote pairs with don't and would hide the push without the end-of-input net
check $R allow "\$((1+(2*3))) nested parens, approved"  "$(payload_bash 'x=$((1+(2*3))) && git push origin mut')"
check $R allow "nested parens keep << a shift, approved" "$(payload_bash 'x=$(( (a+(b)) << c )) && git push origin mut')"
check $P block "git clean -fdxenode_modules (clustered -e)" "$(payload_bash 'git clean -fdxenode_modules')"
check $P allow "git clean -fdxedata (clustered -e data)"    "$(payload_bash 'git clean -fdxedata')"
check $R block "<<E\"OF\" partly quoted delimiter"      "$(payload_bash 'cat <<E"OF"
x
EOF
git push origin other2
E')"  # a later line "E" would otherwise close the misread heredoc and swallow the push
check $R block "even trailing backslashes don't continue" "$(payload_bash "$(printf 'echo a\\\\\ngit push origin other2')")"
check $R allow "odd trailing backslashes continue (all echo)" "$(payload_bash "$(printf 'echo a\\\\\\\ngit push origin other2')")"
check $R block "continuation splits a word: git pu\\sh" "$(payload_bash "$(printf 'git pu\\\nsh origin other2')")"
check $R block "continuation splits the command: gi\\t" "$(payload_bash "$(printf 'gi\\\nt push origin other2')")"
check $P block "continuation splits a flag: -fd\\x" "$(payload_bash "$(printf 'git clean -fd\\\nx')")"

echo "== round-6 rows (TASK-067 security review: xargs, git -c/aliases, forged records, \$(cat file))"
g switch -q mut
approve                                    # HEAD (mut) approved, so each row below isolates its own check
check $R block "xargs git push (appended refspec unseen)" "$(payload_bash 'echo other2 | xargs git push origin')"
check $R block "xargs sh -c 'git push \"\$@\"'"        "$(payload_bash "echo origin other2 | xargs sh -c 'git push \"\$@\"' sh")"
check $R allow "<<< herestring, then an approved push" "$(payload_bash 'cat <<<x
git push origin mut')"   # a herestring read as a heredoc never ends: the parse fails closed and blocks
check $R allow "xargs of a non-push git command"      "$(payload_bash 'echo x | xargs git log -1')"
# cmdparse.xargs_hides_args is shared: protect-data-dir.sh will refuse the rm/mv/git add forms with it
hides() { python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from cmdparse import simple_commands, xargs_hides_args
print(any(xargs_hides_args(a, d) for a, d in simple_commands(sys.argv[2], sys.argv[3])))' "$HOOKS/lib" "$1" "$REPO"; }
check_hides() {  # check_hides <True|False> <command>
  local got; got=$(hides "$2")
  if [ "$got" = "$1" ]; then pass=$((pass+1)); printf '  ok   %-24s %-60s -> %s\n' "cmdparse" "xargs_hides_args: $2" "$got"
  else fail=$((fail+1)); printf '  FAIL %-24s %-60s -> %s (want %s)\n' "cmdparse" "xargs_hides_args: $2" "$got" "$1"; fi
}
check_hides True  'find . -name x | xargs rm'
check_hides True  'ls | xargs mv -t /tmp'
check_hides True  'ls | xargs git add -f'
check_hides True  'ls | xargs /usr/bin/git commit'
check_hides False 'ls | xargs echo'
check_hides False 'rm -f x'
check $R block "git push --tags (every tag, unchecked)" "$(payload_bash 'git push --tags origin')"
check $R block "git push origin mut --tags"            "$(payload_bash 'git push origin mut --tags')"
check $R allow "--follow-tags with an approved ref"    "$(payload_bash 'git push --follow-tags origin mut')"
# git -c config overrides and aliases: the gate must judge what git will actually push
check $R block "-c remote.origin.push picks the ref"  "$(payload_bash 'git -c remote.origin.push=refs/heads/other2:refs/heads/other2 push origin')"
check $R block "-c push.default, no refspec"          "$(payload_bash 'git -c push.default=matching push origin')"
check $R block "-c remote.pushDefault, no refspec"    "$(payload_bash 'git -c remote.pushDefault=origin push')"
check $R allow "-c of an unrelated key"               "$(payload_bash 'git -c color.ui=never push origin mut')"
check $R allow "-c remote.origin.push, refspec named" "$(payload_bash 'git -c remote.origin.push=other2 push origin mut')"
check $R block "-c alias.p=push p (unreviewed)"       "$(payload_bash 'git -c alias.p=push p origin other2')"
check $R allow "-c alias.p=push p (approved)"         "$(payload_bash 'git -c alias.p=push p origin mut')"
check $R block "-c alias.P (names are case-blind)"    "$(payload_bash 'git -c alias.P=push p origin other2')"
check $R block "alias with options: -c 'alias.p=push -u'" "$(payload_bash "git -c 'alias.p=push -u' p origin other2")"
check $R block "shell alias '!git push'"              "$(payload_bash "git -c 'alias.sp=!git push' sp origin other2")"
check $R block "alias to an alias"                    "$(payload_bash 'git -c alias.a=b -c alias.b=push a origin other2')"
g config alias.pp push
check $R block "repo-configured alias (git config)"   "$(payload_bash 'git pp origin other2')"
check $R allow "repo alias cannot shadow a builtin"   "$(payload_bash 'git -c alias.status=push status origin other2')"
g config --unset alias.pp
git init -q "$TMP/aliasrepo" && git -C "$TMP/aliasrepo" config alias.zz push
check $R block "alias read from the --git-dir repo"   "$(payload_bash "git --git-dir='$TMP/aliasrepo/.git' zz origin other2")"
check $R block "--config-env remote.origin.push=VAR"  "$(payload_bash 'git --config-env remote.origin.push=V push origin')"
check $R allow "self-calling shell alias is bounded"  "$(payload_bash "git -c 'alias.lp=!git lp' lp")"
check $R block "git P runs alias.p (names are case-blind)" "$(payload_bash 'git -c alias.p=push P origin other2')"
check $R allow "-c remote.origin.pushurl is not a refspec" "$(payload_bash 'git -c remote.origin.pushurl=x push origin')"
check $R block "shell alias sees the outer -c settings" "$(payload_bash "git -c remote.origin.push=other2:other2 -c 'alias.sp=!git push origin' sp")"
check $R block "shell alias sees the outer --git-dir"  "$(payload_bash "git --git-dir='$TMP/wt-other/.git' -c 'alias.sp=!git push origin HEAD' sp")"
check $R block "shell alias calling an outer -c alias" "$(payload_bash "git -c alias.p=push -c 'alias.sp=!git p origin other2' sp")"
check $R block "xargs through an alias"               "$(payload_bash 'echo other2 | xargs git -c alias.p=push p origin')"
check $R block "xargs through a shell alias"          "$(payload_bash "echo other2 | xargs git -c 'alias.sp=!git push origin' sp")"
check $R block "--git-dir: HEAD of the other worktree" "$(payload_bash "git --git-dir='$TMP/wt-other/.git' push origin HEAD")"
check $R block "GIT_DIR=: HEAD of the other worktree"  "$(payload_bash "GIT_DIR='$TMP/wt-other/.git' git push origin HEAD")"

# a message read from a file inside a quoted $(…) is scanned too ($TMP/msg.txt holds a Claude trailer)
check $A block "-m \"\$(cat msg.txt)\""                "$(payload_bash "git commit -m \"\$(cat '$TMP/msg.txt')\"")"
check $A block "-m \"\$(< msg.txt)\""                  "$(payload_bash "git commit -m \"\$(< '$TMP/msg.txt')\"")"
check $A block "-m \"\$(<msg.txt)\" relative, no space" "$(payload_bash "cd '$TMP' && git commit -m \"\$(<msg.txt)\"")"
check $A block "-m \"\`cat msg.txt\`\" (backticks)"     "$(payload_bash "git commit -m \"\`cat '$TMP/msg.txt'\`\"")"
check $A allow "-m \"\$(cat notes.md)\", clean file"   "$(payload_bash "git commit -m \"\$(cat '$TMP/notes.md')\"")"
# review records are written only by record-review.py: no shell write or file tool may forge one
check $R block "printf APPROVE > …/op-reviews/<sha>"   "$(payload_bash "printf 'APPROVE\n' > \"\$(git rev-parse --git-common-dir)/op-reviews/\$(git rev-parse HEAD)\"")"
check $R block "… with the \$(…) target unquoted"     "$(payload_bash "printf 'APPROVE\n' > \$(git rev-parse --git-common-dir)/op-reviews/abc")"
check $R block "tee into op-reviews/"                 "$(payload_bash 'echo APPROVE | tee .git/op-reviews/abc')"
check $R block "cp a record into op-reviews/"         "$(payload_bash 'cp /tmp/r .git/op-reviews/abc')"
check $R block "rm a record"                          "$(payload_bash 'rm .git/op-reviews/abc')"
check $R block "cd into op-reviews, then write"       "$(payload_bash 'cd .git/op-reviews && echo APPROVE > abc')"
check $R block "python -c writing a record"           "$(payload_bash "python3 -c \"open('.git/op-reviews/x','w').write('APPROVE')\"")"
check $R block "OP-Reviews in another case (APFS)"    "$(payload_bash 'echo APPROVE > .git/OP-Reviews/abc')"
check $R block "cat > a record (a reader, redirected)" "$(payload_bash 'cat /tmp/r > .git/op-reviews/abc')"
check $R block "unparseable write to a record"        "$(payload_bash 'echo APPROVE > .git/op-reviews/x "')"
check $R allow "listing records, 2>&1"                "$(payload_bash 'ls .git/op-reviews 2>&1')"
check $R allow "listing records, 2>/dev/null"         "$(payload_bash 'ls .git/op-reviews 2>/dev/null')"
check $R allow "record-review.py writes the record"   "$(payload_bash 'python3 .claude/scripts/record-review.py APPROVE f.md')"
check $R allow "reading a record"                     "$(payload_bash 'cat "$(git rev-parse --git-common-dir)/op-reviews/abc"')"
check $R allow "listing the records"                  "$(payload_bash 'ls .git/op-reviews | head -3')"
check $R block "Write to .git/op-reviews/x"           "$(payload_file Write "$REPO/.git/op-reviews/x")"
check $R block "Edit of a relative op-reviews path"   "$(payload_file Edit ".git/op-reviews/x")"
nbr=$(python3 -c 'import json,sys; print(json.dumps({"tool_name":"NotebookEdit","cwd":sys.argv[1],"tool_input":{"notebook_path":sys.argv[1]+"/.git/op-reviews/n.ipynb"}}))' "$REPO")
check $R block "NotebookEdit into op-reviews/"        "$nbr"
ln -s "$REPO/.git/op-reviews" "$TMP/revlink"
check $R block "Write through a symlink to op-reviews/" "$(payload_file Write "$TMP/revlink/x")"
check $R allow "Write to an ordinary file"            "$(payload_file Write "$REPO/README.md")"

echo "== round-7 rows (TASK-067 review gate: abbreviations, unreadable config, globs, exports, git-<sub>)"
g switch -q mut
approve                                    # HEAD (mut) approved, other2 never reviewed: each row isolates one check
# git reads any unique prefix of a long option
check $R block "git push --al (--all: other2 unreviewed)" "$(payload_bash 'git push --al origin')"
check $R block "git push --mirr"                      "$(payload_bash 'git push --mirr origin')"
check $R block "git push --tag (--tags)"              "$(payload_bash 'git push --tag origin')"
check $R allow "--push-o takes its value (--push-option)" "$(payload_bash 'git push --push-o ci.skip origin mut')"
check $R allow "--force is exact, not ambiguous"      "$(payload_bash 'git push --force origin mut')"
check $R allow "--dele deletes (--delete)"            "$(payload_bash 'git push --dele origin other2')"
check $A block "git commit --fil <file with trailer>" "$(payload_bash "git commit --fil '$TMP/msg.txt'")"
# config git reads from a source this parser can't: an alias or a refspec-less push fails closed
printf '[alias]\n\tp = push\n\tfa = add -f -A\n' > "$TMP/inc.cfg"
check $R block "--config-env alias.p=P p"             "$(payload_bash 'P=push git --config-env alias.p=P p origin other2')"
check $R block "--config-env=alias.p=P p"             "$(payload_bash 'P=push git --config-env=alias.p=P p origin other2')"
check $R block "-c include.path=<file> p"             "$(payload_bash "git -c include.path='$TMP/inc.cfg' p origin other2")"
check $R block "GIT_CONFIG_COUNT/KEY/VALUE alias"     "$(payload_bash 'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push git p origin other2')"
check $R block "GIT_CONFIG_PARAMETERS alias"          "$(payload_bash "GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\" git p origin other2")"
check $R block "GIT_CONFIG_* push target, no refspec" "$(payload_bash 'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=remote.origin.push GIT_CONFIG_VALUE_0=other2:other2 git push origin')"
check $R allow "GIT_CONFIG_* with a named refspec"    "$(payload_bash 'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=color.ui GIT_CONFIG_VALUE_0=never git push origin mut')"
check $R block "-c remote.origin.mirror=true, no refspec" "$(payload_bash 'git -c remote.origin.mirror=true push origin')"
check $R block "-c push.followTags=true, no refspec"  "$(payload_bash 'git -c push.followTags=true push origin')"
check $P block "-c include.path alias: add -f -A"     "$(payload_bash "git -c include.path='$TMP/inc.cfg' fa")"
check $R block "glob refspec refs/heads/*"            "$(payload_bash "git push origin 'refs/heads/*:refs/heads/*'")"
# export / declare -x reach every later command
check $R block "export GIT_DIR=<other>; git push HEAD" "$(payload_bash "export GIT_DIR='$TMP/wt-other/.git'; git push origin HEAD")"
check $R block "GIT_DIR=…; export GIT_DIR; git push"  "$(payload_bash "GIT_DIR='$TMP/wt-other/.git'; export GIT_DIR; git push origin HEAD")"
check $R block "declare -x GIT_DIR=…; git push"       "$(payload_bash "declare -x GIT_DIR='$TMP/wt-other/.git'; git push origin HEAD")"
check $R allow "GIT_DIR=… unexported: git never sees it" "$(payload_bash "GIT_DIR='$TMP/wt-other/.git'; git push origin HEAD")"
# a git-<sub> program is git <sub>
check $R block "\$(git --exec-path)/git-push"          "$(payload_bash '$(git --exec-path)/git-push origin other2')"
# forged review records through globs and variables
check $R block "cp into a globbed op-revie*/ dir"     "$(payload_bash 'cp /tmp/r .git/op-revie*/abc')"
check $R block "cd .git/op-revie* && write"           "$(payload_bash 'cd .git/op-revie* && printf APPROVE > abc')"
check $R block "cd \$(…)/op-review? && write"          "$(payload_bash 'cd "$(git rev-parse --git-common-dir)"/op-review? && printf APPROVE > abc')"
check $R block "d=op-reviews; write .git/\$d/abc"      "$(payload_bash 'd=op-reviews; printf APPROVE > ".git/$d/abc"')"
check $R block "d=op-reviews; cp to .git/\$d/abc"      "$(payload_bash 'd=op-reviews; cp /tmp/r ".git/$d/abc"')"
check $R block "> \"\$(…)/\$(echo op-reviews)/abc\""   "$(payload_bash 'printf APPROVE > "$(git rev-parse --git-common-dir)/$(echo op-reviews)/abc"')"
check $R allow "ls .git/op-revie* (a reader)"         "$(payload_bash 'ls .git/op-revie*')"
check $R allow "cd \$(toplevel) && make > log"         "$(payload_bash 'cd "$(git rev-parse --show-toplevel)" && make lint > /tmp/lint.log')"
# a shell alias runs at the top of the worktree, wherever it was called from
check $P block "cd frontend && shell alias rm -rf data" "$(payload_bash "cd frontend && git -c 'alias.x=!rm -rf data' x")"
# protect-data-dir: abbreviations, attached values, the dry run's config, and the nits
mkdir -p "$REPO/backend" && echo b > "$REPO/backend/a.py"
echo r > "$REPO/data/snapshots/s1/records.jsonl"; echo s > "$REPO/data/secret.jsonl"
check $P block "git add --forc data/snapshots/s1/…"   "$(payload_bash 'git add --forc data/snapshots/s1/records.jsonl')"
check $P block "git add --forc . (dry run sees data/)" "$(payload_bash 'git add --forc .')"
check $P block "git add --forc -A"                    "$(payload_bash 'git add --forc -A')"
check $P block "git stash push --al"                  "$(payload_bash 'git stash push --al')"
check $P block "git stash --al (an implicit push)"    "$(payload_bash 'git stash --al')"
check $P allow "git stash push -- --al (a pathspec)"  "$(payload_bash 'git stash push -- --al')"
check $P block "update-index --add --cacheinfo=…,data/x" "$(payload_bash 'git update-index --add --cacheinfo=100644,e69de29bb2d1d6434b8b29ae775ad8c2e48c5391,data/x')"
check $P block "GIT_DIR=<repo> add -f from a data-less tree" "$(payload_bash "cd '$TMP/wt-other' && GIT_DIR='$REPO/.git' GIT_WORK_TREE='$REPO' git add -f '*.jsonl'")"
g config core.fsmonitor "touch '$TMP/FSMON2'"
check $P allow "git add -f backend, repo core.fsmonitor set" "$(payload_bash 'git add -f backend')"
g config --unset core.fsmonitor
if [ -e "$TMP/FSMON2" ]; then fail=$((fail+1)); echo "  FAIL the dry run ran the repo's core.fsmonitor program"; else pass=$((pass+1)); echo "  ok   the dry run never runs the repo's core.fsmonitor program"; fi
check $P block "rsync --remove-source-files data/"    "$(payload_bash 'rsync -a --remove-source-files data/ /tmp/x/')"
check $P allow "rsync --remove-source-files from elsewhere" "$(payload_bash 'rsync -a --remove-source-files /tmp/y/ /tmp/x/')"
check $P block "rm -rf \"\$PWD\" (a \$ word, repo has data/)" "$(payload_bash 'rm -rf "$PWD"')"
check $P block "mv \"\$PWD\" away"                      "$(payload_bash 'mv "$PWD" /tmp/x')"
git init -q "$TMP/nodata"   # a repo with no data/ in any worktree
check $P allow "rm -rf \"\$X\" in a repo without data/"  "$(payload_at "$TMP/nodata" 'rm -rf "$X"')"
check $P block "dd of=backlog/…"                      "$(payload_bash 'dd if=/dev/zero of=backlog/tasks/a.md count=1')"
check $P block "ruby -i -pe on a backlog task"        "$(payload_bash "ruby -i -pe 'x' backlog/tasks/a.md")"
check $P block "ruby -pi.bak -e on a snapshot"        "$(payload_bash "ruby -pi.bak -e 'x' data/snapshots/s1/records.jsonl")"
check $P allow "ruby -rtime -ne (r's value has an i)"   "$(payload_bash "ruby -rtime -ne 'print' backlog/tasks/a.md")"
check $P block "awk -i inplace on a backlog task"     "$(payload_bash "awk -i inplace '{print}' backlog/tasks/a.md")"
check $P block "gawk --include=inplace on a snapshot" "$(payload_bash "gawk --include=inplace '{print}' data/snapshots/s1/records.jsonl")"
check $P block "awk -iinplace (attached) on a task"    "$(payload_bash "awk -iinplace '{print}' backlog/tasks/a.md")"
check $P allow "awk -F, on a backlog task (read)"     "$(payload_bash "awk -F, '{print}' backlog/tasks/a.md")"
check $P block "perl -pe … -i (a switch after -e's program)" "$(payload_bash "perl -pe 's/a/b/' -i backlog/tasks/a.md")"
rm -rf "$REPO/backend" "$REPO/data/secret.jsonl" "$REPO/data/snapshots/s1/records.jsonl"
# autofix: prettier reads only the tracked config (an untracked nested one names code to run)
mkdir -p "$TMP/bin" "$REPO/frontend/src" "$REPO/node_modules"
printf '#!/bin/sh\necho "$@" >> "%s/npx.log"\n' "$TMP" > "$TMP/bin/npx"; chmod +x "$TMP/bin/npx"
printf 'x\n' > "$REPO/frontend/src/a.ts"; printf 'module.exports = {plugins: ["./x.js"]}\n' > "$REPO/frontend/src/.prettierrc.cjs"; : > "$TMP/npx.log"
payload_file Edit "$REPO/frontend/src/a.ts" | PATH="$TMP/bin:$PATH" CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1
if grep prettier "$TMP/npx.log" | grep -q -e '--no-config' -e '--config '; then pass=$((pass+1)); echo "  ok   prettier gets its config explicitly (no search upward from the file)"; else fail=$((fail+1)); echo "  FAIL prettier searched for its config: $(cat "$TMP/npx.log")"; fi
printf '{}\n' > "$REPO/frontend/.prettierrc.json"; g add frontend/.prettierrc.json; g commit -qm prettierrc; : > "$TMP/npx.log"
payload_file Edit "$REPO/frontend/src/a.ts" | PATH="$TMP/bin:$PATH" CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1
if grep prettier "$TMP/npx.log" | grep -q -e '--config .*/frontend/\.prettierrc\.json'; then pass=$((pass+1)); echo "  ok   prettier gets the tracked frontend/.prettierrc.json"; else fail=$((fail+1)); echo "  FAIL prettier not given the tracked config: $(cat "$TMP/npx.log")"; fi
rm -rf "$REPO/node_modules" "$REPO/frontend/src/a.ts" "$REPO/frontend/src/.prettierrc.cjs"

echo "== round-8 rows (TASK-067 review gate round 2: braces, ANSI-C quotes, push config, \$ words, pushd)"
g switch -q mut
approve                                    # HEAD (mut) approved, other2 never reviewed: each row isolates one check
# brace expansion and $'…' / $"…" quoting are decoded the way bash runs them
check $R block "tee .git/op-revie{w,}s/<sha> (braces)"  "$(payload_bash 'echo APPROVE | tee .git/op-revie{w,}s/abc')"
check $R block "tee .git/\$'op-review\\x73'/<sha>"     "$(payload_bash "echo APPROVE | tee .git/\$'op-review\\x73'/abc")"
check $R allow "echo {a,b} before an approved push"    "$(payload_bash 'echo {a,b} && git push origin mut')"
check $R block "unterminated \$'… fails closed"         "$(payload_bash "git push origin \$'other2")"
mkdir -p "$REPO/backend" && echo b > "$REPO/backend/a.py" && echo s > "$REPO/data/secret.jsonl"
check $P block "git add -f dat{a,}"                    "$(payload_bash 'git add -f dat{a,}')"
check $P block "git add -f \$'dat\\x61'"                "$(payload_bash "git add -f \$'dat\\x61'")"
check $P block "git add -f \$\"data\""                  "$(payload_bash "git add -f \$\"data\"")"
check $P block "rm -rf data{,}"                        "$(payload_bash 'rm -rf data{,}')"
check $P block "rm -rf data/{cache,snapshots}"         "$(payload_bash 'rm -rf data/{cache,snapshots}')"
check $P block "rm -rf da{t..t}a (a sequence)"          "$(payload_bash 'rm -rf da{t..t}a')"
check $P allow "rm -rf data/cache/{a,b}"               "$(payload_bash 'rm -rf data/cache/{a,b}')"
check $P allow "rm -rf 'data{,}' (quoted: a literal)"  "$(payload_bash "rm -rf 'data{,}'")"
check $P allow "find frontend -name x -exec rm {} +"   "$(payload_bash 'find frontend -name x -exec rm {} +')"
# GIT_COMMON_DIR points git at another repo's config: an alias there is unreadable here
mkdir -p "$TMP/evil" && printf '[alias]\n\tp = push\n' > "$TMP/evil/config"
check $R block "GIT_COMMON_DIR=<evil> git p (alias there)" "$(payload_bash "GIT_COMMON_DIR='$TMP/evil' git p origin other2")"
check $R block "GIT_COMMON_DIR=<evil>, refspec-less push" "$(payload_bash "GIT_COMMON_DIR='$TMP/evil' git push origin")"
# set -a / set -o allexport export every later assignment
check $R block "set -a; GIT_DIR=<other>; git push HEAD" "$(payload_bash "set -a; GIT_DIR='$TMP/wt-other/.git'; git push origin HEAD")"
check $R block "set -o allexport; GIT_CONFIG_* alias"   "$(payload_bash 'set -o allexport; GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push; git p origin other2')"
check $R allow "set -a; set +a; GIT_DIR=…; git push"    "$(payload_bash "set -a; set +a; GIT_DIR='$TMP/wt-other/.git'; git push origin HEAD")"
# a refspec-less push reads the repo's push config; config written mid-command is refused
check $R allow "git push origin (no push config)"     "$(payload_bash 'git push origin')"
check $R block "git config remote.origin.push …; git push origin" "$(payload_bash 'git config remote.origin.push other2:refs/heads/other2; git push origin')"
check $R block "git config alias.p push && git p"     "$(payload_bash 'git config alias.p push && git p origin other2')"
check $R block "git config set alias.p push; git p"   "$(payload_bash 'git config set alias.p push; git p origin other2')"
check $R allow "git config user.email … && approved push" "$(payload_bash 'git config user.email t@t && git push origin mut')"
g config remote.origin.push refs/heads/other2:refs/heads/other2
check $R block "remote.origin.push set by an earlier call" "$(payload_bash 'git push origin')"
check $R allow "… a named refspec doesn't read it"     "$(payload_bash 'git push origin mut')"
g config --unset remote.origin.push
g config remote.origin.mirror true
check $R block "remote.origin.mirror set by an earlier call" "$(payload_bash 'git push origin')"
g config --unset remote.origin.mirror
g config push.default matching
check $R block "push.default=matching in the repo"    "$(payload_bash 'git push origin')"
g config --unset push.default
g config push.followTags true
check $R block "push.followTags in the repo"          "$(payload_bash 'git push origin')"
g config --unset push.followTags
# the matching refspec ':' pushes every branch that exists on both sides
check $R block "git push origin : (matching)"          "$(payload_bash 'git push origin :')"
check $R block "git push origin +: (forced matching)"  "$(payload_bash 'git push origin +:')"
# a $ word, ~ and $(pwd) are resolved (cwd, os.environ, earlier assignments); unresolvable ones fail closed
check $P block "git clean -fdx \"\$PWD\""               "$(payload_bash 'git clean -fdx "$PWD"')"
check $P block "find \"\$PWD\" -delete"                 "$(payload_bash 'find "$PWD" -name x -delete')"
check $P block "rsync --delete … \"\$PWD\"/"            "$(payload_bash 'rsync -a --delete /tmp/empty/ "$PWD"/')"
check $P block "cp onto \"\$PWD\"/data/snapshots/…"     "$(payload_bash 'cp /tmp/x "$PWD"/data/snapshots/s1/records.jsonl')"
check $P block "tee \"\$PWD\"/data/snapshots/…"         "$(payload_bash 'echo x | tee "$PWD"/data/snapshots/s1/x')"
check $P block "sed -i on \"\${PWD}\"/data/snapshots/…" "$(payload_bash 'sed -i s/a/b/ "${PWD}"/data/snapshots/s1/records.jsonl')"
check $P block "> \"\$PWD/data/snapshots/…\""           "$(payload_bash 'echo x > "$PWD/data/snapshots/s1/x"')"
check $P block "git add -f \"\$PWD/data/secret.jsonl\"" "$(payload_bash 'git add -f "$PWD/data/secret.jsonl"')"
check $P block "cd \"\$PWD\" && rm -rf data"            "$(payload_bash 'cd "$PWD" && rm -rf data')"
check $P block "cd \$(pwd)/data && rm -rf snapshots"    "$(payload_bash 'cd $(pwd)/data && rm -rf snapshots')"
check $P block "cd \"\$(pwd)/data\" && rm -rf snapshots" "$(payload_bash 'cd "$(pwd)/data" && rm -rf snapshots')"
check $P block "cd \`pwd\`/data && rm -rf indexes"      "$(payload_bash 'cd `pwd`/data && rm -rf indexes')"
check $P block "pushd data; rm -rf snapshots"          "$(payload_bash 'pushd data; rm -rf snapshots')"
check $P block "pushd frontend; popd; rm -rf data"     "$(payload_bash 'pushd frontend; popd; rm -rf data')"
check $P allow "pushd data; popd; rm -rf snapshots"    "$(payload_bash 'pushd data; popd; rm -rf snapshots')"
check $P block "cd frontend; cd -; rm -rf data"        "$(payload_bash 'cd frontend; cd -; rm -rf data')"
check $P block "rm -rf ~+/data"                        "$(payload_bash 'rm -rf ~+/data')"
check $P block "cd frontend && rm -rf ~-/data"         "$(payload_bash 'cd frontend && rm -rf ~-/data')"
HOME="$TMP" check $P block "rm -rf ~ (HOME above the repo)" "$(payload_bash 'rm -rf ~')"
HOME="$TMP" check $P block "rm -rf \"\$HOME\""         "$(payload_bash 'rm -rf "$HOME"')"
HOME="$TMP" check $P allow "rm -rf ~/elsewhere"        "$(payload_bash 'rm -rf ~/elsewhere')"
TMPDIR="$TMP/scratch" check $P allow "rm -f \"\$TMPDIR/x\" (set, outside the repo)" "$(payload_bash 'rm -f "$TMPDIR/x"')"
TMPDIR="$TMP/scratch" check $P allow "rm -rf \"\${TMPDIR}\"/build" "$(payload_bash 'rm -rf "${TMPDIR}"/build')"
check $P allow "f=<outside>; rm -f \"\$f\""             "$(payload_bash "f='$TMP/scratch/y'; rm -f \"\$f\"")"
check $P block "f=data; rm -rf \"\$f\""                 "$(payload_bash 'f=data; rm -rf "$f"')"
check $P allow "rm -rf \"\$PWD/frontend/x\""            "$(payload_bash 'rm -rf "$PWD/frontend/x"')"
check $P block "rm -rf \"\$OP_UNSET_VAR/x\" (unresolvable)" "$(payload_bash 'rm -rf "$OP_UNSET_VAR/x"')"
check $P block "cd \"\$OP_UNSET_VAR\" && rm -rf data"   "$(payload_bash 'cd "$OP_UNSET_VAR" && rm -rf data')"
check $P allow "sed -i \"s/\$x/y/\" a non-data file"    "$(payload_bash 'sed -i "s/$x/y/" frontend/a.txt')"
check $P allow "cd data; cd -; rm -rf snapshots"       "$(payload_bash 'cd data; cd -; rm -rf snapshots')"
check $P block "cd frontend && cd \"\$UNSET\" && rm -rf data" "$(payload_bash 'cd frontend && cd "$OP_UNSET_VAR" && rm -rf data')"
check $P block "cd frontend && cd \"\$UNSET\" && find -delete" "$(payload_bash 'cd frontend && cd "$OP_UNSET_VAR" && find -name x -delete')"
check $P block "cp onto \"\$UNSET/y\""                 "$(payload_bash 'cp /tmp/x "$OP_UNSET_VAR/y"')"
check $P block "dd of=\"\$UNSET/x\""                   "$(payload_bash 'dd if=/dev/zero of="$OP_UNSET_VAR/x" count=1')"
check $P block "sed -i on \"\$UNSET/x\""               "$(payload_bash 'sed -i s/a/b/ "$OP_UNSET_VAR/x"')"
check $P block "find \"\$UNSET\" -delete"              "$(payload_bash 'find "$OP_UNSET_VAR" -name x -delete')"
check $P block "git clean -fdx \"\$UNSET\""            "$(payload_bash 'git clean -fdx "$OP_UNSET_VAR"')"
check $P block "git add -f \"\$UNSET\""                "$(payload_bash 'git add -f "$OP_UNSET_VAR"')"
check $P block "git update-index --add \"\$UNSET\""    "$(payload_bash 'git update-index --add "$OP_UNSET_VAR"')"
check $P block "rm -rf \"\${OP_X:-data}\" (an operator)" "$(payload_bash 'rm -rf "${OP_X:-data}"')"
check $P allow "rm -rf ~+/frontend/x"                  "$(payload_bash 'rm -rf ~+/frontend/x')"
check $P allow "cd frontend && rm -rf ~-/frontend/x"   "$(payload_bash 'cd frontend && rm -rf ~-/frontend/x')"
TMPDIR="$TMP/scratch" check $P allow "f=\"\$TMPDIR/y\"; rm -f \"\$f\"" "$(payload_bash 'f="$TMPDIR/y"; rm -f "$f"')"
# bundled short flags of git stash push
check $P block "git stash push -qa"                    "$(payload_bash 'git stash push -qa')"
check $P block "git stash push -ua"                    "$(payload_bash 'git stash push -ua')"
check $P block "git stash -au (an implicit push)"      "$(payload_bash 'git stash -au')"
check $P allow "git stash push -qmall (m's value)"     "$(payload_bash 'git stash push -qmall')"
check $P allow "git stash push -u"                     "$(payload_bash 'git stash push -u')"
check $P allow "git stash push -- -qa (a pathspec)"    "$(payload_bash 'git stash push -- -qa')"
# rsync takes any --remove-s… spelling
check $P block "rsync --remove-source-file data/"     "$(payload_bash 'rsync -a --remove-source-file data/ /tmp/x/')"
check $P block "rsync --remove-sent-files data/"      "$(payload_bash 'rsync -a --remove-sent-files data/ /tmp/x/')"
rm -rf "$REPO/backend" "$REPO/data/secret.jsonl"
# a writing command's every word is checked for an unreadable record path
check $R block "tee \"\$(git rev-parse --git-common-dir)\"/op-revie?s/…" "$(payload_bash 'echo APPROVE | tee "$(git rev-parse --git-common-dir)"/op-revie?s/abc')"
check $R block "G=…; tee \"\$G\"/op-revie?s/…"         "$(payload_bash 'G=$(git rev-parse --git-common-dir); echo APPROVE | tee "$G"/op-revie?s/abc')"
check $R block "tee \"\$PWD\"/.git/op-revie?s/…"        "$(payload_bash 'echo APPROVE | tee "$PWD"/.git/op-revie?s/abc')"
check $R allow "cat \"\$(git rev-parse --git-dir)\"/HEAD" "$(payload_bash 'cat "$(git rev-parse --git-dir)"/HEAD')"
check $R allow "cat \"\$G\"/op-revie?s/abc > /tmp/… (a reader)" "$(payload_bash 'cat "$G"/op-revie?s/abc > /tmp/rec.txt')"
check $R allow "cat \"\$(…--git-dir)/HEAD\" > /tmp/…"  "$(payload_bash 'cat "$(git rev-parse --git-dir)/HEAD" > /tmp/head.txt')"
check $R allow "commit -m \"\$(cat <<EOF … op-reviews …)\"" "$(payload_bash "git commit -m \"\$(cat <<'EOF'
Fix the op-reviews gate in .git hooks
EOF
)\"")"
check $R block "cd .git && cp … o?-reviews/abc (glob)"  "$(payload_bash 'cd .git && cp /tmp/r o?-reviews/abc')"
check $R allow "git push origin mut -- --al (a refspec)" "$(payload_bash 'git push origin mut -- --al')"
check $P allow "cd \$(pwd)/frontend && rm -rf x"        "$(payload_bash 'cd $(pwd)/frontend && rm -rf x')"
check $R allow "gh api -f body=\"… op-review …\""      "$(payload_bash 'gh api repos/o/r/issues/1/comments -f body="notes on the op-review process"')"
# … without refusing commands that merely mention reviews
check $R allow "gh api graphql query with reviews(…)"   "$(payload_bash 'gh api graphql -f query="{ repository(owner: \"o\", name: \"r\") { pullRequest(number: 1) { reviews(first: 5) { nodes { state } } } } }"')"
check $R allow "f=\$SCRATCH/…-reviews.md; record-review.py \"\$f\"" "$(payload_bash 'f=$SCRATCH/task067-reviews.md; python3 .claude/scripts/record-review.py APPROVE "$f"')"
check $R allow "cat > \"\$SCRATCH/reviews-round2.md\" <<EOF" "$(payload_bash 'cat > "$SCRATCH/reviews-round2.md" <<EOF
x
EOF')"
check $R block "d=reviews; cd .git; write op-\$d/abc"   "$(payload_bash 'd=reviews; cd .git && printf APPROVE > "op-$d/abc"')"

echo "== round-9 rows (TASK-067 review gate round 3: fail-closed parse errors, unset, worktrees, records)"
WTO="$TMP/wt-other"   # a linked worktree: no data/ of its own; the main worktree ($REPO) has one
echo r > "$REPO/data/snapshots/s1/records.jsonl"
# a multi-line $'…' string and a huge brace expansion are read, not a parse error that fails open
check $P block "rm -rf .; printf \$'a<newline>b'"       "$(payload_bash "rm -rf .; printf \$'a
b'")"
check $P block "for i in {1..5000}; …; rm -rf ."        "$(payload_bash 'for i in {1..5000}; do :; done; rm -rf .')"
check $P block "rm -rf data{,}x13 (8192 words)"        "$(payload_bash 'rm -rf data{,}{,}{,}{,}{,}{,}{,}{,}{,}{,}{,}{,}{,}')"
check $P allow "printf \$'a<newline>b' > /tmp/…"        "$(payload_bash "printf \$'a
b' > /tmp/op-ml.txt")"
# a parse error left over fails closed wherever data/ or backlog/ is, whatever the text names
check $P block "rm -rf . \" (unparseable)"              "$(payload_bash 'rm -rf . "')"
check $P block "rm -rf . \" from a data-less worktree"  "$(payload_at "$WTO" 'rm -rf . "')"
check $R block "gi\\\\<nl>t pu\\\\<nl>sh … \" (unparseable)" "$(payload_bash "$(printf 'gi\\\nt pu\\\nsh origin other2 "')")"
# unset makes a variable empty; the environment is read only for HOME/TMPDIR/USER, and also as ''
TMPDIR="$TMP/scratch" check $P block "unset TMPDIR; rm -rf \"\${TMPDIR}data\"" "$(payload_bash 'unset TMPDIR; rm -rf "${TMPDIR}data"')"
TMPDIR="$TMP/scratch" check $P block "env -u TMPDIR bash -c 'rm -rf …data'" "$(payload_bash "env -u TMPDIR bash -c 'rm -rf \"\${TMPDIR}data\"'")"
TMPDIR="$TMP/scratch" check $P block "unset TMPDIR; mv \"\${TMPDIR}data\" …" "$(payload_bash 'unset TMPDIR; mv "${TMPDIR}data" /tmp/op-x')"
TMPDIR="$TMP/scratch" check $P block "unset TMPDIR; > \"\${TMPDIR}data/snapshots/…\"" "$(payload_bash 'unset TMPDIR; echo x > "${TMPDIR}data/snapshots/s1/x"')"
TMPDIR="$TMP/scratch" check $P block "rm -rf \"\${TMPDIR}data\" (TMPDIR may be '')" "$(payload_bash 'rm -rf "${TMPDIR}data"')"
OP_ENVVAR="$TMP/scratch" check $P block "rm -rf \"\$OP_ENVVAR/x\" (not an allowed env var)" "$(payload_bash 'rm -rf "$OP_ENVVAR/x"')"
TMPDIR="$TMP/scratch" check $P allow "rm -f \"\$TMPDIR/x\" (both readings outside)" "$(payload_bash 'rm -f "$TMPDIR/x"')"
# an unresolved path from a worktree is judged against the MAIN worktree's data/
check $P block "wt: cd \"\$(…--git-common-dir)/../data\" && rm -rf snapshots" "$(payload_at "$WTO" 'cd "$(git rev-parse --git-common-dir)/../data" && rm -rf snapshots')"
check $P block "wt: cd \"\$(…--git-common-dir)/..\" && find . -delete" "$(payload_at "$WTO" 'cd "$(git rev-parse --git-common-dir)/.." && find . -delete')"
check $P block "wt: rm -rf \$(…--git-common-dir)/../data/snapshots" "$(payload_at "$WTO" 'rm -rf $(git rev-parse --git-common-dir)/../data/snapshots')"
check $P allow "wt: rm -rf build"                      "$(payload_at "$WTO" 'rm -rf build')"
# a target is judged against the repo that contains it, not the one the command runs in
check $P block "wt: rm -rf <main>/data/snapshots"      "$(payload_at "$WTO" "rm -rf '$REPO/data/snapshots'")"
check $P block "wt: rm -rf ../<main>/data/snapshots"   "$(payload_at "$WTO" "rm -rf '../R&D repo/data/snapshots'")"
check $P block "wt: mv <main>/data/snapshots/… away"   "$(payload_at "$WTO" "mv '$REPO/data/snapshots/s1/records.jsonl' /tmp/op-x")"
check $P block "wt: mv … into <main>/data/snapshots/"  "$(payload_at "$WTO" "mv /tmp/op-x '$REPO/data/snapshots/s1/y'")"
check $P block "wt: > <main>/data/snapshots/…"         "$(payload_at "$WTO" "echo x > '$REPO/data/snapshots/s1/x'")"
check $P allow "wt: rm -rf <main>/frontend/x"          "$(payload_at "$WTO" "rm -rf '$REPO/frontend/x'")"
check $P allow "rm -rf /tmp/data (outside any repo)"   "$(payload_bash 'rm -rf /tmp/op-none/data')"
# openrsync takes any unique prefix: --rem is --remove-source-files
check $P block "rsync -a --rem data/snapshots/ …"      "$(payload_bash 'rsync -a --rem data/snapshots/ /tmp/x')"
check $P block "rsync -a --remove-so data/snapshots/ …" "$(payload_bash 'rsync -a --remove-so data/snapshots/ /tmp/x')"
check $P allow "rsync -a --re… is not --remove (ambiguous)" "$(payload_bash 'rsync -a --relative data/snapshots/ /tmp/x')"
# cd: -P is physical, a missing target leaves the shell where it was, cd - carries an unknown dir, CDPATH
ln -s "$REPO/frontend" "$TMP/lnk"
check $P block "cd -P <symlink>/.. && rm -rf data"      "$(payload_bash "cd -P '$TMP/lnk/..' && rm -rf data")"
check $P allow "cd <symlink>/.. && rm -rf data (logical)" "$(payload_bash "cd '$TMP/lnk/..' && rm -rf data")"
check $P block "cd /nonexistent; rm -rf data"          "$(payload_bash 'cd /op-nonexistent; rm -rf data')"
check $P block "cd \"\$(echo data)\" && cd /tmp && cd - && rm -rf snapshots" "$(payload_bash 'cd "$(echo data)" && cd /tmp && cd - && rm -rf snapshots')"
mkdir -p "$REPO/snapshots"
check $P block "CDPATH=<data>; cd snapshots && rm -rf s1" "$(payload_bash "CDPATH='$REPO/data'; cd snapshots && rm -rf s1")"
check $P allow "cd snapshots && rm -rf s1 (no CDPATH)"   "$(payload_bash 'cd snapshots && rm -rf s1')"
rmdir "$REPO/snapshots"
# $(git rev-parse --show-toplevel) is the repo root, like $(pwd)
check $P allow "cd \"\$(…--show-toplevel)\" && rm -rf build" "$(payload_bash 'cd "$(git rev-parse --show-toplevel)" && rm -rf build')"
check $P allow "cd \"\$(…--show-toplevel)/frontend\" && rm -rf build" "$(payload_bash 'cd "$(git rev-parse --show-toplevel)/frontend" && rm -rf build')"
check $P block "cd \"\$(…--show-toplevel)\" && rm -rf data" "$(payload_bash 'cd "$(git rev-parse --show-toplevel)" && rm -rf data')"
check $P allow "cd \"\$(…--show-toplevel)\" && rm -rf build (wt)" "$(payload_at "$WTO" 'cd "$(git rev-parse --show-toplevel)" && rm -rf build')"
check $P block "echo {1..5000} > /tmp/… (past BRACE_LIMIT: fails closed)" "$(payload_bash 'echo {1..5000} > /tmp/op-x')"
check $P allow "echo {1..4096} > /tmp/… (at BRACE_LIMIT)" "$(payload_bash 'echo {1..4096} > /tmp/op-x')"
check $P block "X=frontend; unset X; rm -rf \"\${X}data\"" "$(payload_bash 'X=frontend; unset X; rm -rf "${X}data"')"
check $P block "export X=frontend; env -u X bash -c 'rm -rf …'" "$(payload_bash "X=frontend; export X; env -u X bash -c 'rm -rf \"\${X}data\"'")"
TMPDIR="$TMP/scratch" check $P allow "rm -rf \"\$TMPDIR\" (empty when unset: no path)" "$(payload_bash 'rm -rf "$TMPDIR"')"
check $P block "rsync -a --del … ./ (--del: --delete-during)" "$(payload_bash 'rsync -a --del /tmp/op-empty/ ./')"
check $P block "wt: rm -rf .. (above the main worktree)" "$(payload_at "$WTO" 'rm -rf ..')"
check $R block "cd \"\$UNSET\" && git push origin mut"  "$(payload_bash 'cd "$OP_UNSET_DIR" && git push origin mut')"
check $P allow "rm -rf \$'build' (decoded, not a \$ word)" "$(payload_bash "rm -rf \$'build'")"
check $P allow "rm -rf \$\"build\" (a plain string)"   "$(payload_bash 'rm -rf $"build"')"
mkdir -p "$TMP/nodata/backlog"
check $P block "xargs sh -c 'rm \"\$@\"' in a repo with backlog/" "$(payload_at "$TMP/nodata" "echo backlog/x | xargs sh -c 'rm \"\$@\"' sh")"
check $R block "export D=.git/op-reviews; an opaque program" "$(payload_bash 'export D=.git/op-reviews; python3 tool.py')"
check $R block "a=op-r; b=eviews; tee \"\$G/\$a\$b/abc\"" "$(payload_bash 'a=op-r; b=eviews; echo APPROVE | tee "$G/$a$b/abc"')"
check $R allow "gh api -f body=\"the \$G op-review step\"" "$(payload_bash 'gh api repos/o/r/issues/1/comments -f body="the $G op-review step"')"
# a quote right after $NAME ends the name: "$X"a is ${X}a
check $P block "Xa=frontend; X=dat; rm -rf \"\$X\"a"     "$(payload_bash 'Xa=frontend; X=dat; rm -rf "$X"a')"
check $P allow "X=build; rm -rf \"\$X\"a"               "$(payload_bash 'X=build; rm -rf "$X"a')"
# require-review: a push after a command that moves HEAD pushes a HEAD this hook didn't read
check $R block "git commit … && git push origin HEAD"  "$(payload_bash 'git commit -m x && git push origin HEAD')"
check $R block "git checkout other2 && git push origin HEAD" "$(payload_bash 'git checkout other2 && git push origin HEAD')"
check $R block "git reset --hard X && git push -f origin HEAD" "$(payload_bash 'git reset --hard other2 && git push -f origin HEAD')"
check $R allow "git status && git push origin mut"     "$(payload_bash 'git status && git push origin mut')"
# record checks: message values are text, not paths; written words are resolved; $(…)… stays one word
check $R allow "commit -m \"the \$G/op-revie?s case\""  "$(payload_bash 'git commit -m "the $G/op-revie?s case"')"
check $R allow "commit -m \"… .git/op-reviews/<sha> …\"" "$(payload_bash 'git commit -m "write .git/op-reviews/abc only via record-review"')"
check $R allow "gh pr create --body \"… op-reviews/<sha>\"" "$(payload_bash 'gh pr create --label no-learning --title t --body "records live in .git/op-reviews/abc"')"
check $R block "G=…; d=op-; tee \"\$G/\${d}reviews/abc\"" "$(payload_bash 'G=$(git rev-parse --git-common-dir); d=op-; echo APPROVE | tee "$G/${d}reviews/abc"')"
check $R block "tee \"\$G/\${e}reviews/abc\" (unset e)"  "$(payload_bash 'echo APPROVE | tee "$G/${e}reviews/abc"')"
check $R block "cp … \$(…)/op-revie?s/<sha> (unquoted)" "$(payload_bash 'cp /tmp/x $(git rev-parse --git-common-dir)/op-revie?s/abc')"
check $R block "cp … \$(…)/op-revie[w]s/<sha>"          "$(payload_bash 'cp /tmp/x $(git rev-parse --git-common-dir)/op-revie[w]s/abc')"
check $R block "printf APPROVE > \$(…)/op-revie?s/<sha>" "$(payload_bash 'printf APPROVE > $(git rev-parse --git-common-dir)/op-revie?s/abc')"
# config written by other means than `git config`, then a git command that reads it
check $R block "echo [alias] >> .git/config; git p …"   "$(payload_bash 'echo "[alias] p = push" >> .git/config; git p origin other2')"
check $R block "GIT_CONFIG_GLOBAL=… bash -c 'git push origin'" "$(payload_bash "GIT_CONFIG_GLOBAL=/tmp/op-g bash -c 'git push origin'")"

echo "== round-10 rows (TASK-067 final review gate: crashes fail closed, brace limits, records, worktrees)"
# a hook that crashes exits 1, which Claude Code lets through: deep brace nesting, a lone surrogate
BR="echo $(python3 -c 'print("{x," * 1100 + "x" + "}" * 1100)')"
check $P block "1100 nested braces; rm -rf data/snapshots" "$(payload_bash "$BR; rm -rf data/snapshots")"
check $R block "1100 nested braces; git push origin other2" "$(payload_bash "$BR; git push origin other2")"
check $A block "1100 nested braces; commit with a trailer" "$(payload_bash "$BR; git commit -m \"x $TRAILER\"")"
check $P block "rm -rf \$'\\ud800' data/snapshots (lone surrogate)" "$(payload_bash "rm -rf \$'\\ud800' data/snapshots")"
check $P allow "echo {a,{b,c}} > /tmp/… (shallow nesting)" "$(payload_bash 'echo {a,{b,c}} > /tmp/op-x')"
check $A allow "1100 nested braces; clean commit (a parse error: text scanned)" "$(payload_bash "$BR; git commit -m x")"
EV="$(python3 -c 'print("eval " * 1100)')"   # nests deeper than Python recurses: an internal error, refused
check $R block "eval ×1100 git push origin mut (approved)" "$(payload_bash "${EV}git push origin mut")"
check $A block "eval ×1100 git commit -m x"              "$(payload_bash "${EV}git commit -m x")"
check $P block "eval ×1100 rm -rf build"                 "$(payload_bash "${EV}rm -rf build")"
# past BRACE_LIMIT words a brace expression is a parse error (fail closed), not a truncated list
check $P block "rm -rf {x{1..4096},data/snapshots}"      "$(payload_bash 'rm -rf {x{1..4096},data/snapshots}')"
check $P block "git add -f {x{1..4096},data}"            "$(payload_bash 'git add -f {x{1..4096},data}')"
# an inline message is text only for a command that takes one; --output writes a file
check $R block "git log -m --output=.git/op-reviews/<sha>" "$(payload_bash 'git log -m --output=.git/op-reviews/abc --format=tformat:APPROVE -1 abc')"
check $R block "git log --output .git/op-reviews/<sha>"  "$(payload_bash 'git log --output .git/op-reviews/abc -1')"
check $R block "git commit -m --output=.git/op-reviews/x" "$(payload_bash 'git commit -m --output=.git/op-reviews/abc')"
check $R allow "git tag -m \"… op-reviews/<sha> …\""      "$(payload_bash 'git tag -a v1 -m "records live in .git/op-reviews/abc"')"
check $R block "git log -m <record path> (log takes no message)" "$(payload_bash 'git log -m .git/op-reviews/abc -1')"
check $R block "(in .git) git log --output=op-reviews/<sha>" "$(payload_at "$REPO/.git" 'git log --output=op-reviews/abc -1')"
check $P block "git log --output=data/snapshots/s1/x"    "$(payload_bash 'git log --output=data/snapshots/s1/x -1')"
check $P block "git diff --output data/snapshots/s1/x"   "$(payload_bash 'git diff --output data/snapshots/s1/x')"
check $P block "git log --output=\"\$UNSET/x\""           "$(payload_bash 'git log --output="$OP_UNSET_DIR/x" -1')"
check $P allow "git diff --output=/tmp/op-x.diff"        "$(payload_bash 'git diff --output=/tmp/op-x.diff')"
# after a cd whose outcome is unknown, `cd -` / `~-` are unknown too (a failed cd keeps OLDPWD)
check $P block "cd /tmp; cd /nonexistent; cd -; rm -rf data" "$(payload_bash 'cd /tmp; cd /op-nonexistent; cd - ; rm -rf data')"
check $P block "cd /tmp && cd \"\$(echo x)\"; rm -rf ~-/data" "$(payload_bash 'cd /tmp && cd "$(echo x)"; rm -rf ~-/data')"
check $P allow "cd /tmp && cd - && rm -rf build"         "$(payload_bash 'cd /tmp && cd - && rm -rf build')"
# $(git rev-parse --git-common-dir|--git-dir|--absolute-git-dir) is resolved, so a glob after it expands
check $R block "cp … \$(…--git-common-dir)/op-*"         "$(payload_bash 'cp /tmp/abc $(git rev-parse --git-common-dir)/op-*')"
check $R block "cp … \$(…--git-common-dir)/*reviews"     "$(payload_bash 'cp /tmp/abc $(git rev-parse --git-common-dir)/*reviews')"
check $R block "cp -t \$(…--git-common-dir)/op-* …"      "$(payload_bash 'cp -t $(git rev-parse --git-common-dir)/op-* /tmp/abc')"
check $R block "cd \$(…--git-common-dir)/op-* && cp …"   "$(payload_bash 'cd $(git rev-parse --git-common-dir)/op-* && cp /tmp/abc .')"
check $R block "> \$(…--git-common-dir)/op-*/abc"        "$(payload_bash 'printf APPROVE > $(git rev-parse --git-common-dir)/op-*/abc')"
check $R block "G=\$(…--git-common-dir); cp … \$G/op-*"   "$(payload_bash 'G=$(git rev-parse --git-common-dir); cp /tmp/abc $G/op-*')"
check $R block "cp … \"\$(…--absolute-git-dir)\"/op-*"   "$(payload_bash 'cp /tmp/abc "$(git rev-parse --absolute-git-dir)"/op-*')"
check $R block "cp … \$(echo .git)/op-revie?s/abc (tail split off)" "$(payload_bash 'cp /tmp/abc $(echo .git)/op-revie?s/abc')"
check $R allow "ls \$(…--git-common-dir)/op-*/ (a reader)" "$(payload_bash 'ls $(git rev-parse --git-common-dir)/op-*/')"
check $P allow "rm -rf \"\$(…--git-common-dir)/op-scratch\"" "$(payload_bash 'rm -rf "$(git rev-parse --git-common-dir)/op-scratch"')"
check $P block "wt: rm -rf \"\$(…--git-dir)/../../../data\"" "$(payload_at "$WTO" 'rm -rf "$(git rev-parse --git-dir)/../../../data"')"
# a push in the same call only after read-only git commands: any other may move the ref it pushes
check $R block "git branch -f mut other2; git push origin mut" "$(payload_bash 'git branch -f mut other2; git push origin mut')"
check $R block "git fetch . +other2:mut; git push origin mut" "$(payload_bash 'git fetch . +other2:mut; git push origin mut')"
check $R block "git worktree add … -B mut; git push origin mut" "$(payload_bash 'git worktree add ../q other2 -B mut; git push origin mut')"
check $R allow "git fetch origin && git push origin mut" "$(payload_bash 'git fetch origin && git push origin mut')"
check $R allow "git log -1 && git diff && git push origin mut" "$(payload_bash 'git log -1 && git diff --stat && git push origin mut')"
# a path in another worktree is compared case-blind (APFS folds case)
if [ -d "$TMP/R&D REPO" ]; then
  check $P block "wt: rm -rf ../<MAIN>/data/snapshots"   "$(payload_at "$WTO" "rm -rf '../R&D REPO/data/snapshots'")"
  check $P block "wt: cd ../<MAIN> && rm -rf data"        "$(payload_at "$WTO" "cd '../R&D REPO' && rm -rf data")"
  check $P block "wt: mv ../<MAIN>/data /tmp/x"          "$(payload_at "$WTO" "mv '../R&D REPO/data' /tmp/op-x")"
else
  pass=$((pass+3)); echo "  skip case-folding rows: \$TMP is on a case-sensitive volume"
fi
# a data-less worktree: mktemp and for-loop variables are known paths
check $P allow "wt: tmp=\$(mktemp -d) && … && rm -rf \"\$tmp\"" "$(payload_at "$WTO" 'tmp=$(mktemp -d) && echo x > "$tmp/a" && rm -rf "$tmp"')"
check $P allow "wt: for f in /tmp/a /tmp/b; do rm -f \"\$f\"; done" "$(payload_at "$WTO" 'for f in /tmp/op-a /tmp/op-b; do rm -f "$f"; done')"
check $P allow "wt: OUT=\$(mktemp); cp out.txt \"\$OUT\""   "$(payload_at "$WTO" 'OUT=$(mktemp); cp out.txt "$OUT"')"
TMPDIR="$TMP/scratch" check $P allow "wt: rm -rf \"\$TMPDIR\"/*" "$(payload_at "$WTO" 'rm -rf "$TMPDIR"/*')"
check $P allow "rm -rf \"\$(mktemp -d -t op)\"/x"          "$(payload_bash 'rm -rf "$(mktemp -d -t op)"/x')"
check $P block "for f in /tmp/a data; do rm -rf \"\$f\"; done" "$(payload_bash 'for f in /tmp/op-a data; do rm -rf "$f"; done')"
# confirmation pass: a loop left early isn't unrolled; mktemp under a TMPDIR the command sets is unknown
check $P block "for d in data /tmp; do break; done; rm -rf \$d" "$(payload_bash 'for d in data /tmp; do break; done; rm -rf $d')"
check $P block "for … do [ -e x ] || continue; done; rm -rf \$d" "$(payload_bash 'for d in data /tmp; do [ -e x ] || continue; done; rm -rf $d')"
check $P block "export TMPDIR=\$PWD/data; t=\$(mktemp -d); rm -rf \$t/../snapshots" "$(payload_bash 'export TMPDIR=$PWD/data; t=$(mktemp -d); rm -rf "$t/../snapshots"')"
check $P block "TMPDIR=\$PWD/data/snapshots; t=\$(mktemp -d); rm -rf \$t/.." "$(payload_bash 'TMPDIR=$PWD/data/snapshots; t=$(mktemp -d); rm -rf $t/..')"
check $P block "TMPDIR=data/snapshots/; rm -rf \$(mktemp -d)/.." "$(payload_bash 'TMPDIR=data/snapshots/; rm -rf $(mktemp -d)/..')"
check $P block "for f in \$UNSET; do rm -rf \"\$f\"; done" "$(payload_bash 'for f in $OP_UNSET_DIR; do rm -rf "$f"; done')"
check $P block "t=\$(mktemp -d data/x.XXXX); rm -rf \"\$t\"/.." "$(payload_bash 't=$(mktemp -d data/x.XXXX); rm -rf "$t"/..')"
check $P block "for d in snapshots; do rm -rf \"data/\$d\"; done" "$(payload_bash 'for d in snapshots; do rm -rf "data/$d"; done')"
# a redirect target this guard can't resolve is refused where data/ is
check $P block "echo x > \"\$(echo data)/snapshots/…\""   "$(payload_bash 'echo x > "$(echo data)/snapshots/s1/records.jsonl"')"
check $P block "echo x >> \"\$(echo data)/snapshots/…\""  "$(payload_bash 'echo x >> "$(echo data)/snapshots/s1/records.jsonl"')"
check $P block "echo x > \"\`echo data\`/snapshots/…\""   "$(payload_bash 'echo x > "`echo data`/snapshots/s1/records.jsonl"')"
check $P allow "echo x > /tmp/… 2>&1"                    "$(payload_bash 'echo x > /tmp/op-x 2>&1')"
# $(git rev-parse --show-toplevel) is the worktree top, not the directory the command runs in
check $P block "frontend: cd \"\$(…--show-toplevel)\" && rm -rf data" "$(payload_at "$REPO/frontend" 'cd "$(git rev-parse --show-toplevel)" && rm -rf data')"
# everyday commands stay allowed
check $P allow "rm -f \"\$TMPDIR/x\""                     "$(payload_bash 'rm -f "$TMPDIR/x"')"
# TMPDIR unset in the environment is '' in the agent's shell: `/x` is outside, `${TMPDIR}data` is data/
check_no_tmpdir $P allow "no TMPDIR: rm -f \"\$TMPDIR/x\"" "$(payload_bash 'rm -f "$TMPDIR/x"')"
check_no_tmpdir $P block "no TMPDIR: rm -rf \"\${TMPDIR}data\"" "$(payload_bash 'rm -rf "${TMPDIR}data"')"
# `~` with HOME unset is the passwd home, never '' (CI fix re-check). Read as '', `~/<repo path>/data` would be the
# repo's data/; read as the passwd home it is a path under it that holds no repo: allowed. And `unset HOME` in
# the command can't be told from `HOME=`, so its `~` is unknown and refused where data/ exists.
NO_SLASH="${REPO#/}"
check_no_home $P allow "no HOME: rm -rf ~/<repo path>/data/snapshots (passwd home)" "$(payload_bash "rm -rf ~/'$NO_SLASH'/data/snapshots")"
# TASK-067 final re-check: a cd's own VAR=val prefix never reaches its words (bash runs `cd ""` and stays put)
check $P block "X=/tmp cd \"\$X\"; rm -rf data" "$(payload_bash 'X=/tmp cd "$X"; rm -rf data')"
# TASK-067 final re-check: with HOME set, the HOME-'' pass reads ~ as '' (not the passwd home), as $HOME is
check $P block "HOME '' pass: rm -rf ~/<repo path>/data/snapshots" "$(payload_bash "rm -rf ~/'$NO_SLASH'/data/snapshots; echo \$PATH")"
check $P block "unset HOME; rm -f ~/op-x (unknown)" "$(payload_bash 'unset HOME; rm -f ~/op-x')"
check_no_home $P allow "no HOME: rm -f ~/op-not-a-repo-file" "$(payload_bash 'rm -f ~/op-not-a-repo-file')"
# a bare `cd` with no HOME: bash stays put, so `data` is still the repo's (unknown target: refused)
check_no_home $P block "no HOME: cd; rm -rf data" "$(payload_bash 'cd; rm -rf data')"
check $P block "HOME=; cd; rm -rf data" "$(payload_bash 'HOME=; cd; rm -rf data')"
# a HOME prefixed to the cd itself is the one it reads (bash and zsh)
check $P block "HOME=data cd; rm -rf snapshots" "$(payload_bash 'HOME=data cd; rm -rf snapshots')"
check $P block "HOME=/nonexistent cd; rm -rf data" "$(payload_bash 'HOME=/nonexistent cd; rm -rf data')"
# deliberate: the pass that reads HOME as '' leaves a bare cd unknown, so with a \$ in the command a relative
# write after it is refused where data/ exists
check $P block "cd; rm -rf build; echo \$PATH (deliberate)" "$(payload_bash 'cd; rm -rf build; echo $PATH')"
# the bypass the '' reading had: `cd ~` to the passwd home, then back to the repo's data/ by a relative path
FROM_HOME=$(python3 -c 'import os,pwd,sys; print(os.path.relpath(sys.argv[1], pwd.getpwuid(os.getuid()).pw_dir))' "$REPO")
check_no_home $P block "no HOME: cd ~ && rm -rf <repo rel>/data" "$(payload_bash "cd ~ && rm -rf '$FROM_HOME'/data")"
check $P allow "cd \"\$(…--show-toplevel)\" && make"      "$(payload_bash 'cd "$(git rev-parse --show-toplevel)" && make lint')"
check $R allow "git commit -m with braces, \$ and op-reviews" "$(payload_bash 'git commit -m "fix {a,b}: \$HOME and .git/op-reviews/abc"')"
check $R allow "gh pr create --body with braces, \$ and op-reviews" "$(payload_bash 'gh pr create --label no-learning --base dev --head mut --title t --body "{a,b} \$X .git/op-reviews/abc"')"
check $A allow "git commit -F - <<EOF (clean heredoc)"   "$(payload_bash "git commit -F - <<'EOF'
fix: {a,b} \$X op-reviews
EOF")"

echo "== TASK-156 rows (quoted substitutions, split trailers, HOME '' for every gate, ARG_MAX, format-patch -o)"
# the parsed words are scanned too: a trailer split by quoting is whole once bash reads it
check $A block "-m 'Co-Authored-By: Cl''aude <…anthr''opic.com>'" "$(payload_bash "git commit -m 'Co-Authored-By: Cl''aude <noreply@anthr''opic.com>'")"
# a command substitution inside double quotes, in backquotes or in an unquoted heredoc body is a command too
check $R block "x=\"\$(git push origin other2)\""           "$(payload_bash 'x="$(git push origin other2)"')"
check $P block "echo \`rm -rf data/snapshots\`"             "$(payload_bash 'echo `rm -rf data/snapshots`')"
check $P block "cat <<EOF with \$(rm -rf data/snapshots) in the body" "$(payload_bash 'cat <<EOF
$(rm -rf data/snapshots)
EOF')"
check $R block "x=\"\$(case y in y) git push origin other2;; esac)\"" "$(payload_bash 'x="$(case y in y) git push origin other2;; esac)"')"
check $P block "x=\"\$((rm -rf data/snapshots) )\" (a subshell, not arithmetic)" "$(payload_bash 'x="$((rm -rf data/snapshots) )"')"
check $A block "-m \$'Co-Authored-By: \\x43laude …'"        "$(payload_bash "git commit -m \$'Co-Authored-By: \\x43laude <x@y>'")"
check $A block "A=Cl; -m \"Co-Authored-By: \${A}aude …\""   "$(payload_bash 'A=Cl; git commit -m "Co-Authored-By: ${A}aude <x@y>"')"
check $A block "git config alias.ci commit; -m '…Cl''aude…' (unclassifiable)" "$(payload_bash "git config alias.ci commit; git commit -m 'Co-Authored-By: Cl''aude <noreply@anthr''opic.com>'")"
HOOK_INPUT='{}' check $P block "an inherited HOOK_INPUT is not read: rm -rf data/snapshots" "$(payload_bash 'rm -rf data/snapshots')"
check $R allow "git commit -m '… \`git push origin other2\`' (single quotes: text)" "$(payload_bash "git commit -m 'docs: \`git push origin other2\`'")"
check $R block "x=\"\$( (case y in y) :;; esac); git push origin other2 )\"" "$(payload_bash 'x="$( (case y in y) :;; esac); git push origin other2 )"')"
check $R block "x=\"\$(case a in a) case b in b) :;; esac;; c) :;; esac; git push origin other2)\"" "$(payload_bash 'x="$(case a in a) case b in b) :;; esac;; c) :;; esac; git push origin other2)"')"
check $R block "x=\"\$(if true; then case a in a) git push origin other2;; esac; fi)\"" "$(payload_bash 'x="$(if true; then case a in a) git push origin other2;; esac; fi)"')"
check $P block "echo \`case y in y) rm -rf data/snapshots;; esac\`" "$(payload_bash 'echo `case y in y) rm -rf data/snapshots;; esac`')"
check $P block "cat <<EOF with \$(case y in y) rm -rf data/snapshots;; esac)" "$(payload_bash 'cat <<EOF
$(case y in y) rm -rf data/snapshots;; esac)
EOF')"
# every case shape the security review probed (rounds 1-4): the body ends where bash ends it
check $P block "case form: 3-level nested case" "$(payload_bash 'x="$(case a in a) case b in b) case c in c) :;; esac;; esac;; d) :;; esac; rm -rf data/snapshots)"')"
check $P block "case form: case a in a) esac" "$(payload_bash 'x="$(case a in a) esac; rm -rf data/snapshots)"')"
check $P block "case form: … c) esac" "$(payload_bash 'x="$(case a in b) :;; c) esac; rm -rf data/snapshots)"')"
check $P block "case form: (a|b) pattern" "$(payload_bash 'x="$(case a in (a|b) :;; esac; rm -rf data/snapshots)"')"
check $P block "case form: case … <newline> in" "$(payload_bash 'x="$(case a
in a) :;; esac; rm -rf data/snapshots)"')"
check $P block "case form: f() case …" "$(payload_bash 'x="$(f() case a in a) :;; esac; f; rm -rf data/snapshots)"')"
check $P block "case form: while case …" "$(payload_bash 'x="$(while case a in a) false;; esac; do :; done; rm -rf data/snapshots)"')"
check $P block "case form: { case …; }" "$(payload_bash 'x="$({ case a in a) :;; esac; }; rm -rf data/snapshots)"')"
check $P block "case form: ( case … ) in a pattern" "$(payload_bash 'x="$(case a in a) ( case b in b) :;; esac );; esac; rm -rf data/snapshots)"')"
check $P block "case form: heredoc: nested case after a pattern" "$(payload_bash 'cat <<EOF
$(case a in a) case b in b) :;; esac;; c) :;; esac; rm -rf data/snapshots)
EOF')"
check $P allow "x=\"\$(case \"\$1\" in -h) …;; *) …;; esac)\" (a real case)" "$(payload_bash 'x="$(case "$1" in -h) echo h;; *) echo o;; esac)"; echo "$x"')"
check $P allow "echo \"\$((1<<n))\" (arithmetic, not a body)"  "$(payload_bash 'echo "$((1<<n))"')"
check $P allow "git commit -m \"\$(echo use case)\" (case as a word)" "$(payload_bash 'git commit -m "$(echo use case)"')"
check $R block "bash -c 'x=\"\$(git push origin other2)\"'"  "$(payload_bash "bash -c 'x=\"\$(git push origin other2)\"'")"
check $R block "eval 'x=\"\$(git push origin other2)\"'"     "$(payload_bash "eval 'x=\"\$(git push origin other2)\"'")"
check $R block "x=\"\$(echo \"\$(git push origin other2)\")\"" "$(payload_bash 'x="$(echo "$(git push origin other2)")"')"
check $A block "git config alias.ci commit; -m \"\$(echo '…Cl''aude…')\"" "$(payload_bash "git config alias.ci commit; git commit -m \"\$(echo 'Co-Authored-By: Cl''aude <noreply@anthr''opic.com>')\"")"
check $P block "x=\"\$(cd /tmp)\"; rm -rf data (a subshell's cd stays in it)" "$(payload_bash 'x="$(cd /tmp)"; rm -rf data')"
# a body ends where bash ends it: not at a `)` in its heredoc or in its own quotes
check $P allow "git commit -m \"\$(cat <<'EOF' … a) b … EOF)\"" "$(payload_bash "git commit -m \"\$(cat <<'EOF'
fix: a) b
EOF
)\"")"
check $P allow "x=\"\$(echo \"a)\")\"; echo ok"             "$(payload_bash 'x="$(echo "a)")"; echo ok')"
# the HOME '' pass starts afresh: a ref moved after the push in the first pass is no move before it
check $R allow "git push origin mut && git branch -f op-x mut; echo \$PATH" "$(payload_bash 'git push origin mut && git branch -f op-x mut; echo $PATH')"
# HOME '' in the agent's shell: `cd ~` stays put, for every gate (not only a push)
check $P block "cd ~ && rm -rf data"                        "$(payload_bash 'cd ~ && rm -rf data')"
# HOME is a repo whose HEAD is reviewed; with HOME '' the push runs where it is, on an unreviewed HEAD
g worktree add -q --detach "$TMP/wt156" other2 && approve
HOME="$REPO" check $R block "HOME=<reviewed repo>: cd ~ && git push origin HEAD:op-x (from other2)" "$(payload_at "$TMP/wt156" 'cd ~ && git push origin HEAD:op-x')"
# with HOME '' a `cd ~/<path>` to nothing is a failed cd: the shell stays (not an unknown directory)
HOME="$TMP" check $P allow "HOME=\$TMP: cd ~/<repo> && ls > op-out.txt" "$(payload_bash 'cd ~/"R&D repo" && ls > op-out.txt')"
printf 'x\n\n%s\n' "$TRAILER" > "$REPO/op-msg.txt"
check $A block "cd ~ && git commit -F op-msg.txt (a trailer)" "$(payload_bash 'cd ~ && git commit -F op-msg.txt')"
rm -f "$REPO/op-msg.txt"
# a payload past ARG_MAX reaches Python on stdin, and any exit but 0 or 2 (no python3 here) blocks
BIG=$(python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","cwd":sys.argv[1],"tool_input":{"command":"echo ok # " + "x" * 1100000}}))' "$REPO")
NOPY="$TMP/nopy"; mkdir -p "$NOPY"
for tool in bash dirname; do ln -s "$(command -v "$tool")" "$NOPY/$tool"; done
check_nopy() { local saved="$PATH"; PATH="$NOPY"; check "$@"; PATH="$saved"; }
for h in $A $R $P; do
  check "$h" allow "1.1 MB command (echo ok # …)"          "$BIG"
  check_nopy "$h" block "no python3: echo ok"                "$(payload_bash 'echo ok')"
done
# git format-patch writes its patches into -o/--output-directory, format.outputDirectory or where it runs
check $P block "git format-patch -o data/snapshots -1"      "$(payload_bash 'git format-patch -o data/snapshots -1')"
check $P block "git format-patch --output-dir=data/indexes/abc -1" "$(payload_bash 'git format-patch --output-dir=data/indexes/abc -1')"
check $P block "git -c format.outputDirectory=data/snapshots format-patch -1" "$(payload_bash 'git -c format.outputDirectory=data/snapshots format-patch -1')"
check $P block "git -C data/snapshots format-patch -1"      "$(payload_bash 'git -C data/snapshots format-patch -1')"
check $P block "GIT_CONFIG_* … git format-patch -1 (unreadable config)" "$(payload_bash 'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=format.outputDirectory GIT_CONFIG_VALUE_0=data/snapshots git format-patch -1')"
check $P block "git config format.outputDirectory …; git format-patch -1" "$(payload_bash 'git config format.outputDirectory data/snapshots; git format-patch -1')"
check $P allow "git format-patch -o /tmp/op-patches -1"    "$(payload_bash 'git format-patch -o /tmp/op-patches -1')"

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
if [ ! -x "$HOOKS/../../.venv/bin/ruff" ]; then pass=$((pass+1)); echo "  skip python formatting rows: no .venv (run uv sync)"
elif [ $rc -eq 0 ] && grep -q '^x = 1$' "$REPO/fmt_me.py"; then pass=$((pass+1)); echo "  ok   python file formatted in place (exit 0)"; else fail=$((fail+1)); echo "  FAIL python not formatted / nonzero exit ($rc)"; fi
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
