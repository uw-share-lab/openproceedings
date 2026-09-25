#!/usr/bin/env bash
# PostToolUse(Write|Edit|MultiEdit): auto-format and auto-fix the file that was just edited, then report
# anything that still fails back to the agent. Never blocks (exit 0). Modelled on the naturalschema repo's
# ruff hook, extended to the whole monorepo. Standard: .claude/skills/autolint/SKILL.md.
#   *.py        → ruff format, ruff check --fix, py_compile        (root uv workspace)
#   frontend/*  → prettier --write, eslint --fix (ts/tsx/js/jsx)   (only once frontend/node_modules exists)
#   *.sh, .githooks/* → shellcheck (report only; it cannot fix)
# Skips data/, backlog/, generated files, and anything outside the repo.
input=$(cat)
file=$(printf '%s' "$input" | python3 -c 'import json,sys
try: print((json.load(sys.stdin).get("tool_input") or {}).get("file_path") or "")
except Exception: print("")' 2>/dev/null)
[ -n "$file" ] && [ -f "$file" ] || exit 0
root="${CLAUDE_PROJECT_DIR:-$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$root" ] || exit 0
case "$file" in "$root"/*) rel="${file#"$root"/}" ;; *) exit 0 ;; esac
case "$rel" in
  data/*|backlog/*|.claude/learnings/INDEX.md|.claude/README.md|*/node_modules/*|uv.lock|*/package-lock.json) exit 0 ;;
esac

report=""
note() { report="${report}${1}"$'\n'; }

case "$rel" in
  *.py)
    if command -v uv >/dev/null 2>&1; then
      (cd "$root" && uv run --quiet ruff format "$rel" >/dev/null 2>&1)
      out=$(cd "$root" && uv run --quiet ruff check --fix "$rel" 2>&1) || note "ruff check still fails on $rel:"$'\n'"$out"
      out=$(cd "$root" && python3 -m py_compile "$rel" 2>&1) || note "py_compile failed on $rel:"$'\n'"$out"
    else
      note "autofix: uv not found — skipped ruff for $rel (run scripts/setup-dev.sh)."
    fi
    ;;
  frontend/*.ts|frontend/*.tsx|frontend/*.js|frontend/*.jsx|frontend/*.json|frontend/*.css|frontend/*.md)
    if [ -d "$root/frontend/node_modules" ]; then
      sub="${rel#frontend/}"
      (cd "$root/frontend" && npx --no-install prettier --write "$sub" >/dev/null 2>&1)
      case "$sub" in
        *.ts|*.tsx|*.js|*.jsx)
          out=$(cd "$root/frontend" && npx --no-install eslint --fix "$sub" 2>&1) || note "eslint still fails on $rel:"$'\n'"$out" ;;
      esac
    fi
    ;;
  *.sh|.githooks/*)
    if command -v shellcheck >/dev/null 2>&1; then
      out=$(cd "$root" && shellcheck -x "$rel" 2>&1) || note "shellcheck findings in $rel (fix by hand):"$'\n'"$out"
    fi
    ;;
esac

[ -z "$report" ] && exit 0
REPORT="$report" python3 -c 'import json,os
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
  "additionalContext": "autofix (skill: autolint) could not fix everything:\n" + os.environ["REPORT"][:4000]}}))'
exit 0
