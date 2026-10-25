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
check $A allow "-F /dev/null reads as empty"          "$(payload_bash 'git commit -F /dev/null')"
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

echo "== TASK-243 rows (a generated-by footer naming an AI tool; bodies gh api and gh issue send from files)"
# The shared pattern: "generated with" or "generated by", but only before an AI or tool name (owner's ruling)
for footer in 'Generated by [Claude Code](https://claude.ai/code)' '_Generated by Claude_' 'generated by ChatGPT' \
              'generated by Copilot' 'generated by an AI' 'Generated by **Claude**' 'generated by GitHub Copilot' \
              'generated by gpt-4o' 'Generated by: Claude' 'generated with ChatGPT' 'Generated with  [Claude Code]' \
              'generated by an LLM' 'generated by GPT4' 'generated by Gemini' 'generated by OpenAI Codex' 'generated by the Claude API' \
              'generated by Codex' 'generated by Anthropic' 'generated by Bard' 'generated by _Claude_' 'generated by OpenAI' \
              'generated by Microsoft Copilot' 'generated by Google Gemini' 'generated by a LLM' 'Generated with ClaudeCode' \
              'Generated by Claude4' 'Generated-by: Claude Code' 'generated by [an AI]' \
              'generated by GPT4o' 'generated by GitHub  Copilot' 'generated by an  AI'; do
  check $A block "footer: $footer" "$(payload_bash "git commit -m \"x

$footer\"")"
done
for line in 'generated by changelog.py' 'generated by make changelog' 'generated by Dependabot' \
            'generated by GitHub Actions' 'generated with make openapi' 'generated by the Lezer generator' \
            'Generated by `.claude/scripts/roster_index.py`' 'generated by openapi-typescript 7.13.0' \
            'generated by airflow' 'generated with uv lock' 'generated by gptools' 'Generated-by: changelog.py' \
            'generated by Google Takeout' 'generated by a script'; do
  check $A allow "tooling text: $line" "$(payload_bash "git commit -m \"x

