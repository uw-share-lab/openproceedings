#!/usr/bin/env bash
# PreToolUse(Bash) gate: no AI authorship in commits or PRs.
#
# Project decision (2026-09-25): `.claude/` is committed, but commits and PRs are authored by people.
# When the command contains a message-writing git command (commit, merge, tag, notes, revert,
# cherry-pick), a PR- or issue-writing gh command (pr create/new/edit/comment/review/merge/close/reopen, issue
# create/new/edit/comment/close/reopen), a release-writing one (release create/edit: its notes are the release
# notes, spec 08 §Release) or a `gh api` call that sends text (--input; a -f/-F/--field/--raw-field unless the
# method is GET, where gh puts them in the query string; a method other than GET; a bundled `-iF` too: the
# routine's comments and PR bodies, TASK-243), the WHOLE raw
# command text is scanned — not individual flags — so -m, -am, -qm, --message=, --trailer, heredoc
# bodies (`-F - <<EOF`, `-m "$(cat <<'EOF' …)"`), --body and --notes are all covered — plus the whole contents
# of every file the call reads into a message: -F/--file/--body-file/--notes-file, `gh api` -F key=@file and
# --input, any `< file`, and any file a reader reads (`cat`, `head`, `tail`, `sed`: the WHOLE file is scanned, not
# the lines they print; `$(< file)`, backquotes too; sed's -f/--file script files as well). One it can't read whole
# (missing, not a regular file, unreadable, over 1 MB; /dev/null is empty) is refused: the call may write it
# before it runs (TASK-243). A file the call writes before sending it (as a `>`/`>>` target, a `tee` argument or a
# `cp`/`mv`/`install`/`ln` destination) is judged by what writes it: text in the command itself (`cat > f <<'EOF'`,
# `printf '…' > f`, `tee f <<< '…'`, no unknown variable) is scanned as that text, and the file is read too when it
# exists (the write may append, not run, or run alongside); anything else (`cp`, `jq … > f`, `… | tee f`, a group's
# `{ …; } > f`) or a write target it can't resolve is refused. So is a writer file option with no value after it (`--body-file <(…)`),
# and a command it can't parse that names gh or git and a message-file option or a reader (the file can't be read), or
# that may be a writer at all: git and a message verb, gh pr/issue/release and a write verb, or gh api (TASK-266),
# read as written, without quotes or `$'`, and as tokenize's words, names case-blind (`GIT` runs git on macOS). When a
# gh writer reads its text from a pipe (`--body-file -`, `--input -`, `-F body=@-`, with no `<`, `<<` or `<<<` of its
# own), any other program in the call but gh run on a file is refused, as in a `$(…)`. gh's -R/--repo is skipped
# between group and verb too (`gh pr --repo o/r comment`). Known limitations (TASK-243; CI's attribution check on
# commits and PR text is the backstop): inline interpreter code that opens a file (`python3 -c 'open(…)' | gh api
# … --input -`), a `git tag`/`git notes` message fed from a pipe, a program's own output-file option (`sort -o`,
# `curl -o`, `dd of=`, `sed -i`), and other shell obfuscation. And every word as bash
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
# A command it can't parse is scanned as raw text, and refused if it may be a writer; one it can't check at all (an
# internal error) is blocked.
# Exit 2 blocks the call and feeds stderr back to the agent.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
# The program goes to Python as an argument and the payload on stdin, never in an environment variable: past
# ARG_MAX (about 1 MB) exec fails with 126, which Claude Code lets through. Any exit but 0 blocks (TASK-156).
IFS= read -r -d '' PROG <<'PY' || true
import glob, os, re, sys
sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
from cmdparse import (ParseError, expand_known, expand_word, gh_subcommand, git_subcommand, join_continuations,
                      heredoc_quoting, opt_values, read_payload, tokenize, walk)

