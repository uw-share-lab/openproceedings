#!/usr/bin/env bash
# PreToolUse(Bash) gate: no AI authorship in commits or PRs.
#
# Project decision (2026-09-25): `.claude/` is committed, but commits and PRs are authored by people.
# Blocks `git commit` whose message (-m / --message / -F / --file) and `gh pr create|edit` whose title or
# body (--title / --body / --body-file / -t / -b / -F) contains a Claude co-author trailer or a
# "Generated with Claude Code" footer. `git commit` with no message flag opens an editor; that path is
# covered by .githooks/commit-msg (installed by scripts/setup-dev.sh) and by CI (pr-gates.yml).
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

def file_text(path, base):
    p = path if os.path.isabs(path) else os.path.join(base, path)
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""

cmd, cwd = read_payload()
if not cmd or not re.search(r"\b(git|gh)\b", cmd):
    sys.exit(0)
try:
    commands = list(simple_commands(cmd, cwd))
except ParseError:
    # Unbalanced quotes: bash would refuse to run it anyway. Fall back to scanning the raw text.
    commands = []
    if PATTERN.search(cmd):
        print("Blocked: this command appears to add AI attribution (Claude co-author / 'Generated with').", file=sys.stderr)
        sys.exit(2)

for argv, d in commands:
    texts = []
    g = git_subcommand(argv, d)
    if g and g[0] == "commit":
        _, args, eff = g
        texts += opt_values(args, "-m", "--message")
        texts += [file_text(f, eff) for f in opt_values(args, "-F", "--file")]
        texts += [a[2:] for a in args if a.startswith("-m") and len(a) > 2]  # -m"msg"
    h = gh_subcommand(argv)
    if h and h[0] == "pr" and h[1] in ("create", "edit", "comment", "review", "merge"):
        args = h[2]
        texts += opt_values(args, "--title", "-t", "--body", "-b", "--subject")
        texts += [file_text(f, d) for f in opt_values(args, "--body-file", "-F")]
    for t in texts:
        if PATTERN.search(t or ""):
            print("Blocked: commits and PRs in openproceedings carry no AI authorship.", file=sys.stderr)
            print("Remove the 'Co-Authored-By: Claude …' trailer / 'Generated with Claude Code' footer and retry.", file=sys.stderr)
            print("(.claude/ tooling is committed; authorship is not. See CLAUDE.md → 'Authorship'.)", file=sys.stderr)
            sys.exit(2)
sys.exit(0)
PY
