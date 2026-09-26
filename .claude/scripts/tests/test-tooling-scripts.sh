#!/usr/bin/env bash
# shellcheck disable=SC2016  # commands under test are single-quoted on purpose: $(…), $(( )) and backticks must reach the hooks unexpanded
# Case table for the CI tooling scripts: learnings_index.py, check_backlog.py, lint_tooling.py and
# roster_index.py. Each case copies the real .claude/ (and CLAUDE.md / CONTRIBUTING.md) into a throwaway
# tree, confirms the script passes on it, then breaks exactly one thing and confirms the script fails —
# so a regression in a check can't hide behind the repo's own content being clean (review round 2).
# Usage: ./test-tooling-scripts.sh
set -u
# Never inherit a repo from the caller (git exports GIT_DIR etc. to hooks such as pre-push).
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
SRC="$(cd "$(dirname "$0")/../../.." && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0

fresh() {  # a clean copy of the tooling tree at $TMP/r
  rm -rf "$TMP/r" && mkdir -p "$TMP/r/backlog/tasks" "$TMP/r/backlog/completed"
  cp -R "$SRC/.claude" "$TMP/r/.claude"
  cp "$SRC/CLAUDE.md" "$SRC/CONTRIBUTING.md" "$TMP/r/"
}
# expect <ok|err> <label> <script> [args...]   — runs the COPIED script inside $TMP/r
expect() {
  local want="$1" label="$2" script="$3"; shift 3; local got
  if python3 "$TMP/r/.claude/scripts/$script" "$@" >/dev/null 2>&1; then got=ok; else got=err; fi
  if [ "$got" = "$want" ]; then pass=$((pass+1)); printf '  ok   %-22s %-58s -> %s\n' "$script" "$label" "$got"
  else fail=$((fail+1)); printf '  FAIL %-22s %-58s -> %s (want %s)\n' "$script" "$label" "$got" "$want"; fi
}
L="$TMP/r/.claude/learnings"

echo "== learnings_index.py --check"
fresh; expect ok  "clean copy passes"                                   learnings_index.py --check
fresh; printf '# t\n\n**Key lesson:** <one sentence a future session can act on>\n' > "$L/2026-09-26-x.md"
python3 "$TMP/r/.claude/scripts/learnings_index.py" >/dev/null 2>&1
expect err "template placeholder in the key lesson"                     learnings_index.py --check
fresh; printf '# t\n\n**Key lesson:** use Map<string, number> not Optional<SearchRecord>\n' > "$L/2026-09-26-code.md"
python3 "$TMP/r/.claude/scripts/learnings_index.py" >/dev/null 2>&1
expect ok  "code generics are not placeholders"                         learnings_index.py --check
fresh; printf '# t\n\n**Key lesson:** k\n' > "$L/2026-99-99-bad-date.md"
python3 "$TMP/r/.claude/scripts/learnings_index.py" >/dev/null 2>&1   # regenerate, so only the check itself can fail
expect err "impossible date in the name"                                learnings_index.py --check
fresh; printf '# t\n\n**Key lesson:**\n- **Date:** x\n' > "$L/2026-09-26-empty-key.md"
expect err "empty key lesson (must not borrow the next line)"           learnings_index.py --check
fresh; printf '# t\n\n**Key lesson:** k\n' > "$L/2026-09-26-Upper-Slug.md"
expect err "uppercase slug"                                             learnings_index.py --check
fresh; mkdir -p "$L/sub"; printf '# t\n\n**Key lesson:** k\n' > "$L/sub/2026-09-26-x.md"
python3 "$TMP/r/.claude/scripts/learnings_index.py" >/dev/null 2>&1   # regenerate, so only the check itself can fail
expect err "entry in a subfolder"                                       learnings_index.py --check
fresh; printf 'x\n' > "$L/notes.txt"
expect err "stray non-entry file"                                       learnings_index.py --check
fresh; printf '# t\n\n**Key lesson:** k\n' > "$L/2026-09-26-new.md"
expect err "new entry not yet in INDEX.md (stale)"                      learnings_index.py --check

echo "== check_backlog.py"
fresh; expect ok  "no tasks at all"                                     check_backlog.py
fresh; printf -- '---\nid: task-1\nstatus: In Progress\n---\n' > "$TMP/r/backlog/tasks/task-1 - x.md"
expect ok  "an In Progress task"                                        check_backlog.py
fresh; printf -- '---\nid: task-1\nstatus: Done\n---\n' > "$TMP/r/backlog/tasks/task-1 - x.md"
expect err "a Done task left in tasks/"                                 check_backlog.py
fresh; printf -- "---\nid: task-1\nstatus: 'Done'\n---\n" > "$TMP/r/backlog/tasks/task-1 - x.md"
expect err "a quoted 'Done' status"                                     check_backlog.py
fresh; printf -- '---\nid: task-1\nstatus: Done\n---\n' > "$TMP/r/backlog/completed/task-1 - x.md"
expect ok  "a Done task in completed/"                                  check_backlog.py

echo "== lint_tooling.py"
C="$TMP/r/.claude"
fresh; expect ok  "clean copy passes"                                   lint_tooling.py
fresh; printf '\nSpawn `qa-auditer` too.\n' >> "$C/commands/audit.md"
expect err "misspelled agent name in a command"                         lint_tooling.py
fresh; printf '\nThen run `/review-gatee`.\n' >> "$C/commands/open-pr.md"
expect err "unknown slash command in a command"                         lint_tooling.py
fresh; printf '\nSee `.claude/skills/no-such-skill/SKILL.md`.\n' >> "$C/agents/code-reviewer.md"
expect err "path reference to a missing skill"                          lint_tooling.py
fresh; printf '\nAlso ask `ghost-reviewer`.\n' >> "$C/skills/learnings/SKILL.md"
expect err "the learnings SKILL is linted (not skipped as journal)"     lint_tooling.py
fresh; sed -i.bak 's/^name: code-reviewer$/name: code-reviwer/' "$C/agents/code-reviewer.md"
expect err "frontmatter name != filename"                               lint_tooling.py
fresh; sed -i.bak 's/^tools: Read, Grep, Glob, Bash$/tools: Read, Grep, Glob, Bash, Edit/' "$C/agents/security-reviewer.md"
expect err "a reviewer agent granted Edit"                              lint_tooling.py
fresh; printf -- '---\nname: lonely-engineer\ndescription: An agent that nothing references anywhere in the roster at all. Use never.\ntools: Read\n---\n%s\n' "$(printf 'word %.0s' $(seq 1 90))" > "$C/agents/lonely-engineer.md"
expect err "orphan agent"                                               lint_tooling.py

echo "== roster_index.py --check"
fresh; expect ok  "clean copy passes"                                   roster_index.py --check
fresh; sed -i.bak 's/^description: \(.\)/description: CHANGED \1/' "$C/agents/code-reviewer.md"
expect err "a changed description makes README stale"                   roster_index.py --check
fresh; cp "$C/agents/ci-engineer.md" "$C/agents/new-engineer.md"; sed -i.bak 's/^name: ci-engineer$/name: new-engineer/' "$C/agents/new-engineer.md"; rm -f "$C/agents/"*.bak
python3 "$TMP/r/.claude/scripts/roster_index.py" >/dev/null 2>&1   # regenerate, so only the no-area rule can fail
expect err "a new agent with no area"                                   roster_index.py --check

echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
