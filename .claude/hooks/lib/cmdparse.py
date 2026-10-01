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
    the argv comes back as an `Argv` that records the `VAR=val` words and whether xargs runs it;
  * command names compare by basename (`/usr/bin/git` is `git`);
  * redirections leave argv as (operator, target) pairs (`redirect_targets`);
  * `cd <dir>` is tracked and `bash -c "…"` / `eval "…"` are recursed into;
  * a git alias (`-c alias.<name>=…` or the repo's config; `!shell` ones too) becomes what git runs for it;
  * a `git-<sub>` program (`$(git --exec-path)/git-push`) is `git <sub>`;
  * an abbreviated long option (`--forc`, `--al`) becomes the option git reads it as (`normalize_git_options`);
  * `export`/`declare -x` assignments reach every later command's `Argv.assigns` (`note_exports`).
A command that cannot be parsed raises ParseError; every gate treats that as a reason to BLOCK a command
that looks like what it guards (fail closed), never to allow it. A git command that parses but can't be
classified (an ambiguous abbreviated option; config git reads from a source this parser can't, deciding an
alias) raises FailClosed, a ParseError every gate refuses whatever the text looks like.

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
GIT_VALUE_OPTS = {"-C", "-c", "--config-env", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
# git's builtins: git never lets an alias shadow one, so only another name is looked up as an alias (a name
# missing here costs one `git config` call, never a wrong answer).
GIT_BUILTINS = frozenset(
    [
        "add",
        "am",
        "apply",
        "bisect",
        "blame",
        "branch",
        "cat-file",
        "check-ignore",
        "check-ref-format",
        "checkout",
        "cherry",
        "cherry-pick",
        "clean",
        "clone",
        "commit",
        "commit-tree",
        "config",
        "describe",
        "diff",
        "fetch",
        "for-each-ref",
        "format-patch",
        "fsck",
        "gc",
        "grep",
        "hash-object",
        "help",
        "init",
        "log",
        "ls-files",
        "ls-remote",
        "ls-tree",
        "merge",
        "merge-base",
        "mv",
        "notes",
        "pull",
        "push",
        "range-diff",
        "rebase",
        "reflog",
        "remote",
        "reset",
        "restore",
        "rev-list",
        "rev-parse",
        "revert",
        "rm",
        "shortlog",
        "show",
        "show-ref",
        "sparse-checkout",
        "stage",
        "stash",
        "status",
        "switch",
        "symbolic-ref",
        "tag",
        "update-index",
        "update-ref",
        "var",
        "version",
        "worktree",
        "write-tree",
    ]
)
ALIAS_DEPTH = 8  # git itself refuses a non-shell alias loop; this bounds shell aliases calling git aliases
GH_VALUE_OPTS = {"-R", "--repo"}
# Every long option (negations included) of the git subcommands a gate reads options of, as `git <sub>
# --git-completion-helper-all` lists them (git 2.42). git takes any unique prefix of one (`--forc` is
# --force: TASK-067 review gate), so `normalize_git_options` writes each out in full before a gate looks.
GIT_LONG_OPTS: dict[str, frozenset[str]] = {
    k: frozenset(v.split())
    for k, v in {
        "add": (
            "dry-run verbose interactive patch edit force update renormalize intent-to-add all "
            "ignore-removal refresh ignore-errors ignore-missing sparse chmod warn-embedded-repo "
            "pathspec-from-file pathspec-file-nul no-dry-run no-verbose no-interactive no-patch no-edit "
            "no-force no-update no-renormalize no-intent-to-add no-all no-ignore-removal no-refresh "
            "no-ignore-errors no-ignore-missing no-sparse no-chmod no-warn-embedded-repo "
            "no-pathspec-from-file no-pathspec-file-nul"
        ),
        "branch": (
            "verbose quiet track set-upstream set-upstream-to unset-upstream color remotes contains "
            "no-contains with without abbrev all delete move omit-empty copy list show-current "
            "create-reflog edit-description force merged no-merged column sort points-at ignore-case "
            "recurse-submodules format no-verbose no-quiet no-track no-set-upstream no-set-upstream-to "
            "no-unset-upstream no-color no-abbrev no-delete no-move no-omit-empty no-copy no-list "
            "no-show-current no-create-reflog no-edit-description no-force no-column no-sort no-points-at "
            "no-ignore-case no-recurse-submodules no-format"
        ),
        "checkout": (
            "guess overlay quiet recurse-submodules progress merge conflict detach track force orphan "
            "overwrite-ignore ignore-other-worktrees ours theirs patch ignore-skip-worktree-bits "
            "pathspec-from-file pathspec-file-nul no-guess no-overlay no-quiet no-recurse-submodules "
            "no-progress no-merge no-conflict no-detach no-track no-force no-orphan no-overwrite-ignore "
            "no-ignore-other-worktrees no-patch no-ignore-skip-worktree-bits no-pathspec-from-file "
            "no-pathspec-file-nul"
        ),
        "clean": "quiet dry-run force interactive exclude no-quiet no-dry-run no-force no-interactive",
        "commit": (
            "quiet verbose file author date message reedit-message reuse-message fixup squash "
            "reset-author trailer signoff template edit cleanup status gpg-sign all include interactive "
            "patch only no-verify dry-run short branch ahead-behind porcelain long null amend "
            "no-post-rewrite untracked-files pathspec-from-file pathspec-file-nul allow-empty "
            "allow-empty-message verify post-rewrite no-quiet no-verbose no-file no-author no-date "
            "no-message no-reedit-message no-reuse-message no-fixup no-squash no-reset-author no-signoff "
            "no-template no-edit no-cleanup no-status no-gpg-sign no-all no-include no-interactive "
            "no-patch no-only no-dry-run no-short no-branch no-ahead-behind no-porcelain no-long no-null "
            "no-amend no-untracked-files no-pathspec-from-file no-pathspec-file-nul no-allow-empty "
            "no-allow-empty-message"
        ),
        "fetch": (
            "verbose quiet all set-upstream append atomic upload-pack force multiple tags jobs prefetch "
            "prune prune-tags recurse-submodules dry-run porcelain write-fetch-head keep update-head-ok "
            "progress depth shallow-since shallow-exclude deepen unshallow refetch submodule-prefix "
            "recurse-submodules-default update-shallow refmap server-option ipv4 ipv6 negotiation-tip "
            "negotiate-only filter auto-maintenance auto-gc show-forced-updates write-commit-graph stdin "
            "no-verbose no-quiet no-all no-set-upstream no-append no-atomic no-upload-pack no-force "
            "no-multiple no-tags no-jobs no-prefetch no-prune no-prune-tags no-recurse-submodules "
            "no-dry-run no-porcelain no-write-fetch-head no-keep no-update-head-ok no-progress no-depth "
            "no-shallow-since no-shallow-exclude no-deepen no-submodule-prefix "
            "no-recurse-submodules-default no-update-shallow no-server-option no-negotiation-tip "
            "no-negotiate-only no-filter no-auto-maintenance no-auto-gc no-show-forced-updates "
            "no-write-commit-graph no-stdin"
        ),
        "merge": (
            "stat summary log squash commit edit cleanup ff ff-only rerere-autoupdate verify-signatures "
            "strategy strategy-option message file into-name verbose quiet abort quit continue "
            "allow-unrelated-histories progress gpg-sign autostash overwrite-ignore signoff no-verify "
            "verify no-stat no-summary no-log no-squash no-commit no-edit no-cleanup no-ff "
            "no-rerere-autoupdate no-verify-signatures no-strategy no-strategy-option no-message "
            "no-into-name no-verbose no-quiet no-abort no-quit no-continue no-allow-unrelated-histories "
            "no-progress no-gpg-sign no-autostash no-overwrite-ignore no-signoff"
        ),
        "pull": (
            "verbose quiet progress recurse-submodules rebase stat summary log signoff squash commit edit "
            "cleanup ff ff-only verify verify-signatures autostash strategy strategy-option gpg-sign "
            "allow-unrelated-histories all append upload-pack force tags prune jobs dry-run keep depth "
            "shallow-since shallow-exclude deepen unshallow update-shallow refmap server-option ipv4 ipv6 "
            "negotiation-tip show-forced-updates set-upstream no-verbose no-quiet no-progress "
            "no-recurse-submodules no-rebase no-stat no-summary no-log no-signoff no-squash no-commit "
            "no-edit no-cleanup no-ff no-verify no-verify-signatures no-autostash no-strategy "
            "no-strategy-option no-gpg-sign no-allow-unrelated-histories no-all no-append no-upload-pack "
            "no-force no-tags no-prune no-jobs no-dry-run no-keep no-depth no-shallow-since "
            "no-shallow-exclude no-deepen no-update-shallow no-server-option no-ipv4 no-ipv6 "
            "no-negotiation-tip no-show-forced-updates no-set-upstream"
        ),
        "push": (
            "verbose quiet repo all branches mirror delete tags dry-run porcelain force force-with-lease "
            "force-if-includes recurse-submodules thin receive-pack exec set-upstream progress prune "
            "no-verify follow-tags signed atomic push-option ipv4 ipv6 verify no-verbose no-quiet no-repo "
            "no-all no-branches no-mirror no-delete no-tags no-dry-run no-porcelain no-force "
            "no-force-with-lease no-force-if-includes no-recurse-submodules no-thin no-receive-pack "
            "no-exec no-set-upstream no-progress no-prune no-follow-tags no-signed no-atomic "
            "no-push-option"
        ),
        "reset": (
            "quiet no-refresh mixed soft hard merge keep recurse-submodules patch intent-to-add "
            "pathspec-from-file pathspec-file-nul refresh no-quiet no-recurse-submodules no-patch "
            "no-intent-to-add no-pathspec-from-file no-pathspec-file-nul"
        ),
        "stash push": (
            "keep-index staged patch quiet include-untracked all message pathspec-from-file "
            "pathspec-file-nul no-keep-index no-staged no-patch no-quiet no-include-untracked no-all "
            "no-message no-pathspec-from-file no-pathspec-file-nul"
        ),
        "stash save": (
            "keep-index staged patch quiet include-untracked all message no-keep-index no-staged no-patch "
            "no-quiet no-include-untracked no-all no-message"
        ),
        "switch": (
            "create force-create guess discard-changes quiet recurse-submodules progress merge conflict "
            "detach track force orphan overwrite-ignore ignore-other-worktrees no-create no-force-create "
            "no-guess no-discard-changes no-quiet no-recurse-submodules no-progress no-merge no-conflict "
            "no-detach no-track no-force no-orphan no-overwrite-ignore no-ignore-other-worktrees"
        ),
        "tag": (
            "list delete verify annotate message file edit sign cleanup local-user force create-reflog "
            "column contains no-contains with without merged no-merged omit-empty sort points-at format "
            "color ignore-case no-annotate no-file no-edit no-sign no-cleanup no-local-user no-force "
            "no-create-reflog no-column no-omit-empty no-sort no-points-at no-format no-color "
            "no-ignore-case"
        ),
        "update-index": (
            "ignore-submodules add replace remove unmerged refresh really-refresh cacheinfo chmod "
            "assume-unchanged no-assume-unchanged skip-worktree no-skip-worktree "
            "ignore-skip-worktree-entries info-only force-remove stdin index-info unresolve again "
            "ignore-missing verbose clear-resolve-undo index-version split-index untracked-cache "
            "test-untracked-cache force-untracked-cache force-write-index fsmonitor fsmonitor-valid "
            "no-fsmonitor-valid no-ignore-submodules no-add no-replace no-remove no-unmerged "
            "no-ignore-skip-worktree-entries no-info-only no-force-remove no-ignore-missing no-verbose "
            "no-index-version no-split-index no-untracked-cache no-test-untracked-cache "
            "no-force-untracked-cache no-force-write-index no-fsmonitor"
        ),
        "update-ref": "no-deref stdin create-reflog deref no-stdin no-create-reflog",
    }.items()
}
GIT_LONG_OPTS["stage"] = GIT_LONG_OPTS["add"]
# Assignments that point git at config this parser can't read (the global or system file, or settings
# passed in the environment): with one, an unknown subcommand may be an alias, and a refspec-less push may
# go anywhere (TASK-067 review gate).
OPAQUE_CONFIG_ENV = re.compile(
    r"GIT_CONFIG(_COUNT|_KEY_\d+|_VALUE_\d+|_PARAMETERS|_GLOBAL|_SYSTEM)?|HOME|XDG_CONFIG_HOME"
)
EXPORTERS = {"export", "declare", "typeset", "local"}
HEREDOC = re.compile(r"<<(?P<dash>-?)[ \t]*\\?(?P<q>['\"]?)(?P<delim>[A-Za-z_][\w-]*)(?P=q)")


ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class ParseError(ValueError):
    pass


class FailClosed(ParseError):
    """A git command that parses but can't be classified: an ambiguous abbreviated option (`git push --a`),
    or a subcommand that may be an alias defined where this parser can't read it (`--config-env`, `-c
    include.path`, `GIT_CONFIG_*`). Every gate refuses it, whatever the rest of the text looks like."""


class Argv(list):
    """An argv from `simple_commands`: the words, plus what its stripped prefixes said about it.
    `via_xargs`: xargs runs it, appending words read from stdin that no gate can see (TASK-067: `echo other |
    xargs git push origin` pushed `other` unchecked); see `xargs_hides_args`. `assigns`: the `VAR=val` words
    before it, env's included (`GIT_DIR=… git commit`)."""

    via_xargs: bool = False
    assigns: dict[str, str]

    def __init__(self, words: list[str], via_xargs: bool = False, assigns: dict[str, str] | None = None):
        super().__init__(words)
        self.via_xargs = via_xargs
        self.assigns = assigns or {}


# What xargs may not run: a command whose appended words (paths, refspecs) decide what a gate allows.
XARGS_GUARDED = {"rm", "mv"}
XARGS_GUARDED_GIT = {"push", "add", "stage", "commit", "rm", "mv"}


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
            out_lines[-1] += text  # bash deletes backslash-newline and inserts nothing (review round 6)
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


def strip_prefixes(argv: list[str], state: dict | None = None) -> Argv:
    """Drop leading reserved words, `VAR=val` and wrappers (with their option values). `env -S 'cmd'`
    splits its string into the command; `env -C dir` / `sudo -D dir` change the directory in `state`.
    The result records whether xargs runs the command and the assignments before it (`Argv`)."""
    return _strip_prefixes(argv, state, Argv([]))


def _strip_prefixes(argv: list[str], state: dict | None, out: Argv) -> Argv:
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in RESERVED or ASSIGNMENT.match(a):
            if a not in RESERVED:
                name, _, value = a.partition("=")
                out.assigns[name] = value
            i += 1
        elif base(a) in WRAPPERS:
            name = base(a)
            out.via_xargs = out.via_xargs or name == "xargs"
            i += 1
            while i < len(argv) and argv[i].startswith("-"):  # env -i, nice -n 5, sudo -u x, timeout -s KILL
                opt, eq, attached = argv[i].partition("=")
                takes_value = opt in WRAPPER_VALUE_OPTS[name]
                value = attached if eq else (argv[i + 1] if takes_value and i + 1 < len(argv) else None)
                if name == "env" and opt in ("-S", "--split-string") and value is not None:
                    return _strip_prefixes([*tokenize(value), *argv[i + (1 if eq else 2) :]], state, out)
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
    name = base(rest[0]) if rest else ""
    if name.startswith("git-") and len(name) > 4:  # `$(git --exec-path)/git-push` is `git push` (TASK-067)
        out[:] = ["git", name[4:], *rest[1:]]
    else:
        out[:] = [name, *rest[1:]] if rest else []
    return out


def note_exports(argv: Argv, state: dict) -> bool:
    """Record what `argv` exports for the commands after it, in `state["exports"]` (TASK-067 review gate:
    `export GIT_DIR=<main>/.git; git commit` reached the main worktree unseen). `VAR=val` alone sets a shell
    variable (exported only once `export VAR` or `declare -x VAR` names it, or if already exported);
    `export`, `declare`/`typeset`/`local -x` export; `export -n` and `unset` drop. True when `argv` was one of
    these, which run nothing a gate checks."""
    exports, shell = state.setdefault("exports", {}), state.setdefault("vars", {})
    if not argv:
        for name, value in argv.assigns.items():
            shell[name] = value
            if name in exports or name in os.environ:
                exports[name] = value
        return bool(argv.assigns)
    head, words = argv[0], argv[1:]
    if head == "unset":
        for name in words:
            exports.pop(name, None)
            shell.pop(name, None)
        return True
    if head not in EXPORTERS:
        return False
    opts = [w for w in words if w[:1] in ("-", "+")]
    unexport = head == "export" and "-n" in opts
    exporting = not unexport and (head == "export" or any(o.startswith("-") and "x" in o for o in opts))
    for word in words:
        name, eq, value = word.partition("=")
        if word in opts or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            continue
        if eq:
            shell[name] = value
        if unexport:
            exports.pop(name, None)
        elif (exporting or name in exports) and name in shell:
            exports[name] = shell[name]
    return True


def xargs_hides_args(argv: list[str], directory: str) -> bool:
    """True when xargs runs `argv` and it is `rm`, `mv` or a git push/add/commit/rm/mv: the words xargs
    appends are the paths or refspecs a gate decides on, and it cannot see them, so the gate fails closed."""
    if not getattr(argv, "via_xargs", False):
        return False
    if argv and argv[0] in XARGS_GUARDED:
        return True
    g = git_subcommand(argv, directory)
    return g is not None and g[0] in XARGS_GUARDED_GIT


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
        argv = strip_prefixes(args, state)
        if note_exports(argv, state) or not argv:
            if redirects:
                yield [], state["dir"], redirects
            continue
        argv.assigns = {**state.get("exports", {}), **argv.assigns}
        head = argv[0]
        if head == "git":
            if state.get("git_c") or state.get("git_dir"):
                # inside a `!shell` alias: git hands its -c settings (GIT_CONFIG_PARAMETERS) and git dir
                # (GIT_DIR) on to the git commands the alias runs; an explicit GIT_DIR= still wins
                gd = {"GIT_DIR": state["git_dir"]} if state.get("git_dir") else {}
                argv = Argv(
                    ["git", *state.get("git_c", []), *argv[1:]], argv.via_xargs, {**gd, **argv.assigns}
                )
            # an alias is replaced by what git runs for it (TASK-067: `git -c alias.p=push p origin x`)
            for expanded, d in expand_git_alias(argv, state["dir"], state.get("depth", 0)):
                yield expanded, d, redirects
            continue
        if head == "cd" and len(argv) > 1 and not argv[1].startswith("-"):
            state["dir"] = _resolve(argv[1], state["dir"])
            continue
        if head in SHELLS:
            for k, a in enumerate(argv[1:], start=1):
                if a.startswith("-") and not a.startswith("--") and "c" in a and k + 1 < len(argv):
                    for inner in _walk(tokenize(argv[k + 1]), state):
                        # `xargs sh -c 'git push origin "$0"'`: the words still come from xargs
                        inner[0].via_xargs = inner[0].via_xargs or argv.via_xargs
                        yield inner
                    break
            continue
        if head == "eval":
            yield from _walk(tokenize(" ".join(argv[1:])), state)
            continue
        yield argv, state["dir"], redirects


def _git_options(argv: list[str], directory: str) -> tuple[int, str, dict[str, str], str | None, bool]:
    """Read git's global options: (index of the subcommand, effective dir after chained -C, the `-c` /
    `--config-env` settings with lower-cased keys (a `--config-env` value is unknown: ''), the git dir from
    `--git-dir` or a `GIT_DIR=` before the command, resolved against the effective dir, or None, and whether
    git also reads config this parser can't: a `--config-env` value, a `-c include.path` / `includeIf.*`
    file, or an `OPAQUE_CONFIG_ENV` assignment)."""
    assigns = getattr(argv, "assigns", {})
    eff, config, gitdir = directory, {}, assigns.get("GIT_DIR")
    opaque = any(OPAQUE_CONFIG_ENV.fullmatch(name) for name in assigns)
    j = 1
    while j < len(argv) and argv[j].startswith("-"):
        opt, eq, attached = argv[j].partition("=") if argv[j].startswith("--") else (argv[j], "", "")
        if opt not in GIT_VALUE_OPTS:
            j += 1
            continue
        value = attached if eq else (argv[j + 1] if j + 1 < len(argv) else "")
        j += 1 if eq else 2
        if opt == "-C":
            eff = _resolve(value, eff)
        elif opt in ("-c", "--config-env"):
            key, _, v = value.partition("=")
            config[key.lower()] = v if opt == "-c" else ""
            opaque = (
                opaque
                or opt == "--config-env"
                or re.match(r"include(if\..*)?\.path$", key.lower()) is not None
            )
        elif opt == "--git-dir":
            gitdir = value
    return j, eff, config, (_resolve(gitdir, eff) if gitdir else None), opaque


def git_subcommand(argv: list[str], directory: str) -> tuple[str, list[str], str] | None:
    """For a `git ...` argv return (subcommand, args, effective_dir), honouring chained -C; else None.
    Aliases are already expanded by `simple_commands` (`expand_git_alias`)."""
    if not argv or argv[0] != "git":
        return None
    j, eff, _, _, _ = _git_options(argv, directory)
    if j >= len(argv):
        return None
    return argv[j], argv[j + 1 :], eff


def git_config(argv: list[str]) -> dict[str, str]:
    """The `-c key=value` / `--config-env key=…` settings on a `git ...` argv, keys lower-cased."""
    return _git_options(argv, ".")[2] if argv and argv[0] == "git" else {}


def git_config_opaque(argv: list[str]) -> bool:
    """Does git read config for this `git ...` argv that this parser can't (`_git_options`)? Then a
    refspec-less push may go anywhere, and a gate refuses it (TASK-067 review gate)."""
    return _git_options(argv, ".")[4] if argv and argv[0] == "git" else False


def git_dir(argv: list[str], directory: str) -> str | None:
    """The repository a `git ...` argv runs against when it isn't the one `directory` is in: `--git-dir`,
    else a `GIT_DIR=` assignment before it (TASK-067: `GIT_DIR=<main>/.git git commit` from a worktree)."""
    return _git_options(argv, directory)[3] if argv and argv[0] == "git" else None


def expand_git_alias(argv: Argv, directory: str, depth: int = 0) -> list[tuple[Argv, str]]:
    """The command(s) git runs for `git [opts] <alias> args`: an alias from `-c alias.<name>=…` or the repo's
    config (`git config --get alias.<name>`) is replaced by its words, and a `!shell` alias by the commands
    in its text (run from the top of the worktree, the outer `-c` settings passed on, as git does). Anything
    else comes back unchanged as [(argv, directory)]. Raises ParseError on an unreadable or looping alias."""
    j, eff, config, gitdir, opaque = _git_options(argv, directory)
    if j >= len(argv) or argv[j] in GIT_BUILTINS:
        return [(normalize_git_options(argv, j), directory)]
    if opaque:
        # the alias may be defined where this parser can't read it (TASK-067 review gate: `P=push git
        # --config-env alias.p=P p origin HEAD:dev`)
        raise FailClosed(
            f"git {argv[j]!r} may be an alias set by --config-env, include.path or GIT_CONFIG_*, unreadable here"
        )
    name = argv[j].lower()
    body = config.get(f"alias.{name}")
    if body is None:
        body = git(eff, *(["--git-dir", gitdir] if gitdir else []), "config", "--get", f"alias.{name}")
    if not body:
        return [(normalize_git_options(argv, j), directory)]  # not an alias: a git-<name> program, or a typo
    if depth >= ALIAS_DEPTH:
        raise ParseError(f"git alias {name!r} nests too deep (a loop?)")
    rest = argv[j + 1 :]
    if not body.startswith("!"):
        try:
            words = shlex.split(body)
        except ValueError as exc:
            raise ParseError(f"git alias {name!r}: {exc}") from exc
        expanded = Argv([*argv[:j], *words, *rest], argv.via_xargs, argv.assigns)
        return expand_git_alias(expanded, directory, depth + 1)
    # A shell alias: git runs `sh -c '<text> "$@"'` with the args at the worktree top; its git commands see
    # the outer -c settings (GIT_CONFIG_PARAMETERS) and git dir (GIT_DIR).
    outer_c = [w for k, v in config.items() for w in ("-c", f"{k}={v}")]
    text = " ".join([body[1:], *(shlex.quote(r) for r in rest)])
    inner_state = {
        "dir": repo_root(eff),
        "depth": depth + 1,
        "git_c": outer_c,
        "git_dir": gitdir,
    }
    out = []
    for inner, d, _ in _walk(tokenize(text), inner_state):
        inner.via_xargs = inner.via_xargs or argv.via_xargs
        out.append((inner, d))
    return out


def _long_option(name: str, names: frozenset[str]) -> str | None:
    """The long option git reads `--<name>` as: an exact name, else the one option it is a prefix of
    (negations are names too: `no-f` is `no-ff` for merge). None if it names none; FailClosed if several
    (git refuses it as ambiguous, and this parser won't guess)."""
    if name in names:
        return name
    candidates = sorted(o for o in names if o.startswith(name))
    if len(candidates) > 1:
        raise FailClosed(f"--{name} is ambiguous: {', '.join('--' + c for c in candidates[:4])}")
    return candidates[0] if candidates else None


def normalize_git_options(argv: Argv, j: int) -> Argv:
    """`argv` with every abbreviated long option of its subcommand (`argv[j]`) written out in full, as git
    reads it: `git add --forc .` is `git add --force .`, `git stash --al` is `git stash --all` (TASK-067
    review gate). Words after `--`, and subcommands without a `GIT_LONG_OPTS` table, are left alone."""
    if j >= len(argv):
        return argv
    args, start, key = list(argv[j + 1 :]), 0, argv[j]
    if key == "stash":
        if args and args[0] in ("push", "save"):
            key, start = f"stash {args[0]}", 1
        elif args and args[0].startswith("-"):
            key = "stash push"  # `git stash -a` is `git stash push -a`
    names = GIT_LONG_OPTS.get(key)
    if names is None:
        return argv
    for k in range(start, len(args)):
        a = args[k]
        if a == "--":
            break
        if a.startswith("--") and len(a) > 2:
            name, eq, value = a[2:].partition("=")
            full = _long_option(name, names)
            if full is not None:
                args[k] = f"--{full}{eq}{value}"
    return Argv([*argv[: j + 1], *args], getattr(argv, "via_xargs", False), getattr(argv, "assigns", {}))


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