$line\"")"
done
printf 'Summary\n\n_Generated by [Claude Code](https://claude.ai/code)_\n' > "$TMP/footer.md"
printf 'Summary of the bump\n' > "$TMP/clean.md"
mkdir -p "$TMP/adir"
U=repos/o/r/issues/1/comments
check $A block "gh api -F body=@file (footer)"        "$(payload_bash "gh api -X POST $U -F body=@'$TMP/footer.md' --jq .id")"
check $A allow "gh api -F body=@file (clean)"         "$(payload_bash "gh api -X POST $U -F body=@'$TMP/clean.md' --jq .id")"
check $A block "gh api -F body=@file, no -X (POST)"   "$(payload_bash "gh api $U -F body=@'$TMP/footer.md'")"
check $A block "gh api --field body=@file"            "$(payload_bash "gh api $U --field body=@'$TMP/footer.md'")"
check $A block "gh api --field=body=@file"            "$(payload_bash "gh api $U --field=body=@'$TMP/footer.md'")"
check $A block "gh api -Fbody=@file (attached)"       "$(payload_bash "gh api $U -Fbody=@'$TMP/footer.md'")"
check $A block "gh api -F body=@file after -R"        "$(payload_bash "gh -R o/r api $U -F body=@'$TMP/footer.md'")"
check $A block "gh api -F body=@missing (fail closed)" "$(payload_bash "gh api $U -F body=@'$TMP/nope.md'")"
check $A block "gh api -F body=@directory"            "$(payload_bash "gh api $U -F body=@'$TMP/adir'")"
check $A block "gh api -F body=@\$UNSET"              "$(payload_bash 'gh api repos/o/r/issues/1/comments -F body=@"$NOPE_UNSET/x.md"')"
check $A allow "gh api -F body=@\$VAR (set, clean)"   "$(payload_bash "F='$TMP/clean.md'; gh api $U -F body=@\"\$F\"")"
check $A block "gh api -F body=@\$VAR (set, footer)"  "$(payload_bash "F='$TMP/footer.md'; gh api $U -F body=@\"\$F\"")"
check $A block "gh api -F body=@- < file"             "$(payload_bash "gh api $U -F body=@- < '$TMP/footer.md'")"
check $A block "gh api -F body=@- < missing"          "$(payload_bash "gh api $U -F body=@- < '$TMP/nope.md'")"
check $A allow "gh api -F count=3 (no file)"          "$(payload_bash "gh api $U -F count=3")"
check $A block "gh api -f body=<footer>"              "$(payload_bash "gh api $U -f body='Generated by Claude Code'")"
check $A block "gh api --raw-field body=<footer>"     "$(payload_bash "gh api $U --raw-field 'body=_Generated by Claude_'")"
check $A block "gh api --input file"                  "$(payload_bash "gh api -X PATCH repos/o/r/pulls/1 --input '$TMP/footer.md'")"
check $A block "gh api --input=file"                  "$(payload_bash "gh api -X PATCH repos/o/r/pulls/1 --input='$TMP/footer.md'")"
check $A block "gh api --input file, no -X (POST)"    "$(payload_bash "gh api repos/o/r/pulls/1 --input '$TMP/footer.md'")"
check $A allow "gh api --input file (clean)"          "$(payload_bash "gh api -X PATCH repos/o/r/pulls/1 --input '$TMP/clean.md'")"
check $A block "gh api --input missing"               "$(payload_bash "gh api -X PATCH repos/o/r/pulls/1 --input '$TMP/nope.md'")"
check $A block "gh api --input - < file"              "$(payload_bash "gh api -X PATCH repos/o/r/pulls/1 --input - < '$TMP/footer.md'")"
check $A block "gh api -X DELETE with footer text"    "$(payload_bash "gh api -X DELETE $U/9 -H 'X-Note: Generated by Claude'")"
check $A block "gh api --method PATCH with footer"    "$(payload_bash "gh api --method PATCH $U/9 -H 'X-Note: Generated by Claude'")"
check $A allow "gh api GET read of a footer"          "$(payload_bash "gh api $U/9 --jq .body | grep -c 'Generated by Claude'")"
check $A allow "gh api -X GET read of a footer"       "$(payload_bash "gh api -X GET $U/9 --jq .body | grep -c 'Generated by Claude'")"
check $A block "gh issue comment --body-file (footer)" "$(payload_bash "gh issue comment 1 --body-file '$TMP/footer.md'")"
check $A allow "gh issue comment --body-file (clean)"  "$(payload_bash "gh issue comment 1 --body-file '$TMP/clean.md'")"
check $A block "gh issue create -F (footer)"          "$(payload_bash "gh issue create -t t -F '$TMP/footer.md'")"
check $A block "gh issue edit --body-file=missing"    "$(payload_bash "gh issue edit 1 --body-file='$TMP/nope.md'")"
check $A block "gh issue comment --body footer"       "$(payload_bash "gh issue comment 1 --body 'Generated by Claude Code'")"
check $A block "gh issue close --comment footer"      "$(payload_bash "gh issue close 1 --comment 'Generated by Claude Code'")"
check $A block "gh issue reopen --comment footer"     "$(payload_bash "gh issue reopen 1 --comment 'Generated by Claude Code'")"
check $A block "gh pr close --comment footer"         "$(payload_bash "gh pr close 1 --comment 'Generated by Claude Code'")"
check $A block "gh pr reopen --comment footer"        "$(payload_bash "gh pr reopen 1 --comment 'Generated by Claude Code'")"
check $A allow "gh issue view is not a write"         "$(payload_bash "gh issue view 1 --json body | grep 'Generated by Claude'")"
check $A block "gh pr comment --body-file (footer)"   "$(payload_bash "gh pr comment 1 --body-file '$TMP/footer.md'")"
check $A block "gh pr comment --body-file missing"    "$(payload_bash "gh pr comment 1 --body-file '$TMP/nope.md'")"
check $A block "gh pr edit -F directory"              "$(payload_bash "gh pr edit 1 -F '$TMP/adir'")"
check $A block "gh release create --notes-file missing" "$(payload_bash "gh release create v0.1.0 --notes-file '$TMP/nope.md'")"
check $A block "written in the same call (cp && send)" "$(payload_bash "cp '$TMP/footer.md' '$TMP/later.md' && gh pr comment 1 --body-file '$TMP/later.md'")"
check $A block "git commit -F missing (fail closed)"  "$(payload_bash "git commit -F '$TMP/nope.md'")"
check $A block "git commit -F - < missing"            "$(payload_bash "git commit -F - < '$TMP/nope.md'")"
check $A allow "git commit -F /dev/null still allowed" "$(payload_bash 'git commit -F /dev/null')"
python3 -c 'import sys; open(sys.argv[1], "w").write("x" * 1_000_001)' "$TMP/big.md"
check $A block "gh api -F body=@file over 1 MB"       "$(payload_bash "gh api $U -F body=@'$TMP/big.md'")"
python3 -c 'import sys; open(sys.argv[1], "w").write("x" * 1_000_000)' "$TMP/edge.md"
check $A allow "gh api -F body=@file of exactly 1 MB" "$(payload_bash "gh api $U -F body=@'$TMP/edge.md'")"
printf 'x\n' > "$TMP/locked.md"; chmod 000 "$TMP/locked.md"
if [ -r "$TMP/locked.md" ]; then pass=$((pass+1)); echo "  ok   (skipped: running as a user who can read a mode-000 file)"
else check $A block "gh api -F body=@unreadable file" "$(payload_bash "gh api $U -F body=@'$TMP/locked.md'")"; fi
chmod 600 "$TMP/locked.md"
check $A block "any < missing in a writer's call"     "$(payload_bash "wc -l < '$TMP/nope.md'; gh pr comment 1 --body ok")"
printf 'x\n\nGenerated by `Claude`\n' > "$TMP/tick.md"
check $A block "footer: a backquoted name (file)"     "$(payload_bash "git commit -F '$TMP/tick.md'")"
check $A block "gh issue new --body footer (alias)"   "$(payload_bash "gh issue new -t t --body 'Generated by Claude Code'")"
check $A block "gh issue new -F footer file (alias)"  "$(payload_bash "gh issue new -t t -F '$TMP/footer.md'")"
mkdir -p "$TMP/home"; cp "$TMP/clean.md" "$TMP/home/clean.md"
TMPDIR="$TMP/home" check $A allow "-F \"\$TMPDIR/x\" (clean, exists)" "$(payload_bash 'git commit --amend -F "$TMPDIR/clean.md"')"
HOME="$TMP/home" check $A allow "--body-file ~/x (clean, exists)" "$(payload_bash 'gh issue comment 1 --body-file ~/clean.md')"
cp "$TMP/footer.md" "$TMP/home/footer.md"
HOME="$TMP/home" check $A block "--body-file ~/x (footer)"        "$(payload_bash 'gh issue comment 1 --body-file ~/footer.md')"
check $A block "cp && cat later | --body-file -"      "$(payload_bash "cp '$TMP/footer.md' '$TMP/later2.md' && cat '$TMP/later2.md' | gh pr comment 1 --body-file -")"
check $A block "cp && --body \"\$(cat later)\""      "$(payload_bash "cp '$TMP/footer.md' '$TMP/later2.md' && gh pr comment 1 --body \"\$(cat '$TMP/later2.md')\"")"
check $A block "cp && -f body=\"\$(< later)\""       "$(payload_bash "cp '$TMP/footer.md' '$TMP/later2.md' && gh api $U -f body=\"\$(< '$TMP/later2.md')\"")"
check $A block "git commit -m \"\$(cat missing)\""     "$(payload_bash "git commit -m \"\$(cat '$TMP/nope.md')\"")"
check $A block "jq builds the --input - body (footer)" "$(payload_bash "jq -Rs '{body: .}' '$TMP/footer.md' | gh api -X PATCH repos/o/r/pulls/1 --input -")"
check $A block "jq builds the body=@- body (clean)"   "$(payload_bash "jq -r .x '$TMP/clean.md' | gh api $U -F body=@-")"
check $A allow "printf feeds --input -"               "$(payload_bash "printf '{\"body\":\"ok\"}' | gh api -X PATCH repos/o/r/pulls/1 --input -")"
check $A allow "git add, then --body-file - heredoc"  "$(payload_bash "git add '$TMP/clean.md' && gh pr comment 1 --body-file - <<'EOF'
ok
EOF")"
check $A allow "jq on a file, git commit -F - heredoc" "$(payload_bash "jq . '$TMP/clean.md' >/dev/null; git commit -F - <<'EOF'
ok
EOF")"
check $A block "gh api -iF body=@file (bundled -i)"   "$(payload_bash "gh api $U -iF body=@'$TMP/footer.md'")"
check $A block "gh api -iiF body=@file"               "$(payload_bash "gh api $U -iiF body=@'$TMP/footer.md'")"
check $A allow "gh api -X GET search -f q=<footer>"   "$(payload_bash "gh api -X GET search/issues -f q='\"generated by claude\" repo:o/r'")"
check $A allow "gh api --method get -F q=<footer>"    "$(payload_bash "gh api --method get search/issues -F q='generated by claude'")"
check $A block "gh api -X GET --input footer file"    "$(payload_bash "gh api -X GET repos/o/r --input '$TMP/footer.md'")"
check $A block "gh api -X GET -X POST -f footer"      "$(payload_bash "gh api -X GET -X POST $U -f body='Generated by Claude'")"
# round 2: a gh writer's own heredoc, herestring or < file is its stdin (scanned), so nothing else feeds it
check $A allow "python3 file && --body-file - heredoc" "$(payload_bash "python3 '$TMP/clean.md' && gh pr comment 1 --body-file - <<'EOF'
ok
EOF")"
check $A allow "wc file && --body-file - <<< text"    "$(payload_bash "wc -l '$TMP/clean.md' && gh pr comment 1 --body-file - <<< hello")"
check $A allow "wc file && --body-file - < clean"     "$(payload_bash "wc -l '$TMP/clean.md' && gh pr comment 1 --body-file - < '$TMP/clean.md'")"
check $A block "git diff --no-index | --body-file -"  "$(payload_bash "git diff --no-index /dev/null '$TMP/footer.md' | gh pr comment 1 --body-file -")"
check $A block "git log -p | gh api -F body=@-"       "$(payload_bash "git log -p -- '$TMP/footer.md' | gh api $U -F body=@-")"
check $A allow "a descriptor copy 0<&3 is no file"    "$(payload_bash 'git commit -m hi 0<&3')"
check $A allow "a descriptor copy <&- is no file"     "$(payload_bash 'gh pr comment 1 --body ok <&-')"
check $A block "gh issue -R o/r create (flag between)" "$(payload_bash "gh issue -R o/r create -t t --body-file '$TMP/footer.md'")"
check $A block "gh pr -R o/r comment --body-file f"  "$(payload_bash "gh pr -R o/r comment 1 --body-file '$TMP/footer.md'")"
check $A allow "gh issue new --body-file clean"      "$(payload_bash "gh issue new -t t --body-file '$TMP/clean.md'")"
check $A allow "gh api -R-like word after api kept"  "$(payload_bash "gh api repos/o/r/pulls/1 --jq .body")"
check $A block "gh pr --repo o/r comment (between)"   "$(payload_bash "gh pr --repo o/r comment 1 --body-file '$TMP/footer.md'")"
check $A block "--body-file <(awk …) (no value seen)" "$(payload_bash "gh pr comment 1 --body-file <(awk 1 '$TMP/footer.md')")"
check $A block "gh api -F with no value"              "$(payload_bash "gh api -X POST $U -F")"
check $A block "a body file relative to the cwd"      "$(payload_at "$TMP" "gh pr comment 1 --body-file footer.md")"
check $A allow "relative clean body file"             "$(payload_at "$TMP" "gh pr comment 1 --body-file clean.md")"
check $A block "-F relative to the cwd after cd"      "$(payload_at "$TMP" "cd adir && gh api $U -F body=@../footer.md")"
printf 'x\n\nGenerated by Copilot' > "$TMP/noeol.md"
check $A block "a footer with no final newline (file)" "$(payload_bash "gh pr comment 1 --body-file '$TMP/noeol.md'")"
check_cmd err "commit-msg: a footer with no final newline" bash "$HOOKS/../../.githooks/commit-msg" "$TMP/noeol.md"
check $A block "--body-file <(jq …) (no value seen)"  "$(payload_bash "gh pr comment 1 --body-file <(jq -r . '$TMP/footer.md')")"
check $A block "git commit -F <(jq …)"                "$(payload_bash "git commit -F <(jq -r . '$TMP/footer.md')")"
cp "$TMP/clean.md" "$TMP/body.md"
check $A block "cp onto an existing body, then send"  "$(payload_bash "cp '$TMP/footer.md' '$TMP/body.md' && gh pr comment 1 --body-file '$TMP/body.md'")"
check $A block "> onto an existing body, then -F @"   "$(payload_bash "jq -Rs . '$TMP/footer.md' > '$TMP/body.md' && gh api $U -F body=@'$TMP/body.md'")"
check $A block "| tee an existing body, then send"    "$(payload_bash "jq -r . '$TMP/footer.md' | tee '$TMP/body.md' >/dev/null; gh issue comment 1 --body-file '$TMP/body.md'")"
cp "$TMP/clean.md" "$TMP/adir/footer.md"
check $A block "cp into a directory, then send"       "$(payload_bash "cp '$TMP/footer.md' '$TMP/adir' && gh pr comment 1 --body-file '$TMP/adir/footer.md'")"
rm -f "$TMP/adir/footer.md"
# each walk's writes count only before that walk's own sender: with HOME '' `cd ~` stays, so only that walk's printf
# writes $REPO/op-243w.md; the first walk still sends it unwritten and missing, so it is refused (TASK-261)
HOME="$TMP/home" check $A block "cd ~; printf > f; send \$REPO/f: written only in the HOME '' walk" "$(payload_bash "cd ~; printf 'clean\\n' > op-243w.md; gh issue comment 1 --body-file '$REPO/op-243w.md'")"
check $A allow "printf > f; send f (one walk: the inline write is the text sent)" "$(payload_bash "printf 'clean\\n' > '$REPO/op-243w.md'; gh issue comment 1 --body-file '$REPO/op-243w.md'")"
# a body written by text in the command itself is scanned as that text (coordinator, TASK-243)
check $A block "cat > f <<'EOF' footer, then send f"  "$(payload_bash "cat > '$TMP/new1.md' <<'EOF'
Generated by Claude Code
EOF
gh pr comment 1 --body-file '$TMP/new1.md'")"
check $A allow "cat > f <<'EOF' clean, then send f"   "$(payload_bash "cat > '$TMP/new1.md' <<'EOF'
Summary
EOF
gh pr comment 1 --body-file '$TMP/new1.md'")"
check $A allow "cat <<EOF > f (no \$), then -F @f"     "$(payload_bash "cat <<EOF > '$TMP/new2.md'
Summary
EOF
gh api $U -F body=@'$TMP/new2.md'")"
check $A block "cat <<EOF with a \$VAR, then send"     "$(payload_bash "cat > '$TMP/new3.md' <<EOF
\$BODY_FROM_ENV
EOF
gh pr comment 1 --body-file '$TMP/new3.md'")"
check $A allow "printf clean > f && -F body=@f"       "$(payload_bash "printf 'ok\\n' > '$TMP/new4.md' && gh api $U -F body=@'$TMP/new4.md'")"
check $A block "printf footer > f && -F body=@f"      "$(payload_bash "printf '_Generated by Claude_\\n' > '$TMP/new4.md' && gh api $U -F body=@'$TMP/new4.md'")"
check $A block "printf \"\$UNKNOWN\" > f, then send"     "$(payload_bash "printf '%s' \"\$BODY_FROM_ENV\" > '$TMP/new5.md' && gh pr comment 1 --body-file '$TMP/new5.md'")"
check $A allow "tee f <<< clean, then send"           "$(payload_bash "tee '$TMP/new6.md' <<< 'ok' >/dev/null; gh issue comment 1 --body-file '$TMP/new6.md'")"
check $A block "printf | tee f (a pipe), then send"   "$(payload_bash "printf ok | tee '$TMP/new7.md'; gh issue comment 1 --body-file '$TMP/new7.md'")"
cp "$TMP/footer.md" "$TMP/app.md"
check $A block ">> clean onto a footer file, then send" "$(payload_bash "printf 'more\\n' >> '$TMP/app.md' && gh pr comment 1 --body-file '$TMP/app.md'")"
cp "$TMP/clean.md" "$TMP/app2.md"
check $A allow ">> clean onto a clean file, then send" "$(payload_bash "printf 'more\\n' >> '$TMP/app2.md' && gh pr comment 1 --body-file '$TMP/app2.md'")"
check $A block "send f, then overwrite it (read as is)" "$(payload_bash "gh pr comment 1 --body-file '$TMP/footer.md'; printf ok > '$TMP/footer.md'")"
check $A block "an unresolvable write target, then send" "$(payload_bash "jq . '$TMP/clean.md' > \"\$NOPE_UNSET/o.md\"; gh pr comment 1 --body-file '$TMP/clean.md'")"
cp "$TMP/footer.md" "$TMP/app3.md"
check $A block "tee -ia appends: the old text is read" "$(payload_bash "tee -ia '$TMP/app3.md' <<< 'x' >/dev/null; gh pr comment 1 --body-file '$TMP/app3.md'")"
check $A allow "commit piped to tee \"log-\$(date)\""   "$(payload_bash 'git commit -m "fix: tidy" 2>&1 | tee "commit-$(date +%s).log"')"
check $A allow "commit > \"\$LOGFILE\" (nothing sent)"  "$(payload_bash 'git commit -m "fix: tidy" > "$LOGFILE_UNSET" 2>&1')"
check $A block "an unparseable call sending a file"    "$(payload_bash "gh pr comment 1 --body-file '$TMP/clean.md' --title 'unclosed")"
check $A block "an unparseable gh api -F body=@"      "$(payload_bash "gh api $U -F body=@'$TMP/clean.md' -f x='unclosed")"
check $A block "an unparseable call reading \$(cat f)"  "$(payload_bash "git commit -m \"\$(cat '$TMP/clean.md')\" --author 'unclosed")"
check $A block "\$(cat f) body, unclosed quote next line" "$(payload_bash "gh pr comment 1 --body \"\$(cat '$TMP/clean.md')\"
echo 'unclosed")"
check $A block "\$(< f) body, unclosed quote next line" "$(payload_bash "gh pr comment 1 --body \"\$(< '$TMP/clean.md')\"
echo 'unclosed")"
check $A block "an unparseable writer sending no file (TASK-266)" "$(payload_bash "gh pr comment 1 --body 'ok' --title 'unclosed")"
check $A block "quoted and unquoted heredocs with \$"  "$(payload_bash "cat > '$TMP/new9.md' <<EOF
\$GH_FOOTER_UNSET
EOF
cat <<'EOF'
x
EOF
gh pr comment 1 --body-file '$TMP/new9.md'")"
check $A allow "<<-'EOF' in a call with a backquote"  "$(payload_bash "cat > '$TMP/new10.md' <<-'EOF'
Summary
EOF
gh pr comment 1 --body-file '$TMP/new10.md' --title \"\\\`x\\\`\"")"
check $A allow "<<< then a quoted heredoc with \$"     "$(payload_bash "cat > '$TMP/new11.md' <<'EOF'
\$NOT_EXPANDED
EOF
wc -l <<< x; gh pr comment 1 --body-file '$TMP/new11.md'")"
check $A block "{ jq f; } > clean, then send"         "$(payload_bash "{ jq -r . '$TMP/footer.md'; } > '$TMP/clean.md' && gh pr comment 1 --body-file '$TMP/clean.md'")"
check $A block "( jq f ) > clean, then send"          "$(payload_bash "( jq -r . '$TMP/footer.md' ) > '$TMP/clean.md' && gh pr comment 1 --body-file '$TMP/clean.md'")"
cp "$TMP/footer.md" "$TMP/stale.md"
check $A block "false && printf > f: f is read too"   "$(payload_bash "false && printf 'ok\\n' > '$TMP/stale.md'; gh pr comment 1 --body-file '$TMP/stale.md'")"
check $A block "if …; then cat > f <<'EOF'; f read too" "$(payload_bash "if test -e '$TMP/nothere'; then cat > '$TMP/stale.md' <<'EOF'
ok
EOF
fi; gh pr comment 1 --body-file '$TMP/stale.md'")"
check $A block "tee f <<< \"\$UNKNOWN\", then send"     "$(payload_bash "tee '$TMP/new12.md' <<< \"\$BODY_FROM_ENV\" >/dev/null; gh issue comment 1 --body-file '$TMP/new12.md'")"
check $A block "unquoted heredoc + a quoted one later" "$(payload_bash "cat > '$TMP/new13.md' <<EOF
\$BODY_FROM_ENV
EOF
gh pr comment 1 --body-file '$TMP/new13.md'
git commit -F - <<'EOF'
msg
EOF")"
check $A allow "commit -F clean > \"\$LOG\" (write after)" "$(payload_bash "git commit -F '$TMP/clean.md' > \"\$COMMIT_LOG_UNSET\" 2>&1")"
check $A allow "pr create … | tee \"pr-\$(date).log\""   "$(payload_bash "gh pr create --body-file '$TMP/clean.md' 2>&1 | tee \"pr-\$(date +%s).log\"")"
check $A block "send footer | tee log (write after)"  "$(payload_bash "gh pr comment 1 --body-file '$TMP/footer.md' 2>&1 | tee \"pr-\$(date +%s).log\"")"
check $A allow "a quoted heredoc body that mentions <<" "$(payload_bash "cat > '$TMP/new14.md' <<'EOF'
Summary: run \\\`cat <<EOF\\\` here; \$HOME stays literal
EOF
gh pr create --body-file '$TMP/new14.md'")"
check $A allow "a quoted heredoc body: x << 2 shifts" "$(payload_bash "cat > '$TMP/new15.md' <<'EOF'
\\\`x << 2\\\` is a shift
EOF
gh pr create --body-file '$TMP/new15.md'")"
check $A allow "send clean, then jq over it (after)"  "$(payload_bash "gh pr comment 1 --body-file '$TMP/clean.md'; jq . '$TMP/footer.md' > '$TMP/clean.md'")"
check $A allow "printf | gh release create asset --notes-file -" "$(payload_bash "printf 'Release notes\\n' | gh release create v9.9.9 '$TMP/clean.md' --notes-file -")"
check $A allow "wc file && printf | git commit -F -"  "$(payload_bash "wc -l '$TMP/clean.md' && printf 'fix: tidy\\n' | git commit -F -")"
check $A block "a quoted <<'EOF' in a string, then an unquoted heredoc" "$(payload_bash "echo \"<<'EOF'\"
cat > '$TMP/new16.md' <<EOF
\$ATTRIB_FOOTER_UNSET
EOF
gh pr create --body-file '$TMP/new16.md'")"
check $A allow "-m mentions <<EOF, then a quoted heredoc with \$" "$(payload_bash "git commit -m 'docs: explain <<EOF heredocs'
cat > '$TMP/new17.md' <<'EOF'
\$HOME stays literal
EOF
gh pr create --body-file '$TMP/new17.md'")"
cp "$TMP/clean.md" "$TMP/rw.md"
check $A block "cat f; jq > f; send f (last sender)"  "$(payload_bash "cat '$TMP/rw.md'; jq -r . '$TMP/footer.md' > '$TMP/rw.md'; gh pr comment 1 --body-file '$TMP/rw.md'")"
check $A block "<<-'EOF' tab-closed, then unquoted \$" "$(payload_bash "cat <<-'EOF'
	x
	EOF
cat > '$TMP/new18.md' <<EOF
\$ATTRIB_FOOTER_UNSET
EOF
gh pr create --body-file '$TMP/new18.md'")"
check $A allow "<<\\EOF is quoted"                     "$(payload_bash "cat > '$TMP/new19.md' <<\\EOF
Summary for \$HOME
EOF
gh pr create --body-file '$TMP/new19.md'")"
check $A block "<<1 (a delimiter the scan can't read) with \$" "$(payload_bash "cat > '$TMP/new20.md' <<1
\$ATTRIB_FOOTER_UNSET
1
gh pr create --body-file '$TMP/new20.md'")"
# a `case` in a substitution makes cmdparse join the text after it out of context; with the join cache evicted (200
# substitutions) that must not record the string's <<'Q' as a quoted heredoc (review round 8)
PAD=$(for i in $(seq 0 199); do printf '"$(echo case %s)" ' "$i"; done)
check $A block "<<1 with \$, a <<'Q' string, 200 case substs" "$(payload_bash "X=\"\$(echo a case b)\"; Y=\" <<'Q' \"; cat > '$TMP/new21.md' <<1
\$ATTRIB_FOOTER_UNSET
1
: $PAD
gh pr create --body-file '$TMP/new21.md'")"
cp "$TMP/clean.md" "$TMP/two.md"
check $A allow "send f, jq > f, send another (between)" "$(payload_bash "gh pr comment 1 --body-file '$TMP/two.md'; jq -r . '$TMP/footer.md' > '$TMP/two.md'; gh pr comment 2 --body-file '$TMP/clean.md'")"
check $A allow "cat > f <<'EOF' read by \$(cat f)"     "$(payload_bash "cat > '$TMP/new8.md' <<'EOF'
Summary
EOF
git commit -m \"\$(cat '$TMP/new8.md')\"")"
check $A allow "cp elsewhere, send another body"      "$(payload_bash "cp '$TMP/footer.md' '$TMP/other.md' && gh pr comment 1 --body-file '$TMP/clean.md'")"
check $A allow "-F /dev/null with >/dev/null"         "$(payload_bash 'git commit -F /dev/null >/dev/null')"
check $A allow "jq > /dev/null, then -F /dev/null"    "$(payload_bash "jq . '$TMP/clean.md' > /dev/null; git commit -F /dev/null")"
# known limitation (header): inline interpreter code that opens a file is not modelled; CI's PR-body check is the backstop
check $A allow "known gap: python3 -c open() | --input -" "$(payload_bash "python3 -c 'print(1)' | gh api -X PATCH repos/o/r/pulls/1 --input -")"

# commit-msg uses the same pattern (an editor commit never reaches the PreToolUse hook)
CM="$HOOKS/../../.githooks/commit-msg"
printf 'x\n\n_Generated by [Claude Code](https://claude.ai/code)_\n' > "$TMP/cm-bad"
printf 'x\n\nGenerated by `make changelog`\n' > "$TMP/cm-ok"
check_cmd err "commit-msg refuses a generated-by footer" bash "$CM" "$TMP/cm-bad"
check_cmd ok  "commit-msg passes generated-by tooling" bash "$CM" "$TMP/cm-ok"
# One pattern in every place it lives (no-ai-attribution skill): the hook, commit-msg, pr-gates.yml, the
# merge-queue gate and the changelog's check. The program is read into a variable first: bash 3.2 (macOS's
# /bin/bash) misparses a heredoc inside $(…) whose body has a `(` (TASK-267).
IFS= read -r -d '' SAME_PATTERN <<'PY' || true
import re, sys
from pathlib import Path
root = Path(sys.argv[1])
files = [".claude/hooks/block-ai-attribution.sh", ".githooks/commit-msg", ".github/workflows/pr-gates.yml",
         ".claude/scripts/merge_group_gate.py", ".claude/scripts/changelog.py"]
found = {f: re.findall(r"""(?:r"|')(co-authored-by[^"']*)["']""", (root / f).read_text()) for f in files}
bad = [f"{f}: {len(v)} copies" for f, v in found.items() if len(v) != 1]
if not bad and len({v[0] for v in found.values()}) != 1:
    bad = [f"{f}: {v[0]}" for f, v in found.items()]
print("\n".join(bad))
sys.exit(1 if bad else 0)
PY
if out=$(python3 -c "$SAME_PATTERN" "$HOOKS/../.."); then pass=$((pass+1)); echo "  ok   the attribution pattern is identical in all five places"
else fail=$((fail+1)); echo "  FAIL the attribution pattern differs: $out"; fi

echo "== require-review.sh"
R=require-review.sh
check $R block "push with no review record"           "$(payload_bash 'git push -u origin feat')"
check $R block "gh pr --repo o/r create (flag between)" "$(payload_bash 'gh pr --repo o/r create --base dev --fill')"
check $R block "gh pr --repo o/r comment --body <record path> (as dev)" "$(payload_bash 'gh pr --repo o/r comment 1 --body .git/op-reviews/abc')"
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

echo "== record-review.py --attest (a fake gh; --pr reads over REST, TASK-213)"
mkdir -p "$TMP/ghbin"
# the fake gh: logs each call; `api repos/o/r/pulls/5` prints $TMP/pr5.json; `pr view` fails as $GH_VIEW says
cat > "$TMP/ghbin/gh" <<EOF
#!/bin/sh
printf '%s\n' "\$*" >> "$TMP/gh.log"
case "\$1 \$2" in
  "api repos/o/r/pulls/5") cat "$TMP/pr5.json"; exit 0 ;;
  "api graphql") if [ -n "\${GH_GQL-}" ]; then echo "\$GH_GQL" >&2; exit 1; fi; echo '{"data":{"viewer":{"login":"m"}}}'; exit 0 ;;
  "api -X") exit 0 ;;
  "pr view") echo "\$GH_VIEW" >&2; exit 1 ;;
esac
exit 3
EOF
chmod +x "$TMP/ghbin/gh"
HEADSHA=$(g rev-parse HEAD)
OTHERSHA=$(printf 'f%.0s' $(seq 40))
# attest_case <want: ok|err> <PATCH sent: yes|no> <message (grep -E)> <label> <pr state|garbage> <pr head> [args...]
attest_case() {
  local want="$1" patch="$2" msg="$3" label="$4" state="$5" prhead="$6" got sent; shift 6
  if [ "$state" = garbage ]; then printf 'not json' > "$TMP/pr5.json"
  else printf '{"state":"%s","head":{"sha":"%s"},"body":"Summary"}' "$state" "$prhead" > "$TMP/pr5.json"; fi
  : > "$TMP/gh.log"
  if (cd "$REPO" && env PATH="$TMP/ghbin:$PATH" GH_VIEW="${GH_VIEW-}" GH_GQL="${GH_GQL-}" python3 "$RECORD" APPROVE "$TMP/none.md" "$@" >"$TMP/attest.out" 2>&1); then got=ok; else got=err; fi
  if grep -q '^api -X PATCH' "$TMP/gh.log"; then sent=yes; else sent=no; fi
  if [ "$got" = "$want" ] && [ "$sent" = "$patch" ] && grep -Eq -- "$msg" "$TMP/attest.out"; then
    pass=$((pass+1)); printf '  ok   %-24s %-60s -> %s\n' "script" "$label" "$got"
  else fail=$((fail+1)); printf '  FAIL %-24s %-60s -> %s, PATCH %s: %s\n' "script" "$label" "$got" "$sent" "$(cat "$TMP/attest.out")"; fi
}
attest_case ok  yes "PR #5 body attested"              "--pr: an open PR at HEAD is attested"     open "$HEADSHA" --attest --pr 5 --repo o/r
if grep -q "op-review: $HEADSHA APPROVE" "$TMP/gh.log" && grep -q '^api -X PATCH repos/o/r/pulls/5' "$TMP/gh.log"; then pass=$((pass+1)); echo "  ok   --pr: the PATCH carries the attestation for HEAD"
else fail=$((fail+1)); echo "  FAIL --pr: no PATCH with the attestation: $(cat "$TMP/gh.log")"; fi
attest_case err no  "head is f{10}, not HEAD"         "--pr: a PR at another head is refused"   open "$OTHERSHA" --attest --pr 5 --repo o/r
attest_case err no  "is closed, not open"             "--pr: a closed PR is refused"            closed "$HEADSHA" --attest --pr 5 --repo o/r
attest_case err no  "isn't a pull request"            "--pr: an answer that isn't a PR is refused" garbage "$HEADSHA" --attest --pr 5 --repo o/r
GH_VIEW="no pull requests found for branch \"feat\"" attest_case ok no "no open PR for this branch yet" "no PR yet: told to attest after gh pr create" open "$HEADSHA" --attest
GH_VIEW="GitHub GraphQL is not available from Claude Code sessions" attest_case err no "could not find this branch's PR .*--pr <n> --repo" "gh pr view failing otherwise is an error" open "$HEADSHA" --attest
attest_case err no  "--pr needs --repo"               "--pr without --repo is refused"          open "$HEADSHA" --attest --pr 5
attest_case err no  "only apply with --attest"        "--pr without --attest is refused"        open "$HEADSHA" --pr 5 --repo o/r
attest_case err no  "--repo only applies with --pr"   "--repo without --pr is refused"          open "$HEADSHA" --attest --repo o/r
STORE="$(cd "$REPO" && git rev-parse --path-format=absolute --git-common-dir)/op-reviews"
MARK="$(dirname "$STORE")/op-no-dep-code"
: > "$MARK"   # prs.py preflight's cloud marker: notify-only (decision-048, 2026-10-16)
rm -f "$STORE/$HEADSHA"
attest_case err no  "op-no-dep-code is there: a cloud /dependabot-review run is notify-only" "--attest in a cloud clone is refused" open "$HEADSHA" --attest --pr 5 --repo o/r
if [ ! -e "$STORE/$HEADSHA" ]; then pass=$((pass+1)); echo "  ok   --attest in a cloud clone writes no record (refused before anything is written)"
else fail=$((fail+1)); echo "  FAIL --attest in a cloud clone wrote a record"; fi
attest_case ok  no  "recorded APPROVE"                "a record without --attest in a cloud clone is still written" open "$HEADSHA"
rm -f "$MARK"
GH_GQL="gh: GitHub GraphQL is not available from Claude Code sessions; use the REST API (HTTP 403)" attest_case err no "this is a Claude Code cloud session" "--attest --pr in a cloud session without the marker is refused" open "$HEADSHA" --attest --pr 5 --repo o/r
GH_GQL="gh: HTTP 401: Bad credentials (https://api.github.com/graphql)" attest_case ok yes "PR #5 body attested" "--attest --pr: GraphQL failing otherwise still attests" open "$HEADSHA" --attest --pr 5 --repo o/r

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
check $P block "ls | xargs mv -t frontend"            "$(payload_bash 'ls | xargs mv -t frontend')"   # not /tmp: on Linux it is above $REPO (TASK-261)
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
check $R block "git commit && gh pr -R o/r create (moved, flag between)" "$(payload_bash 'git commit -m x && gh pr -R o/r create --label no-learning --title t --body b')"
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
check $P allow "git clean -fdx -e data"               "$(payload_bash 'git clean -fdx -e data -e backlog')"
check $P allow "git clean -fdx --exclude=data/"       "$(payload_bash 'git clean -fdx --exclude=data/ --exclude=backlog')"
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
# learnings: an unchanged rename adds no lesson; rename + new content counts
g switch -q -c mut-rename dev
git -C "$REPO" mv ".claude/learnings/2026-01-01-old.md" ".claude/learnings/2026-01-01-old-renamed.md"
g commit -qm rename-only
approve
check $R block "unchanged learning rename adds no lesson" "$(payload_bash 'gh pr create --base dev --fill')"
printf '\n## Addendum\nmore\n' >> "$REPO/.claude/learnings/2026-01-01-old-renamed.md"; g add -A; g commit -qm extend-renamed
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
# the tools autofix and pre-push run load installed dependencies: none sees the GitHub token (decision-048, TASK-211)
mkdir -p "$TMP/bin2" "$REPO/.venv/bin"
printf '#!/bin/sh\necho "${GH_TOKEN-unset} ${GITHUB_TOKEN-unset} ${GH_CONFIG_DIR-none} $1" >> "%s/cred.log"\n' "$TMP" > "$TMP/bin2/npx"
chmod +x "$TMP/bin2/npx"; cp "$TMP/bin2/npx" "$REPO/.venv/bin/ruff"; cp "$TMP/bin2/npx" "$TMP/bin2/make"
printf 'x=1\n' > "$REPO/cred.py"; : > "$TMP/cred.log"
payload_file Edit "$REPO/frontend/a.ts" | GH_TOKEN=probe-token GITHUB_TOKEN=probe-token PATH="$TMP/bin2:$PATH" CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1
payload_file Edit "$REPO/cred.py" | GH_TOKEN=probe-token GITHUB_TOKEN=probe-token PATH="$TMP/bin2:$PATH" CLAUDE_PROJECT_DIR="$REPO" "$HOOKS/autofix.sh" >/dev/null 2>&1
if [ "$(grep -c '^unset unset /' "$TMP/cred.log")" = 4 ] && ! grep -q probe-token "$TMP/cred.log"; then pass=$((pass+1)); echo "  ok   autofix runs ruff, prettier and eslint without the GitHub token"
else fail=$((fail+1)); echo "  FAIL autofix tools saw the token: $(cat "$TMP/cred.log")"; fi
: > "$TMP/cred.log"
( cd "$REPO" && GH_TOKEN=probe-token GITHUB_TOKEN=probe-token PATH="$TMP/bin2:$PATH" bash "$HOOKS/../../.githooks/pre-push" >/dev/null 2>&1 )
if [ "$(grep -c '^unset unset /' "$TMP/cred.log")" = 2 ] && ! grep -q probe-token "$TMP/cred.log"; then pass=$((pass+1)); echo "  ok   pre-push runs make lint and make tooling without the GitHub token"
else fail=$((fail+1)); echo "  FAIL pre-push's make saw the token: $(cat "$TMP/cred.log")"; fi
rm -rf "$REPO/.venv" "$REPO/cred.py" "$REPO/__pycache__"   # py_compile writes __pycache__/cred.*.pyc
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
check $R allow "'EOF ' (trailing space) is not the end" "$(payload_bash $'cat <<EOF\nEOF \ngit push origin other2\nEOF')"  # $'…' keeps the trailing space editors strip
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
check $P allow "git clean -fdxedata (clustered -e data)"    "$(payload_bash 'git clean -fdxedata -e backlog')"
check $R block "<<E\"OF\" partly quoted delimiter"      "$(payload_bash 'cat <<E"OF"
x
EOF
git push origin other2
E')"  # a later line "E" would otherwise close the misread heredoc and swallow the push
check $R block "even trailing backslashes don't continue" "$(payload_bash $'echo a\\\\\ngit push origin other2')"
check $R allow "odd trailing backslashes continue (all echo)" "$(payload_bash $'echo a\\\\\\\ngit push origin other2')"
check $R block "continuation splits a word: git pu\\sh" "$(payload_bash $'git pu\\\nsh origin other2')"
check $R block "continuation splits the command: gi\\t" "$(payload_bash $'gi\\\nt push origin other2')"
check $P block "continuation splits a flag: -fd\\x" "$(payload_bash $'git clean -fd\\\nx')"

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
# git_bool fails toward true: false only for what git 2.42 reads as false (TASK-282). git reads 1k, 0x1 and +1
# as true, so a gate that read only digits as a number let these push every tag, or mirror every ref, unreviewed.
for v in 1 1k 1K 1m 1g 0x1 0X1 +1 -1 010 ² --1 0x 1t; do
  g config push.followTags "$v"
  check $R block "push.followTags=$v (git: true, or a value git refuses)" "$(payload_bash 'git push origin')"
done
g config push.followTags "$(printf '9%.0s' $(seq 5000))"
check $R block "push.followTags of 5,000 nines"       "$(payload_bash 'git push origin')"
for v in 0 00 0k 0K -0 +0 -0k 0x0 0X0 -0x0 false No OFF; do
  g config push.followTags "$v"
  check $R allow "push.followTags=$v (git: false)"   "$(payload_bash 'git push origin')"
done
g config --unset push.followTags
for v in 1k 0x1 +1; do
  g config remote.origin.mirror "$v"
  check $R block "remote.origin.mirror=$v (git: a mirror)" "$(payload_bash 'git push origin')"
done
g config remote.origin.mirror 0x0
check $R allow "remote.origin.mirror=0x0 (git: not a mirror)" "$(payload_bash 'git push origin')"
g config --unset remote.origin.mirror
for v in 0g 0M; do
  g config push.followTags "$v"
  check $R allow "push.followTags=$v (git: false)"   "$(payload_bash 'git push origin')"
done
# '0' + KELVIN SIGN (U+212A, lower() makes it 'k'); \x1c is whitespace to Python, not to git
for v in 0t 0kk +-0 '0 ' "$(printf '0\342\204\252')" $'\x1c'0 ' false' $'\tno' 'off '; do
  g config push.followTags "$v"
  check $R block "push.followTags=$v (git refuses it)" "$(payload_bash 'git push origin')"
done
g config push.followTags "$(printf '\t0')"
check $R allow "push.followTags=<tab>0 (git skips leading whitespace: false)" "$(payload_bash 'git push origin')"
g config --unset push.followTags
# a key with no value is true to git; --get-regexp prints it with value ''
printf '[push]\n\tfollowTags\n' >> "$REPO/.git/config"
check $R block "push.followTags with no value (git: true)" "$(payload_bash 'git push origin')"
g config --unset push.followTags
printf '[remote "origin"]\n\tmirror\n' >> "$REPO/.git/config"
check $R block "remote.origin.mirror with no value (git: a mirror)" "$(payload_bash 'git push origin')"
g config --unset remote.origin.mirror
# push config is read NUL-separated (-z): a value with a newline can't forge a key, a remote name with a space
# can't hide one (TASK-282 review)
g config remote.origin.mirror true
g config remote.pushdefault "$(printf 'x\nremote.origin.mirror 0')"
check $R block "a mirror a forged remote.pushdefault line can't undo" "$(payload_bash 'git push origin')"
g config --unset remote.pushdefault
g config --unset remote.origin.mirror
g config push.followTags true
g config remote.pushdefault "$(printf 'x\npush.followtags 0')"
check $R block "push.followTags a forged line can't undo" "$(payload_bash 'git push origin')"
g config --unset remote.pushdefault
g config --unset push.followTags
g config "remote.x y.mirror" true
check $R block "remote.<x y>.mirror (a space in the remote name)" "$(payload_bash 'git push origin')"
g config --unset "remote.x y.mirror"
g config "remote.x y.push" refs/heads/other2:refs/heads/other2
check $R block "remote.<x y>.push (a space in the remote name)" "$(payload_bash 'git push origin')"
g config --unset "remote.x y.push"
# remote names are case-sensitive to git: remote.Origin and remote.origin are two keys, in either file order
g config remote.Origin.mirror true
g config remote.origin.mirror false
check $R block "remote.Origin.mirror=true before remote.origin.mirror=false" "$(payload_bash 'git push origin')"
g config --unset remote.Origin.mirror
g config --unset remote.origin.mirror
g config remote.origin.mirror false
g config remote.Origin.mirror true
check $R block "remote.origin.mirror=false before remote.Origin.mirror=true" "$(payload_bash 'git push origin')"
g config --unset remote.origin.mirror
g config --unset remote.Origin.mirror
g config remote.Origin.push refs/heads/other2:refs/heads/other2
g config remote.origin.push refs/heads/mut:refs/heads/mut
check $R block "remote.Origin.push and remote.origin.push (regression: both refspecs refused)" "$(payload_bash 'git push origin')"
g config --unset remote.Origin.push
g config --unset remote.origin.push
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
check $R block "gi\\\\<nl>t pu\\\\<nl>sh … \" (unparseable)" "$(payload_bash $'gi\\\nt pu\\\nsh origin other2 "')"
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
check $A block "1100 nested braces; clean commit (a writer it can't parse: TASK-266)" "$(payload_bash "$BR; git commit -m x")"
check $A allow "1100 nested braces; git status (a parse error, no writer)" "$(payload_bash "$BR; git status")"
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
HOOK_INPUT='{}' check $P block "an inherited malformed HOOK_INPUT is harmless: rm -rf data/snapshots" "$(payload_bash 'rm -rf data/snapshots')"
# a well-formed harmless one: guard_payload refuses '{}' as malformed, so only this one shows which is read (TASK-261)
HOOK_INPUT="$(payload_bash 'true')" check $P block "an inherited well-formed HOOK_INPUT is not read: rm -rf data/snapshots" "$(payload_bash 'rm -rf data/snapshots')"
HOOK_INPUT="$(payload_bash 'true')" check $A block "an inherited well-formed HOOK_INPUT is not read: -m <trailer>" "$(payload_bash "git commit -m 'x' -m '$TRAILER'")"
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
check $P block "case form: coproc case …" "$(payload_bash 'x="$(coproc case a in a) :;; c) :;; esac; rm -rf data/snapshots)"')"
check $P block "case form: function g case …" "$(payload_bash 'x="$(function g case a in a) :;; c) :;; esac; rm -rf data/snapshots)"')"
check $P block "case form: time -p case …" "$(payload_bash 'x="$(time -p case a in a) :;; c) :;; esac; rm -rf data/snapshots)"')"
check $P block "case form: case \$(…) in …" "$(payload_bash 'x="$(case $(echo a) in a) :;; c) :;; esac; rm -rf data/snapshots)"')"
check $P block "case form: a comment before in" "$(payload_bash 'x="$(case a # c
in a) :;; c) :;; esac; rm -rf data/snapshots)"')"
check $P block "case form: \${x:- a} as the word" "$(payload_bash 'x="$(case ${x:- a} in a) :;; c) :;; esac; rm -rf data/snapshots)"')"
check $P block "case form: \\-newline before in" "$(payload_bash 'x="$(case a \
in a) :;; c) :;; esac; rm -rf data/snapshots)"')"
check $P block "case form: ca\\-newline-se (split keyword)" "$(payload_bash 'x="$(ca\
se a in a) :;; c) :;; esac; rm -rf data/snapshots)"')"
# a case is told by its shape, and an `esac` after a pattern's `)` closes it: real cases stay allowed
# Conservative shape policy: these commands stay data; unsupported case shapes are refused.
check $P block "case-shaped argument data without esac is refused" "$(payload_bash 'x="$(echo case x in x)"')"
check $P block "comment before in stays an unsupported case shape" "$(payload_bash 'x="$(case x #comment
 in x) :;; esac)"')"
check $P allow "ordinary benign case substitution stays allowed" "$(payload_bash 'x="$(case x in x) :;; esac)"')"
check $P allow "x=\"\$(git log --grep case -1)\" (case as an argument)" "$(payload_bash 'x="$(git log --grep case -1)"; echo "$x"')"
check $P allow "x=\"\$(case a in a) esac)\" (esac after a pattern)" "$(payload_bash 'x="$(case a in a) esac)"; echo ok')"
check $P allow "x=\"\$(time -p case a in a) echo ok;; esac)\"" "$(payload_bash 'x="$(time -p case a in a) echo ok;; esac)"; echo "$x"')"
check $A block "git config alias.ci commit; -m \$'…\\x43laude…' (unclassifiable)" "$(payload_bash "git config alias.ci commit; git commit -m \$'Co-Authored-By: \\x43laude <x@y>'")"
check $R block "coproc git push origin other2"           "$(payload_bash 'coproc git push origin other2')"
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
# HOME holds a clean op-msg.txt, so only the HOME '' reading, which stays in $REPO, sends the trailer; with the
# real HOME the file is missing there and refused as unreadable in the first reading alone (TASK-261)
cp "$TMP/clean.md" "$TMP/home/op-msg.txt"
HOME="$TMP/home" check $A block "HOME=<clean op-msg.txt>: cd ~ && git commit -F op-msg.txt (a trailer here)" "$(payload_bash 'cd ~ && git commit -F op-msg.txt')"
HOME="$TMP/home" check $A allow "HOME=<clean op-msg.txt>: git commit -F ~/op-msg.txt (positive control)" "$(payload_bash 'git commit -F ~/op-msg.txt')"
rm -f "$TMP/home/op-msg.txt"
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

echo "== TASK-164 rows (one shared continuation join, cmdparse.join_continuations, for every raw-text scan)"
# the walk: a heredoc's << line continues before its body starts, and a joined body line can be its delimiter
check $R block 'cat <<EOF \<nl>&& git push: the << line continues' "$(payload_bash $'cat <<EOF \\\n&& git push origin other2\nx\nEOF')"
check $R block 'E\<nl>OF in an unquoted body is the delimiter'    "$(payload_bash $'cat <<EOF\nE\\\nOF\ngit push origin other2\nEOF')"
check $R allow "E\\<nl>OF in a quoted body is not"                 "$(payload_bash $'cat <<\'EOF\'\nE\\\nOF\ngit push origin other2\nEOF')"
check $R block 'unquoted body ending in \ keeps its end'           "$(payload_bash $'cat <<EOF\nx \\\nEOF\ngit push origin other2\nEOF')"
check $P allow 'a lone backslash at the end is dropped: ls <bs>'   "$(payload_bash $'ls \\')"
# require-review's parse-failure net ({1..5000} is past the brace limit): quote-aware where it can scan the text
check $R block "stray ' then git pu\\<nl>sh: every one joined"      "$(payload_bash $'echo \'x; git pu\\\nsh origin other2')"
check $R allow "'pu\\<nl>sh' single-quoted: not joined"             "$(payload_bash $'echo \'pu\\\nsh\' {1..5000}')"
check $R allow 'pu\<nl>sh in a quoted heredoc body: not joined'    "$(payload_bash $'cat <<\'EOF\'\npu\\\nsh\nEOF\necho {1..5000}')"
check $R block 'pu\<nl>sh in an unquoted heredoc body: joined'     "$(payload_bash $'cat <<EOF\npu\\\nsh\nEOF\necho {1..5000}')"
check $R allow 'pu\<nl>sh in a quoted <<- body: not joined'      "$(payload_bash $'cat <<-\'EOF\'\n\tpu\\\nsh\n\tEOF\necho {1..5000}')"
check $R allow 'after "a\"b": an escaped quote in double quotes'   "$(payload_bash $'echo "a\\"b" \'pu\\\nsh\' {1..5000}')"
check $R allow "after \"\$(echo 'a\"b')\": a quoted substitution"   "$(payload_bash $'x="$(echo \'a"b\')" \'pu\\\nsh\' {1..5000}')"
check $R allow "after \$'a\\'b': ANSI-C quotes"                     "$(payload_bash $'echo $\'a\\\'b\' \'pu\\\nsh\' {1..5000}')"
check $R allow "after \"it's\": an apostrophe in double quotes"     "$(payload_bash $'echo "it\'s" \'pu\\\nsh\' {1..5000}')"
check $R allow 'after `echo a #`: a backquoted body'               "$(payload_bash $'x=`echo a #` \'pu\\\nsh\' {1..5000}')"
check $R allow "after # it's: a comment"                           "$(payload_bash $'echo a # it\'s\necho \'pu\\\nsh\' {1..5000}')"
check $R allow 'after $((1<<EOF)): arithmetic, no heredoc'         "$(payload_bash $'x=$((1<<EOF)); echo \'pu\\\nsh\' {1..5000}')"
check $R allow 'after $(( (1+(2)) <<EOF )): nested parens'         "$(payload_bash $'x=$(( (1+(2)) <<EOF )); echo \'pu\\\nsh\' {1..5000}')"
check $R allow 'after <<<word: a herestring, no heredoc'           "$(payload_bash $'cat <<<word; echo \'pu\\\nsh\' {1..5000}')"
# the case cut-short check (`_case_cut_short`) joins as bash does too
check $P allow "' ca\\<nl>se …' single-quoted in a \$(…) is no case" "$(payload_bash $'x="$(echo \' ca\\\nse a in a\')"; echo esac')"
check $R block 'ca\<nl>se cut short at a pattern: every one joined' "$(payload_bash $'x="$(ca\\\nse a in a) echo \'x\' ;; esac)" \'pu\\\nsh\' {1..5000}')"
check $R block '… and es\<nl>ac after it is its esac'             "$(payload_bash $'x="$(ca\\\nse a in a) echo \'x\' ;; es\\\nac)" \'pu\\\nsh\' {1..5000}')"
# block-ai-attribution: its unparseable-text scan and its raw-text scan
check $A block "unclosed \", Co-Authored-By: Cl\\<nl>aude"         "$(payload_bash $'git commit -m "x\n\nCo-Authored-By: Cl\\\naude Opus')"
check $A block "stray ', Co-Authored-By: Cl\\<nl>aude"             "$(payload_bash $'git commit -m \'x Co-Authored-By: Cl\\\naude Opus')"
check $A allow "'…Cl\\<nl>aude' single-quoted, unparseable"        "$(payload_bash $'echo \'Co-Authored-By: Cl\\\naude Opus\' {1..5000}')"
check $A block 'unquoted heredoc: Cl\<nl>aude is Claude'          "$(payload_bash $'git commit -F - <<EOF\nx\n\nCo-Authored-By: Cl\\\naude Opus\nEOF')"
check $A allow 'quoted heredoc: Cl\<nl>aude stays split'          "$(payload_bash $'git commit -F - <<\'EOF\'\nx\n\nCo-Authored-By: Cl\\\naude Opus\nEOF')"

