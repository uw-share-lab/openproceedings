#!/usr/bin/env bash
# shellcheck disable=SC2016  # commands under test are single-quoted on purpose: $(…), $(( )) and backticks must reach the hooks unexpanded
# Case table for the CI tooling scripts: learnings_index.py, check_backlog.py, check_digest_pins.py, npm_specs.py,
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
B="$TMP/r/backlog"
# expect_msg <label> <ERE> — exits 1 AND prints a `backlog: ` line matching <ERE>, so an unrelated failure
# (a traceback, another problem) can't pass the row
expect_msg() {
  local label="$1" re="$2" got
  if python3 "$TMP/r/.claude/scripts/check_backlog.py" 2>&1 >/dev/null | grep -Eq "^backlog: $re"; then got=match; else got=none; fi
  if [ "$got" = match ]; then pass=$((pass+1)); printf '  ok   %-22s %-58s -> %s\n' check_backlog.py "$label" "$got"
  else fail=$((fail+1)); printf '  FAIL %-22s %-58s -> %s (want: %s)\n' check_backlog.py "$label" "$got" "$re"; fi
}
expect_clash() { expect_msg "$1" "$2 is used by 2 files"; }  # <label> <id as printed, e.g. task-75>
task() { printf -- '---\nid: %s\nstatus: To Do\n---\n' "$2" > "$B/$1"; }
dec() { mkdir -p "$B/decisions"; printf -- '---\nid: %s\nstatus: accepted\n---\n' "$2" > "$B/decisions/$1"; }
fresh; expect ok  "no tasks at all"                                     check_backlog.py
fresh; printf -- '---\nid: task-1\nstatus: In Progress\n---\n' > "$B/tasks/task-1 - x.md"
expect ok  "an In Progress task"                                        check_backlog.py
fresh; printf -- '---\nid: task-1\nstatus: Done\n---\n' > "$B/tasks/task-1 - x.md"
expect_msg "a Done task left in tasks/"                                 "'task-1 - x.md' is Done but still in backlog/tasks/"
fresh; printf -- "---\nid: task-1\nstatus: 'Done'\n---\n" > "$B/tasks/task-1 - x.md"
expect_msg "a quoted 'Done' status"                                     "'task-1 - x.md' is Done"
fresh; printf -- '---\nid: task-1\nstatus: Done\n---\n' > "$B/completed/task-1 - x.md"
expect ok  "a Done task in completed/"                                  check_backlog.py
fresh; rm -rf "$B/completed"
expect_msg "a missing completed/ fails (not 0 files)"                   "backlog/completed/ is missing"
fresh; rm -rf "$B/tasks"
expect_msg "a missing tasks/ fails (not 0 files)"                       "backlog/tasks/ is missing"
# duplicate ids (decision-027: the queue merges two PRs that each created task-N under different filenames)
fresh; task "tasks/task-1 - a.md" TASK-1; task "tasks/task-2 - b.md" TASK-2; task "completed/task-3 - c.md" TASK-3
expect ok  "distinct ids across tasks/ and completed/"                  check_backlog.py
fresh; task "tasks/task-1 - a.md" TASK-1; task "tasks/task-1 - b.md" TASK-1
expect_clash "one id twice in tasks/"                                   task-1
fresh; task "tasks/task-7 - a.md" TASK-7; task "completed/task-7 - b.md" TASK-7
expect_clash "one id in tasks/ and completed/"                          task-7
fresh; task "tasks/task-75 - a.md" task-75; task "completed/task-075 - b.md" TASK-075
expect_clash "TASK-075 and task-75 are one id"                          task-75
fresh; task "tasks/task-8 - a.md" "'TASK-8'"; task "tasks/task-8 - b.md" '"task-8"'
expect_clash "quoted ids are read"                                      task-8
fresh; printf -- '---\nstatus: To Do\n---\n' > "$B/tasks/task-4 - a.md"; printf -- '---\ntitle: b\n---\n' > "$B/completed/task-4 - b.md"
expect_clash "no id field: the filename prefix is the id"               task-4
fresh; printf -- '---\nstatus: To Do\n---\n' > "$B/tasks/task-4 - a.md"
expect_msg "no id field fails (Backlog.md lists it as TASK-)"           "'tasks/task-4 - a.md' has no frontmatter .id:."
fresh; printf -- '---\ndescription: |\n  id: TASK-3\ntitle: nested\n---\n' > "$B/tasks/task-3 - a.md"
expect_msg "an indented id: is nested, not the task's id"               "'tasks/task-3 - a.md' has no frontmatter .id:."
fresh; task "tasks/x - a.md" TASK-3; task "tasks/y - b.md" TASK-3
expect_clash "no filename prefix: the frontmatter id is the id"         task-3
fresh; printf -- '---\nid: TASK-5\n---\nid: TASK-7\n' > "$B/tasks/task-5 - a.md"; printf -- '---\nid: TASK-6\n---\nid: TASK-7\n' > "$B/tasks/task-6 - b.md"
expect ok  "an id: line below the frontmatter is body text"             check_backlog.py
fresh; printf -- '---\r\nid: TASK-9\r\nstatus: To Do\r\n---\r\n' > "$B/tasks/x - a.md"; task "tasks/y - b.md" TASK-9
expect_clash "CRLF frontmatter is read"                                 task-9
fresh; printf '\357\273\277---\nid: TASK-9\nstatus: To Do\n---\n' > "$B/tasks/x - a.md"; task "tasks/y - b.md" TASK-9
expect_clash "a byte-order mark does not hide the frontmatter id"       task-9
fresh; printf -- '--- \nid: TASK-9\nstatus: To Do\n--- \n' > "$B/tasks/x - a.md"; task "tasks/y - b.md" TASK-9
expect_clash "trailing spaces on the --- lines"                         task-9
fresh; printf -- '---\n"id" : TASK-9\nstatus: To Do\n---\n' > "$B/tasks/x - a.md"; task "tasks/y - b.md" TASK-9
expect_clash "a quoted id key with a space before the colon"            task-9
fresh; task "tasks/task-12 - a.md" TASK-12; task "tasks/task-12.1 - b.md" TASK-12.1
expect ok  "a subtask 12.1 is not task 12"                              check_backlog.py
# a hand-edited file fails closed rather than hiding its id
fresh; task "tasks/task-6 - b.md" TASK-5; task "tasks/task-5 - a.md" TASK-5
expect_msg "frontmatter id and filename disagree"                       "'tasks/task-6 - b.md' has a frontmatter .id:. that disagrees"
fresh; printf -- '---\nid: TASK-6\nid: TASK-5\n---\n' > "$B/tasks/task-6 - b.md"
expect_msg "two id: fields in one frontmatter"                          "'tasks/task-6 - b.md' has 2 .id:. fields"
fresh; task "tasks/task-3 - a.md" TASK-3-old
expect_msg "an id with trailing junk fails closed"                      "'tasks/task-3 - a.md' has no readable task id in its frontmatter"
fresh; task "tasks/task-5 - a.md" TASK-5; task "tasks/task-6 - b.md" "'TASK-5' # moved"
expect_msg "a quoted id with a trailing comment fails closed"           "'tasks/task-6 - b.md' has no readable task id in its frontmatter"
fresh; task "tasks/task-5 - a.md" TASK-5; printf -- '---\n{id: TASK-5, status: To Do}\n---\n' > "$B/tasks/task-6 - b.md"
expect_msg "a flow-mapping frontmatter fails closed"                    "'tasks/task-6 - b.md' has frontmatter this check can't read"
fresh; task "tasks/task-5 - a.md" TASK-5; printf -- '---\n? id\n: TASK-5\n---\n' > "$B/tasks/task-6 - b.md"
expect_msg "an explicit ? key fails closed"                             "'tasks/task-6 - b.md' has frontmatter this check can't read"
fresh; task "tasks/task-5 - a.md" TASK-5; printf -- '---\n"i\\x64": TASK-5\n---\n' > "$B/tasks/task-6 - b.md"
expect_msg "an escaped quoted key fails closed"                         "'tasks/task-6 - b.md' has frontmatter this check can't read"
fresh; task "tasks/task-5 - a.md" TASK-5; printf -- '---\n<<: {id: TASK-5}\n---\n' > "$B/tasks/task-6 - b.md"
expect_msg "a << merge key fails closed"                                "'tasks/task-6 - b.md' has frontmatter this check can't read"
fresh; task "tasks/task-5 - a.md" TASK-5; printf -- '---\nx: &a {id: TASK-5}\n<<: *a\n---\n' > "$B/tasks/task-6 - b.md"
expect_msg "an anchor merged through an alias fails closed"             "'tasks/task-6 - b.md' has frontmatter this check can't read"
fresh; printf -- '---\n  id: TASK-6\n---\n' > "$B/tasks/task-6 - b.md"
expect_msg "an indented first frontmatter line fails closed"            "'tasks/task-6 - b.md' has frontmatter this check can't read"
fresh; task "tasks/task-5 - a.md" TASK-5; printf -- '---\n# c\n  "i\\x64": TASK-5\n  title: hidden\n---\n' > "$B/tasks/task-6 - b.md"
expect_msg "a comment, then an indented mapping, fails closed"          "'tasks/task-6 - b.md' has frontmatter this check can't read"
fresh; printf -- '---\nid: TASK-6\ntitle: >-\n  Read every file when the\n  {frontmatter} holds ?odd values\nlabels:\n- a\n  - b\n# a comment\nstatus: To Do\n---\n' > "$B/tasks/task-6 - b.md"
expect ok  "CLI-shaped frontmatter: {/? on folded lines, lists, comment" check_backlog.py
fresh; printf '\n---\nid: TASK-5\n---\n' > "$B/tasks/task-6 - b.md"
expect_msg "no frontmatter at the top fails closed"                     "'tasks/task-6 - b.md' has no frontmatter"
fresh; task "tasks/notes.md" "some note"
expect_msg "a file with no readable id fails closed"                    "'tasks/notes.md' has no readable task id in its frontmatter"
fresh; printf -- '---\ntitle: x\n---\n' > "$B/tasks/task-12abc.md"
expect_msg "a filename prefix glued to letters is not an id"            "'tasks/task-12abc.md' has no readable task id \(frontmatter"
fresh; task "tasks/task-12 - a.md" TASK-12; printf -- '---\ntitle: x\n---\n' > "$B/tasks/task-12.1x.md"
expect_msg "task-12.1x is not read back as task-12"                     "'tasks/task-12.1x.md' has no readable task id \(frontmatter"
fresh; task "tasks/task-3 - a.md" decision-3
expect_msg "a decision id in tasks/ fails closed"                       "'tasks/task-3 - a.md' has no readable task id"
fresh; printf -- '---\nid: TASK-1\n---\n\377\376\n' > "$B/tasks/task-1 - a.md"
expect_msg "a file that isn't UTF-8 is named, not a traceback"          "'tasks/task-1 - a.md' can't be read as UTF-8"
fresh; mkdir -p "$B/archive/tasks"; task "archive/tasks/task-2 - a.md" TASK-2; task "tasks/task-2 - b.md" TASK-2
expect ok  "backlog/archive/ is not compared (the CLI reuses its ids)"  check_backlog.py
fresh; dec "decision-1 - a.md" decision-1; dec "decision-2 - b.md" decision-2; task "tasks/task-1 - c.md" TASK-1
expect ok  "distinct decisions; task-1 and decision-1 don't clash"      check_backlog.py
fresh; dec "decision-29 - a.md" decision-29; dec "decision-029 - b.md" decision-029
expect_clash "one decision id twice"                                    decision-29
fresh; dec "x - a.md" decision-5; dec "y - b.md" decision-5
expect_clash "decision clash read from the frontmatter"                 decision-5

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

