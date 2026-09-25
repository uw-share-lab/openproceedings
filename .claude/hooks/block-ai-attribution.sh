#!/usr/bin/env bash
# PreToolUse(Bash) gate: no AI authorship in commits or PRs.
#
# Project decision (2026-09-25): `.claude/` is committed, but commits and PRs are authored by people.
# When the command contains a message-writing git command (commit, merge, tag, notes, revert,
# cherry-pick) or a PR-writing gh command (pr create/new/edit/comment/review/merge), the WHOLE raw
# command text is scanned — not individual flags — so -m, -am, -qm, --message=, --trailer, heredoc
# bodies (`-F - <<EOF`, `-m "$(cat <<'EOF' …)"`) and --body are all covered — plus the contents of any
# -F/--file/--body-file that is a regular file (≤1 MB). `git commit` with no message opens an editor;
# that path is covered by .githooks/commit-msg (scripts/setup-dev.sh installs it) and CI (pr-gates.yml).
# Exit 2 blocks the call and feeds stderr back to the agent.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
input=$(cat)
HOOK_INPUT="$input" python3 - "$HOOK_DIR" <<'PY'
import os, re, sys
sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
from cmdparse import ParseError, gh_subcommand, git_subcommand, opt_values, read_payload, simple_commands

PATTERN = re.compile(
    r"co-authored-by:[^\n]*(claude|anthropic)|generated with \[?claude|🤖 generated|noreply@anthropic\.com",
    re.IGNORECASE,
)
GIT_MSG = {"commit", "merge", "tag", "notes", "revert", "cherry-pick"}
GH_PR_WRITE = {"create", "edit", "comment", "review", "merge"}
MAX_BYTES = 1_000_000

def file_text(path, base):
    if path == "-":
        return ""  # stdin: its heredoc body is part of the raw command, which is scanned
    p = path if os.path.isabs(path) else os.path.join(base, path)
    if not os.path.isfile(p):
        return ""
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return fh.read(MAX_BYTES)
    except OSError:
        return ""

def blocked():
    print("Blocked: commits and PRs in openproceedings carry no AI authorship.", file=sys.stderr)
    print("Remove the 'Co-Authored-By: Claude …' trailer / 'Generated with Claude Code' footer and retry.", file=sys.stderr)
    print("(.claude/ tooling is committed; authorship is not. See CLAUDE.md → 'Authorship'.)", file=sys.stderr)
    sys.exit(2)

cmd, cwd = read_payload()
if not cmd or not re.search(r"\b(git|gh)\b", cmd):
    sys.exit(0)
try:
    commands = list(simple_commands(cmd, cwd))
except ParseError:
    if PATTERN.search(cmd):  # unbalanced quotes: bash won't run it, but don't let it look approved
        blocked()
    sys.exit(0)

texts, relevant = [], False
for argv, d in commands:
    g = git_subcommand(argv, d)
    if g and g[0] in GIT_MSG:
        relevant = True
        texts += [file_text(f, g[2]) for f in opt_values(g[1], "-F", "--file")]
    h = gh_subcommand(argv)
    if h and h[0] == "pr" and h[1] in GH_PR_WRITE:
        relevant = True
        texts += [file_text(f, d) for f in opt_values(h[2], "--body-file", "-F")]
if relevant and (PATTERN.search(cmd) or any(PATTERN.search(t) for t in texts)):
    blocked()
sys.exit(0)
PY