PATTERN = re.compile(
    r"co-authored-by[:=].*(claude|anthropic)|generated[ -](with|by):? +[`*_[]*((an?|the) +)?((github|microsoft|google) +)?(claude|(anthropic|openai|(chat)?gpt(-?[0-9][0-9a-z.]*)?|copilot|gemini|bard|codex|llm|ai)([^a-zA-Z0-9]|$))|🤖 generated|noreply@anthropic\.com",
    re.IGNORECASE,
)
GIT_MSG = {"commit", "merge", "tag", "notes", "revert", "cherry-pick"}
GH_PR_WRITE = {"create", "edit", "comment", "review", "merge", "close", "reopen"}
GH_ISSUE_WRITE = {"create", "edit", "comment", "close", "reopen"}
GH_RELEASE_WRITE = {"create", "edit"}
GH_API_FILE_FIELDS = ("-F", "--field")  # `-F key=@file` sends the file's contents (`@-`: stdin)
GH_API_TEXT_FIELDS = ("-f", "--raw-field")  # sent as written: the text is in the command, which is scanned
# options whose value is a file a writer sends: one written last, with no value, is refused
WRITER_FILE_OPTS = {"-F", "--file", "--body-file", "--notes-file", "--input", "--field"}
MAX_BYTES = 1_000_000
# Readers whose file arguments are read and scanned whole (TASK-170: their first lines are no safer than the rest)
READERS = {"cat", "head", "tail", "sed"}
COUNT_OPTS = {"-n", "-c", "--lines", "--bytes"}  # head/tail: the next word is a count, not a file
SED_SCRIPT_OPTS = {"-e", "--expression", "-f", "--file"}  # sed: the next word is a script (or its file)
TEXT_COMMANDS = {"echo", "printf"}  # in a substitution, their words are the text, which is scanned as words

class Unresolved(Exception):
    """A file word this gate can't resolve: what it reads can't be scanned."""

class Unreadable(Exception):
    """A message file this gate can't read whole (missing, not a regular file, unreadable or too large): what
    it sends can't be scanned (TASK-243)."""

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
    """The whole text of a file the command reads into a message: one a git or gh writer sends (`-F`,
    `--body-file`, `--notes-file`, `gh api` `-F key=@file` and `--input`), one fed on stdin (`< file`), or one a
    cat, head, tail or sed reads. One this gate can't read whole (missing, not a regular file, unreadable, over
    MAX_BYTES) is refused (Unreadable): the command may write it before it runs (`cp draft.md body.md && gh pr
    comment 1 --body-file body.md`, or `… --body "$(cat body.md)"`), and a missing file would let that text
    through unscanned (TASK-243). `-` is stdin, whose heredoc is part of the raw command; /dev/null is empty. In
    the reading with HOME/TMPDIR/USER as '' a path that isn't a file is skipped: `"$TMPDIR/msg"` is then `/msg`,
    and the first reading has already checked the real one."""
    if word == "-":
        return ""
    out = []
    for p in files_named(word, argv, d):
        if os.path.realpath(p) == os.devnull:
            continue
        if not os.path.isfile(p):
            if argv.env_empty:
                continue
            raise Unreadable(word)
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                text = fh.read(MAX_BYTES + 1)
        except OSError:
            raise Unreadable(word) from None
        if len(text) > MAX_BYTES:
            raise Unreadable(word)
        out.append(text)
    return "\n".join(out)

def inline_stdin(op, target, argv, d):
    """Is this redirect a stdin whose text is all in the command: a herestring with no unknown variable, or a
    heredoc whose delimiter is quoted (`<<'EOF'`) or whose call has no `$` or backquote to expand?"""
    if op == "<<<":
        return "$" not in expand_known(target, argv, d) and "`" not in target
    if op.startswith("<<"):
        # literal when the call has nothing to expand, or when every heredoc in it has a quoted delimiter (which one
        # is this redirect's isn't told here, so all must be)
        quoting = heredoc_quoting(CMD[0])  # None: the text can't be scanned, so nothing counts as literal
        # an empty list with a `<<` seen (`<<1`, `<<$X`: delimiters the scan doesn't read) is not literal either
        return quoting is not None and ((bool(quoting) and all(quoting)) or not any(ch in CMD[0] for ch in "$`"))
    return False

def api_args(args):
    """`gh api`'s arguments with a bundled `-i` (its one short flag that takes no value) split off: `-iF x` is
    `-i -F x` to gh, so `-F` is seen."""
    out = []
    for a in args:
        while a.startswith("-i") and len(a) > 2 and not a.startswith("--"):
            out.append("-i")
            a = "-" + a[2:]
        out.append(a)
    return out