echo "== dependabot/npm_specs.py (TASK-212)"
S=dependabot/npm_specs.py
# npmws <root manifest> <frontend manifest> <lock packages[""]> <lock packages["frontend"]>: each a JSON fragment
# (`,"dependencies":{…}`) added to that object; writes package.json, frontend/package.json and package-lock.json
npmws() {
  fresh; mkdir -p "$TMP/r/frontend"
  printf '{"name":"r","workspaces":["frontend"]%s}\n' "$1" > "$TMP/r/package.json"
  printf '{"name":"f","engines":{"node":">=22"}%s}\n' "$2" > "$TMP/r/frontend/package.json"
  printf '{"name":"r","lockfileVersion":3,"packages":{"":{"name":"r"%s},"frontend":{"name":"f"%s}}}\n' "$3" "$4" > "$TMP/r/package-lock.json"
}
# expect_spec <label> <ERE> — exits 1 AND prints an `npm specs: ` line matching <ERE> (an unrelated failure
# can't pass the row)
expect_spec() {  # expect_spec <label> <ERE> [args...]
  local label="$1" re="$2" out rc; shift 2
  out=$(python3 "$TMP/r/.claude/scripts/$S" "$@" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s\n' "$out" | grep -Eq "^npm specs: $re"; then
    pass=$((pass+1)); printf '  ok   %-22s %-58s -> match\n' npm_specs.py "$label"
  else fail=$((fail+1)); printf '  FAIL %-22s %-58s -> rc %s: %s (want: %s)\n' npm_specs.py "$label" "$rc" "$out" "$re"; fi
}
N=',"dependencies":{"next":"16.3.8","react":"19.3.0"}'
DV=',"devDependencies":{"eslint-config-next":"16.3.8","eslint":"^9"}'
OP=',"optionalDependencies":{"fsevents":"2.3.3"}'
PR=',"peerDependencies":{"react":">=19"}'
ALL="$N$DV$OP$PR"
FE='packages\["frontend"\]'
fresh; expect ok  "no package.json and no lock: nothing to check"      "$S"
fresh; mkdir -p "$TMP/r/frontend"; cp "$SRC/package.json" "$SRC/package-lock.json" "$TMP/r/"; cp "$SRC/frontend/package.json" "$TMP/r/frontend/"
expect ok  "the repo's own manifests and lock pass"                     "$S"
npmws "$N" "$ALL" "$N" "$ALL"
expect ok  "all four sections equal, in both entries"                   "$S"
npmws '' '' '' ''
expect ok  "no dependencies anywhere"                                   "$S"
npmws '' "$N" '' ',"dependencies":{"react":"19.3.0","next":"16.3.8"}'
expect ok  "key order does not matter"                                  "$S"
npmws '' "$ALL" '' "$ALL"',"engines":{"node":">=20"},"version":"9.9.9"'
expect ok  "fields outside the four sections are not compared"          "$S"
npmws '' "$ALL" '' "$N"',"devDependencies":{"eslint-config-next":"^16.3.8","eslint":"^9"}'"$OP$PR"
expect_spec "PR #124: a caret in the lock's devDependencies"            "frontend/package\.json devDependencies\.eslint-config-next is '16\.3\.8', the lock's $FE has '\^16\.3\.8'"
npmws '' "$ALL" '' ',"dependencies":{"next":"^16.3.8","react":"19.3.0"}'"$DV$OP$PR"
expect_spec "a caret in the lock's dependencies"                        "frontend/package\.json dependencies\.next is '16\.3\.8', the lock's $FE has '\^16\.3\.8'"
npmws '' "$ALL" '' "$N$DV"',"optionalDependencies":{"fsevents":"~2.3.3"}'"$PR"
expect_spec "a tilde in the lock's optionalDependencies"                "frontend/package\.json optionalDependencies\.fsevents is '2\.3\.3', the lock's $FE has '~2\.3\.3'"
npmws '' "$ALL" '' "$N$DV$OP"',"peerDependencies":{"react":">=18"}'
expect_spec "another range in the lock's peerDependencies"              "frontend/package\.json peerDependencies\.react is '>=19', the lock's $FE has '>=18'"
npmws '' ',"dependencies":{"next":"^16.3.8"}' '' ',"dependencies":{"next":"16.3.8"}'
expect_spec "a range in the manifest, an exact pin in the lock"         "frontend/package\.json dependencies\.next is '\^16\.3\.8', the lock's $FE has '16\.3\.8'"
npmws '' ',"devDependencies":{"typescript":"^5"}' '' ',"devDependencies":{"typescript":"^5"}'
expect ok  "the same range on both sides passes"                        "$S"
npmws '' "$N" '' ',"dependencies":{"next":"16.3.8"}'
expect_spec "a manifest dependency missing from the lock"               "frontend/package\.json dependencies\.react is '19\.3\.0', the lock's $FE has None"
npmws '' ',"dependencies":{"next":"16.3.8"}' '' "$N"
expect_spec "an extra dependency in the lock"                           "frontend/package\.json dependencies\.react is None, the lock's $FE has '19\.3\.0'"
npmws '' ',"dependencies":{"next":"16.3.8"}' '' ',"devDependencies":{"next":"16.3.8"}'
expect_spec "a dependency in another section of the lock"               "frontend/package\.json dependencies\.next is '16\.3\.8', the lock's $FE has None"
npmws ',"devDependencies":{"prettier":"3.9.9"}' '' ',"devDependencies":{"prettier":"^3.9.9"}' ''
expect_spec "the root entry is compared too"                            "package\.json devDependencies\.prettier is '3\.9\.9', the lock's packages\[\"\"\] has '\^3\.9\.9'"
npmws '' "$N" '' "$N"; printf '{"name":"r","lockfileVersion":3,"packages":{"":{"name":"r"}}}\n' > "$TMP/r/package-lock.json"
expect_spec "a manifest with no lock entry"                             "frontend/package\.json exists, but package-lock\.json has no $FE entry"
npmws '' '' '' "$N"; rm "$TMP/r/frontend/package.json"
expect_spec "a lock entry with dependencies and no manifest"            "package-lock\.json $FE lists dependencies, but frontend/package\.json does not exist"
npmws '' '' '' ''; rm "$TMP/r/frontend/package.json"
expect ok  "no manifest and a lock entry without dependencies"          "$S"
npmws '' "$N" '' "$N"; rm "$TMP/r/package-lock.json"
expect_spec "a manifest with no lock"                                   "package-lock\.json does not exist"
npmws '' "$N" '' "$N"; printf '{"name":"r","lockfileVersion":3}\n' > "$TMP/r/package-lock.json"
expect_spec "a lock with no packages object"                            "package-lock\.json has no .packages. object"
npmws '' "$N" '' "$N"; printf '{"name":"r","lockfileVersion":3,"packages":{"":{},"frontend":["x"]}}\n' > "$TMP/r/package-lock.json"
expect_spec "a lock entry that isn't an object"                         "package-lock\.json $FE is not an object"
npmws '' "$N" '' "$N"; printf '{"name":"f",\n' > "$TMP/r/frontend/package.json"
expect_spec "a manifest that isn't JSON"                                "frontend/package\.json can't be read as JSON"
npmws '' "$N" '' "$N"; printf '["frontend"]\n' > "$TMP/r/package.json"
expect_spec "a manifest that isn't a JSON object"                       "package\.json is not a JSON object"
npmws '' ',"dependencies":["next"]' '' "$N"
expect_spec "a section that isn't an object"                            "frontend/package\.json dependencies or the lock's $FE dependencies is not an object"
npmws '' ',"dependencies":null' '' ''
expect_spec "a null section is not read as empty"                       "frontend/package\.json dependencies or the lock's $FE dependencies is not an object"
# --root: /dependabot-review runs dev's copy of the script on the PR branch's checkout
npmws '' "$N" '' "$N"; mkdir -p "$TMP/pr/frontend"
printf '{"name":"f","dependencies":{"next":"16.3.8"}}\n' > "$TMP/pr/frontend/package.json"
printf '{"lockfileVersion":3,"packages":{"":{},"frontend":{"dependencies":{"next":"^16.3.8"}}}}\n' > "$TMP/pr/package-lock.json"
expect ok  "the script's own checkout matches"                         "$S"
expect_spec "--root reads the other checkout"                          "frontend/package\.json dependencies\.next is '16\.3\.8', the lock's $FE has '\^16\.3\.8'" --root "$TMP/pr"
expect_spec "--root that is not a directory"                           ".*/pr/missing is not a directory" --root "$TMP/pr/missing"
npmws '' "$N" '' "$N"; printf '{"name":"r","workspaces":["frontend","docs"]}\n' > "$TMP/r/package.json"
expect_spec "a workspace the check doesn't know"                       "package\.json workspaces .*'docs'.*: this check compares only"
npmws '' '' '' ''; rm "$TMP/r/frontend/package.json"; printf '{"lockfileVersion":3,"packages":{"":{},"frontend":{"dependencies":[]}}}\n' > "$TMP/r/package-lock.json"
expect_spec "an empty non-object lock section with no manifest"        "package-lock\.json $FE lists dependencies, but frontend/package\.json does not exist"

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

echo "== lint_probes.py (a case-table probe reaches the hook only as data, TASK-169)"
fresh; expect ok  "clean copy passes"                                   lint_probes.py
F="$SRC/.claude/scripts/tests/lint-probes"   # one table fragment per case, kept as data (*.txt: never run)
for f in "$F"/bad-*.txt; do expect err "$(basename "$f" .txt)" lint_probes.py "$f"; done
for f in "$F"/good-*.txt; do expect ok "$(basename "$f" .txt)" lint_probes.py "$f"; done
# line 1 is a real finding; line 2's \`…\` is escaped (literal), and the scan of line 1 must not run on into it
out=$(python3 "$TMP/r/.claude/scripts/lint_probes.py" "$F/mixed-nested-then-escaped.txt" 2>&1)
case "$out" in
  *":1: "*":2: "*|*":2: "*) fail=$((fail+1)); echo "  FAIL lint_probes.py        escaped backquotes after a nested wrapper flagged: $out" ;;
  *":1: "*) pass=$((pass+1)); echo "  ok   lint_probes.py         only the real finding of mixed-nested-then-escaped" ;;
  *) fail=$((fail+1)); echo "  FAIL lint_probes.py        line 1 of mixed-nested-then-escaped not flagged: $out" ;;
