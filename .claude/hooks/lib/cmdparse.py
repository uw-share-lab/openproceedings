"""Shared command-string parsing for the openproceedings PreToolUse(Bash) gates.

Parses a Bash tool command into simple commands (argv lists) the way bash reads it, for the cases that
matter to a gate:
  * `preprocess` makes ONE pass over the whole text: quote state carries across lines (a multi-line quoted
    message is one word), an unquoted `#` at the start of a word starts a comment, and an unquoted
    `<<DELIM` / `<<'DELIM'` / `<<-"DELIM"` starts a heredoc whose body is dropped unread (never `<<<`);
  * separators split with or without spaces: `;` `&&` `||` `|` `&` `(` `)`, newlines, `<(`/`>(`;
  * leading reserved words (`if`/`then`/`do`/`{`/`!` …), `VAR=val`, and wrappers (`env`, `sudo`, `nice`,
    `timeout`, `xargs`, `stdbuf`, `watch`, `exec`, `time`, `nohup`, `command`, `builtin`) are stripped, each
    wrapper with its own table of value-taking options; `env -S '…'` is split, `env -C`/`sudo -D` move dir;
  * command names compare by basename (`/usr/bin/git` is `git`);
  * redirections leave argv as (operator, target) pairs (`redirect_targets`);
  * `cd <dir>` is tracked and `bash -c "…"` / `eval "…"` are recursed into.
A command that cannot be parsed raises ParseError; every gate treats that as a reason to BLOCK a command
that looks like what it guards (fail closed), never to allow it.

Threat model (same as enforce-pr-workflow.sh): a guardrail against honest mistakes, not an adversarial
control. `$(...)`, variables and script files are opaque to a static parser.
"""

from __future__ import annotations

import functools
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Iterator

SEP_CHARS = set(";&|()\n")
PUNCT = ";&|()\n<>"
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
# Wrappers that run the rest of the line as a command, with the options of EACH that consume the next word
# (review round 2: one shared set made `sudo -n git push` skip `git`). A wrapper not listed takes none.
WRAPPER_VALUE_OPTS: dict[str, set[str]] = {
    "env": {"-u", "-C", "-S", "--unset", "--chdir", "--split-string"},
    "command": set(),
    "builtin": set(),
    "exec": {"-a"},
    "time": {"-f", "-o"},
    "nohup": set(),
    "nice": {"-n"},
    "sudo": {
        "-u",
        "-g",
        "-h",
        "-p",
        "-C",
        "-D",
        "-r",
        "-t",
        "-U",
        "-T",
        "--user",
        "--group",
        "--host",
        "--prompt",
        "--close-from",
        "--chdir",
        "--role",
        "--type",
        "--other-user",
        "--command-timeout",
    },
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "stdbuf": {"-i", "-o", "-e"},
    "xargs": {
        "-a",
        "-d",
        "-E",
        "-I",
        "-L",
        "-n",
        "-P",
        "-s",
        "--arg-file",
        "--delimiter",
        "--max-args",
        "--max-procs",
    },
    "watch": {"-n", "-d", "--interval"},
}
WRAPPERS = set(WRAPPER_VALUE_OPTS)
# Shell reserved words that can start a simple command without being the command (review 2026-09-25:
# `if …; then git push; fi`, `{ git push; }`, `! gh pr create` slipped past).
RESERVED = {
    "{",
    "}",
    "!",
    "if",
    "then",
    "elif",
    "else",
    "fi",
    "while",
    "until",
    "do",
    "done",
    "esac",
    "function",
}
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
GH_VALUE_OPTS = {"-R", "--repo"}
HEREDOC = re.compile(r"<<(?P<dash>-?)[ \t]*\\?(?P<q>['\"]?)(?P<delim>[A-Za-z_][\w-]*)(?P=q)")


ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class ParseError(ValueError):
    pass


