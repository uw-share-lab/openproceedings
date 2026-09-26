#!/usr/bin/env bash
# PostToolUse(Write|Edit|MultiEdit): auto-format and auto-fix the file that was just edited, then report
# anything that still fails back to the agent. Never blocks (exit 0). Modelled on the naturalschema repo's
# ruff hook, extended to the whole monorepo. Standard: .claude/skills/autolint/SKILL.md.
#   *.py        → ruff format, ruff check --fix, py_compile        (root uv workspace)
#   frontend/*  → prettier --write, eslint --fix (ts/tsx/js/jsx)   (only once frontend/node_modules exists)
#   *.sh, .githooks/* → shellcheck (report only; it cannot fix)
# Skips data/, backlog/, generated files, and anything outside the repo (compared by real path, so a
# symlink or `..` cannot escape it).
# Security (review round 2): tools run straight from the workspace venv — never `uv run`, which may sync
# and fetch/build packages an agent just added to pyproject.toml — and eslint is skipped while its config
# or package.json differs from HEAD, because eslint executes its (JS) config. File names are passed after
# `--` so a name can never be read as an option.
input=$(cat)
file=$(printf '%s' "$input" | python3 -c 'import json,sys
try: print((json.load(sys.stdin).get("tool_input") or {}).get("file_path") or "")
except Exception: print("")' 2>/dev/null)
[ -n "$file" ] && [ -f "$file" ] || exit 0
root="${CLAUDE_PROJECT_DIR:-$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$root" ] || exit 0
realpath_py() { python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"; }
root=$(realpath_py "$root"); file=$(realpath_py "$file")
case "$file" in "$root"/*) rel="${file#"$root"/}" ;; *) exit 0 ;; esac
case "$rel" in
  data/*|backlog/*|.claude/learnings/INDEX.md|.claude/README.md|*/node_modules/*|uv.lock|*/package-lock.json) exit 0 ;;
esac

report=""
note() { report="${report}${1}"$'\n'; }

case "$rel" in
  *.py)
    ruff="$root/.venv/bin/ruff"
    if [ -x "$ruff" ]; then
      (cd "$root" && "$ruff" format --quiet -- "$rel" >/dev/null 2>&1)
      out=$(cd "$root" && "$ruff" check --fix --quiet -- "$rel" 2>&1) || note "ruff check still fails on $rel:"$'\n'"$out"
    else
      note "autofix: $root/.venv/bin/ruff not found — skipped ruff for $rel (run: uv sync)."
    fi
    out=$(cd "$root" && python3 -m py_compile -- "$rel" 2>&1) || note "py_compile failed on $rel:"$'\n'"$out"
    ;;
  frontend/*.ts|frontend/*.tsx|frontend/*.js|frontend/*.jsx|frontend/*.json|frontend/*.css|frontend/*.md)
    if [ -d "$root/frontend/node_modules" ]; then
      sub="${rel#frontend/}"
      (cd "$root/frontend" && npx --no-install prettier --write -- "$sub" >/dev/null 2>&1)
      case "$sub" in
        *.ts|*.tsx|*.js|*.jsx)
          cfg_state=$(git -C "$root" status --porcelain -- 'frontend/eslint.config.*' 'frontend/.eslintrc*' frontend/package.json 2>/dev/null)
          if [ -z "$cfg_state" ]; then   # tracked AND untracked changes both count (review round 3)
            out=$(cd "$root/frontend" && npx --no-install eslint --fix -- "$sub" 2>&1) || note "eslint still fails on $rel:"$'\n'"$out"
          else
            note "autofix: eslint skipped for $rel — its config or package.json has uncommitted changes (eslint runs its config as code). Run make lint after reviewing them."
          fi ;;
      esac
    fi
    ;;
  *.sh|.githooks/*)
    if command -v shellcheck >/dev/null 2>&1; then
      out=$(cd "$root" && shellcheck -x -- "$rel" 2>&1) || note "shellcheck findings in $rel (fix by hand):"$'\n'"$out"
    fi
    ;;
esac

[ -z "$report" ] && exit 0
REPORT="$report" python3 -c 'import json,os
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
  "additionalContext": "autofix (skill: autolint) could not fix everything:\n" + os.environ["REPORT"][:4000]}}))'
exit 0