echo "== TASK-170 rows (block-ai-attribution reads a message file named through a variable or by head/tail/sed)"
printf 'x\n\n%s\n' "$TRAILER" > "$REPO/op-170.txt"
printf 'clean notes\n' > "$REPO/op-170-clean.txt"
printf 's/.*/%s/\n' "$TRAILER" > "$REPO/op-170-script.sed"
printf '1p\n' > "$REPO/op-170-clean.sed"
printf '%s\n' "$TRAILER" > "$REPO/-op-170-message"
cp "$REPO/-op-170-message" "$REPO/--file=op-170-message"
printf 'clean notes\n' > "$REPO/-op-170-clean"
cp "$REPO/-op-170-clean" "$REPO/--file=op-170-clean"
for reader in cat head tail; do
  check $A block "$reader -- scans a leading-dash message file" "$(payload_bash "git commit -m \"\$($reader -- -op-170-message)\"")"
  check $A allow "$reader -- permits a clean leading-dash file" "$(payload_bash "git commit -m \"\$($reader -- -op-170-clean)\"")"
  check $A block "$reader -- refuses an unknown file variable" "$(payload_bash "git commit -m \"\$($reader -- \"\$UNSET_170\")\"")"
done
check $A block 'sed -- treats --file=message as an input filename' "$(payload_bash 'git commit -m "$(sed -n -e p -- --file=op-170-message)"')"
check $A allow 'sed -- permits clean --file=message input' "$(payload_bash 'git commit -m "$(sed -n -e p -- --file=op-170-clean)"')"
check $A block 'sed -- refuses an unknown input file variable' "$(payload_bash 'git commit -m "$(sed -n -e p -- "$UNSET_170")"')"
check $A block 'sed -- preserves implicit expression then leading-dash input' "$(payload_bash 'git commit -m "$(sed -n -- 1p -op-170-message)"')"
check $A allow 'sed -- permits implicit expression and clean leading-dash input' "$(payload_bash 'git commit -m "$(sed -n -- 1p -op-170-clean)"')"
check $A allow 'sed -- implicit expression is text rather than a file' "$(payload_bash $'git commit -m "$(sed -n -- \'$p\' -op-170-clean)"')"
check $A block 'sed -f scans its script file' "$(payload_bash 'git commit -m "$(sed -f op-170-script.sed op-170-clean.txt)"')"
check $A block 'sed -fFILE scans its script file' "$(payload_bash 'git commit -m "$(sed -fop-170-script.sed op-170-clean.txt)"')"
check $A block 'sed --file=FILE scans its script file' "$(payload_bash 'git commit -m "$(sed --file=op-170-script.sed op-170-clean.txt)"')"
check $A block 'sed --file scans its script file' "$(payload_bash 'git commit -m "$(sed --file op-170-script.sed op-170-clean.txt)"')"
check $A block 'sed -f refuses an unresolved script file' "$(payload_bash 'git commit -m "$(sed -f "$UNSET_170" op-170-clean.txt)"')"
check $A block 'sed -f scans a script file through a variable' "$(payload_bash 'F=op-170-script.sed; git commit -m "$(sed -f "$F" op-170-clean.txt)"')"
check $A block 'sed -fFILE refuses an unresolved script file' "$(payload_bash 'git commit -m "$(sed -f"$UNSET_170" op-170-clean.txt)"')"
check $A block 'sed --file=FILE refuses an unresolved script file' "$(payload_bash 'git commit -m "$(sed --file="$UNSET_170" op-170-clean.txt)"')"
check $A allow 'sed -f permits a clean script and clean input file' "$(payload_bash 'git commit -m "$(sed -f op-170-clean.sed op-170-clean.txt)"')"
check $A allow 'sed -fFILE permits a clean script and clean input file' "$(payload_bash 'git commit -m "$(sed -fop-170-clean.sed op-170-clean.txt)"')"
check $A allow 'sed --file=FILE permits a clean script and clean input file' "$(payload_bash 'git commit -m "$(sed --file=op-170-clean.sed op-170-clean.txt)"')"
check $A block 'sed -nfFILE scans its script file' "$(payload_bash 'git commit -m "$(sed -nfop-170-script.sed op-170-clean.txt)"')"
check $A block 'sed -nf FILE scans its script file' "$(payload_bash 'git commit -m "$(sed -nf op-170-script.sed op-170-clean.txt)"')"
check $A block 'sed -nfFILE refuses an unresolved script file' "$(payload_bash 'git commit -m "$(sed -nf"$UNSET_170" op-170-clean.txt)"')"
check $A block 'sed -nf FILE refuses an unresolved script file' "$(payload_bash 'git commit -m "$(sed -nf "$UNSET_170" op-170-clean.txt)"')"
check $A allow 'sed -nfFILE permits clean script and input' "$(payload_bash 'git commit -m "$(sed -nfop-170-clean.sed op-170-clean.txt)"')"
check $A allow 'sed -nf FILE permits clean script and input' "$(payload_bash 'git commit -m "$(sed -nf op-170-clean.sed op-170-clean.txt)"')"
check $A allow 'sed -neSCRIPT consumes expression letters as text' "$(payload_bash $'git commit -m "$(sed -ne \'$p\' op-170-clean.txt)"')"
check $A allow 'sed -neSCRIPT with f in expression is not a file' "$(payload_bash 'git commit -m "$(sed -nes/f/x/ op-170-clean.txt)"')"
check $A block 'sed -neSCRIPT still scans its input file' "$(payload_bash 'git commit -m "$(sed -ne1p op-170.txt)"')"
check $A block 'sed -nE flags preserve the implicit script then input' "$(payload_bash 'git commit -m "$(sed -nE 1p op-170.txt)"')"
check $A allow 'sed -if suffix is not a script-file option' "$(payload_bash 'git commit -m "$(sed -nif 1p op-170-clean.txt)"')"
check $A block 'sed refuses an unfamiliar bundle in a message reader' "$(payload_bash 'git commit -m "$(sed -Qnfop-170-clean.sed op-170-clean.txt)"')"
check $A block 'F=…; -m "$(cat "$F")": the variable is put in'    "$(payload_bash 'F=op-170.txt; git commit -m "$(cat "$F")"')"
check $A allow 'F=…; -m "$(cat "$F")", a clean file'              "$(payload_bash 'F=op-170-clean.txt; git commit -m "$(cat "$F")"')"
check $A block '-F "$F"'                                          "$(payload_bash 'F=op-170.txt; git commit -F "$F"')"
check $A block '-F - < "$F"'                                      "$(payload_bash 'F=op-170.txt; git commit -F - < "$F"')"
check $A block '-m "$(cat op-170*.txt)": a glob'                  "$(payload_bash 'git commit -m "$(cat op-170*.txt)"')"
check $A allow '-m "$(cat op-170-cl*.txt)": a glob, a clean file'  "$(payload_bash 'git commit -m "$(cat op-170-cl*.txt)"')"   # unexpanded it is unreadable (TASK-261)
check $A block '-m "$(head -5 …)": the whole file is read'        "$(payload_bash 'git commit -m "$(head -5 op-170.txt)"')"
check $A block '-m "$(head -n 1 …)"'                              "$(payload_bash 'git commit -m "$(head -n 1 op-170.txt)"')"
check $A block '-m "$(tail -n 3 …)"'                              "$(payload_bash 'git commit -m "$(tail -n 3 op-170.txt)"')"
check $A block '-m "$(sed -n 1,9p …)"'                            "$(payload_bash 'git commit -m "$(sed -n 1,9p op-170.txt)"')"
check $A block '-m "$(sed -e1p …)": an attached -e script'        "$(payload_bash 'git commit -m "$(sed -n -e1p op-170.txt)"')"
check $A allow '-m "$(head -5 …)", a clean file'                  "$(payload_bash 'git commit -m "$(head -5 op-170-clean.txt)"')"
check $A allow '-m "$(head -n "$N" …)": a count, not a file'       "$(payload_bash 'git commit -m "$(head -n "$N_170" op-170-clean.txt)"')"
check $A allow "-m \"\$(sed -n '\$p' …)\": sed's script, not a file" "$(payload_bash $'git commit -m "$(sed -n \'$p\' op-170-clean.txt)"')"
check $A allow "-m \"\$(sed -e 1p -e '\$p' …)\": two -e scripts"    "$(payload_bash $'git commit -m "$(sed -n -e 1p -e \'$p\' op-170-clean.txt)"')"
check $A block '-m "$(cat "$UNSET")": a file it can'"'"'t name'      "$(payload_bash 'git commit -m "$(cat "$UNSET_170")"')"
check $A block '-F "$UNSET"'                                      "$(payload_bash 'git commit -F "$UNSET_170"')"
check $A block 'cd "$UNSET" && git commit -F <relative file>'     "$(payload_bash 'cd "$UNSET_170" && git commit -F op-170-clean.txt')"
check $A block '-m "$(awk 1 …)": a reader it does not model'      "$(payload_bash 'git commit -m "$(awk 1 op-170-clean.txt)"')"
check $A block '-m "$(awk 1 "$UNSET")"'                           "$(payload_bash 'git commit -m "$(awk 1 "$UNSET_170")"')"
check $A block 'x=$(awk 1 …); -m "$x": an unquoted $(…)'          "$(payload_bash 'x=$(awk 1 op-170-clean.txt); git commit -m "$x"')"
check $A allow '-m "wip $(date)": reads no file'                  "$(payload_bash 'git commit -m "wip $(date)"')"
check $A allow '-m "$(git log -1 --format=%s)": reads no file'    "$(payload_bash 'git commit -m "$(git log -1 --format=%s)"')"
check $A allow '-m "$(printf %s "$UNSET")": text, not a file'     "$(payload_bash 'git commit -m "$(printf %s "$UNSET_170")"')"
check $A allow '-F - <<< "$UNSET": a herestring, not a file'      "$(payload_bash 'git commit -F - <<< "$UNSET_170"')"
check $A allow 'git add <file> && git commit: no substitution'    "$(payload_bash 'git add op-170.txt && git commit -m "add notes"')"
check $A allow '-m "$(echo $(date))" -- <file>: the subst ends'   "$(payload_bash 'git commit -m "$(echo $(date))" -- op-170-clean.txt')"
check $A allow 'cat "$UNSET" in a command that writes no message' "$(payload_bash 'cat "$UNSET_170"; ls')"
rm -f "$REPO/op-170.txt" "$REPO/op-170-clean.txt" "$REPO/op-170-script.sed" "$REPO/op-170-clean.sed"
rm -f "$REPO/-op-170-message" "$REPO/--file=op-170-message" "$REPO/-op-170-clean" "$REPO/--file=op-170-clean"

