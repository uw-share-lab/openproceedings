#!/usr/bin/env bash
# PreToolUse(Bash) gate: no AI authorship in commits or PRs.
#
# Project decision (2026-09-25): `.claude/` is committed, but commits and PRs are authored by people.
# When the command contains a message-writing git command (commit, merge, tag, notes, revert,
# cherry-pick), a PR-writing gh command (pr create/new/edit/comment/review/merge) or a release-writing one
# (release create/edit: its notes are the release notes, spec 08 §Release), the WHOLE raw
# command text is scanned — not individual flags — so -m, -am, -qm, --message=, --trailer, heredoc
# bodies (`-F - <<EOF`, `-m "$(cat <<'EOF' …)"`), --body and --notes are all covered — plus the contents of
# any -F/--file/--body-file/--notes-file that is a regular file (≤1 MB), and of any file a `cat`, `< file`,
# `$(cat file)`, `$(< file)` or backquoted `cat` in the command reads, and every word as bash makes it
# (`'Co-Authored-By: Cl''aude'`, `$'…'`, variables set in the command: TASK-156), the command walked a second
# time with HOME/TMPDIR/USER read as '' (`cd ~` then stays put). `git commit` with no message opens
# an editor; that path is covered by .githooks/commit-msg (scripts/setup-dev.sh installs it) and CI
# (pr-gates.yml).
# A command it can't parse is scanned as raw text; one it can't check at all (an internal error) is blocked.
# Exit 2 blocks the call and feeds stderr back to the agent.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
# The program goes to Python as an argument and the payload on stdin, never in an environment variable: past
# ARG_MAX (about 1 MB) exec fails with 126, which Claude Code lets through. Any exit but 0 blocks (TASK-156).
IFS= read -r -d '' PROG <<'PY' || true
import os, re, shlex, sys
sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
from cmdparse import ParseError, expand_known, gh_subcommand, git_subcommand, opt_values, read_payload, walk

PATTERN = re.compile(
    r"co-authored-by[:=][^\n]*(claude|anthropic)|generated with \[?claude|🤖 generated|noreply@anthropic\.com",
    re.IGNORECASE,
)
GIT_MSG = {"commit", "merge", "tag", "notes", "revert", "cherry-pick"}
GH_PR_WRITE = {"create", "edit", "comment", "review", "merge"}
GH_RELEASE_WRITE = {"create", "edit"}
MAX_BYTES = 1_000_000
# A file read inside a word: `-m "$(cat msg.txt)"`, `"$(< msg.txt)"`, "`cat msg.txt`" (TASK-067: a quoted
# substitution is one word, so its `cat` is no command of its own).
SUBST_READ = re.compile(r"\$\(\s*(?:cat\s+([^()]*?)|<\s*([^()]*?))\s*\)|`\s*cat\s+([^`]*?)\s*`")

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
    print("Blocked: commits, PRs and releases in openproceedings carry no AI authorship.", file=sys.stderr)
    print("Remove the 'Co-Authored-By: Claude …' trailer / 'Generated with Claude Code' footer and retry.", file=sys.stderr)
    print("(.claude/ tooling is committed; authorship is not. See CLAUDE.md → 'Authorship'.)", file=sys.stderr)
    sys.exit(2)

def main():
    cmd, cwd = read_payload()
    if not cmd:  # no raw-text prefilter: `gi\<newline>t push` only becomes `git` after parsing (review round 6)
        sys.exit(0)
    try:
        walked = list(walk(cmd, cwd))
        if "~" in cmd or "$" in cmd:
            # and with HOME/TMPDIR/USER read as '', which the agent's shell may have: `cd ~` then stays put (TASK-156)
            walked += walk(cmd, cwd, env_empty=True)
    except ParseError:
        if PATTERN.search(cmd):  # unbalanced quotes: bash won't run it, but don't let it look approved
            blocked()
        sys.exit(0)

    commands = [(argv, d) for argv, d, _ in walked if argv]
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
        if h and h[0] == "release" and h[1] in GH_RELEASE_WRITE:
            relevant = True
            texts += [file_text(f, d) for f in opt_values(h[2], "--notes-file", "-F")]
    if relevant:
        # A message fed on stdin: `git commit -F - < msg.txt` (input redirect) or `cat msg.txt | git commit -F -`.
        for _, d, redirects in walked:
            texts += [file_text(target, d) for op, target in redirects if "<" in op and target]
        # every word as bash makes it, with the variables this gate can tell put in: a trailer split by quoting
        # (`'Co-Authored-By: Cl''aude'`), written with `$'…'` escapes or in a variable reads whole here (TASK-156)
        texts += [" ".join(expand_known(w, argv, d) for w in argv) for argv, d in commands]
        for argv, d in commands:
            if argv and argv[0] == "cat":
                texts += [file_text(a, d) for a in argv[1:] if not a.startswith("-")]
            for m in (m for word in argv for m in SUBST_READ.finditer(word)):
                try:
                    names = shlex.split(next(g for g in m.groups() if g is not None))
                except ValueError:
                    continue
                texts += [file_text(a, d) for a in names if not a.startswith("-")]
    if relevant and (PATTERN.search(cmd) or any(PATTERN.search(t) for t in texts)):
        blocked()
    sys.exit(0)

try:
    main()
except Exception as exc:  # a crash exits 1, which Claude Code lets through: block instead (TASK-067 final review gate)
    print(f"Blocked: block-ai-attribution.sh could not check this command ({type(exc).__name__}). Write it more "
          "plainly and retry.", file=sys.stderr)
    sys.exit(2)
PY
python3 -c "$PROG" "$HOOK_DIR"
rc=$?
if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
  echo "Blocked: block-ai-attribution.sh could not run its check (exit $rc); refusing rather than letting the command through." >&2
fi
[ "$rc" -eq 0 ] || exit 2