def api_files(args):
    """The files a `gh api` call sends: each `-F`/`--field` `key=@file` value, and `--input`'s file."""
    files = []
    for v in opt_values(args, *GH_API_FILE_FIELDS):
        _, eq, value = v.partition("=")
        if eq and value.startswith("@"):
            files.append(value[1:])
    return files + opt_values(args, "--input")

def api_writes(args):
    """Does a `gh api` call send text: an --input body, a field (unless the method is GET, where gh puts the fields
    in the query string: a search for a footer is a read), or a method other than GET?"""
    methods = [m.upper() for m in opt_values(args, "-X", "--method")]
    if opt_values(args, "--input"):
        return True
    if methods and all(m == "GET" for m in methods):
        return False
    return bool(methods) or bool(opt_values(args, *GH_API_FILE_FIELDS, *GH_API_TEXT_FIELDS))

def reader_files(argv):
    """The words a cat, head, tail or sed in `argv` reads as files."""
    words, k, script = [], 1, argv[0] == "sed"
    end_options = False
    while k < len(argv):
        a = argv[k]
        if a == "--" and not end_options:
            end_options = True
            k += 1
            continue
        if end_options:
            if script:
                script = False  # sed still needs its implicit expression if no -e/-f supplied one
            else:
                words.append(a)  # even -message or --file=message is now a literal input filename
            k += 1
            continue
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
          "cat/head/tail/sed run on a file in a command substitution, or in a call whose gh writer reads stdin). Name the "
          "message file plainly (-F <file>, --body-file <file>, -F body=@<file>, or $(cat <file>)) and retry.", file=sys.stderr)
    sys.exit(2)

def unreadable(word):
    if word == "":
        word = "an option value this gate couldn't read (a <(…)?)"
    print(f"Blocked: this commit, PR, issue or release text is sent from a file this gate can't read whole "
          f"({word!r}: missing, not a regular file, unreadable, or over {MAX_BYTES} bytes), so it can't be checked "
          "for AI attribution. Write the file in an earlier call, then send it.", file=sys.stderr)
    sys.exit(2)

def named(names, text):
    """Is one of `names` a word of `text`, in any case (`GIT` runs git on a case-blind filesystem)?"""
    return re.search(r"\b(" + "|".join(map(re.escape, sorted(names))) + r")\b", text, re.IGNORECASE) is not None

def may_write(text):
    """Text the walk couldn't parse, so couldn't split into commands: does it name, anywhere, a writer main() checks?
    git with a message verb, gh pr or issue with a write verb (`new` too), gh release create/edit, or any gh api (its
    method and fields can't be read, so a read isn't told from a write) (TASK-266)."""
    if named({"git"}, text) and named(GIT_MSG, text):
        return True
    if not named({"gh"}, text):
        return False
    return (named({"api"}, text) or named({"pr", "issue"}, text) and named(GH_PR_WRITE | GH_ISSUE_WRITE | {"new"}, text)
            or named({"release"}, text) and named(GH_RELEASE_WRITE, text))

def unparsed_writer():
    print("Blocked: this command can't be parsed, and it may write a commit, tag, PR, issue or release, or send a gh api "
          "write, whose text and files can't then be checked for AI attribution. Fix its quoting, or write it more "
          "plainly (one command per call, options named outright), and retry.", file=sys.stderr)
    sys.exit(2)

def blocked():
    print("Blocked: commits, PRs and releases in openproceedings carry no AI authorship.", file=sys.stderr)
    print("Remove the 'Co-Authored-By: Claude …' trailer / the 'Generated with' or 'Generated by' footer naming an AI "
          "tool and retry.", file=sys.stderr)
    print("(.claude/ tooling is committed; authorship is not. See CLAUDE.md → 'Authorship'.)", file=sys.stderr)
    sys.exit(2)

CMD = [""]  # the raw command, for inline_stdin