echo "== TASK-244 rows (git writes backlog/ by pathspec: restore, checkout <commit> --, reset <commit> --, rm, mv, apply, …)"
# A repo of its own: dev holds a task in backlog/tasks/; `finished` has it completed (moved to backlog/completed/), as
# the CLI leaves it; `conflicted` is a second repo stopped on a merge conflict in a task file. No data/ here: the
# backlog rule must hold without one.
BL="$TMP/bl repo"
bl() { git -C "$BL" -c user.email=t@t -c user.name=t "$@"; }
git init -q -b dev "$BL"
mkdir -p "$BL/backlog/tasks" "$BL/backlog/completed" "$BL/backlog/decisions" "$BL/src" "$BL/frontend"
printf 'id: TASK-1\n' > "$BL/backlog/tasks/task-1 - a.md"
printf 'id: decision-1\n' > "$BL/backlog/decisions/decision-1 - d.md"
printf 'x\n' > "$BL/src/x.md"; printf 'y\n' > "$BL/frontend/y.ts"
bl add -A && bl commit -qm init
bl switch -qc finished && bl mv "backlog/tasks/task-1 - a.md" "backlog/completed/task-1 - a.md" && bl commit -qm complete
bl switch -qc same finished   # same tree as HEAD: a reset to it only unstages
bl branch backlog/old dev   # a ref whose name reads as a backlog/ path
bl switch -q finished
printf 'diff --git a/backlog/tasks/n.md b/backlog/tasks/n.md\nnew file mode 100644\n--- /dev/null\n+++ b/backlog/tasks/n.md\n@@ -0,0 +1 @@\n+x\n' > "$TMP/bl.patch"
printf 'diff --git a/src/n.md b/src/n.md\nnew file mode 100644\n--- /dev/null\n+++ b/src/n.md\n@@ -0,0 +1 @@\n+x\n' > "$TMP/src.patch"
printf 'diff --git a/backlog/completed/task-1 - a.md b/src/a.md\nsimilarity index 100%%\nrename from backlog/completed/task-1 - a.md\nrename to src/a.md\n' > "$TMP/out.patch"
printf 'diff --git a/src/x.md b/src/z.md\nsimilarity index 100%%\nrename from src/x.md\nrename to src/z.md\n' > "$TMP/srcmv.patch"
printf -- '--- /dev/null\n+++ backlog/tasks/n.md\n@@ -0,0 +1 @@\n+x\n' > "$TMP/p0.patch"   # no a/ b/: read with -p0
printf 'diff --git a/src/a.md b/backlog/completed/a.md\nsimilarity index 100%%\nrename from src/a.md\nrename to backlog/completed/a.md\n' > "$TMP/in.patch"
printf 'diff --git "a/backlog/caf\\303\\251.md" b/src/c.md\nsimilarity index 100%%\nrename from "backlog/caf\\303\\251.md"\nrename to src/c.md\n' > "$TMP/quoted.patch"
printf 'diff --git a/src/r.md b/src/r.md\nnew file mode 100644\n--- /dev/null\n+++ b/src/r.md\n@@ -0,0 +1,5 @@\n+x\n' > "$TMP/recount.patch"   # wrong counts: needs --recount
printf 'diff --git a/src/a.md b/backlog/tasks/a.md\nsimilarity index 100%%\ncopy from src/a.md\ncopy to backlog/tasks/a.md\n' > "$TMP/copy.patch"
printf 'diff --git "a/backlog/\346\227\245\\"x.md" b/src/u.md\nsimilarity index 100%%\nrename from "backlog/\346\227\245\\"x.md"\nrename to src/u.md\n' > "$TMP/utf8.patch"   # quoted, UTF-8 left raw (core.quotePath=false)
mkdir -p "$TMP/oldbl/backlog/tasks"; : > "$TMP/oldbl/backlog/tasks/x.md"
payload_bl() { payload_at "$BL" "$1"; }
T1='"backlog/tasks/task-1 - a.md"'; C1='"backlog/completed/task-1 - a.md"'
# the PR #146 shapes: the pre-completion copy put back, the completed one removed
check $P block "git restore --source=dev -- <task>"            "$(payload_bl "git restore --source=dev -- $T1")"
check $P block "git restore --source=dev -- <task> <completed>" "$(payload_bl "git restore --source=dev --staged --worktree -- $T1 $C1")"
check $P block "git restore -s dev <task> (short, separate)"   "$(payload_bl "git restore -s dev $T1")"
check $P block "git restore -SWsdev <task> (one cluster)"      "$(payload_bl "git restore -SWsdev $T1")"
check $P block "git restore --sour=dev --staged (abbreviated)" "$(payload_bl "git restore --sour=dev --staged $T1")"
check $P block "git restore --staged --source=dev (index from a commit)" "$(payload_bl "git restore --staged --source=dev $T1")"
check $P block "git restore --staged --work <task> (abbreviated)" "$(payload_bl "git restore --staged --work $T1")"
check $P block "git restore -S --no-staged <task> (last wins)" "$(payload_bl "git restore -S --no-staged $T1")"
check $P block "git restore <task> (worktree from the index)"  "$(payload_bl "git restore $T1")"
check $P block "git checkout dev -- <task>"                    "$(payload_bl "git checkout dev -- $T1")"
check $P block "git checkout dev -- backlog/"                  "$(payload_bl 'git checkout dev -- backlog/')"
check $P block "git checkout dev <task> (no --)"               "$(payload_bl "git checkout dev $T1")"
check $P block "git checkout -- <completed> (from the index)"  "$(payload_bl "git checkout -- $C1")"
check $P block "git checkout <completed> (a path, not a commit)" "$(payload_bl "git checkout $C1")"
check $P block "git checkout -p dev -- <task>"                 "$(payload_bl "git checkout -p dev -- $T1")"
check $P block "git reset dev -- <task>"                       "$(payload_bl "git reset dev -- $T1")"
check $P block "git reset dev <task> (no --)"                  "$(payload_bl "git reset dev $T1")"
check $P block "git reset nosuchrev -- <task> (unknown tree-ish)" "$(payload_bl "git reset nosuchrev -- $T1")"
check $P block "git rm <completed>"                            "$(payload_bl "git rm $C1")"
check $P block "git rm --cached <completed>"                   "$(payload_bl "git rm --cached $C1")"
check $P block "git rm -n --no-dry-run <completed> (last wins)" "$(payload_bl "git rm -n --no-dry-run $C1")"
check $P block "git mv <completed> backlog/tasks/"             "$(payload_bl "git mv $C1 backlog/tasks/")"
check $P block "git mv src/x.md backlog/tasks/ (into backlog/)" "$(payload_bl 'git mv src/x.md backlog/tasks/')"
# variants: -C, cd, case, globs, magic and whole-tree pathspecs, files, xargs, words it can't resolve, work trees
check $P block "git -C <repo> restore --source=dev -- <task>"  "$(payload_at "$TMP" "git -C '$BL' restore --source=dev -- $T1")"
check $P block "cd backlog && git restore --source=dev tasks"  "$(payload_bl 'cd backlog && git restore --source=dev tasks')"
check $P block "cd backlog/tasks && git checkout dev -- ."     "$(payload_bl 'cd backlog/tasks && git checkout dev -- .')"
check $P block "cd src && git restore -s dev ../backlog"       "$(payload_bl 'cd src && git restore -s dev ../backlog')"
check $P block "cd src && git restore -s dev .. (above backlog/)" "$(payload_bl 'cd src && git restore -s dev ..')"
check $P block "git restore -s dev BACKLOG/tasks (case-blind)" "$(payload_bl 'git restore -s dev BACKLOG/tasks')"
check $P block "git restore -s dev . (the whole tree)"         "$(payload_bl 'git restore -s dev .')"
check $P block "git restore . (the whole tree, from the index)" "$(payload_bl 'git restore .')"
check $P block "git checkout dev -- '*.md' (git's * crosses /)" "$(payload_bl "git checkout dev -- '*.md'")"
check $P block "git checkout dev -- 'b*' (a root glob)"        "$(payload_bl "git checkout dev -- 'b*'")"
check $P block "git restore -s dev 'backlog/t*'"               "$(payload_bl "git restore -s dev 'backlog/t*'")"
check $P block "git rm -r 'backlog/completed/*'"               "$(payload_bl "git rm -r 'backlog/completed/*'")"
check $P block "git rm -r --cached . (the whole index)"        "$(payload_bl 'git rm -r --cached .')"
check $P block "git restore -s dev ':/backlog' (magic)"        "$(payload_bl "git restore -s dev ':/backlog'")"
check $P block "cd src && git restore -s dev ':(top)backlog'"  "$(payload_bl "cd src && git restore -s dev ':(top)backlog'")"
check $P block "git restore -s dev -- ':!src' (only excludes: all else)" "$(payload_bl "git restore -s dev -- ':!src'")"
check $P block "git restore -s dev -- . ':!backlog/tasks' (part excluded)" "$(payload_bl "git restore -s dev -- . ':!backlog/tasks'")"
check $P block "cd backlog && git restore -s dev -- . ':!' (an empty exclude)" "$(payload_bl "cd backlog && git restore -s dev -- . ':!'")"
check $P block "git restore -s dev -- . ':!back*' (an exclude glob)" "$(payload_bl "git restore -s dev -- . ':!back*'")"
check $P block "git restore --pathspec-from-file=list -s dev"  "$(payload_bl 'git restore --pathspec-from-file=list -s dev')"
check $P block "git checkout dev --pathspec-from-file=list"    "$(payload_bl 'git checkout dev --pathspec-from-file=list')"
check $P block "git checkout -b x --pathspec-from-file=list"   "$(payload_bl 'git checkout -b x --pathspec-from-file=list')"
check $P block "git reset dev --pathspec-from-file=list"       "$(payload_bl 'git reset dev --pathspec-from-file=list')"
check $P block "git rm --pathspec-from-file=list"              "$(payload_bl 'git rm --pathspec-from-file=list')"
check $P block "git restore -s dev \"\$UNSET\" (unresolved)"   "$(payload_bl 'git restore -s dev "$OP_UNSET_244"')"
check $P block "cd \"\$UNSET\" && git restore -s dev ."        "$(payload_bl 'cd "$OP_UNSET_244" && git restore -s dev .')"
check $P block "git -C \"\$UNSET\" restore -s dev x"           "$(payload_bl 'git -C "$OP_UNSET_244" restore -s dev x')"
check $P block "git --work-tree=\"\$UNSET\" restore -s dev x"  "$(payload_bl 'git --work-tree="$OP_UNSET_244" restore -s dev x')"
check $P block "GIT_WORK_TREE=<repo> git restore -s dev backlog (from elsewhere)" "$(payload_at "$TMP" "GIT_WORK_TREE='$BL' GIT_DIR='$BL/.git' git restore -s dev backlog")"
check $P block "git --work-tree <repo> rm backlog/x (from elsewhere)" "$(payload_at "$TMP" "git --git-dir='$BL/.git' --work-tree '$BL' rm backlog/x")"
check $P block "git --work-tree <repo> mv src/x.md backlog/tasks/ (from elsewhere)" "$(payload_at / "git --git-dir='$BL/.git' --work-tree='$BL' mv src/x.md backlog/tasks/")"
check $P allow "git --work-tree <repo> mv -n … backlog/ (a dry run, from elsewhere)" "$(payload_at / "git --git-dir='$BL/.git' --work-tree='$BL' mv -n src/x.md backlog/tasks/")"
check $P allow "git --work-tree <repo> rm -n backlog/x (a dry run, from elsewhere)" "$(payload_at / "git --git-dir='$BL/.git' --work-tree='$BL' rm -n backlog/x")"
check $P allow "git --work-tree <repo> mv --dry … backlog/ (abbreviated dry run)" "$(payload_at / "git --git-dir='$BL/.git' --work-tree='$BL' mv --dry src/x.md backlog/tasks/")"
check $P block "ls | xargs git restore"                        "$(payload_bl 'ls | xargs git restore')"
check $P block "ls | xargs git checkout dev --"                "$(payload_bl 'ls | xargs git checkout dev --')"
check $P block "echo x | xargs git apply"                      "$(payload_bl 'echo x | xargs git apply')"
# the other git writers
check $P block "git stash push -- backlog/"                    "$(payload_bl 'git stash push -- backlog/')"
check $P block "git stash -- <completed> (push implied)"       "$(payload_bl "git stash -- $C1")"
check $P block "git stash push -m msg <completed>"             "$(payload_bl "git stash push -m msg $C1")"
check $P block "git apply <patch into backlog/>"               "$(payload_bl "git apply '$TMP/bl.patch'")"
check $P block "git apply -R <patch into backlog/>"            "$(payload_bl "git apply -R '$TMP/bl.patch'")"
check $P block "git apply --check --apply <patch> (applies)"   "$(payload_bl "git apply --check --apply '$TMP/bl.patch'")"
check $P block "git apply --directory=backlog <src patch>"     "$(payload_bl "git apply --directory=backlog '$TMP/src.patch'")"
check $P block "git apply --directory backlog <src patch> (separate)" "$(payload_bl "git apply --directory backlog '$TMP/src.patch'")"
check $P block "git apply --directory=backlog -p1 <src patch>" "$(payload_bl "git apply --directory=backlog -p1 '$TMP/src.patch'")"
check $P block "git apply <rename out of backlog/>"            "$(payload_bl "git apply '$TMP/out.patch'")"
check $P block "git apply < patch (stdin)"                     "$(payload_bl "git apply < '$TMP/src.patch'")"
check $P block "cat patch | git apply - (stdin)"               "$(payload_bl "cat '$TMP/src.patch' | git apply -")"
check $P block "git apply <missing patch> (git can't read it)" "$(payload_bl 'git apply nosuch.patch')"
check $P block "git checkout-index -f -- <task>"               "$(payload_bl "git checkout-index -f -- $T1")"
check $P block "git checkout-index -a -f (every file)"         "$(payload_bl 'git checkout-index -a -f')"
check $P block "git checkout-index --stdin"                    "$(payload_bl 'git checkout-index --stdin')"
check $P block "git checkout-index --prefix=backlog/tasks/ src/x.md" "$(payload_bl 'git checkout-index --prefix=backlog/tasks/ src/x.md')"
check $P block "git update-index --force-remove <completed>"   "$(payload_bl "git update-index --force-remove $C1")"
check $P block "git update-index --cacheinfo=100644,<sha>,backlog/tasks/b.md" "$(payload_bl 'git update-index --add --cacheinfo=100644,e69de29bb2d1d6434b8b29ae775ad8c2e48c5391,backlog/tasks/b.md')"
check $P block "git update-index --cacheinfo <m>,<sha>,backlog/… (separate)" "$(payload_bl 'git update-index --add --cacheinfo 100644,e69de29bb2d1d6434b8b29ae775ad8c2e48c5391,backlog/tasks/b.md')"
check $P block "git update-index --remove --stdin"             "$(payload_bl 'git update-index --remove --stdin')"
check $P block "git read-tree --prefix=backlog/tasks/ dev"     "$(payload_bl 'git read-tree --prefix=backlog/tasks/ dev')"
check $P block "git read-tree --prefix= dev (the root)"        "$(payload_bl 'git read-tree --prefix= dev')"
# what stays allowed: the CLI, unstaging, dry runs, reads, commit and branch operations, other paths
check $P allow "backlog task complete 1"                       "$(payload_bl 'backlog task complete 1')"
check $P allow "git restore --staged <task> (unstage)"         "$(payload_bl "git restore --staged $T1")"
check $P allow "git restore -S <task> (unstage, short)"        "$(payload_bl "git restore -S $T1")"
check $P allow "git restore --staged . (unstage everything)"   "$(payload_bl 'git restore --staged .')"
check $P allow "git reset -- <task> (unstage)"                 "$(payload_bl "git reset -- $T1")"
check $P allow "git reset HEAD -- <task> (unstage)"            "$(payload_bl "git reset HEAD -- $T1")"
check $P allow "git reset same -- <task> (HEAD's tree)"        "$(payload_bl "git reset same -- $T1")"
check $P allow "git reset <task> (a path, unstage)"            "$(payload_bl "git reset $C1")"
check $P block "git reset --hard dev (rewrites backlog/ too)"       "$(payload_bl 'git reset --hard dev')"
check $P allow "git reset --soft HEAD~1"                       "$(payload_bl 'git reset --soft HEAD~1')"
check $P allow "git checkout dev (a branch)"                   "$(payload_bl 'git checkout dev')"
check $P allow "git checkout HEAD~1 (a commit)"                "$(payload_bl 'git checkout HEAD~1')"
check $P allow "git checkout -b x dev"                         "$(payload_bl 'git checkout -b x dev')"
check $P allow "git checkout --orphan x"                       "$(payload_bl 'git checkout --orphan x')"
check $P allow "git switch dev / rebase / merge / cherry-pick" "$(payload_bl 'git switch dev && git rebase dev && git merge dev && git cherry-pick finished')"
check $P allow "git checkout dev -- src (not backlog/)"        "$(payload_bl 'git checkout dev -- src')"
check $P allow "git checkout dev src/x.md (no --)"             "$(payload_bl 'git checkout dev src/x.md')"
check $P allow "git restore --source backlog/old -- src/x.md (a value, not a path)" "$(payload_bl 'git restore --source backlog/old -- src/x.md')"
check $P allow "git restore -s dev 'src/*' (a glob in src/)"   "$(payload_bl "git restore -s dev 'src/*'")"
check $P allow "git restore -s dev -- . ':!backlog'"           "$(payload_bl "git restore -s dev -- . ':!backlog'")"
check $P allow "git restore -s dev -- . ':(exclude)backlog/'"  "$(payload_bl "git restore -s dev -- . ':(exclude)backlog/'")"
check $P allow "git checkout dev -- '*.md' ':^backlog'"        "$(payload_bl "git checkout dev -- '*.md' ':^backlog'")"
check $P block "git checkout dev -- '*.md' ':^Backlog' (git's exclude is case-exact)" "$(payload_bl "git checkout dev -- '*.md' ':^Backlog'")"
check $P block "git rm -n <completed> (dry run; the older rule refuses it)"               "$(payload_bl "git rm -n $C1")"
check $P allow "git rm --dry-run -r . (dry run)"               "$(payload_bl 'git rm --dry-run -r .')"
check $P block "git mv -n <completed> backlog/tasks/ (dry run; the older rule)" "$(payload_bl "git mv -n $C1 backlog/tasks/")"
check $P allow "git rm src/x.md"                               "$(payload_bl 'git rm src/x.md')"
check $P allow "git mv src/x.md src/z.md"                      "$(payload_bl 'git mv src/x.md src/z.md')"
check $P allow "git log / show / diff / status -- backlog/"    "$(payload_bl 'git log -- backlog/ && git show dev:backlog/tasks/x.md && git diff dev -- backlog/ && git status -- backlog')"
check $P allow "git stash push -- src"                         "$(payload_bl 'git stash push -- src')"
check $P allow "git stash (the whole tree) and git stash pop"  "$(payload_bl 'git stash && git stash pop')"
check $P allow "git apply --directory vendor <src patch> (separate)" "$(payload_bl "git apply --directory vendor '$TMP/src.patch'")"
check $P allow "git apply <src patch>"                         "$(payload_bl "git apply '$TMP/src.patch'")"
check $P allow "git apply <rename inside src/>"                "$(payload_bl "git apply '$TMP/srcmv.patch'")"
check $P allow "git apply --exclude='backlog/*' <backlog patch>" "$(payload_bl "git apply --exclude='backlog/*' '$TMP/bl.patch'")"
check $P allow "cd src && git apply <backlog patch> (outside cwd: skipped)" "$(payload_bl "cd src && git apply '$TMP/bl.patch'")"
check $P allow "git apply --check / --stat / --numstat <patch>" "$(payload_bl "git apply --check '$TMP/bl.patch' && git apply --stat '$TMP/bl.patch' && git apply --numstat '$TMP/bl.patch'")"
check $P allow "git checkout-index --temp <task>"              "$(payload_bl "git checkout-index --temp $T1")"
check $P allow "git checkout-index -f src/x.md"                "$(payload_bl 'git checkout-index -f src/x.md')"
check $P allow "git update-index --refresh"                    "$(payload_bl 'git update-index --refresh')"
check $P allow "git update-index --chmod=+x src/x.md"          "$(payload_bl 'git update-index --chmod=+x src/x.md')"
check $P allow "git read-tree dev (the whole index)"           "$(payload_bl 'git read-tree dev')"
check $P allow "git read-tree --prefix=vendor/ dev"            "$(payload_bl 'git read-tree --prefix=vendor/ dev')"
check $P allow "git checkout -b backlog dev (-b takes a value)"  "$(payload_bl 'git checkout -b backlog dev')"
check $P allow "git stash save backlog (a message)"            "$(payload_bl 'git stash save backlog')"
check $P allow "git stash push -m backlog -- src"              "$(payload_bl 'git stash push -m backlog -- src')"
check $P allow "git stash push --message backlog -- src"       "$(payload_bl 'git stash push --message backlog -- src')"
check $P allow "git apply --include='src/*' <backlog patch>"   "$(payload_bl "git apply --include='src/*' '$TMP/bl.patch'")"
check $P block "git apply -p0 <patch naming backlog/ plainly>" "$(payload_bl "git apply -p0 '$TMP/p0.patch'")"
check $P allow "git apply <that patch> (-p1: tasks/n.md)"      "$(payload_bl "git apply '$TMP/p0.patch'")"
check $P allow "git checkout-index --prefix=out/ <task>"       "$(payload_bl "git checkout-index --prefix=out/ $T1")"
check $P allow "cd src && git checkout-index -a -f (src/ only)" "$(payload_bl 'cd src && git checkout-index -a -f')"
check $P block "cd src && git read-tree --prefix=backlog/ dev (from the top)" "$(payload_bl 'cd src && git read-tree --prefix=backlog/ dev')"
# abbreviated long options are read as git reads them (cmdparse.GIT_LONG_OPTS)
check $P block "git rm --pathspec-f=list"                      "$(payload_bl 'git rm --pathspec-f=list')"
check $P block "git mv --dry <completed> backlog/tasks/ (the older rule)"       "$(payload_bl "git mv --dry $C1 backlog/tasks/")"
check $P block "git apply --direc=backlog <src patch>"         "$(payload_bl "git apply --direc=backlog '$TMP/src.patch'")"
check $P block "git checkout-index --pref=backlog/tasks/ src/x.md" "$(payload_bl 'git checkout-index --pref=backlog/tasks/ src/x.md')"
check $P block "git read-tree --pref=backlog/ dev"             "$(payload_bl 'git read-tree --pref=backlog/ dev')"
# find picks files this guard can't see: deleting them, or running a writer on them, from where backlog/ is in reach
check $P block "find backlog -name '*.md' -exec git rm {} +"   "$(payload_bl "find backlog -name '*.md' -exec git rm {} +")"
check $P block "find backlog/completed -delete"                "$(payload_bl 'find backlog/completed -delete')"
check $P block "find . -path '*completed*' -delete (the root)" "$(payload_bl "find . -path '*completed*' -delete")"
check $P block "find -name x -delete (no start: .)"            "$(payload_bl 'find -name x -delete')"
check $P block "cd src && find .. -name x -delete"             "$(payload_bl 'cd src && find .. -name x -delete')"
check $P block "find <dir above the repo> -name x -delete"     "$(payload_bl "find '$TMP' -name x -delete")"
check $P block "find BACKLOG -execdir mv {} x ';' (case-blind)" "$(payload_bl "find BACKLOG -execdir mv {} x ';'")"
check $P block "find backlog -ok sh -c x {} ';'"               "$(payload_bl "find backlog -ok sh -c x {} ';'")"
check $P block "find backlog -exec (no command)"               "$(payload_bl 'find backlog -exec')"
check $P block "find \"\$UNSET\" -delete"                      "$(payload_bl 'find "$OP_UNSET_244" -delete')"
check $P block "cd \"\$UNSET\" && find . -delete"              "$(payload_bl 'cd "$OP_UNSET_244" && find . -delete')"
check $P block "cd src && cd \"\$UNSET\" && find -name x -delete (no start)" "$(payload_bl 'cd src && cd "$OP_UNSET_244" && find -name x -delete')"
git -C "$BL" worktree add -q "$TMP/bl-wt" dev   # another worktree's root, with its own backlog/
check $P block "find <another worktree's root> -name x -delete" "$(payload_bl "find '$TMP/bl-wt' -name x -delete")"
check $P allow "find backlog -name '*.md' -exec grep -l x {} +" "$(payload_bl "find backlog -name '*.md' -exec grep -l x {} +")"
check $P allow "find . -exec /usr/bin/grep x {} + (a reader by path)" "$(payload_bl "find . -name '*.md' -exec /usr/bin/grep x {} +")"
check $P allow "find src -name '*.pyc' -delete"                "$(payload_bl "find src -name '*.pyc' -delete")"
check $P allow "find backlog -type f (lists only)"             "$(payload_bl 'find backlog -type f')"
# TASK-244 review gate: a payload this hook can't read is refused (fail closed); a well-formed one is checked
check $P block "invalid JSON payload"                          'not json'
check $P block "empty payload"                                 ''
check $P block "a JSON array, not an object"                   '[1]'
check $P block "no tool_name"                                  '{"tool_input":{"command":"ls"}}'
check $P block "a tool this hook isn't wired to"               '{"tool_name":"Read","tool_input":{"file_path":"/tmp/x"}}'
check $P block "Bash with no command"                          '{"tool_name":"Bash","cwd":"/tmp","tool_input":{}}'
check $P block "Bash with a blank command"                     '{"tool_name":"Bash","cwd":"/tmp","tool_input":{"command":"  "}}'
check $P block "Bash with a command that isn't a string"       '{"tool_name":"Bash","cwd":"/tmp","tool_input":{"command":5}}'
check $P block "Bash with tool_input not an object"            '{"tool_name":"Bash","cwd":"/tmp","tool_input":"ls"}'
check $P block "Edit with no file_path"                        '{"tool_name":"Edit","cwd":"/tmp","tool_input":{}}'
check $P allow "Bash ls (well formed)"                         "$(payload_at /tmp 'ls')"
check $P allow "Edit /tmp/x (well formed)"                     '{"tool_name":"Edit","cwd":"/tmp","tool_input":{"file_path":"/tmp/x"}}'
# commands git runs from its own words are checked as commands (pagers, editors, drivers, --exec, run, foreach, …)
check $P block "git -c core.pager='rm -rf backlog' log"        "$(payload_bl "git -c core.pager='rm -rf backlog' log")"
check $P block "GIT_PAGER='git restore -s dev backlog' git log" "$(payload_bl "GIT_PAGER='git restore -s dev backlog' git log")"
check $P block "PAGER='rm -rf backlog' git log"                "$(payload_bl "PAGER='rm -rf backlog' git log")"
check $P block "git -c diff.external='rm backlog/x' diff"      "$(payload_bl "git -c diff.external='rm backlog/x' diff")"
check $P block "GIT_EDITOR='rm -rf backlog' git commit"        "$(payload_bl "GIT_EDITOR='rm -rf backlog' git commit")"
check $P block "git rebase --exec 'rm -rf backlog' dev"        "$(payload_bl "git rebase --exec 'rm -rf backlog' dev")"
check $P block "git rebase --exec='rm -rf backlog' dev"        "$(payload_bl "git rebase --exec='rm -rf backlog' dev")"
check $P block "git rebase -x 'git rm -r backlog' dev"         "$(payload_bl "git rebase -x 'git rm -r backlog' dev")"
check $P block "git rebase -x'rm -rf backlog' dev (attached)"  "$(payload_bl "git rebase -x'rm -rf backlog' dev")"
check $P block "git bisect run rm -rf backlog"                 "$(payload_bl 'git bisect run rm -rf backlog')"
check $P block "git submodule foreach 'rm -rf backlog'"        "$(payload_bl "git submodule foreach 'rm -rf backlog'")"
check $P block "git submodule foreach --recursive 'rm …'"      "$(payload_bl "git submodule foreach --recursive 'rm -rf backlog'")"
check $P block "git grep -O'rm -rf backlog' x"                 "$(payload_bl "git grep -O'rm -rf backlog' x")"
check $P block "git grep --open-files-in-pager='rm …' x"       "$(payload_bl "git grep --open-files-in-pager='rm -rf backlog' x")"
check $P block "git difftool -x 'rm -rf backlog' dev"          "$(payload_bl "git difftool -x 'rm -rf backlog' dev")"
check $P block "git difftool --extcmd='rm -rf backlog' dev"    "$(payload_bl "git difftool --extcmd='rm -rf backlog' dev")"
check $P block "git filter-branch --tree-filter 'rm -rf backlog'" "$(payload_bl "git filter-branch --tree-filter 'rm -rf backlog' HEAD")"
check $P block "git filter-branch --index-filter 'git rm …'"   "$(payload_bl "git filter-branch --index-filter 'git rm -r --cached backlog' HEAD")"
check $P block "git config core.pager 'rm -rf backlog'"        "$(payload_bl "git config core.pager 'rm -rf backlog'")"
check $P block "git bisect run … nested past four levels"      "$(payload_bl 'git bisect run git bisect run git bisect run git bisect run git bisect run git bisect run ls')"
check $P allow "git bisect run … nested four levels (the limit)" "$(payload_bl 'git bisect run git bisect run git bisect run git bisect run ls')"
check $P block "git bisect run … nested five levels"           "$(payload_bl 'git bisect run git bisect run git bisect run git bisect run git bisect run ls')"
check $P allow "git -c core.pager=less log"                    "$(payload_bl 'git -c core.pager=less log')"
check $P allow "git rebase --exec 'make lint' dev"             "$(payload_bl "git rebase --exec 'make lint' dev")"
check $P allow "git -c user.email=t@t commit -m x"             "$(payload_bl 'git -c user.email=t@t commit -m x')"
check $P allow "git config user.name 'A B'"                    "$(payload_bl "git config user.name 'A B'")"
check $P allow "git bisect run make test"                      "$(payload_bl 'git bisect run make test')"
check $P allow "git grep -O x (the default pager)"             "$(payload_bl 'git grep -O x')"
# git clean deletes untracked files: a task the CLI just created or completed is one
check $P block "git clean -f backlog/"                         "$(payload_bl 'git clean -f backlog/')"
check $P block "git clean -fd (the whole tree)"                "$(payload_bl 'git clean -fd')"
check $P block "cd backlog && git clean -f"                    "$(payload_bl 'cd backlog && git clean -f')"
check $P block "git clean -fd -e backlog -e '!backlog/x'"      "$(payload_bl "git clean -fd -e backlog -e '!backlog/x'")"
check $P block "git clean -n --no-dry-run -f backlog/"         "$(payload_bl 'git clean -n --no-dry-run -f backlog/')"
check $P allow "git clean -n backlog/ (dry run)"               "$(payload_bl 'git clean -n backlog/')"
check $P allow "git clean -fd -e backlog"                      "$(payload_bl 'git clean -fd -e backlog')"
check $P allow "git clean -fd --exclude=backlog/"              "$(payload_bl 'git clean -fd --exclude=backlog/')"
check $P allow "git clean -fd src"                             "$(payload_bl 'git clean -fd src')"
check $P allow "git clean -fd -- . ':!backlog'"                "$(payload_bl "git clean -fd -- . ':!backlog'")"
# git am applies patches like git apply
check $P block "git am <patch into backlog/>"                  "$(payload_bl "git am '$TMP/bl.patch'")"
check $P block "git am < patch (stdin)"                        "$(payload_bl "git am < '$TMP/src.patch'")"
check $P block "git am --directory=backlog <src patch>"        "$(payload_bl "git am --directory=backlog '$TMP/src.patch'")"
check $P block "git am --dir=backlog <src patch> (abbreviated)" "$(payload_bl "git am --dir=backlog '$TMP/src.patch'")"
check $P allow "git am <src patch>"                            "$(payload_bl "git am '$TMP/src.patch'")"
check $P allow "git am --continue / --abort / --skip"          "$(payload_bl 'git am --continue && git am --abort && git am --skip')"
check $P allow "git am --show-current-patch=diff"              "$(payload_bl 'git am --show-current-patch=diff')"
# git merge-file rewrites its first file
check $P block "git merge-file <task> a b"                     "$(payload_bl "git merge-file $T1 src/x.md src/x.md")"
check $P allow "git merge-file -p <task> a b (prints)"         "$(payload_bl "git merge-file -p $T1 src/x.md src/x.md")"
check $P allow "git merge-file --stdout <task> a b"            "$(payload_bl "git merge-file --stdout $T1 src/x.md src/x.md")"
check $P allow "git merge-file src/x.md a b"                   "$(payload_bl 'git merge-file src/x.md frontend/y.ts frontend/y.ts')"
check $P allow "git merge-file -L a -L b -L c src/x.md a b"     "$(payload_bl 'git merge-file -L backlog -L b -L c src/x.md frontend/y.ts frontend/y.ts')"
# find writes a file with -fprint and its kin; BSD find takes start paths with -f
check $P block "find src -fprint backlog/tasks/x.md"           "$(payload_bl 'find src -fprint backlog/tasks/x.md')"
check $P block "find src -fprint0 / -fprintf / -fls into backlog/" "$(payload_bl "find src -fls backlog/x; find src -fprintf backlog/y '%p'; find src -fprint0 backlog/z")"
check $P block "find src -fls backlog/x (alone)"              "$(payload_bl 'find src -fls backlog/x')"
check $P block "find src -fprint \"\$UNSET\""                  "$(payload_bl 'find src -fprint "$OP_UNSET_244"')"
check $P allow "find src -fprint /tmp/op-244-list"             "$(payload_bl 'find src -fprint /tmp/op-244-list')"
check $P block "cd src && find -f ../backlog -delete (BSD -f)" "$(payload_bl 'cd src && find -f ../backlog -delete')"
check $P block "cd src && find -f../backlog -delete (attached)" "$(payload_bl 'cd src && find -f../backlog -delete')"
check $P block "find -x -f backlog -delete"                    "$(payload_bl 'find -x -f backlog -delete')"
check $P block "cd src && find -Lx -f ../backlog -delete (a two-letter cluster)" "$(payload_bl 'cd src && find -Lx -f ../backlog -delete')"
ln -s ../backlog "$BL/src/-bl"   # a start path that begins with -: what BSD -f is for
check $P block "cd src && find -f -bl -delete (a start that begins with -)" "$(payload_bl 'cd src && find -f -bl -delete')"
rm -f "$BL/src/-bl"
check $P allow "find -f src -name x -delete"                   "$(payload_bl 'find -f src -name x -delete')"
check $P block "find backlog -exec rg --pre rm x {} +"         "$(payload_bl 'find backlog -exec rg --pre rm x {} +')"
# a reset word that is no commit yet and no path is a tree-ish; -p with no pathspec is the whole tree
check $P block "git reset nosuchref <task> (no --)"            "$(payload_bl "git reset nosuchref $T1")"
check $P allow "git reset src/x.md (a path)"                   "$(payload_bl 'git reset src/x.md')"
check $P block "git restore -p -s dev (whole tree)"            "$(payload_bl 'git restore -p -s dev')"
check $P block "git restore -p (whole tree, from the index)"   "$(payload_bl 'git restore -p')"
check $P block "git checkout -p dev (whole tree)"              "$(payload_bl 'git checkout -p dev')"
check $P block "git reset -p dev (whole tree)"                 "$(payload_bl 'git reset -p dev')"
check $P allow "git reset -p (HEAD: unstage)"                  "$(payload_bl 'git reset -p')"
check $P allow "git restore -p --staged (unstage)"             "$(payload_bl 'git restore -p --staged')"
# literal pathspecs make ':!backlog' a plain path, not an exclude
check $P block "GIT_LITERAL_PATHSPECS=1 git reset dev -- . ':!backlog'" "$(payload_bl "GIT_LITERAL_PATHSPECS=1 git reset dev -- . ':!backlog'")"
check $P block "git --literal-pathspecs restore -s dev -- . ':!backlog'" "$(payload_bl "git --literal-pathspecs restore -s dev -- . ':!backlog'")"
check $P allow "GIT_LITERAL_PATHSPECS=0 git restore -s dev -- . ':!backlog'" "$(payload_bl "GIT_LITERAL_PATHSPECS=0 git restore -s dev -- . ':!backlog'")"
# a relative --work-tree is read after -C; a path-valued option written with a $ word is unresolved
check $P block "git -C <parent> --git-dir=… --work-tree=<relative> restore" "$(payload_at / "git -C '$TMP' --git-dir='$BL/.git' --work-tree='bl repo' restore -s dev backlog")"
check $P block "git checkout-index -a -f --prefix=\$P"         "$(payload_bl 'git checkout-index -a -f --prefix=$P')"
check $P block "git apply --directory=\$D <src patch>"         "$(payload_bl "git apply --directory=\$D '$TMP/src.patch'")"
check $P allow "git checkout-index -f --prefix=out/ src/x.md"  "$(payload_bl 'git checkout-index -f --prefix=out/ src/x.md')"
check $P block "cd src && git checkout-index --prefix=backlog/ x.md (from the top)" "$(payload_bl 'cd src && git checkout-index --prefix=backlog/ x.md')"
# both sides of a rename count, C-unquoted
check $P block "git apply -R <rename src → backlog> (deletes the backlog side)" "$(payload_bl "git apply -R '$TMP/in.patch'")"
check $P block "git apply <rename from a quoted backlog path>" "$(payload_bl "git apply '$TMP/quoted.patch'")"
# read-tree -u writes the tree over the worktree; update-index flags write no file
check $P block "git read-tree -u --reset dev"                  "$(payload_bl 'git read-tree -u --reset dev')"
check $P block "git read-tree -m -u dev"                       "$(payload_bl 'git read-tree -m -u dev')"
check $P allow "git update-index --assume-unchanged <task>"    "$(payload_bl "git update-index --assume-unchanged $T1")"
check $P allow "git update-index --skip-worktree <task>"       "$(payload_bl "git update-index --skip-worktree $T1")"
check $P block "git update-index --skip-worktree --force-remove <task>" "$(payload_bl "git update-index --skip-worktree --force-remove $C1")"
check $P block "git update-index --index-info"                 "$(payload_bl 'git update-index --index-info')"
# a patch is read before the command runs: git apply/am go in a call of their own
check $P block "true && git apply <src patch>"                 "$(payload_bl "true && git apply '$TMP/src.patch'")"
check $P allow "cd src && git apply <src patch>"               "$(payload_bl "cd src && git apply '$TMP/src.patch'")"
# copies into a directory land at dest/<name> or, for src/, dest/<each entry>
check $P block "cp -R <old>/backlog . (lands at ./backlog)"    "$(payload_bl "cp -R '$TMP/oldbl/backlog' .")"
check $P block "rsync -a <old>/ ./ (its contents: backlog/ too)" "$(payload_bl "rsync -a '$TMP/oldbl/' ./")"
check $P block "ditto <old>/backlog backlog"                   "$(payload_bl "ditto '$TMP/oldbl/backlog' backlog")"
check $P allow "cp -R <old>/backlog /tmp (outside the repo)"   "$(payload_bl "cp -R '$TMP/oldbl/backlog' /tmp")"
check $P allow "cp -R src <tmp dir>"                           "$(payload_bl "cp -R src '$TMP/oldbl'")"
# other writers: patch(1), archives extracted here, sponge, touch
check $P block "patch -p1 -R < <patch>"                        "$(payload_bl "patch -p1 -R < '$TMP/src.patch'")"
check $P allow "patch --dry-run -p1 < <patch>"                 "$(payload_bl "patch --dry-run -p1 < '$TMP/src.patch'")"
check $P block "tar -xf a.tar (here)"                          "$(payload_bl 'tar -xf a.tar')"
check $P block "tar xzf a.tgz (bundled)"                       "$(payload_bl 'tar xzf a.tgz')"
check $P block "git archive dev backlog | tar -x"              "$(payload_bl 'git archive dev backlog | tar -x')"
check $P block "unzip a.zip (here)"                            "$(payload_bl 'unzip a.zip')"
check $P block "tar -xf a.tar -C \"\$UNSET\""                  "$(payload_bl 'tar -xf a.tar -C "$OP_UNSET_244"')"
check $P allow "tar -xf a.tar -C <dir of its own>"             "$(payload_bl "tar -xf a.tar -C '$TMP/oldbl'")"
check $P allow "tar -xf a.tar --directory=src"                 "$(payload_bl 'tar -xf a.tar --directory=src')"
check $P allow "tar -czf /tmp/o.tgz src (creates)"             "$(payload_bl 'tar -czf /tmp/o.tgz src')"
check $P allow "unzip -l a.zip (lists)"                        "$(payload_bl 'unzip -l a.zip')"
check $P allow "unzip a.zip -d src"                            "$(payload_bl 'unzip a.zip -d src')"
check $P block "sponge backlog/tasks/x.md"                     "$(payload_bl 'sponge backlog/tasks/x.md')"
check $P block "touch backlog/tasks/new.md"                    "$(payload_bl 'touch backlog/tasks/new.md')"
check $P allow "touch src/new.md"                              "$(payload_bl 'touch src/new.md')"
# a path only the shell knows is refused where backlog/ is, data/ or not
check $P block "rm -f \"\$UNSET\" (repo with backlog/, no data/)" "$(payload_bl 'rm -f "$OP_UNSET_244"')"
check $P block "echo x > \"\$UNSET\" (repo with backlog/)"     "$(payload_bl 'echo x > "$OP_UNSET_244"')"
check $P block "mv \"\$UNSET\" src/ (repo with backlog/)"      "$(payload_bl 'mv "$OP_UNSET_244" src/')"
# every protected sibling, and no prefix confusion
check $P block "git rm -r backlog/archive"                     "$(payload_bl 'git rm -r backlog/archive')"
check $P block "git restore -s dev backlog/decisions"          "$(payload_bl 'git restore -s dev backlog/decisions')"
check $P block "git checkout dev -- backlog/milestones"        "$(payload_bl 'git checkout dev -- backlog/milestones')"
check $P allow "git restore -s dev backlogX/y (another dir)"   "$(payload_bl 'git restore -s dev backlogX/y')"
check $P allow "git rm -r backlog-old (another dir)"           "$(payload_bl 'git rm -r backlog-old')"
check $P allow "rm -rf backlogX"                               "$(payload_bl 'rm -rf backlogX')"
check $P block "git rm -r data/snapshots (main repo)"          "$(payload_bash 'git rm -r data/snapshots')"
check $P block "git checkout dev -- data/indexes/abc"          "$(payload_bash 'git checkout dev -- data/indexes/abc')"
check $P block "git restore -s dev 'data/snap*'"               "$(payload_bash "git restore -s dev 'data/snap*'")"
check $P block "find src -fprint data/snapshots/s1/x"          "$(payload_bash 'find frontend -fprint data/snapshots/s1/x')"
check $P block "cd frontend && find -f ../data/snapshots -delete" "$(payload_bash 'cd frontend && find -f ../data/snapshots -delete')"
check $P allow "git restore -s dev -- frontend/src/data (not data/)" "$(payload_bash 'git restore -s dev -- frontend/src/data')"
check $P allow "rm -rf data-old (another dir)"                 "$(payload_bash 'rm -rf data-old')"
# review rows: values that read as backlog/ paths, stash from a file, a file named -, --recount
check $P allow "git restore -s backlog/old -- src/x.md (-s takes a value)" "$(payload_bl 'git restore -s backlog/old -- src/x.md')"
check $P allow "git checkout --orphan backlog"                 "$(payload_bl 'git checkout --orphan backlog')"
check $P allow "git checkout -B backlog dev"                   "$(payload_bl 'git checkout -B backlog dev')"
check $P block "git stash push --pathspec-from-file=list"      "$(payload_bl 'git stash push --pathspec-from-file=list')"
: > "$BL/-"
check $P block "git apply --allow-empty - (a file named - exists)" "$(payload_bl 'git apply --allow-empty -')"
rm -f "$BL/-"
check $P allow "git apply --recount <src patch with wrong counts>" "$(payload_bl "git apply --recount '$TMP/recount.patch'")"
check $P allow "git merge-file src/x.md <task> <task> (reads them)" "$(payload_bl "git merge-file src/x.md $T1 $T1")"
mv "$BL/frontend/y.ts" "$TMP/y.ts.bak"   # tracked, not on disk: still a path to git
check $P allow "git reset frontend/y.ts <task> (y.ts in the index only: a path, so unstaging)" "$(payload_bl "git reset frontend/y.ts $T1")"
mv "$TMP/y.ts.bak" "$BL/frontend/y.ts"
# review round 2: a parse failure anywhere refuses (a nested -c value once ended the check with exit 0)
check $P block "from outside a repo: git -C <repo> -c user.name=\"it's\" rm -r backlog" "$(payload_at / "git -C '$BL' -c user.name=\"it's\" rm -r backlog")"
check $P block "from outside a repo: git -C <repo> -c core.pager='\"' rm -r backlog" "$(payload_at / "git -C '$BL' -c core.pager='\"' rm -r backlog")"
check $P block "an unparseable command outside any repo"       "$(payload_at / 'echo "unbalanced')"
check $P allow "git -c user.name=\"O'Brien\" commit -m x (not a command key)" "$(payload_bl "git -c user.name=\"O'Brien\" commit -m x")"
check $P allow "git config branch.feat.description \"it's done\"" "$(payload_bl "git config branch.feat.description \"it's done\"")"
check $P block "git config --file .git/config core.pager 'rm -rf backlog'" "$(payload_bl "git config --file .git/config core.pager 'rm -rf backlog'")"
check $P block "git config set core.pager 'rm -rf backlog'"    "$(payload_bl "git config set core.pager 'rm -rf backlog'")"
check $P block "git -c pager.log='rm -rf backlog' log"         "$(payload_bl "git -c pager.log='rm -rf backlog' log")"
check $P block "git -c filter.x.smudge='rm -rf backlog' checkout dev" "$(payload_bl "git -c filter.x.smudge='rm -rf backlog' checkout dev")"
check $P block "git rebase -ix 'rm -rf backlog' dev (in a cluster)" "$(payload_bl "git rebase -ix 'rm -rf backlog' dev")"
check $P block "git rebase --exe 'rm -rf backlog' dev (abbreviated)" "$(payload_bl "git rebase --exe 'rm -rf backlog' dev")"
check $P block "git difftool --extc='rm -rf backlog' dev (abbreviated)" "$(payload_bl "git difftool --extc='rm -rf backlog' dev")"
check $P block "git grep --open='rm -rf backlog' x (abbreviated)" "$(payload_bl "git grep --open='rm -rf backlog' x")"
check $P block "git filter-branch --setup 'rm -rf backlog' HEAD" "$(payload_bl "git filter-branch --setup 'rm -rf backlog' HEAD")"
check $P block "find -follow -name '*.md' -delete (a primary, not -f ollow)" "$(payload_bl "find -follow -name '*.md' -delete")"
check $P block "cd src && find -O3 ../backlog -delete (GNU -O)" "$(payload_bl 'cd src && find -O3 ../backlog -delete')"
check $P block "cd src && find -D tree -O3 ../backlog -delete (GNU -D)" "$(payload_bl 'cd src && find -D tree -O3 ../backlog -delete')"
check $P allow "find backlog -exec rg --pretty x {} + (not --pre)" "$(payload_bl 'find backlog -exec rg --pretty x {} +')"
check $P block "tar -v -xf a.tar (x after another flag)"       "$(payload_bl 'tar -v -xf a.tar')"
check $P block "tar --verbose -xf a.tar"                       "$(payload_bl 'tar --verbose -xf a.tar')"
check $P block "tar -C . -xf a.tar"                            "$(payload_bl 'tar -C . -xf a.tar')"
check $P block "tar -xf a.tar --directory=\$X"                 "$(payload_bl 'tar -xf a.tar --directory=$X')"
check $P block "ditto <old repo> . (its contents land here)"   "$(payload_bl "ditto '$TMP/oldbl' .")"
check $P block "git checkout-index -a -f --prefix \"\$UNSET\" (separate)" "$(payload_bl 'git checkout-index -a -f --prefix "$OP_UNSET_244"')"
check $P block "cd src && cd \"\$UNSET\" && git checkout-index -a -f (a built pathspec after an unknown cd)" "$(payload_bl 'cd src && cd "$OP_UNSET_244" && git checkout-index -a -f')"
check $P block "git restore -s dev \"\${HOME}backlog\" (backlog/ only with HOME read as '')" "$(payload_bl 'git restore -s dev "${HOME}backlog"')"
check $P block "ditto src/x.md backlog/tasks/new.md (a new file in backlog/)" "$(payload_bl 'ditto src/x.md backlog/tasks/new.md')"
check $P block "cd \"\$UNSET\" && tar -xf a.tar -C sub (an unresolved extract dir)" "$(payload_bl 'cd "$OP_UNSET_244" && tar -xf a.tar -C sub')"
check $P block "cp src/x.md \"\$UNSET\" (an unresolved destination, repo with backlog/)" "$(payload_bl 'cp src/x.md "$OP_UNSET_244"')"
check $P block "git apply --directory \"\$UNSET\" <src patch> (separate)" "$(payload_bl "git apply --directory \"\$OP_UNSET_244\" '$TMP/src.patch'")"
check $P block "git apply -R <copy src → backlog> (deletes the copy)" "$(payload_bl "git apply -R '$TMP/copy.patch'")"
check $P block "git apply <rename from a quoted UTF-8 backlog path>" "$(payload_bl "git apply '$TMP/utf8.patch'")"
check $P allow "git apply --check <patch> && git apply <patch>" "$(payload_bl "git apply --check '$TMP/src.patch' && git apply '$TMP/src.patch'")"
check $P block "git clean -fdX -e backlog -- backlog (-X adds it)" "$(payload_bl 'git clean -fdX -e backlog -- backlog')"
# every sink judged after normalization: .., a trailing slash, an absolute path, a symlink, -t <dir>
check $P block "rm -r ./backlog/ (trailing slash)"             "$(payload_bl 'rm -r ./backlog/')"
check $P block "rm src/../backlog/tasks/x.md (..)"             "$(payload_bl 'rm src/../backlog/tasks/x.md')"
check $P block "mv src/x.md <abs repo>/backlog/tasks/"         "$(payload_at / "mv '$BL/src/x.md' '$BL/backlog/tasks/'")"
check $P block "git restore -s dev src/../backlog/"            "$(payload_bl 'git restore -s dev src/../backlog/')"
check $P block "cp -t backlog/tasks src/x.md (GNU -t)"         "$(payload_bl 'cp -t backlog/tasks src/x.md')"
check $P block "mv --target-directory=backlog/tasks src/x.md"  "$(payload_bl 'mv --target-directory=backlog/tasks src/x.md')"
check $P block "cp -t \"\$UNSET\" src/x.md"                    "$(payload_bl 'cp -t "$OP_UNSET_244" src/x.md')"
check $P allow "cp -t /tmp src/x.md"                           "$(payload_bl 'cp -t /tmp src/x.md')"
ln -s backlog "$BL/bl"   # a symlink into backlog/
check $P block "rm bl/tasks/x.md (through a symlink)"          "$(payload_bl 'rm bl/tasks/x.md')"
check $P block "cp src/x.md bl/tasks/ (through a symlink)"     "$(payload_bl 'cp src/x.md bl/tasks/')"
check $P block "git rm bl/tasks/x.md (through a symlink)"      "$(payload_bl 'git rm bl/tasks/x.md')"
rm -f "$BL/bl"
mkdir -p "$TMP/plain244"; git init -q "$TMP/plain244"
check $P allow "git restore \"\$UNSET\" in a repo without backlog/" "$(payload_at "$TMP/plain244" 'git restore "$OP_UNSET_244"')"
check $P allow "git restore --pathspec-from-file=l, no backlog/" "$(payload_at "$TMP/plain244" 'git restore --pathspec-from-file=l')"
check $P allow "git restore . / ':/' / '*.md' / ':!src', no backlog/" "$(payload_at "$TMP/plain244" "git restore . && git restore ':/' && git checkout -- '*.md' && git restore -- ':!src'")"
check $P allow "find . -name x -delete, no backlog/"           "$(payload_at "$TMP/plain244" "find . -name '*.pyc' -delete")"
check $P block "git reset nosuch -- backlog/x (no HEAD: unborn)" "$(payload_at "$TMP/plain244" 'git reset nosuch -- backlog/x')"
# a conflict in a task file (a rebase, merge or cherry-pick stopped on it) is settled with git: Edit is refused there
BLC="$TMP/blc repo"
blc() { git -C "$BLC" -c user.email=t@t -c user.name=t "$@"; }
git init -q -b dev "$BLC"; mkdir -p "$BLC/backlog/tasks" "$BLC/src"
printf 'a\n' > "$BLC/backlog/tasks/task-2 - c.md"; printf 'a\n' > "$BLC/backlog/tasks/task-3 - d.md"; printf 'a\n' > "$BLC/src/s.md"
blc add -A && blc commit -qm init
blc switch -qc side && printf 'side\n' > "$BLC/backlog/tasks/task-2 - c.md" && blc commit -qam side
blc switch -q dev && printf 'dev\n' > "$BLC/backlog/tasks/task-2 - c.md" && blc commit -qam dev
blc merge -q side >/dev/null 2>&1
T2='"backlog/tasks/task-2 - c.md"'
payload_blc() { payload_at "$BLC" "$1"; }
check $P allow "git checkout --theirs <conflicted task>"       "$(payload_blc "git checkout --theirs -- $T2")"
check $P allow "git restore --ours <conflicted task>"          "$(payload_blc "git restore --ours $T2")"
check $P allow "git checkout -m <conflicted task>"             "$(payload_blc "git checkout -m $T2")"
check $P block "git rm <conflicted task> (the older rule refuses git rm there)"                      "$(payload_blc "git rm $T2")"
check $P block "git checkout --theirs backlog/ (a merged file too)" "$(payload_blc 'git checkout --theirs -- backlog/')"
check $P block "git checkout --theirs <merged task>"           "$(payload_blc "git checkout --theirs -- 'backlog/tasks/task-3 - d.md'")"
check $P block "git checkout side -- <conflicted task> (a commit's copy)" "$(payload_blc "git checkout side -- $T2")"
check $P block "git restore --source=side <conflicted task>"   "$(payload_blc "git restore --source=side $T2")"
check $P block "git rm backlog/tasks/nosuch.md (matches nothing)" "$(payload_blc 'git rm backlog/tasks/nosuch.md')"
check $P block "git checkout side <conflicted task> (no --)"   "$(payload_blc "git checkout side $T2")"
# conflicts are read in this repository only
check $P block "git --git-dir/--work-tree … checkout --theirs <conflicted> (git pointed elsewhere: no exemption)" "$(payload_blc "git --git-dir='$BLC/.git' --work-tree='$BLC' checkout --theirs -- $T2")"
# a repo whose only file is in conflict: paths from a file are still unseen
BLX="$TMP/blx"
git init -q -b dev "$BLX"; mkdir -p "$BLX/backlog/tasks"; printf 'a\n' > "$BLX/backlog/tasks/x.md"
git -C "$BLX" -c user.email=t@t -c user.name=t add -A && git -C "$BLX" -c user.email=t@t -c user.name=t commit -qm init
git -C "$BLX" switch -qc side && printf 'b\n' > "$BLX/backlog/tasks/x.md" && git -C "$BLX" -c user.email=t@t -c user.name=t commit -qam side
git -C "$BLX" switch -q dev && printf 'c\n' > "$BLX/backlog/tasks/x.md" && git -C "$BLX" -c user.email=t@t -c user.name=t commit -qam dev
git -C "$BLX" -c user.email=t@t -c user.name=t merge -q side >/dev/null 2>&1
check $P block "git restore --ours --pathspec-from-file=list (all in conflict)" "$(payload_at "$BLX" 'git restore --ours --pathspec-from-file=list')"
# review round 3 and the additive guard: whole-worktree resets, more command keys, -t forms, and state that can drift
check $P block "git reset --merge dev"                         "$(payload_bl 'git reset --merge dev')"
check $P block "git reset --keep dev"                          "$(payload_bl 'git reset --keep dev')"
check $P allow "git reset --soft HEAD~1 (index and worktree kept)" "$(payload_bl 'git reset --soft HEAD~1')"
check $P allow "git reset --hard in a repo without backlog/"   "$(payload_at "$TMP/plain244" 'git reset --hard')"
check $P block "git -c difftool.x.cmd='rm -rf backlog' difftool -t x" "$(payload_bl "git -c difftool.x.cmd='rm -rf backlog' difftool -t x")"
check $P block "git -c mergetool.x.cmd='rm -rf backlog' mergetool -t x" "$(payload_bl "git -c mergetool.x.cmd='rm -rf backlog' mergetool -t x")"
check $P block "git config alias.x '!rm -rf backlog' (a ! value)" "$(payload_bl "git config alias.x '!rm -rf backlog'")"
check $P block "git config alias.x '!git restore -s dev backlog' (a ! value only the guard reads)" "$(payload_bl "git config alias.x '!git restore -s dev backlog'")"
check $P block "git -c credential.helper='!rm -rf backlog' push" "$(payload_bl "git -c credential.helper='!rm -rf backlog' push")"
check $P block "git grep -nO'rm -rf backlog' x (in a cluster)" "$(payload_bl "git grep -nO'rm -rf backlog' x")"
check $P block "cp -vt backlog/tasks src/x.md (-t in a cluster)" "$(payload_bl 'cp -vt backlog/tasks src/x.md')"
check $P block "cp -tbacklog/tasks src/x.md (attached)"        "$(payload_bl 'cp -tbacklog/tasks src/x.md')"
check $P block "cp --target-directory backlog/tasks src/x.md (separate)" "$(payload_bl 'cp --target-directory backlog/tasks src/x.md')"
check $P block "mv --target=backlog/tasks src/x.md (a prefix)" "$(payload_bl 'mv --target=backlog/tasks src/x.md')"
check $P block "cp -t data/snapshots/s1 x (main repo)"         "$(payload_bash 'cp -t data/snapshots/s1 README.md')"
check $P block "ditto x data/indexes/abc (main repo)"          "$(payload_bash 'ditto README.md data/indexes/abc')"
check $P allow "git add -u <conflicted task> (accepts a deletion)" "$(payload_blc "git add -u $T2")"
check $P block "Bash with no cwd"                              '{"tool_name":"Bash","tool_input":{"command":"ls"}}'
check $P block "Bash with a cwd that is no directory"          '{"tool_name":"Bash","cwd":"/nonexistent/op-244","tool_input":{"command":"ls"}}'
ln -s "$BL" "$TMP/bl-link"   # the repo reached through a symlink
check $P block "git rm backlog/x from a symlinked cwd"         "$(payload_at "$TMP/bl-link" 'git rm backlog/tasks/x.md')"
check $P block "git restore -s dev backlog via a symlinked -C" "$(payload_at / "git -C '$TMP/bl-link' restore -s dev backlog")"
check $P block "find <symlinked repo> -name x -delete"         "$(payload_at / "find '$TMP/bl-link/backlog' -name x -delete")"
rm -f "$TMP/bl-link"
mkdir -p "$TMP/broken244"; printf 'gitdir: /nonexistent/op-244\n' > "$TMP/broken244/.git"   # git rev-parse fails here
check $P block "a repo git rev-parse can't read (cwd)"         "$(payload_at "$TMP/broken244" 'ls')"
check $P block "git -C <a repo rev-parse can't read> rm x"     "$(payload_at / "git -C '$TMP/broken244' rm x")"
check $P allow "ls outside any repo"                           "$(payload_at "$TMP/oldbl" 'ls')"
# the guard leaves the older checks' state alone: what it records while reading HOME as '' doesn't stop their globbing
check $P block "rm -rf \${HOME}data* data* (main repo: the older rule still globs data*)" "$(payload_bash 'rm -rf ${HOME}data* data*')"
check $P allow "ls inside .git (rev-parse --git-dir reads it)" "$(payload_at "$BL/.git" 'ls')"