def read_payload() -> tuple[str, str]:
    """Return (command, cwd) from the hook payload: $HOOK_INPUT if set (the bash wrapper captures
    stdin there, because a `python3 - <<'PY'` heredoc occupies Python's stdin), else stdin."""
    raw = os.environ.get("HOOK_INPUT")
    try:
        data = json.loads(raw) if raw is not None else json.load(sys.stdin)
    except Exception:
        return "", os.getcwd()
    cmd = (data.get("tool_input") or {}).get("command") or ""
    cwd = data.get("cwd") or os.getcwd()
    return cmd, cwd


def preprocess(cmd: str) -> str:
    """One pass over the whole command, the way bash reads it, returning the text to tokenize:
    - quote state is carried ACROSS lines, so a multi-line quoted message stays one string (review round 3);
    - an unquoted `#` at the start of a word starts a comment, dropped to the end of the line;
    - an unquoted `<<DELIM` / `<<-'DELIM'` / `<<"DELIM"` / `<<\\DELIM` starts a heredoc: its body lines are
      dropped unread, and it ends only at a line that is exactly DELIM (leading tabs allowed for `<<-`);
      `<<<` (herestring) and `<<` inside `$(( … ))` / `(( … ))` arithmetic are not heredocs (review round 4);
    - a backslash-newline outside single quotes and outside heredoc bodies joins the next line (bash line
      continuation) — done here, not before, so a heredoc body ending in `\\` can't swallow its delimiter;
    - a `<<` inside quotes is text (the usual `-m "$(cat <<'EOF' …)"` stays inside its quoted argument).
    """
    out_lines: list[str] = []
    quote: str | None = None
    pending: list[tuple[str, bool]] = []  # (delimiter, dash)
    arith = 0  # depth of $(( … )) / (( … )) arithmetic, where << is a shift
    inner = 0  # plain ( ) nesting inside the current arithmetic
    joining = False
    for line in cmd.split("\n"):
        if pending:
            delim, dash = pending[0]
            if (line.lstrip("\t") if dash else line) == delim:
                pending.pop(0)
            continue
        kept: list[str] = []
        i, n = 0, len(line)
        while i < n:
            c = line[i]
            if quote:
                kept.append(c)
                if c == "\\" and quote == '"' and i + 1 < n:
                    kept.append(line[i + 1])
                    i += 2
                    continue
                if c == quote:
                    quote = None
                i += 1
                continue
            if c in "'\"":
                quote = c
                kept.append(c)
                i += 1
                continue
            if c == "\\" and i + 1 < n:
                kept.append(line[i : i + 2])
                i += 2
                continue
            if c == "#" and (i == 0 or line[i - 1] in " \t;&|()") and not arith:
                break
            if line.startswith("$((", i) or (
                line.startswith("((", i) and (i == 0 or line[i - 1] in " \t;&|(")
            ):
                step = 3 if c == "$" else 2
                arith += 1
                kept.append(line[i : i + step])
                i += step
                continue
            if arith and c == "(":
                inner += 1
                kept.append(c)
                i += 1
                continue
            if arith and c == ")" and inner:
                inner -= 1
                kept.append(c)
                i += 1
                continue
            if arith and line.startswith("))", i):
                arith -= 1
                kept.append("))")
                i += 2
                continue
            if line.startswith("<<<", i):
                kept.append("<<<")
                i += 3
                continue
            if not arith and line.startswith("<<", i) and (m := HEREDOC.match(line, i)):
                if m.end() < n and line[m.end()] not in " \t;&|<>()":
                    raise ParseError(f"heredoc delimiter not understood near {line[i : m.end() + 3]!r}")
                pending.append((m.group("delim"), m.group("dash") == "-"))
                kept.append(m.group(0))
                i = m.end()
                continue
            kept.append(c)
            i += 1
        text = "".join(kept)
        # line continuation: a trailing unescaped backslash outside single quotes, not starting a heredoc
        trailing = len(text) - len(text.rstrip("\\"))
        continues = trailing % 2 == 1 and quote != "'" and not pending
        if continues:
            text = text[:-1]
        if joining and out_lines:
            out_lines[-1] += " " + text
        else:
            out_lines.append(text)
        joining = continues
    if arith or pending:
        # Unclosed arithmetic or a heredoc that never ends: the scan's model of this command has diverged
        # from bash's, so every later line may be misread. Raise; every gate treats that as BLOCK when the
        # command looks like what it guards (review round 5: `$((cmd) | …)`, `<<E"OF"`).
        raise ParseError(
            "unterminated arithmetic or heredoc" if arith else f"heredoc {pending[0][0]!r} never ends"
        )
    return "\n".join(out_lines)