def main():
    cmd, cwd = read_payload()
    CMD[0] = cmd
    if not cmd:  # no raw-text prefilter: `gi\<newline>t push` only becomes `git` after parsing (review round 6)
        sys.exit(0)
    try:
        walked = list(walk(cmd, cwd))
        first = len(walked)  # the walks are compared each on its own: the second starts here
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
        # the file scan (TASK-243) can't run on a command it can't parse: one that may send a message file is
        # refused before this early exit, rather than let that file through unread
        raw = join_continuations(cmd)
        # read three ways: as written, with its quotes, backslashes and the `$` of `$'…'`/`$"…"` gone (`g''it`,
        # `g$''it`), and as the words tokenize makes when it can (`$'\x67'it` is `git`) (TASK-266 review)
        readings = [raw, re.sub(r"\$?[\"'\\]", "", raw)]
        try:
            readings.append(" ".join(tokenize(cmd)))
        except ParseError:
            pass
        for text in readings:
            # `GIT` runs git on a case-blind filesystem (macOS): the names are read case-blind (TASK-266 review)
            if re.search(r"\b(gh|git)\b", text, re.IGNORECASE) and re.search(r"--body-file|--notes-file|--input|--file|--field|=@|(^|\s)-[A-Za-z]*F|\b(cat|head|tail|sed)\b|\$\(\s*<", text):
                unreadable("a message file in a command this gate can't parse")
        # nor can a writer's options be read (a file option held in a variable, say): one that may be a gh or git
        # writer is refused, with or without a file option the text shows (TASK-266)
        if any(may_write(text) for text in readings[1:]):
            unparsed_writer()
        sys.exit(0)

    # command names come case-folded from the walk (`GIT commit`, `Gh pr create`: cmdparse.fold, TASK-269 review)
    commands = [(argv, d) for argv, d, _ in walked if argv]
    # (file word, argv, directory): files the command reads into a message, read whole once it is relevant (`file_text`)
    sent, writers = [], set()
    for argv, d in commands:
        g = git_subcommand(argv, d)
        if g and g[0] in GIT_MSG:
            writers.add(id(argv))
            sent += [(f, argv, g[2]) for f in opt_values(g[1], "-F", "--file")]
        h = gh_subcommand(argv, between=True)
        if h and (h[0] == "pr" and h[1] in GH_PR_WRITE or h[0] == "issue" and h[1] in GH_ISSUE_WRITE):
            writers.add(id(argv))
            sent += [(f, argv, d) for f in opt_values(h[2], "--body-file", "-F")]
        if h and h[0] == "release" and h[1] in GH_RELEASE_WRITE:
            writers.add(id(argv))
            sent += [(f, argv, d) for f in opt_values(h[2], "--notes-file", "-F")]
        if h and h[0] == "api" and api_writes(api_args([h[1], *h[2]])):
            # the routine's comments and PR bodies: `gh api … -F body=@file` (TASK-243)
            writers.add(id(argv))
            sent += [(f, argv, d) for f in api_files(api_args([h[1], *h[2]]))]
    if not writers:
        sys.exit(0)
    # A writer file option with no value after it (`--body-file <(awk 1 msg.md)`: the walk drops the `<(…)`) sends
    # something this gate can't see: refused (TASK-243).
    for argv, d in commands:
        if id(argv) in writers and argv[-1] in WRITER_FILE_OPTS:
            unreadable(argv[-1] + " with no value")
    # an input redirect, but not a descriptor copy (`0<&3`)
    def reads_in(op, target):
        return "<" in op and target and not (op.endswith("&") and (target.isdigit() or target == "-"))
    redirs = {id(argv): r for argv, _, r in walked}
    # a gh writer that reads its text from a pipe (`--body-file -`, `-F -`, `--input -`, `-F body=@-`, with no `<`,
    # `<<` or `<<<` of its own, which are scanned): another program in the call may be what feeds it (`jq -Rs
    # '{body: .}' msg.md | gh api … --input -`, `git diff --no-index /dev/null msg.md | gh …`, TASK-243)
    stdin_writer = any(word == "-" and argv[0] == "gh" and not any(reads_in(op, t or "x") for op, t in redirs.get(id(argv), []))
                       for word, argv, _ in sent)
    # A message fed on stdin: `git commit -F - < msg.txt` (input redirect) or `cat msg.txt | git commit -F -`
    # (a heredoc or herestring is part of the raw text, which is scanned).
    for argv, d, redirects in walked:
        for op, target in redirects:
            if reads_in(op, target) and not op.startswith("<<"):
                sent.append((target, argv, d))
    for argv, d in commands:
        # a cat, head, tail or sed anywhere, in a `$(…)` or backquotes too: the walk reads the bodies
        if argv[0] in READERS:
            sent += [(a, argv, d) for a in reader_files(argv)]
        elif (argv.in_subst or stdin_writer and argv[0] != "gh") and reads_unmodeled_file(argv, d):
            unresolved(" ".join(argv[:3]))
    # A file the call writes before it sends it is read here as it was before the call. When what writes it is
    # text in the command itself (`cat > body.md <<'EOF' … EOF`, `printf '…' > body.md`, `tee body.md <<< '…'`),
    # that text is scanned with the raw command, and the file is read too when it exists.
    # When it is anything else (`cp draft.md body.md`, `jq … > body.md`, `… | tee body.md`), or its target can't be
    # resolved, the call is refused: what is sent can't be known here (TASK-243).
    # path -> [(position in the call, written by inline text)]; only a write before the sender counts
    writes = {}
    # (walk, index): the first walk and the HOME-empty one are each in order on their own
    position = {id(argv): ((0, k) if k < first else (1, k - first)) for k, (argv, _, _) in enumerate(walked)}
    last_sender = {}
    for word, argv, _ in sent:
        if word != "-" and id(argv) in position:
            w, i = position[id(argv)]
            last_sender[w] = max(last_sender.get(w, -1), i)
    def track():
        for argv, d, redirects in walked:
            k = position[id(argv)]
            if k[1] >= last_sender.get(k[0], -1):  # a write after the walk's last sender can't change what is sent
                continue
            # a group, subshell or loop (`{ jq … f; } > body.md`) has no argv of its own: its writes aren't inline text
            head = argv[0] if argv else ":group"
            words = [w for w in argv[1:] if not w.startswith("-")]
            targets = [t for op, t in redirects if ">" in op and t and not (op.endswith("&") and (t.isdigit() or t == "-"))]
            if head == "tee":
                targets += words
            elif head in ("cp", "mv", "install", "ln") and len(words) >= 2:
                targets.append(words[-1])
            if not targets:
                continue
            if head in TEXT_COMMANDS:
                known = all("$" not in expand_known(w, argv, d) and "`" not in w for w in argv[1:])
            elif head in ("cat", "tee") and (head == "tee" or not reader_files(argv)):
                known = any(inline_stdin(op, t, argv, d) for op, t in redirects)
            else:
                known = False
            for t in targets:
                for path in files_named(t, argv, d):  # Unresolved: refused below
                    real = os.path.realpath(path)
                    if os.path.isdir(path):
                        for w in words[:-1]:
                            writes.setdefault(os.path.realpath(os.path.join(path, os.path.basename(w))), []).append((k, False))
                    is_inline = known and head not in ("cp", "mv", "install", "ln")
                    writes.setdefault(real, []).append((k, is_inline))
    def sent_text(word, argv, d):
        if word == "-":
            return ""
        out = []
        for x in (os.path.realpath(y) for y in files_named(word, argv, d)):
            before = [w for w in writes.get(x, []) if w[0][0] == position[id(argv)][0] and w[0][1] < position[id(argv)][1]] if x != os.devnull else []
            if any(not is_inline for _, is_inline in before):
                unreadable(word + ", written earlier in the same call by something this gate can't read")
            if before:  # all inline text, scanned with the command; the file is read too when it exists, since the write
                # may append, may not run (`false && printf … > f`, an `if`) or may run alongside (`&`)
                if os.path.isfile(x):
                    out.append(file_text(x, argv, d))
                continue
            out.append(file_text(x, argv, d))
        return "\n".join(out)
    try:
        track()  # with no file sent there is no sender, so it records nothing
        texts = [sent_text(word, argv, d) for word, argv, d in sent]
    except Unresolved as exc:
        unresolved(exc.args[0])
    except Unreadable as exc:
        unreadable(exc.args[0])
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
