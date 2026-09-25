#!/usr/bin/env bash
# Case table for the openproceedings gates: block-ai-attribution.sh, require-review.sh,
# protect-data-dir.sh, remind-token-contract.sh, and .claude/scripts/record-review.py.
# Runs the real hooks against a throwaway repo with a bare "origin", so git resolution is real.
# Usage: ./test-openproceedings-gates.sh
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
mkdir -p "$REPO/.claude/learnings" "$REPO/backlog/tasks"
echo x > "$REPO/README.md"
g add -A && g commit -q -m init && g remote add origin "$ORIGIN" && g push -q origin dev
g switch -q -c feat

payload_bash() { python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","cwd":sys.argv[1],"tool_input":{"command":sys.argv[2]}}))' "$REPO" "$1"; }
payload_file() { python3 -c 'import json,sys; print(json.dumps({"tool_name":sys.argv[1],"tool_input":{"file_path":sys.argv[2]}}))' "$1" "$2"; }

# check <hook> <want: allow|block> <label> <json>
check() {
  local hook="$1" want="$2" label="$3" json="$4" got
  if printf '%s' "$json" | "$HOOKS/$hook" >/dev/null 2>&1; then got=allow; else got=block; fi
  if [ "$got" = "$want" ]; then pass=$((pass+1)); printf '  ok   %-26s %-58s -> %s\n' "$hook" "$label" "$got"
  else fail=$((fail+1)); printf '  FAIL %-26s %-58s -> %s (want %s)\n' "$hook" "$label" "$got" "$want"; fi
}
# check_cmd <want: ok|err> <label> <cmd...>   (for scripts)
check_cmd() {
  local want="$1" label="$2"; shift 2; local got
  if (cd "$REPO" && "$@" >/dev/null 2>&1); then got=ok; else got=err; fi
  if [ "$got" = "$want" ]; then pass=$((pass+1)); printf '  ok   %-26s %-58s -> %s\n' "script" "$label" "$got"
  else fail=$((fail+1)); printf '  FAIL %-26s %-58s -> %s (want %s)\n' "script" "$label" "$got" "$want"; fi
}

echo "== block-ai-attribution.sh"
A=block-ai-attribution.sh
check $A allow "plain commit message"            "$(payload_bash 'git commit -m "feat: add parser"')"
check $A block "Claude co-author trailer in -m"   "$(payload_bash 'git commit -m "feat: x

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"')"
check $A block "heredoc-style message"            "$(payload_bash "git commit -m \"\$(cat <<'EOF'
fix: y

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)\"")"
check $A block "gh pr create body footer"         "$(payload_bash 'gh pr create --base dev --title t --body "Summary