def tokenize(cmd: str) -> list[str]:
    text = preprocess(cmd)
    lex = shlex.shlex(text, posix=True, punctuation_chars=PUNCT)
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        return list(lex)
    except ValueError as exc:
        raise ParseError(str(exc)) from exc


def is_separator(tok: str) -> bool:
    """`;` `&&` `||` `|` `&` `(` `)` newline — and process substitution `<(` / `>(`, whose contents are a
    command in their own right (`diff <(git push …)`)."""
    if not tok:
        return False
    if set(tok) <= SEP_CHARS:
        return True
    return "(" in tok and set(tok) <= SEP_CHARS | {"<", ">"}


def _resolve(candidate: str, base: str) -> str:
    return candidate if os.path.isabs(candidate) else os.path.normpath(os.path.join(base, candidate))


def base(word: str) -> str:
    """Command name without its directory, so `/usr/bin/git` is `git`."""
    return os.path.basename(word) if "/" in word else word


def _strip_prefixes(argv: list[str], state: dict | None = None) -> list[str]:
    """Drop leading reserved words, `VAR=val` and wrappers (with their option values). `env -S 'cmd'`
    splits its string into the command; `env -C dir` / `sudo -D dir` change the directory in `state`."""
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in RESERVED or ASSIGNMENT.match(a):
            i += 1
        elif base(a) in WRAPPERS:
            name = base(a)
            i += 1
            while i < len(argv) and argv[i].startswith("-"):  # env -i, nice -n 5, sudo -u x, timeout -s KILL
                opt, eq, attached = argv[i].partition("=")
                takes_value = opt in WRAPPER_VALUE_OPTS[name]
                value = attached if eq else (argv[i + 1] if takes_value and i + 1 < len(argv) else None)
                if name == "env" and opt in ("-S", "--split-string") and value is not None:
                    return _strip_prefixes([*tokenize(value), *argv[i + (1 if eq else 2) :]], state)
                if (
                    state is not None
                    and value is not None
                    and (
                        (name == "env" and opt in ("-C", "--chdir"))
                        or (name == "sudo" and opt in ("-D", "--chdir"))
                    )
                ):
                    state["dir"] = _resolve(value, state["dir"])
                i += 1 if (eq or not takes_value) else 2
            if name == "timeout" and i < len(argv):  # the duration
                i += 1
        else:
            break
    rest = argv[i:]
    if rest:
        rest = [base(rest[0]), *rest[1:]]
    return rest


def is_redirect(tok: str) -> bool:
    return bool(tok) and ("<" in tok or ">" in tok) and set(tok) <= set("<>&|")


