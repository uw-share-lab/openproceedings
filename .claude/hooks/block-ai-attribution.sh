#!/usr/bin/env bash
# PreToolUse(Bash) gate: no AI authorship in commits or PRs.
#
# Project decision (2026-09-25): `.claude/` is committed, but commits and PRs are authored by people.
# When the command contains a message-writing git command (commit, merge, tag, notes, revert,
# cherry-pick), a PR-writing gh command (pr create/new/edit/comment/review/merge) or a release-writing one
# (release create/edit: its notes are the release notes, spec 08 §Release), the WHOLE raw
# command text is scanned — not individual flags — so -m, -am, -qm, --message=, --trailer, heredoc
# bodies (`-F - <<EOF`, `-m "$(cat <<'EOF' …)"`), --body and --notes are all covered — plus the contents of
# any -F/--file/--body-file/--notes-file that is a regular file (≤1 MB), and of any file a reader in the
# command reads (`cat`, `head`, `tail`, `sed`: the WHOLE file is scanned, not the lines they print; `< file`,
# `$(< file)`, backquotes too; sed's -f/--file script files are scanned as well), and every word as bash
# makes it (`'Co-Authored-By: Cl''aude'`, `$'…'`, variables
# set in the command: TASK-156), the command walked a second time with HOME/TMPDIR/USER read as '' (`cd ~`
# then stays put). A file word is read after its variables are put in (`F=msg.txt; … "$(cat "$F")"`), and one
# it can't resolve (an unknown variable, a `$(…)`, a relative path after a `cd` it couldn't follow) is refused,
# and so is a command substitution that runs another program on a file (`$(awk 1 msg.txt)`, or an argument it
# can't resolve: a reader this gate doesn't model); one that reads no file (`$(date)`, `$(git log -1
# --format=%s)`) is fine (TASK-170). The raw text is searched with its line continuations joined
# (cmdparse.join_continuations: `Cl\<newline>aude` in an unquoted heredoc is `Claude`, TASK-164). `git commit`
# with no message opens an editor; that path is covered by .githooks/commit-msg (scripts/setup-dev.sh installs
# it) and CI (pr-gates.yml).
# A command it can't parse is scanned as raw text; one it can't check at all (an internal error) is blocked.
# Exit 2 blocks the call and feeds stderr back to the agent.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
# The program goes to Python as an argument and the payload on stdin, never in an environment variable: past
# ARG_MAX (about 1 MB) exec fails with 126, which Claude Code lets through. Any exit but 0 blocks (TASK-156).
IFS= read -r -d '' PROG <<'PY' || true
import glob, os, re, sys
sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
from cmdparse import (ParseError, expand_known, expand_word, gh_subcommand, git_subcommand, join_continuations,
                      opt_values, read_payload, tokenize, walk)

PATTERN = re.compile(
    r"co-authored-by[:=][^\n]*(claude|anthropic)|generated with \[?claude|🤖 generated|noreply@anthropic\.com",
    re.IGNORECASE,
)
GIT_MSG = {"commit", "merge", "tag", "notes", "revert", "cherry-pick"}
GH_PR_WRITE = {"create", "edit", "comment", "review", "merge"}
GH_RELEASE_WRITE = {"create", "edit"}
MAX_BYTES = 1_000_000
# Readers whose file arguments are read and scanned whole (TASK-170: their first lines are no safer than the rest)
READERS = {"cat", "head", "tail", "sed"}
COUNT_OPTS = {"-n", "-c", "--lines", "--bytes"}  # head/tail: the next word is a count, not a file
SED_SCRIPT_OPTS = {"-e", "--expression", "-f", "--file"}  # sed: the next word is a script (or its file)
TEXT_COMMANDS = {"echo", "printf"}  # in a substitution, their words are the text, which is scanned as words

class Unresolved(Exception):
    """A file word this gate can't resolve: what it reads can't be scanned."""

def files_named(word, argv, d):
    """The paths `word` names, run from `d`, with its variables put in and a glob expanded; Unresolved when it
    can't tell (`$UNSET`, `$(…)`, a relative path after a `cd` it couldn't follow)."""
    value = expand_word(word, None if argv.dir_unknown else d, argv.shell_vars, argv.olddir, env_empty=argv.env_empty)
    if value is None or (argv.dir_unknown and not os.path.isabs(value)):
        raise Unresolved(word)
    path = os.path.join(d, value)
    if any(ch in value for ch in "*?["):
        return glob.glob(path) or [path]  # bash leaves a glob that matches nothing as written
    return [path]

def file_text(word, argv, d):
    if word == "-":
        return ""  # stdin: its heredoc body is part of the raw command, which is scanned
    out = []
    for p in files_named(word, argv, d):
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    out.append(fh.read(MAX_BYTES))
            except OSError:
                pass
    return "\n".join(out)