🤖 Generated with [Claude Code](https://claude.com/claude-code)"')"
printf 'msg\n\nCo-authored-by: claude <noreply@anthropic.com>\n' > "$TMP/msg.txt"
check $A block "commit -F file with trailer"      "$(payload_bash "git commit -F '$TMP/msg.txt'")"
check $A allow "human co-author is fine"          "$(payload_bash 'git commit -m "x

Co-Authored-By: A Reviewer <reviewer@example.org>"')"
check $A block "inside bash -c wrapper"           "$(payload_bash "bash -c 'git commit -m \"x Co-Authored-By: Claude\"'")"
check $A allow "unrelated command"                "$(payload_bash 'ls -la')"

echo "== require-review.sh"
R=require-review.sh
check $R block "push with no review record"       "$(payload_bash 'git push -u origin feat')"
check $R allow "deleting a remote branch"         "$(payload_bash 'git push origin --delete feat')"
printf 'No findings.\n' > "$TMP/none.md"
check_cmd ok  "record APPROVE on clean tree"      python3 "$RECORD" APPROVE "$TMP/none.md"
check $R allow "push after APPROVE of HEAD"       "$(payload_bash 'git push -u origin feat')"
echo y >> "$REPO/README.md"; g commit -qam "more"
check $R block "new commit invalidates approval"  "$(payload_bash 'git push origin feat')"
check $R block "push hidden in cd && chain"       "$(payload_bash "cd '$REPO' && git push origin feat")"
check_cmd ok  "re-record APPROVE"                 python3 "$RECORD" APPROVE "$TMP/none.md"
check $R block "gh pr create, no learnings entry" "$(payload_bash 'gh pr create --base dev --fill')"
check $R allow "gh pr create --label no-learning" "$(payload_bash 'gh pr create --base dev --fill --label no-learning')"
printf '# t\n\n**Key lesson:** k\n' > "$REPO/.claude/learnings/2026-09-25-x.md"; g add -A; g commit -qm learn
check $R block "learning added but not re-reviewed" "$(payload_bash 'gh pr create --base dev --fill')"
check_cmd ok  "record APPROVE incl. learning"     python3 "$RECORD" APPROVE "$TMP/none.md"
check $R allow "gh pr create with learning + review" "$(payload_bash 'gh pr create --base dev --fill')"
printf '# t\n\n**Key lesson:** k\n' > "$REPO/.claude/learnings/README.md"
check_cmd err "record refuses a dirty tree"       python3 "$RECORD" APPROVE "$TMP/none.md"
rm "$REPO/.claude/learnings/README.md"

echo "== record-review.py dispositions"
SHA=$(g rev-parse --short HEAD)
printf -- '- [must] a.py:1 bug\n' > "$TMP/d1.md"
check_cmd err "undispositioned finding"           python3 "$RECORD" APPROVE "$TMP/d1.md"
printf -- '- [must] a.py:1 bug → rejected: we disagree strongly\n' > "$TMP/d2.md"
check_cmd err "must-fix cannot be rejected"       python3 "$RECORD" APPROVE "$TMP/d2.md"
printf -- '- [must] a.py:1 bug → fixed %s\n- [nit] b.py:2 name → rejected: matches surrounding style\n' "$SHA" > "$TMP/d3.md"
check_cmd ok  "fixed ancestor + reasoned reject"  python3 "$RECORD" APPROVE "$TMP/d3.md"
printf -- '- [should] a.py:1 slow → task-999\n' > "$TMP/d4.md"
check_cmd err "task that does not exist"          python3 "$RECORD" APPROVE "$TMP/d4.md"
: > "$REPO/backlog/tasks/task-999 - Speed up.md"; g add -A; g commit -qm task
check_cmd ok  "task that exists"                  python3 "$RECORD" APPROVE "$TMP/d4.md"
printf -- '- [must] a.py:1 bug → fixed deadbeef\n' > "$TMP/d5.md"
check_cmd err "fixed sha not an ancestor"         python3 "$RECORD" APPROVE "$TMP/d5.md"
: > "$TMP/empty.md"
check_cmd err "empty dispositions file"           python3 "$RECORD" APPROVE "$TMP/empty.md"

echo "== protect-data-dir.sh"
P=protect-data-dir.sh
check $P block "Write into data/indexes/"         "$(payload_file Write "$REPO/data/indexes/abc/meta.json")"
check $P block "Edit data/snapshots/ records"     "$(payload_file Edit "$REPO/data/snapshots/2026-09-25-ab/records.jsonl")"
check $P allow "Write data/cache/ (mutable)"      "$(payload_file Write "$REPO/data/cache/x.json")"
check $P allow "Write normal source"              "$(payload_file Write "$REPO/backend/src/openproceedings/cli.py")"
check $P block "git add -f data/"                 "$(payload_bash 'git add -f data/snapshots')"
check $P block "git add -Af data"                 "$(payload_bash 'git add -Af data')"
check $P allow "git add docs/data-model.md"       "$(payload_bash 'git add docs/data-model.md')"
check $P block "rm -rf an index"                  "$(payload_bash 'rm -rf data/indexes/abc')"
check $P allow "sed read-only on a snapshot"      "$(payload_bash "sed -n 1p data/snapshots/x/records.jsonl")"

echo "== remind-token-contract.sh (non-blocking; must emit context on contract files only)"
out=$(payload_file Edit "$REPO/backend/src/openproceedings/query/normalize.py" | "$HOOKS/remind-token-contract.sh")
case "$out" in *TOKENIZER_VERSION*) pass=$((pass+1)); echo "  ok   reminder on normalize.py";; *) fail=$((fail+1)); echo "  FAIL no reminder on normalize.py";; esac
out=$(payload_file Edit "$REPO/backend/src/openproceedings/api/app.py" | "$HOOKS/remind-token-contract.sh")
[ -z "$out" ] && { pass=$((pass+1)); echo "  ok   silent on api/app.py"; } || { fail=$((fail+1)); echo "  FAIL spoke on api/app.py"; }

echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
