#!/usr/bin/env bash
# shellcheck disable=SC2016  # commands under test are single-quoted on purpose: $(…), $(( )) and backticks must reach the hooks unexpanded
# Case table for the CI tooling scripts: learnings_index.py, check_backlog.py, check_digest_pins.py,
# lint_tooling.py and roster_index.py. Each case copies the real .claude/ (and CLAUDE.md / CONTRIBUTING.md) into a throwaway
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
  # .claude/worktrees/ holds gitignored agent checkouts (GBs); copying it per case made the table take hours
  rsync -a --exclude /worktrees "$SRC/.claude/" "$TMP/r/.claude/"
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
fresh; printf '# t\n\n**Key lesson:** a lesson wrapped\nonto a second line\n\n- **Date:** x\n' > "$L/2026-09-26-wrapped.md"
python3 "$TMP/r/.claude/scripts/learnings_index.py" >/dev/null 2>&1
expect err "key lesson wrapped onto a second line"                      learnings_index.py --check
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

echo "== check_digest_pins.py"
W="$TMP/r/deploy/web.Dockerfile"
D="sha256:$(printf 'a%.0s' $(seq 1 64))"
deploy() { fresh; cp -R "$SRC/deploy" "$TMP/r/deploy"; }
fresh; expect ok  "no deploy/ directory"                                check_digest_pins.py
deploy; expect ok  "the repo's own deploy/ passes"                      check_digest_pins.py
deploy; printf 'FROM node:22-bookworm-slim\n' > "$W"
expect err "a FROM with only a tag"                                     check_digest_pins.py
deploy; printf 'FROM node@%s\n' "$D" > "$W"
expect err "a digest with no tag (the tag is kept for readers)"         check_digest_pins.py
deploy; printf 'FROM node:22@sha256:abc\n' > "$W"
expect err "a truncated digest"                                         check_digest_pins.py
deploy; printf 'from node:22 as build\n' > "$W"
expect err "lowercase from is still checked"                            check_digest_pins.py
deploy; printf 'FROM --platform=linux/amd64 node:22\n' > "$W"
expect err "a --platform flag does not hide the image"                  check_digest_pins.py
deploy; printf 'ARG BASE=node:22\nFROM ${BASE}\n' > "$W"
expect err "an ARG-named image"                                         check_digest_pins.py
deploy; printf 'ARG TAG=22\nFROM node:${TAG}@%s\n' "$D" > "$W"
expect err "an ARG-named tag, even with a digest"                       check_digest_pins.py
deploy; printf 'FROM --platform=linux/amd64 node:22@%s\n' "$D" > "$W"
expect ok  "a pinned image after a --platform flag"                     check_digest_pins.py
deploy; printf 'FROM node:22@%s AS build\nFROM build\nFROM node:22\n' "$D" > "$W"
expect err "the second of three FROMs pinned, the third not"            check_digest_pins.py
deploy; printf 'FROM node:22@%s AS Build\nFROM build\nFROM scratch\n' "$D" > "$W"
expect ok  "an earlier stage (any case) and scratch need no digest"     check_digest_pins.py
deploy; printf 'FROM node:22@%s AS build extra\n' "$D" > "$W"
expect err "a FROM it can't read (trailing words) is refused"           check_digest_pins.py
deploy; printf 'FROM build\nFROM node:22@%s AS build\n' "$D" > "$W"
expect err "a stage named before it is defined is an image"             check_digest_pins.py
deploy; mkdir -p "$TMP/r/deploy/api"; printf 'FROM python:3.12-slim\n' > "$TMP/r/deploy/api/Dockerfile"
expect err "a Dockerfile in a subdirectory of deploy/"                  check_digest_pins.py
deploy; printf 'FROM python:3.12-slim\n' > "$TMP/r/deploy/api.dockerfile"
expect err "a lowercase .dockerfile name"                               check_digest_pins.py

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
fresh; mkdir -p "$C/worktrees/agent-x/.claude/agents" && printf '\nAlso ask `ghost-reviewer`.\n' > "$C/worktrees/agent-x/.claude/agents/code-reviewer.md"
expect ok  "an agent worktree under .claude/worktrees/ is not linted"   lint_tooling.py
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