echo "== TASK-244: the older data/ rules in a repo with data/ and no backlog/ (the backlog guard can't mask them there)"
DO="$TMP/data only"
git init -q -b dev "$DO"; mkdir -p "$DO/data/snapshots/s1" "$DO/data/indexes/i1" "$DO/src"; printf '/data/\n' > "$DO/.gitignore"; printf 'x\n' > "$DO/src/x.md"
git -C "$DO" -c user.email=t@t -c user.name=t add -A && git -C "$DO" -c user.email=t@t -c user.name=t commit -qm init
git -C "$DO" worktree add -q "$TMP/data only wt" -b dowt
payload_do() { payload_at "$DO" "$1"; }
check $P block "data-only: dd of=\"\$UNSET\""                   "$(payload_do 'dd if=/dev/zero of="$OP_UNSET_244" count=1')"
check $P block "data-only: find . -execdir rm {} +"             "$(payload_do 'find . -name x -execdir rm {} +')"
check $P block "data-only: find . -ok rm {} ;"                  "$(payload_do "find . -name x -ok rm {} ';'")"
# the first start must not cover the root itself: on Linux mktemp's root is under /tmp, so `find /tmp .` was blocked
# by its first start and the second went untested (TASK-261)
check $P block "data-only: find src . -delete (the second start)" "$(payload_do 'find src . -name x -delete')"
check $P allow "data-only: find src -delete (the first start alone)" "$(payload_do 'find src -name x -delete')"
check $P block "data-only: find <sibling dir> . -delete (an absolute first start)" "$(payload_do "find '$TMP/home' . -name x -delete")"
check $P block "data-only: find -delete (no start: .)"          "$(payload_do 'find -name x -delete')"
check $P block "data-only: find \"\$UNSET\" -delete"            "$(payload_do 'find "$OP_UNSET_244" -delete')"
check $P block "data-only: cd src && cd \"\$UNSET\" && find -name x -delete" "$(payload_do 'cd src && cd "$OP_UNSET_244" && find -name x -delete')"
check $P block "data-only: git clean -fdX -e data"              "$(payload_do 'git clean -fdX -e data')"
check $P block "data-only: git clean -fdx data/snapshots"       "$(payload_do 'git clean -fdx data/snapshots')"
check $P block "data-only: git clean -fdx data"                 "$(payload_do 'git clean -fdx data')"
check $P block "data-only: git clean -fdx :/"                   "$(payload_do 'git clean -fdx :/')"
check $P block "data-only: git clean -fdx \"\$UNSET\""          "$(payload_do 'git clean -fdx "$OP_UNSET_244"')"
check $P block "data-only: cd \"\$UNSET\" && git clean -fdx"    "$(payload_do 'cd "$OP_UNSET_244" && git clean -fdx')"
check $P block "data-only: ls | xargs git add"                  "$(payload_do 'ls | xargs git add')"
check $P block "data-only: git update-index --index-info"       "$(payload_do 'git update-index --index-info')"
check $P block "data-only: git update-index --add --stdin"      "$(payload_do 'git update-index --add --stdin')"
check $P block "data-only: git update-index --add \"\$UNSET\""  "$(payload_do 'git update-index --add "$OP_UNSET_244"')"
check $P block "data-only: rm -rf \"\$UNSET\""                  "$(payload_do 'rm -rf "$OP_UNSET_244"')"
check $P block "data-only: cp x \"\$UNSET\""                    "$(payload_do 'cp src/x.md "$OP_UNSET_244"')"
check $P block "data-only: echo x > \"\$UNSET\""                "$(payload_do 'echo x > "$OP_UNSET_244"')"
check $P block "data-only: cd /tmp && rm -rf \"\$UNSET\" (the call's own worktree has data/)" "$(payload_do 'cd /tmp && rm -rf "$OP_UNSET_244"')"
check $P block "data-only worktree: rm -rf \"\$UNSET\" (its main worktree has data/)" "$(payload_at "$TMP/data only wt" 'rm -rf "$OP_UNSET_244"')"
check $P allow "data-only: rm -rf src (no data/ under it)"      "$(payload_do 'rm -rf src')"
# starts the older find check misreads (it reads only exact leading flags), and a `!` exclude after -e data
check $P block "data-only: cd src && find -O3 ../data/snapshots -delete" "$(payload_do 'cd src && find -O3 ../data/snapshots -delete')"
check $P block "data-only: cd src && find -Lx ../data/snapshots -delete" "$(payload_do 'cd src && find -Lx ../data/snapshots -delete')"
check $P block "data-only: cd src && find -D tree ../data/snapshots -delete" "$(payload_do 'cd src && find -D tree ../data/snapshots -delete')"
check $P block "data-only: cd src && find -f ../data/snapshots -delete" "$(payload_do 'cd src && find -f ../data/snapshots -delete')"
check $P block "data-only: cd src && find -Lx \"\$UNSET\" -delete" "$(payload_do 'cd src && find -Lx "$OP_UNSET_244" -delete')"
check $P block "data-only: git clean -fdx -e data -e '!data' data/snapshots" "$(payload_do "git clean -fdx -e data -e '!data' data/snapshots")"
check $P block "data-only: git clean -fdx -e data -e '!data'"  "$(payload_do "git clean -fdx -e data -e '!data'")"
check $P allow "data-only: git clean -fdx -e data"             "$(payload_do 'git clean -fdx -e data')"
check $P allow "data-only: git clean -fdx -e '!data' -e data (the last pattern keeps data/)" "$(payload_do "git clean -fdx -e '!data' -e data")"
check $P allow "data-only: git clean -fdx -e data -e '!node_modules'" "$(payload_do "git clean -fdx -e data -e '!node_modules'")"
check $P block "data-only: git clean -fdx -e data -e '!DATA' (core.ignorecase)" "$(payload_do "git clean -fdx -e data -e '!DATA'")"
check $P block "data-only: git clean -fdx -e data -e '!d*' (a glob)" "$(payload_do "git clean -fdx -e data -e '!d*'")"
check $P block "data-only: find -name x -exec grep y {} + (no start: ., a reader)" "$(payload_do 'find -name x -exec grep y {} +')"
check $P block "data-only: cd /tmp && find -Lx \"\$UNSET\" -delete (the call's worktree has data/)" "$(payload_do 'cd /tmp && find -Lx "$OP_UNSET_244" -delete')"