def reader_files(argv):
    """The words a cat, head, tail or sed in `argv` reads as files."""
    words, k, script = [], 1, argv[0] == "sed"
    while k < len(argv):
        a = argv[k]
        if argv[0] == "sed" and a.startswith("-") and not a.startswith("--") and len(a) > 2 and a[1] not in "ef":
            # sed accepts bundles: -nfFILE / -nf FILE / -neSCRIPT. The first e/f consumes the remaining
            # bundle (or the next word), so letters in its value are never interpreted as more options.
            for offset, flag in enumerate(a[1:], 2):
                if flag in "ef":
                    value = a[offset:]
                    if flag == "f":
                        if value:
                            words.append(value)
                        elif k + 1 < len(argv):
                            words.append(argv[k + 1])
                    script = False
                    k += 1 if value else 2
                    break
                if flag == "i":
                    # -i's optional backup suffix consumes the rest; it can't contain another option.
                    k += 1
                    break
                if flag not in "nErsuz":
                    raise Unresolved(a)  # don't guess how an unfamiliar bundle consumes file arguments
            else:
                k += 1  # a bundle of flags without a script, e.g. -nE
            continue
        if argv[0] in ("head", "tail") and a in COUNT_OPTS or argv[0] == "sed" and a in SED_SCRIPT_OPTS:
            if argv[0] == "sed" and a in ("-f", "--file") and k + 1 < len(argv):
                words.append(argv[k + 1])  # a script file can print attribution without reading an input file
            script = False if argv[0] == "sed" else script
            k += 2
            continue
        if argv[0] == "sed" and a.startswith(("-e", "--expression=", "-f", "--file=")):
            if a.startswith("-f") and len(a) > 2:
                words.append(a[2:])
            elif a.startswith("--file="):
                words.append(a.partition("=")[2])
            script = False
        if a.startswith("-") and a != "-":
            k += 1
            continue
        if script:
            script = False  # sed's first word is its script when no -e/-f gave one
        else:
            words.append(a)
        k += 1
    return words

def reads_unmodeled_file(argv, d):
    """Does `argv`, a program in a command substitution other than a reader this gate models, have an argument
    that names a file, or one it can't resolve? What it prints may be that file's text."""
    if argv[0] in READERS or argv[0] in TEXT_COMMANDS:
        return False
    for a in argv[1:]:
        if a.startswith("-"):
            continue
        try:
            if any(os.path.isfile(p) for p in files_named(a, argv, d)):
                return True
        except Unresolved:
            return True
    return False

def unresolved(word):
    print(f"Blocked: this commit, PR or release message reads a file this gate can't check for AI attribution "
          f"({word!r}: an unknown variable, a $(…), a path after a cd it couldn't follow, or a program other than "
          "cat/head/tail/sed run on a file in a command substitution). Name the message file plainly (-F <file>, "
          "--body-file <file>, or $(cat <file>)) and retry.", file=sys.stderr)
    sys.exit(2)

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
        # unbalanced quotes: bash won't run it, but don't let it look approved; read with its line continuations
        # joined (every one, when it can't be scanned: TASK-164), then its quotes and backslashes gone, which keeps
        # every raw match and joins `'Cl''aude'` (TASK-156 review)
        if PATTERN.search(re.sub(r"[\"'\\]", "", join_continuations(cmd))):
            blocked()
        try:  # a git command it can't classify (FailClosed) still has words: `'Cl''aude'` (TASK-156 review)
            if PATTERN.search(" ".join(tokenize(cmd))):
                blocked()
        except ParseError:
            pass
        sys.exit(0)

    commands = [(argv, d) for argv, d, _ in walked if argv]
    named, relevant = [], False  # (file word, argv, directory): message files, read once the command is relevant
    for argv, d in commands:
        g = git_subcommand(argv, d)
        if g and g[0] in GIT_MSG:
            relevant = True
            named += [(f, argv, g[2]) for f in opt_values(g[1], "-F", "--file")]
        h = gh_subcommand(argv)
        if h and h[0] == "pr" and h[1] in GH_PR_WRITE:
            relevant = True
            named += [(f, argv, d) for f in opt_values(h[2], "--body-file", "-F")]
        if h and h[0] == "release" and h[1] in GH_RELEASE_WRITE:
            relevant = True
            named += [(f, argv, d) for f in opt_values(h[2], "--notes-file", "-F")]
    if not relevant:
        sys.exit(0)
    # A message fed on stdin: `git commit -F - < msg.txt` (input redirect) or `cat msg.txt | git commit -F -`
    # (a heredoc or herestring is part of the raw text, which is scanned).
    named += [(target, argv, d) for argv, d, redirects in walked for op, target in redirects
              if "<" in op and not op.startswith("<<") and target]
    for argv, d in commands:
        # a cat, head, tail or sed anywhere, in a `$(…)` or backquotes too: the walk reads the bodies
        if argv[0] in READERS:
            named += [(a, argv, d) for a in reader_files(argv)]
        elif argv.in_subst and reads_unmodeled_file(argv, d):
            unresolved(" ".join(argv[:3]))
    try:
        texts = [file_text(word, argv, d) for word, argv, d in named]
    except Unresolved as exc:
        unresolved(exc.args[0])
    # every word as bash makes it, with the variables this gate can tell put in: a trailer split by quoting
    # (`'Co-Authored-By: Cl''aude'`), written with `$'…'` escapes or in a variable reads whole here (TASK-156)
    texts += [" ".join(expand_known(w, argv, d) for w in argv) for argv, d in commands]
    if PATTERN.search(join_continuations(cmd)) or any(PATTERN.search(t) for t in texts):
        blocked()
    sys.exit(0)

try:
    main()
except Exception as exc:  # a crash exits 1, which Claude Code lets through: block instead (TASK-067 final review gate)
    print(f"Blocked: block-ai-attribution.sh could not check this command ({type(exc).__name__}). Write it more "
          "plainly and retry.", file=sys.stderr)
    sys.exit(2)
PY
if [ -z "$PROG" ]; then  # the heredoc couldn't be read: an empty program would exit 0
  echo "Blocked: block-ai-attribution.sh could not load its check; refusing rather than letting the command through." >&2
  exit 2
fi
python3 -c "$PROG" "$HOOK_DIR"
rc=$?
if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
  echo "Blocked: block-ai-attribution.sh could not run its check (exit $rc); refusing rather than letting the command through." >&2
fi
[ "$rc" -eq 0 ] || exit 2