def split_redirects(argv: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Separate redirections from arguments: returns (args, [(operator, target), ...]).

    `2>&1` tokenizes as '2', '>&', '1' — the fd digit before an operator and the target after it are
    dropped from args, so `git push origin feat 2>&1` has refspecs ['feat'] (review 2026-09-25)."""
    args: list[str] = []
    redirects: list[tuple[str, str]] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if is_redirect(tok):
            if args and args[-1].isdigit():
                args.pop()
            target = argv[i + 1] if i + 1 < len(argv) else ""
            redirects.append((tok, target))
            i += 2
            continue
        args.append(tok)
        i += 1
    return args, redirects


def simple_commands(cmd: str, cwd: str) -> Iterator[tuple[list[str], str]]:
    """Yield (argv, directory) for every simple command in `cmd`, with redirections removed from argv.
    Raises ParseError on bad quoting. Use `redirect_targets` to see where output is written."""
    state = {"dir": cwd}
    for argv, d, _ in _walk(tokenize(cmd), state):
        yield argv, d


def redirect_targets(cmd: str, cwd: str) -> Iterator[tuple[str, str, str]]:
    """Yield (operator, target, directory) for every redirection in `cmd`."""
    state = {"dir": cwd}
    for _, d, redirects in _walk(tokenize(cmd), state):
        for op, target in redirects:
            yield op, target, d


def _walk(tokens: list[str], state: dict) -> Iterator[tuple[list[str], str, list[tuple[str, str]]]]:
    i = 0
    while i < len(tokens):
        j = i
        while j < len(tokens) and not is_separator(tokens[j]):
            j += 1
        raw, i = tokens[i:j], j + 1
        args, redirects = split_redirects(raw)
        argv = _strip_prefixes(args, state)
        if not argv:
            if redirects:
                yield [], state["dir"], redirects
            continue
        head = argv[0]
        if head == "cd" and len(argv) > 1 and not argv[1].startswith("-"):
            state["dir"] = _resolve(argv[1], state["dir"])
            continue
        if head in SHELLS:
            for k, a in enumerate(argv[1:], start=1):
                if a.startswith("-") and not a.startswith("--") and "c" in a and k + 1 < len(argv):
                    yield from _walk(tokenize(argv[k + 1]), state)
                    break
            continue
        if head == "eval":
            yield from _walk(tokenize(" ".join(argv[1:])), state)
            continue
        yield argv, state["dir"], redirects


def git_subcommand(argv: list[str], directory: str) -> tuple[str, list[str], str] | None:
    """For a `git ...` argv return (subcommand, args, effective_dir), honouring chained -C; else None."""
    if not argv or argv[0] != "git":
        return None
    eff = directory
    j = 1
    while j < len(argv) and argv[j].startswith("-"):
        if argv[j] in GIT_VALUE_OPTS:
            if argv[j] == "-C" and j + 1 < len(argv):
                eff = _resolve(argv[j + 1], eff)
            j += 2
        else:
            j += 1
    if j >= len(argv):
        return None
    return argv[j], argv[j + 1 :], eff


def gh_subcommand(argv: list[str]) -> tuple[str, str, list[str]] | None:
    """For `gh [-R repo] <group> <verb> ...` return (group, verb, args); `pr new` is `pr create`."""
    if not argv or argv[0] != "gh":
        return None
    rest = argv[1:]
    while rest and rest[0].startswith("-"):
        rest = rest[2:] if rest[0] in GH_VALUE_OPTS else rest[1:]
    if len(rest) < 2:
        return None
    group, verb = rest[0], rest[1]
    if group == "pr" and verb == "new":
        verb = "create"
    return group, verb, rest[2:]


def _matches(arg: str, name: str) -> str | None:
    """Value carried by `arg` itself for option `name` (`--opt=v`, or attached short `-Xv`), else None."""
    if name.startswith("--") and arg.startswith(name + "="):
        return arg.split("=", 1)[1]
    if not name.startswith("--") and len(name) == 2 and arg.startswith(name) and len(arg) > 2:
        return arg[2:]
    return None


def opt_values(args: list[str], *names: str) -> list[str]:
    """All values of the given options: `--opt v`, `--opt=v`, `-o v`, `-ov`."""
    out = []
    for k, a in enumerate(args):
        for n in names:
            if a == n and k + 1 < len(args):
                out.append(args[k + 1])
            elif (v := _matches(a, n)) is not None:
                out.append(v)
    return out


def opt_value(args: list[str], *names: str) -> str | None:
    vals = opt_values(args, *names)
    return vals[0] if vals else None


def git(directory: str, *args: str) -> str:
    """Run git in `directory`; return stripped stdout, or '' on any failure."""
    try:
        r = subprocess.run(["git", "-C", directory, *args], capture_output=True, text=True, timeout=10)
    except Exception:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


@functools.lru_cache(maxsize=256)
def repo_root(directory: str) -> str:
    """Top of the git worktree containing `directory` — walking up to the nearest existing ancestor
    first, because a Write may target a directory that doesn't exist yet (data/indexes/<new>/)."""
    d = os.path.abspath(directory)
    while not os.path.isdir(d) and os.path.dirname(d) != d:
        d = os.path.dirname(d)
    return git(d, "rev-parse", "--show-toplevel") or d