echo "== TASK-248 rows (more wrappers cmdparse strips: xcrun, caffeinate, arch, doas, flock, unbuffer)"
# block-ai-attribution reads a commit's -F file only once it sees git commit ($TMP/msg.txt holds a Claude trailer)
check $A block "xcrun git commit -F msg"                        "$(payload_bash "xcrun git commit -F '$TMP/msg.txt'")"
check $A block "xcrun --sdk macosx git commit -F msg"           "$(payload_bash "xcrun --sdk macosx git commit -F '$TMP/msg.txt'")"
check $A block "caffeinate -w 1 git commit -F msg"              "$(payload_bash "caffeinate -w 1 git commit -F '$TMP/msg.txt'")"
check $A block "arch -arch arm64 git commit -F msg"             "$(payload_bash "arch -arch arm64 git commit -F '$TMP/msg.txt'")"
check $A block "doas -C /etc/doas.conf git commit -F msg"       "$(payload_bash "doas -C /etc/doas.conf git commit -F '$TMP/msg.txt'")"
check $A block "flock --timeout 5 <lock> git commit -F msg"     "$(payload_bash "flock --timeout 5 /tmp/op.lock git commit -F '$TMP/msg.txt'")"
check $A block "flock <lock> -c 'git commit -F msg'"            "$(payload_bash "flock /tmp/op.lock -c \"git commit -F '$TMP/msg.txt'\"")"
check $A block "unbuffer git commit -F msg"                     "$(payload_bash "unbuffer git commit -F '$TMP/msg.txt'")"
check $A allow "flock <lock> -c 'git commit -F clean notes'"    "$(payload_bash "flock /tmp/op.lock -c \"git commit -F '$TMP/notes.md'\"")"
# require-review: other2 is never reviewed
check $R block "xcrun git push"                                 "$(payload_bash 'xcrun git push origin other2')"
check $R block "xcrun -toolchain swift git push"                "$(payload_bash 'xcrun -toolchain swift git push origin other2')"
check $R block "caffeinate -t 60 git push"                      "$(payload_bash 'caffeinate -t 60 git push origin other2')"
check $R block "arch -d HOME git push"                          "$(payload_bash 'arch -d HOME git push origin other2')"
check $R block "doas -u root git push"                          "$(payload_bash 'doas -u root git push origin other2')"
check $R block "flock -E 3 <lock> git push"                     "$(payload_bash 'flock -E 3 /tmp/op.lock git push origin other2')"
check $R block "flock -n <lock> --command 'git push'"           "$(payload_bash "flock -n /tmp/op.lock --command 'git push origin other2'")"
check $R block "unbuffer -p git push"                           "$(payload_bash 'unbuffer -p git push origin other2')"
check $R block "doas -a passwd git push (-a takes a style)"     "$(payload_bash 'doas -a passwd git push origin other2')"
check $R allow "flock <lock> -c 'git status'"                   "$(payload_bash "flock /tmp/op.lock -c 'git status'")"
check $R allow "flock <lock> --command 'git status'"            "$(payload_bash "flock /tmp/op.lock --command 'git status'")"
# flock creates its lock file: a write, as a `>>` redirect is (review round 1: it hid an op-reviews/ path)
check $R block "flock .git/op-reviews/<sha> true (creates a record)" "$(payload_bash 'flock .git/op-reviews/0123abc true')"
check $R block "flock -w 5 .git/op-reviews/<sha> -c true"       "$(payload_bash "flock -w 5 .git/op-reviews/0123abc -c 'true'")"
check $R allow "flock <lock> true"                              "$(payload_bash 'flock /tmp/op.lock true')"
# ... whatever flock runs: eval and cd are read by the walk, not yielded (review round 2)
check $R block "flock .git/op-reviews/<sha> eval true"          "$(payload_bash 'flock .git/op-reviews/0123abc eval true')"
check $R block "flock .git/op-reviews/<sha> cd ."               "$(payload_bash 'flock .git/op-reviews/0123abc cd .')"
check $R block "arch -e A=1 -e B=2 git push (-e takes a value)" "$(payload_bash 'arch -e A=1 -e B=2 git push origin other2')"
# protect-data-dir, in the data-only repo and the backlog repo
check $P block "data-only: xcrun -sdk macosx rm -rf data/snapshots" "$(payload_do 'xcrun -sdk macosx rm -rf data/snapshots')"
check $P block "data-only: caffeinate -t 5 rm -rf data/snapshots" "$(payload_do 'caffeinate -t 5 rm -rf data/snapshots')"
check $P block "data-only: arch -arch arm64 rm -rf data/indexes" "$(payload_do 'arch -arch arm64 rm -rf data/indexes')"
check $P block "data-only: doas -u root rm -rf data/snapshots"  "$(payload_do 'doas -u root rm -rf data/snapshots')"
check $P block "data-only: flock --wait 5 <lock> rm -rf data/snapshots" "$(payload_do 'flock --wait 5 /tmp/op.lock rm -rf data/snapshots')"
check $P block "data-only: flock <lock> -c 'rm -rf data/snapshots'" "$(payload_do "flock /tmp/op.lock -c 'rm -rf data/snapshots'")"
check $P block "data-only: unbuffer rm -rf data/indexes"        "$(payload_do 'unbuffer rm -rf data/indexes')"
check $P block "data-only: doas -a passwd rm -rf data/snapshots" "$(payload_do 'doas -a passwd rm -rf data/snapshots')"
check $P block "data-only: flock data/snapshots/s1/x.lock true (creates it)" "$(payload_do 'flock data/snapshots/s1/x.lock true')"
check $P block "flock backlog/tasks/x.lock true (creates it)"   "$(payload_bl 'flock backlog/tasks/x.lock true')"
check $P allow "data-only: flock /tmp/op.lock true"             "$(payload_do 'flock /tmp/op.lock true')"
check $P block "flock backlog/tasks/x.lock eval true"           "$(payload_bl 'flock backlog/tasks/x.lock eval true')"
check $P block "data-only: flock data/snapshots/x.lock env -C /tmp true (created where flock runs)" "$(payload_do 'flock data/snapshots/x.lock env -C /tmp true')"
check $P allow "cd backlog/tasks && flock -n 9 (a file descriptor, not a file)" "$(payload_bl 'cd backlog/tasks && flock -n 9')"
check $P allow "data-only: flock <lock> -c 'ls data/snapshots'" "$(payload_do "flock /tmp/op.lock -c 'ls data/snapshots'")"
# protect-data-dir refuses every command it can't parse, so this is the row that tells --command from a stray option
check $P allow "data-only: flock <lock> --command 'ls data/snapshots'" "$(payload_do "flock /tmp/op.lock --command 'ls data/snapshots'")"
check $P allow "data-only: caffeinate -t 5 ls data/snapshots"   "$(payload_do 'caffeinate -t 5 ls data/snapshots')"
check $P block "xcrun git restore -s dev <task>"                "$(payload_bl "xcrun git restore -s dev $T1")"
check $P block "flock <lock> -c 'git restore -s dev <task>'"    "$(payload_bl "flock /tmp/op.lock -c 'git restore -s dev $T1'")"

