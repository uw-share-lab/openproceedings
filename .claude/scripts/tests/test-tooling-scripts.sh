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
# duplicate ids (decision-027: the queue merges two PRs that each created task-N under different filenames)
B="$TMP/r/backlog"
task() { printf -- '---\nid: %s\nstatus: To Do\n---\n' "$2" > "$B/$1"; }
dec() { mkdir -p "$B/decisions"; printf -- '---\nid: %s\nstatus: accepted\n---\n' "$2" > "$B/decisions/$1"; }
# expect_clash <label> <id>  — exits 1 AND names <id> as a duplicate, so an unrelated failure can't pass the row
expect_clash() {
  local label="$1" id="$2" got
  if python3 "$TMP/r/.claude/scripts/check_backlog.py" 2>&1 >/dev/null | grep -q "^backlog: $id is used by 2 files"; then got=clash; else got=none; fi
  if [ "$got" = clash ]; then pass=$((pass+1)); printf '  ok   %-22s %-58s -> %s\n' check_backlog.py "$label" "$got"
  else fail=$((fail+1)); printf '  FAIL %-22s %-58s -> %s (want clash on %s)\n' check_backlog.py "$label" "$got" "$id"; fi
}
fresh; task "tasks/task-1 - a.md" TASK-1; task "tasks/task-2 - b.md" TASK-2; task "completed/task-3 - c.md" TASK-3
expect ok  "distinct ids across tasks/ and completed/"                  check_backlog.py
fresh; task "tasks/task-1 - a.md" TASK-1; task "tasks/task-1 - b.md" TASK-1
expect_clash "one id twice in tasks/" task-1
fresh; task "tasks/task-7 - a.md" TASK-7; task "completed/task-7 - b.md" TASK-7
expect_clash "one id in tasks/ and completed/" task-7
fresh; task "tasks/task-75 - a.md" task-75; task "completed/task-075 - b.md" TASK-075
expect_clash "TASK-075 and task-75 are one id" task-75
fresh; task "tasks/task-8 - a.md" "'TASK-8'"; task "tasks/task-8 - b.md" '"task-8"'
expect_clash "quoted ids are read" task-8
fresh; task "tasks/task-1 - a.md" TASK-3; task "tasks/task-2 - b.md" TASK-3
expect_clash "the frontmatter id wins over the filename (clash)" task-3
fresh; task "tasks/task-1 - a.md" TASK-1; task "tasks/task-1 - b.md" TASK-2
expect ok  "the frontmatter id wins over the filename (no clash)"       check_backlog.py
fresh; printf 'no frontmatter\n' > "$B/tasks/task-4 - a.md"; printf -- '---\nstatus: To Do\n---\n' > "$B/completed/task-4 - b.md"
expect_clash "no id field: the filename prefix is the id" task-4
fresh; printf -- '---\nstatus: To Do\n---\nid: TASK-7\n' > "$B/tasks/task-5 - a.md"; printf -- '---\nstatus: To Do\n---\nid: TASK-7\n' > "$B/tasks/task-6 - b.md"
expect ok  "an id: line below the frontmatter is body text"             check_backlog.py
fresh; printf -- '---\r\nid: TASK-9\r\nstatus: To Do\r\n---\r\n' > "$B/tasks/task-1 - a.md"; task "tasks/task-2 - b.md" TASK-9
expect_clash "CRLF frontmatter is read" task-9
fresh; task "tasks/task-12 - a.md" TASK-12; task "tasks/task-12.1 - b.md" TASK-12.1
expect ok  "a subtask 12.1 is not task 12"                              check_backlog.py
fresh; task "tasks/notes.md" "some note"
expect err "a file with no readable id fails closed"                    check_backlog.py
fresh; task "tasks/task-3 - a.md" decision-3
expect err "a decision id in tasks/ fails closed"                       check_backlog.py
fresh; mkdir -p "$B/archive/tasks"; task "archive/tasks/task-2 - a.md" TASK-2; task "tasks/task-2 - b.md" TASK-2
expect ok  "backlog/archive/ is not compared (the CLI reuses its ids)"  check_backlog.py
fresh; dec "decision-1 - a.md" decision-1; dec "decision-2 - b.md" decision-2; task "tasks/task-1 - c.md" TASK-1
expect ok  "distinct decisions; task-1 and decision-1 don't clash"      check_backlog.py
fresh; dec "decision-29 - a.md" decision-29; dec "decision-29 - b.md" decision-029
expect_clash "one decision id twice" decision-29
fresh; printf 'no frontmatter\n' > "$B/tasks/task-1 - a.md"; dec "decision-5 - a.md" decision-5; dec "decision-6 - b.md" decision-5
expect_clash "decision clash: the frontmatter id wins over the filename" decision-5

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
deploy; printf 'FROM registry:5000/node@%s\n' "$D" > "$W"
expect err "a registry port is not a tag"                               check_digest_pins.py
deploy; printf 'FROM registry:5000/node:22@%s\n' "$D" > "$W"
expect ok  "a registry port and a tag"                                  check_digest_pins.py
deploy; printf 'FROM node:22@sha256:abc\n' > "$W"
expect err "a truncated digest"                                         check_digest_pins.py
deploy; printf 'from node:22 as build\n' > "$W"
expect err "lowercase from is still checked"                            check_digest_pins.py
deploy; printf 'FROM --platform=linux/amd64 node:22\n' > "$W"
expect err "a --platform flag does not hide the image"                  check_digest_pins.py
deploy; printf 'FROM --platform=linux/amd64 node:22@%s\n' "$D" > "$W"
expect ok  "a pinned image after a --platform flag"                     check_digest_pins.py
deploy; printf 'ARG BASE=node:22\nFROM ${BASE}\n' > "$W"
expect err "an ARG-named image"                                         check_digest_pins.py
deploy; printf 'ARG TAG=22\nFROM node:${TAG}@%s\n' "$D" > "$W"
expect err "an ARG-named tag, even with a digest"                       check_digest_pins.py
deploy; printf 'FROM node:22@%s AS build extra\n' "$D" > "$W"
expect err "a FROM it can't read (trailing words) is refused"           check_digest_pins.py
deploy; printf 'FROM node:22@%s AS build\nFROM build\nFROM node:22\n' "$D" > "$W"
expect err "a pinned image, a stage reference, then an unpinned image"  check_digest_pins.py
deploy; printf 'FROM node:22@%s AS Build\nFROM build\nFROM scratch\n' "$D" > "$W"
expect ok  "an earlier stage (any case) and scratch need no digest"     check_digest_pins.py
deploy; printf 'FROM build\nFROM node:22@%s AS build\n' "$D" > "$W"
expect err "a stage named before it is defined is an image"             check_digest_pins.py
deploy; printf 'FROM \\\n  node:22@%s \\\n  AS build\n' "$D" > "$W"
expect ok  "a pinned FROM wrapped over continuation lines"              check_digest_pins.py
deploy; printf 'FROM \\\n# a comment inside the continuation\n  node:22@%s\n' "$D" > "$W"
expect ok  "a pinned FROM wrapped around a comment"                     check_digest_pins.py
deploy; printf 'FROM node:22@%s\nRUN echo \\\n  FROM node:22\n' "$D" > "$W"
expect ok  "FROM inside a RUN continuation is not an instruction"       check_digest_pins.py
deploy; printf '# escape=`\nFROM node:22@%s\nRUN echo `\n  FROM node:22\n' "$D" > "$W"
expect ok  "an escape directive changes the continuation character"     check_digest_pins.py
deploy; printf '# syntax=docker/dockerfile:1\nFROM node:22@%s\n' "$D" > "$W"
expect err "an unpinned syntax directive"                               check_digest_pins.py
deploy; printf '# syntax=docker/dockerfile:1@%s\nFROM node:22@%s\n' "$D" "$D" > "$W"
expect ok  "a pinned syntax directive"                                  check_digest_pins.py
deploy; printf '# a comment\n# syntax=docker/dockerfile:1\nFROM node:22@%s\n' "$D" > "$W"
expect ok  "syntax= after a comment is a comment, not a directive"      check_digest_pins.py
deploy; printf 'FROM node:22@%s\nCOPY --from=nginx:latest /a /b\n' "$D" > "$W"
expect err "COPY --from an unpinned image"                              check_digest_pins.py
deploy; printf 'FROM node:22@%s AS build\nCOPY --chown=node --from=Build /a /b\nCOPY --from=0 /a /b\n' "$D" > "$W"
expect ok  "COPY --from an earlier stage, by name or by index"          check_digest_pins.py
deploy; printf 'FROM node:22@%s\nCOPY --from=1 /a /b\n' "$D" > "$W"
expect err "COPY --from a stage index that doesn't exist yet"           check_digest_pins.py
deploy; printf 'FROM node:22@%s\nFROM node:22@%s\nFROM scratch\nCOPY --from=1 /a /b\n' "$D" "$D" > "$W"
expect ok  "COPY --from the second stage by its index"                  check_digest_pins.py
deploy; printf 'FROM node:22@%s AS a\nRUN --mount=type=bind,from=a,target=/a --mount=type=bind,from=busybox:1,target=/b true\n' "$D" > "$W"
expect err "a second RUN --mount from an unpinned image"                check_digest_pins.py
deploy; printf 'FROM node:22@%s\nRUN --mount=type=cache,target=/c true\n' "$D" > "$W"
expect ok  "a RUN --mount with no from="                                check_digest_pins.py
deploy; printf '\357\273\277FROM node:22\n' > "$W"
expect err "a byte-order mark does not hide an unpinned FROM"           check_digest_pins.py
deploy; printf 'FROM node:22@%s AS build\nCOPY --from=build\\\ner /a /b\n' "$D" > "$W"
expect err "a continuation glues --from=build + er into builder"        check_digest_pins.py
deploy; printf 'FROM node:22@%s\nFROM 0\n' "$D" > "$W"
expect err "FROM names a stage by name only, never by index"            check_digest_pins.py
deploy; printf '# foo=bar\n# syntax=docker/dockerfile:1\nFROM node:22@%s\n' "$D" > "$W"
expect ok  "an unknown directive ends the directives (syntax= a comment)" check_digest_pins.py
deploy; mkdir -p "$TMP/r/deploy/api"; printf 'FROM python:3.12-slim\n' > "$TMP/r/deploy/api/Dockerfile"
expect err "a Dockerfile in a subdirectory of deploy/"                  check_digest_pins.py
deploy; printf 'FROM python:3.12-slim\n' > "$TMP/r/deploy/api.dockerfile"
expect err "a lowercase .dockerfile name"                               check_digest_pins.py
deploy; printf 'FROM python:3.12-slim\n' > "$TMP/r/deploy/Containerfile"
expect err "a Containerfile (Dependabot reads those too)"               check_digest_pins.py

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