esac

echo "== probe_hook.py (feeds one probe to a hook or cmdparse as data, TASK-169)"
# expect_out <label> <ERE> <args...> -- probe_hook.py exits 0 and prints a line matching <ERE>
expect_out() {
  local label="$1" ere="$2" out; shift 2
  if out=$(cd "$TMP" && python3 "$TMP/r/.claude/scripts/probe_hook.py" "$@" 2>&1) && printf '%s\n' "$out" | grep -Eq "$ere"; then
    pass=$((pass+1)); printf '  ok   %-22s %-58s\n' probe_hook.py "$label"
  else fail=$((fail+1)); printf '  FAIL %-22s %-58s -> %s\n' probe_hook.py "$label" "$out"; fi
}
fresh
printf 'git push origin HEAD:dev' > "$TMP/probe-push.txt"
printf 'ls' > "$TMP/probe-ls.txt"
printf 'git pu\\\nsh origin x' > "$TMP/probe-split.txt"
printf 'touch op-probe-made' > "$TMP/probe-touch.txt"
expect_out "a push to dev is blocked"            '^enforce-pr-workflow.sh: block$' enforce-pr-workflow.sh --file "$TMP/probe-push.txt" --cwd "$TMP"
expect_out "ls is allowed"                       '^enforce-pr-workflow.sh: allow$' enforce-pr-workflow.sh --file "$TMP/probe-ls.txt" --cwd "$TMP"
expect_out "--command takes the probe as one word" '^enforce-pr-workflow.sh: block$' enforce-pr-workflow.sh --command 'git push origin HEAD:dev' --cwd "$TMP"
expect_out "cmdparse shows the joined text"      "^joined: 'git push origin x'$" cmdparse --file "$TMP/probe-split.txt" --cwd "$TMP"
expect_out "cmdparse shows the walk"             "\['git', 'push', 'origin', 'x'\]" cmdparse --file "$TMP/probe-split.txt" --cwd "$TMP"
expect err "a path outside .claude/hooks is no hook" probe_hook.py ../scripts/lint_probes.py --command ls
expect_out "sandbox runs it in a removed mktemp dir" '^exit 0 \(in .*op-probe-.*, removed\)$' sandbox --file "$TMP/probe-touch.txt"
if [ ! -e "$TMP/op-probe-made" ]; then pass=$((pass+1)); echo "  ok   probe_hook.py          sandbox wrote nothing where it was run"
else fail=$((fail+1)); echo "  FAIL probe_hook.py          sandbox wrote op-probe-made where it was run"; fi

echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