echo "== TASK-253 rows (getopt wrappers, env -C / sudo -D for one command, sh -c and eval redirects, mv -t)"
# A short group ending in a value-taking letter takes the next word (or the rest of the word); a long option resolves
# by unique prefix; an option the parser can't place is a ParseError, refused (other2 is never reviewed)
check $A block "sudo -nu root git commit -F msg"                "$(payload_bash "sudo -nu root git commit -F '$TMP/msg.txt'")"
check $R block "sudo -nu root git push"                         "$(payload_bash 'sudo -nu root git push origin other2')"
check $R block "sudo -nuroot git push (attached)"               "$(payload_bash 'sudo -nuroot git push origin other2')"
check $R block "doas -nu root git push"                         "$(payload_bash 'doas -nu root git push origin other2')"
check $R block "caffeinate -dt 5 git push"                      "$(payload_bash 'caffeinate -dt 5 git push origin other2')"
check $R block "env -iu FOO git push"                           "$(payload_bash 'env -iu FOO git push origin other2')"
check $R block "env -S '-u FOO git push' (env reads -S words as its own)" "$(payload_bash "env -S '-u FOO git push origin other2'")"
check $R block "nice -n 5 git push"                             "$(payload_bash 'nice -n 5 git push origin other2')"
check $R block "timeout -vk 5 10 git push"                      "$(payload_bash 'timeout -vk 5 10 git push origin other2')"
check $R block "flock -nw 5 <lock> git push"                    "$(payload_bash 'flock -nw 5 /tmp/op.lock git push origin other2')"
check $R block "flock -nw5 <lock> git push (attached)"          "$(payload_bash 'flock -nw5 /tmp/op.lock git push origin other2')"
check $R block "flock --wai 5 <lock> git push (a unique prefix)" "$(payload_bash 'flock --wai 5 /tmp/op.lock git push origin other2')"
check $R block "flock --c 3 <lock> git push (--close or --conflict-exit-code)" "$(payload_bash 'flock --c 3 /tmp/op.lock git push origin other2')"
check $R block "flock <lock> -n git push (an option after the lock file)" "$(payload_bash 'flock /tmp/op.lock -n git push origin other2')"
check $R block "sudo -Q root git push (an option sudo doesn't have)" "$(payload_bash 'sudo -Q root git push origin other2')"
check $R allow "flock --wai 5 <lock> git status"                "$(payload_bash 'flock --wai 5 /tmp/op.lock git status')"
check $R allow "sudo -nu root git status"                       "$(payload_bash 'sudo -nu root git status')"
# an optional value is only ever attached: `sudo -h` and `--preserve-env` alone take no word
check $R block "sudo -h git push (-h's host only attached)"     "$(payload_bash 'sudo -h git push origin other2')"
check $R block "sudo --preserve-env git push"                   "$(payload_bash 'sudo --preserve-env git push origin other2')"
check $R allow "sudo --preserve-env git status"                 "$(payload_bash 'sudo --preserve-env git status')"
check $A block "env -a x git commit -F msg (-a takes argv0)"    "$(payload_bash "env -a x git commit -F '$TMP/msg.txt'")"
check $A allow "nice --5 git commit -F clean notes (nice's --N)" "$(payload_bash "nice --5 git commit -F '$TMP/notes.md'")"
check $A allow "nice -+5 git commit -F clean notes (nice's -+N)" "$(payload_bash "nice -+5 git commit -F '$TMP/notes.md'")"
check $P block "data-only: sudo -nu root rm -rf data/snapshots" "$(payload_do 'sudo -nu root rm -rf data/snapshots')"
check $P block "data-only: flock -nw 5 <lock> rm -rf data/snapshots" "$(payload_do 'flock -nw 5 /tmp/op.lock rm -rf data/snapshots')"
check $P block "data-only: env - rm -rf data/snapshots (env - is env -i)" "$(payload_do 'env - rm -rf data/snapshots')"
check $P allow "data-only: nice -5 ls data/snapshots (nice's old -N form)" "$(payload_do 'nice -5 ls data/snapshots')"
check $P allow "data-only: sudo -- ls data/snapshots"           "$(payload_do 'sudo -- ls data/snapshots')"
check $P allow "data-only: sudo --login ls (an exact name, though --login-class shares it)" "$(payload_do 'sudo --login ls data/snapshots')"
# env -C and sudo -D move only the command they run; its redirects are still opened where the shell is
check $P block "data-only: env -C /tmp true; rm -rf data/snapshots" "$(payload_do 'env -C /tmp true; rm -rf data/snapshots')"
check $P block "data-only: sudo -D /tmp true; rm -rf data/snapshots" "$(payload_do 'sudo -D /tmp true; rm -rf data/snapshots')"
check $P block "data-only: eval 'env -C /tmp true'; rm -rf data/snapshots" "$(payload_do "eval 'env -C /tmp true'; rm -rf data/snapshots")"
check $P allow "data-only: env -C /tmp rm -rf data/snapshots (in /tmp)" "$(payload_do 'env -C /tmp rm -rf data/snapshots')"
check $P block "data-only: env -C src/.. rm -rf data/snapshots (resolved from here)" "$(payload_do 'env -C src/.. rm -rf data/snapshots')"
check $P block "data-only: env -C /tmp true > data/snapshots/s1/f (the shell opens it)" "$(payload_do 'env -C /tmp true > data/snapshots/s1/f')"
check $P allow "data-only: env -C /tmp true > /tmp/op-253.out"  "$(payload_do 'env -C /tmp true > /tmp/op-253.out')"
check $P block "data-only: env -C /tmp true > \$PWD/data/snapshots/s1/f (the shell's PWD)" "$(payload_do 'env -C /tmp true > "$PWD"/data/snapshots/s1/f')"
check $P allow "data-only: env -C /tmp true 2>&1 <<< \$HOME (no file)" "$(payload_do 'env -C /tmp true 2>&1 <<< "$HOME"')"
check $P block "data-only: X=data/snapshots/s1; env -C /tmp true > \$X/f (a relative \$X)" "$(payload_do 'X=data/snapshots/s1; env -C /tmp true > "$X"/f')"
check $P block "data-only: D=data; env -C /tmp true > \$D/snapshots/x" "$(payload_do 'D=data; env -C /tmp true > $D/snapshots/x')"
check $P block "data-only: D=data; sudo -D /tmp true >> \$D/snapshots/x" "$(payload_do 'D=data; sudo -D /tmp true >> $D/snapshots/x')"
check $P allow "data-only: env -C /tmp true > \$HOME/x"         "$(payload_do 'env -C /tmp true > "$HOME"/op-253.x')"
mkdir -p "$TMP/plain253"   # no repo, no data/ or backlog/
check $P allow "outside a repo: env -C /tmp true > ~/op-253.log (HOME doesn't move)" "$(payload_at "$TMP/plain253" 'env -C /tmp true > ~/op-253.log')"
# sh -c and eval keep their own redirects
check $P block "sh -c 'echo x' >> backlog/tasks/x"              "$(payload_bl "sh -c 'echo x' >> backlog/tasks/x")"
check $P block "eval echo x >> backlog/tasks/x"                 "$(payload_bl 'eval echo x >> backlog/tasks/x')"
check $P block "data-only: bash -c true > data/snapshots/s1/f"  "$(payload_do 'bash -c true > data/snapshots/s1/f')"
check $P allow "sh -c 'echo x' >> /tmp/op-253.out"              "$(payload_bl "sh -c 'echo x' >> /tmp/op-253.out")"
# mv -t DIR / --target-directory=DIR: DIR is the destination, not a source (`..` holds data/snapshots)
check $P allow "data-only: mv -t .. src/x.md"                   "$(payload_do 'mv -t .. src/x.md')"
check $P allow "data-only: mv --target .. src/x.md"             "$(payload_do 'mv --target .. src/x.md')"
check $P allow "data-only: mv --target-directory=.. src/x.md"   "$(payload_do 'mv --target-directory=.. src/x.md')"
check $P allow "data-only: mv -vt.. src/x.md"                   "$(payload_do 'mv -vt.. src/x.md')"
check $P allow "data-only: mv src/x.md .. (positive control)"   "$(payload_do 'mv src/x.md ..')"
check $P allow "data-only: cp -t .. src/x.md (positive control)" "$(payload_do 'cp -t .. src/x.md')"
check $P block "data-only: mv -t /tmp data/snapshots"           "$(payload_do 'mv -t /tmp data/snapshots')"
check $P block "data-only: mv --target-directory=/tmp src/x.md data/indexes" "$(payload_do 'mv --target-directory=/tmp src/x.md data/indexes')"
check $P block "data-only: mv -t data/snapshots/s1 src/x.md"    "$(payload_do 'mv -t data/snapshots/s1 src/x.md')"
check $P block "data-only: mv -t\$UNSET src/x.md (attached, unresolved)" "$(payload_do 'mv -t"$OP_UNSET_253" src/x.md')"
check $P allow "data-only: mv src/x.md src/x.md~ (a ~ in a plain name)" "$(payload_do 'mv src/x.md src/x.md~')"
check $P block "data-only: mv -St <repo> ../moved (the t is -S's suffix)" "$(payload_do "mv -St '../data only' ../moved")"
check $P block "data-only: mv -t /tmp -- -t <repo> (after --, operands)" "$(payload_do "mv -t /tmp -- -t '../data only'")"
check $P allow "data-only: mv -t /tmp -- src/x.md (-- ends the options, not an ambiguous long prefix)" "$(payload_do 'mv -t /tmp -- src/x.md')"
# another option's value is no -t: `mv -S -t .. x` moves `..` (it holds data/snapshots) with suffix -t
check $P block "data-only: mv -S -t .. ../moved (-t is -S's value)" "$(payload_do 'mv -S -t .. ../moved')"
check $P block "data-only: mv -bS -t .. ../moved"               "$(payload_do 'mv -bS -t .. ../moved')"
check $P block "data-only: mv --suffix -t .. ../moved"          "$(payload_do 'mv --suffix -t .. ../moved')"
check $P block "data-only: mv -S X -t data/snapshots/s1 src/x.md" "$(payload_do 'mv -S X -t data/snapshots/s1 src/x.md')"
# each command's own long options, resolved as getopt_long does: an exact name wins, then a unique prefix
check $P block "data-only: cp --strip -t data/snapshots/s1 src/x.md (cp's --strip-trailing-slashes)" "$(payload_do 'cp --strip -t data/snapshots/s1 src/x.md')"
check $P block "data-only: install --strip -t data/indexes/i1 src/x.md (install's --strip, exact)" "$(payload_do 'install --strip -t data/indexes/i1 src/x.md')"
check $P block "data-only: install --strip -t data/snapshots/s1 src/x.md" "$(payload_do 'install --strip -t data/snapshots/s1 src/x.md')"
check $P block "data-only: install --strip-program x -t data/indexes/i1 f" "$(payload_do 'install --strip-program x -t data/indexes/i1 f')"
check $P block "data-only: mv --strip -t data/snapshots/s1 f"   "$(payload_do 'mv --strip -t data/snapshots/s1 f')"
check $P block "data-only: mv --strip data/snapshots /tmp/x (a flag: the source stays)" "$(payload_do 'mv --strip data/snapshots /tmp/x')"
check $P block "data-only: mv --str data/snapshots/ /tmp/x"     "$(payload_do 'mv --str data/snapshots/ /tmp/x')"
check $P block "data-only: cp --str -r src -t data/indexes/i1" "$(payload_do 'cp --str -r src -t data/indexes/i1')"
check $P allow "data-only: install --strip -t /tmp src/x.md (an exact name is no ambiguity)" "$(payload_do 'install --strip -t /tmp src/x.md')"
check $P block "data-only: mv --s -t .. ../moved (--strip-… or --suffix: ambiguous)" "$(payload_do 'mv --s -t .. ../moved')"
check $P block "data-only: mv -t\$UNSET '\$UNSET' src/x.md (attached, and a word of the same text)" "$(payload_do "mv -t\"\$OP_UNSET_253\" '\$OP_UNSET_253' src/x.md")"

echo "== TASK-266 rows (block-ai-attribution refuses a gh or git writer it can't parse)"
# its file option held in a variable the text check can't see: let through unread before TASK-266
check $A block "unparseable gh pr comment \$OPT file"            "$(payload_bash "gh pr comment 1 \$OPT_266 '$TMP/clean.md' --title 'unclosed")"
check $A block "unparseable git commit -m (clean)"               "$(payload_bash "git commit -m \"fix: parser")"
check $A block "unparseable git tag -a -m (clean)"               "$(payload_bash "git tag -a v1 -m 'release")"
check $A block "unparseable g''it commit (quotes read away)"     "$(payload_bash "g''it commit -m 'x")"
check $A block "unparseable gh pr new (an alias of create)"      "$(payload_bash "gh pr new --title 'x")"
check $A block "unparseable gh pr --repo o/r edit"               "$(payload_bash "gh pr --repo o/r edit 1 --title 'x")"
check $A block "unparseable gh issue comment"                    "$(payload_bash "gh issue comment 1 --body 'x")"
check $A block "unparseable gh release create --notes"           "$(payload_bash "gh release create v1 --notes 'x")"
check $A block "unparseable gh api -f body= (no file option)"    "$(payload_bash "gh api repos/o/r/issues/1/comments -f body='ok")"
check $A allow "unparseable gh pr view (a read)"                 "$(payload_bash "gh pr view 1 --json 'body")"
check $A allow "unparseable gh release view (a read)"            "$(payload_bash "gh release view v1 'x")"
check $A allow "unparseable gh issue list --search close (no issue write verb)" "$(payload_bash "gh issue list --search 'closed")"
check $A allow "unparseable git status (no message verb)"        "$(payload_bash "git status --short 'x")"
check $A allow "unparseable commit word without git"             "$(payload_bash "echo commit 'x")"
check $A allow "unparseable api word without gh"                 "$(payload_bash "echo api create 'x")"
check $A allow "unparseable cat, no gh or git"                   "$(payload_bash "cat notes 'x")"
check $A allow "unparseable gh label create (no writer group)"   "$(payload_bash "gh label create bug --description 'x")"
check $A allow "unparseable git log --grep tagged (a whole word)" "$(payload_bash "git log --grep tagged 'x")"
# the older unparseable-text checks still refuse a command that is no writer, so each keeps a row the writer check
# can't block first
check $A block "unparseable echo, a 'Cl''aude' trailer (no writer)" "$(payload_bash "echo 'Co-Authored-By: Cl''aude Opus' \"unclosed")"
check $A block "unparseable echo, Cl\\<nl>aude (no writer)"      "$(payload_bash $'echo "Co-Authored-By: Cl\\\naude Opus')"
check $A block "unparseable gh pr view --body-file (no writer)"  "$(payload_bash "gh pr view 1 --body-file '$TMP/clean.md' --title 'unclosed")"
check $A block "unparseable git status; cat f (no writer)"       "$(payload_bash "git status; cat '$TMP/clean.md' 'unclosed")"

echo "== TASK-269 rows (sudo -e / sudoedit edits each file after its options)"
check $P block "data-only: sudo -e data/indexes/i1/x"            "$(payload_do 'sudo -e data/indexes/i1/x')"
check $P block "data-only: sudo --edit data/indexes/i1/x"        "$(payload_do 'sudo --edit data/indexes/i1/x')"
check $P block "data-only: sudo --ed data/indexes/i1/x (a unique prefix)" "$(payload_do 'sudo --ed data/indexes/i1/x')"
check $P block "data-only: sudoedit data/indexes/i1/x"           "$(payload_do 'sudoedit data/indexes/i1/x')"
check $P block "data-only: /usr/bin/sudoedit -u root data/indexes/i1/x" "$(payload_do '/usr/bin/sudoedit -u root data/indexes/i1/x')"
check $P block "data-only: sudo -ne -u root -- /tmp/a data/indexes/i1/x (the second file)" "$(payload_do 'sudo -ne -u root -- /tmp/a data/indexes/i1/x')"
check $P block "data-only: sudo -D /tmp -e data/indexes/i1/x (from the shell's directory too)" "$(payload_do 'sudo -D /tmp -e data/indexes/i1/x')"
check $P block "data-only: sudo -D data/indexes -e i1/x (from -D's directory too)" "$(payload_do 'sudo -D data/indexes -e i1/x')"
check $P allow "data-only: sudo -e /tmp/op-269.txt"              "$(payload_do 'sudo -e /tmp/op-269.txt')"
check $P allow "data-only: sudo -E cat data/indexes/i1/x (-E keeps the environment)" "$(payload_do 'sudo -E cat data/indexes/i1/x')"
check $P allow "data-only: sudo -ue cat data/indexes/i1/x (-u takes e: user e)" "$(payload_do 'sudo -ue cat data/indexes/i1/x')"
check $P block "sudo -e backlog/tasks/x.md"                      "$(payload_bl 'sudo -e backlog/tasks/x.md')"
check $P block "sudo --edit backlog/tasks/x.md"                  "$(payload_bl 'sudo --edit backlog/tasks/x.md')"
check $P block "sudoedit backlog/tasks/x.md"                     "$(payload_bl 'sudoedit backlog/tasks/x.md')"
check $P block "sudo -nu root -e backlog/tasks/x.md" "$(payload_bl 'sudo -nu root -e backlog/tasks/x.md')"
check $P allow "sudoedit src/notes.md"                           "$(payload_bl 'sudoedit src/notes.md')"
# -R/--chroot opens each file inside the chroot, so which file it edits can't be told: a ParseError, refused
check $P block "data-only: sudo -R /x -e /tmp/op-269.txt (inside a chroot)" "$(payload_do 'sudo -R /x -e /tmp/op-269.txt')"
check $P block "data-only: sudoedit --chroot=/x /tmp/op-269.txt" "$(payload_do 'sudoedit --chroot=/x /tmp/op-269.txt')"
check $P block "data-only: sudo -e -R /x /tmp/op-269.txt (-R after -e)" "$(payload_do 'sudo -e -R /x /tmp/op-269.txt')"
check $P allow "data-only: sudo -R /x cat data/indexes/i1/x (a chroot, no edit)" "$(payload_do 'sudo -R /x cat data/indexes/i1/x')"
check $P allow "data-only: sudo -r role -e /tmp/op-269.txt (-r is a role)" "$(payload_do 'sudo -r role -e /tmp/op-269.txt')"
check $P allow "data-only: flock -e <lock> cat data/snapshots/s1/f (flock's -e is exclusive)" "$(payload_do 'flock -e /tmp/op.lock cat data/snapshots/s1/f')"
check $R allow "sudo -e git push origin other2 (files so named: no push runs)" "$(payload_bash 'sudo -e git push origin other2')"
check $R block "sudoedit .git/op-reviews/<sha>"                  "$(payload_bash 'sudoedit .git/op-reviews/0123abc')"

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
