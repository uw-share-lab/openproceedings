"""Shared command-string parsing for the openproceedings PreToolUse(Bash) gates.

Parses a Bash tool command into simple commands (argv lists) the way bash reads it, for the cases that
matter to a gate:
  * `preprocess` makes ONE pass over the whole text: quote state carries across lines (a multi-line quoted
    message is one word), an unquoted `#` at the start of a word starts a comment, and an unquoted
    `<<DELIM` / `<<'DELIM'` / `<<-"DELIM"` starts a heredoc whose body is dropped unread (never `<<<`);
    `$'…'` is decoded (over several lines too) and `$"…"` read as "…" anywhere in a word, `$(pwd)` is written
    as ${PWD}, `$(git rev-parse --show-toplevel)`, `$(git rev-parse --git-common-dir|--git-dir|--absolute-git-dir)`
    and `$(mktemp [-d] [-t prefix])` as variables `expand_word` resolves, and `"$X"a` as ${X}a;
  * `tokenize` brace-expands each word as bash does (`d{e,}v` is `dev dv`, `{a..c}`, nesting; quoted or
    escaped braces and `${…}` stay literal; empty words dropped; past BRACE_LIMIT words or BRACE_GROUPS
    groups in one word, a ParseError);
  * separators split with or without spaces: `;` `&&` `||` `|` `&` `(` `)`, newlines, `<(`/`>(`;
  * `for v in <words>; do …; done` is read once per word with `v` set to it (`_unroll_for`; not when the body
    can leave the loop early); `$(mktemp)` is unknown when the command sets or unsets TMPDIR;
  * leading reserved words (`if`/`then`/`do`/`{`/`!` …), `VAR=val`, and wrappers (`env`, `sudo`, `nice`,
    `timeout`, `xargs`, `stdbuf`, `watch`, `exec`, `time`, `nohup`, `command`, `builtin`) are stripped, each
    wrapper with its own table of value-taking options; `env -S '…'` is split, `env -C`/`sudo -D` move dir;
    the argv comes back as an `Argv` that records the `VAR=val` words and whether xargs runs it;
  * command names compare by basename (`/usr/bin/git` is `git`);
  * redirections leave argv as (operator, target) pairs (`redirect_targets`);
  * `cd`, `pushd` and `popd` are tracked (targets through `expand_word`, `-P` physically; one it can't resolve,
    one that doesn't exist, a relative one under CDPATH, or `cd -` back to an unknown one marks the directory
    unknown) and `bash -c "…"` (with the assignments before it exported to it) / `eval "…"` are recursed into;
    `bash script.sh` is yielded as itself;
  * `expand_word` resolves `~`, `~+`, `~-`, `$PWD`, `$HOME` and other variables a command's path names: set
    (or `unset`, or `env -u`: empty) earlier in the command, else only HOME/TMPDIR/USER from this hook's
    environment, which a gate also reads as '' (`walk(env_empty=True)`);
  * a git alias (`-c alias.<name>=…` or the repo's config; `!shell` ones too) becomes what git runs for it;
  * a `git-<sub>` program (`$(git --exec-path)/git-push`) is `git <sub>`;
  * an abbreviated long option (`--forc`, `--al`) becomes the option git reads it as (`normalize_git_options`);
  * `export`/`declare -x` assignments, and every assignment under `set -a`, reach every later command's
    `Argv.assigns` (`note_exports`);
  * a git command after a `git config` that writes an alias, an include, a push target or an upstream, a `git
    remote add --mirror` / `remote set-branches` / `branch -u`, or a redirect, tee, sed -i, cp/mv/ln into a git
    config file, in the same command line raises FailClosed (`config_steers_git`, `writes_git_config`): this
    parser read the config before it was written; so does a `git push` after a checkout/switch/worktree add
    that creates a branch with an upstream (`-t`, a remote-tracking start point: `creates_with_upstream`);
  * `push_config` reads the repo config a refspec-less push uses.
A command that cannot be parsed raises ParseError; every gate treats that as a reason to BLOCK a command
that looks like what it guards (fail closed), never to allow it. A git command that parses but can't be
classified (an ambiguous abbreviated option; config git reads from a source this parser can't, deciding an
alias; config written earlier in the same command) raises FailClosed, a ParseError every gate refuses
whatever the text looks like.

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
# The options newer gits list too (CI's runner, 2026-10-01): `test-git-long-opts.sh` notes any the table lacks.
_PATCH_OPTS = "auto-advance no-auto-advance inter-hunk-context unified"
_NEGOTIATION = "negotiation-include negotiation-restrict no-negotiation-include no-negotiation-restrict"
for _key, _newer in {
    "add": _PATCH_OPTS,
    "checkout": _PATCH_OPTS,
    "reset": _PATCH_OPTS,
    "stash push": _PATCH_OPTS,
    "stash save": _PATCH_OPTS,
    "commit": "inter-hunk-context unified no-trailer",
    "tag": "trailer no-trailer",
    "fetch": _NEGOTIATION,
    "pull": f"{_NEGOTIATION} compact-summary no-compact-summary",
    "merge": "compact-summary no-compact-summary",
    "update-index": "show-index-version no-show-index-version",
    "update-ref": "batch-updates no-batch-updates",
}.items():
    GIT_LONG_OPTS[_key] = GIT_LONG_OPTS[_key] | frozenset(_newer.split())
GIT_LONG_OPTS["stage"] = GIT_LONG_OPTS["add"]
# Assignments that point git at config this parser can't read (the global or system file, settings passed
# in the environment, or another repository's common dir: GIT_COMMON_DIR): with one, an unknown subcommand
# may be an alias, and a refspec-less push may go anywhere (TASK-067 review gate).
OPAQUE_CONFIG_ENV = re.compile(
    r"GIT_CONFIG(_COUNT|_KEY_\d+|_VALUE_\d+|_PARAMETERS|_GLOBAL|_SYSTEM)?|GIT_COMMON_DIR|HOME|XDG_CONFIG_HOME"
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
    # Set by the walk for `expand_word`: the shell variables known when this command runs, the directory a
    # `cd -` / `~-` names, and whether a `cd`/`pushd`/`popd` before it went somewhere this parser can't tell.
    shell_vars: dict[str, str]
    olddir: str | None = None
    dir_unknown: bool = False
    # `env_empty`: the walk reads HOME/TMPDIR/USER from the environment as '' (`walk`); `head_word`: the command
    # word as written, before it was basenamed (`/op-revie?s/x` after an unquoted `$(…)` split the word)
    env_empty: bool = False
    head_word: str = ""

    def __init__(self, words: list[str], via_xargs: bool = False, assigns: dict[str, str] | None = None):
        super().__init__(words)
        self.via_xargs = via_xargs
        self.assigns = assigns or {}
        self.shell_vars = {}


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
    quote: str | None = None  # "'", '"', or "$'" (ANSI-C, decoded as it is read; review gate round 3)
    ansi_dead = False  # a NUL ended the current $'…' value: the rest of it is dropped
    pending: list[tuple[str, bool]] = []  # (delimiter, dash)
    arith = 0  # depth of $(( … )) / (( … )) arithmetic, where << is a shift
    inner = 0  # plain ( ) nesting inside the current arithmetic
    param = 0  # depth of an unquoted ${ … }, whose braces and commas are no brace expansion
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
            if quote == "$'":
                value, i, closed = _ansi_c(line, i)
                if not ansi_dead:
                    head, nul, _ = value.partition("\0")
                    kept.append(head.replace("'", "'\\''"))
                    ansi_dead = bool(nul)
                if closed:
                    kept.append("'")
                    quote, ansi_dead = None, False
                continue
            if quote != "'" and (m := PWD_SUBST.match(line, i)):
                # `$(pwd)` / `pwd` is the shell's current directory (TASK-067 review gate)
                kept.append("${PWD}")
                i = m.end()
                continue
            if quote != "'" and (m := TOPLEVEL_SUBST.match(line, i)):
                # `$(git rev-parse --show-toplevel)` is the top of the worktree (review gate round 3)
                kept.append("${" + TOPLEVEL_VAR + "}")
                i = m.end()
                continue
            if quote != "'" and (m := GITDIR_SUBST.match(line, i)):
                # `$(git rev-parse --git-common-dir|--git-dir|--absolute-git-dir)`: the repository's git dir, so a
                # glob after it (`…/op-*`) expands as bash expands it (TASK-067 final review gate)
                kept.append("${" + GITDIR_VARS[m.group("which") or m.group("which2")] + "}")
                i = m.end()
                continue
            if quote != "'" and (m := MKTEMP_SUBST.match(line, i)):
                # `$(mktemp [-d] [-t prefix])`: a new path in the temp dir, outside any repository
                kept.append("${" + MKTEMP_VAR + "}")
                i = m.end()
                continue
            if quote != "'" and (m := VAR_BEFORE_QUOTE.match(line, i)):
                # `"$X"a` is ${X}a, not $Xa: the quote that ends the name goes once shlex has read it
                kept.append("${" + m.group(1) + "}")
                i = m.end(1)
                continue
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
            if line.startswith("$'", i):
                # ANSI-C quoting, anywhere in a word: decoded as it is read (above), re-quoted as a plain '…'
                # literal; like any quote it may run on over several lines (review gate round 3)
                kept.append("'")
                quote = "$'"
                i += 2
                continue
            if line.startswith('$"', i):
                i += 1  # $"…" (locale translation) is a "…" string
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
            if param or line.startswith("${", i):
                # inside ${ … } braces nest and nothing is brace-expanded
                if line.startswith("${", i):
                    param += 1
                    kept.append("$")
                    i += 1
                    c = "{"
                elif c == "{":
                    param += 1
                elif c == "}":
                    param -= 1
                kept.append(c)
                i += 1
                continue
            # an unquoted, unescaped brace or comma is marked for brace expansion (`tokenize`)
            kept.append(BRACE_MARK.get(c, c))
            i += 1
        text = "".join(kept)
        # line continuation: a trailing unescaped backslash outside single quotes, not starting a heredoc
        trailing = len(text) - len(text.rstrip("\\"))
        continues = trailing % 2 == 1 and quote not in ("'", "$'") and not pending
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


ANSI_C_SIMPLE = {
    "a": "\a",
    "b": "\b",
    "e": "\x1b",
    "E": "\x1b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "?": "?",
}
ANSI_C_NUMERIC = {"x": (16, 2), "u": (16, 4), "U": (16, 8)}  # \xHH, \uHHHH, \UHHHHHHHH


def _ansi_c(line: str, i: int) -> tuple[str, int, bool]:
    """Decode the body of a `$'…'` string from `line[i]` (just after `$'`, or the start of a line it runs on
    to) as bash does: \\n \\t \\e …, \\nnn octal, \\xHH, \\uHHHH, \\UHHHHHHHH, \\cX; an unknown escape keeps its
    backslash (TASK-067 review gate: `git push origin HEAD:$'\\x64ev'` pushed dev). Returns (value, index after
    the closing quote or the end of the line, whether the quote closed); a NUL in the value ends it, which
    `preprocess` applies (the rest up to the closing quote is dropped)."""
    out: list[str] = []
    n = len(line)
    while i < n:
        c = line[i]
        if c == "'":
            return "".join(out), i + 1, True
        if c != "\\" or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        d = line[i + 1]
        if d in ANSI_C_SIMPLE:
            out.append(ANSI_C_SIMPLE[d])
            i += 2
        elif d in "01234567":
            digits = re.match(r"[0-7]{1,3}", line[i + 1 :]).group(0)  # type: ignore[union-attr]
            out.append(chr(int(digits, 8) & 0xFF))
            i += 1 + len(digits)
        elif d in ANSI_C_NUMERIC and (
            m := re.match(rf"[0-9a-fA-F]{{1,{ANSI_C_NUMERIC[d][1]}}}", line[i + 2 :])
        ):
            out.append(chr(min(int(m.group(0), 16), 0x10FFFF)))
            i += 2 + len(m.group(0))
        elif d == "c" and i + 2 < n:
            out.append(chr(ord(line[i + 2]) & 0x1F))
            i += 3
        else:
            out.append("\\" + d)
            i += 2
    return "".join(out), n, False


# `$(pwd)` and `pwd` in backquotes name the shell's current directory: `preprocess` writes them as ${PWD}
PWD_SUBST = re.compile(r"\$\(\s*pwd(\s+-[LP])?\s*\)|`\s*pwd(\s+-[LP])?\s*`")
# ... and `$(git rev-parse --show-toplevel)` the top of its worktree: `preprocess` writes it as this variable,
# which `expand_word` resolves from the directory the command runs in (review gate round 3)
TOPLEVEL_SUBST = re.compile(
    r"\$\(\s*git\s+rev-parse\s+--show-toplevel\s*\)|`\s*git\s+rev-parse\s+--show-toplevel\s*`"
)
TOPLEVEL_VAR = "OP_SHOW_TOPLEVEL__"
# ... and `$(git rev-parse --git-common-dir)` / `--git-dir` / `--absolute-git-dir` the repository's git dirs (absolute;
# bash gets a relative one, the same directory), so a glob after one expands (TASK-067 final review gate: `cp x
# $(git rev-parse --git-common-dir)/op-*` wrote a review record)
_GITDIR = (
    r"git\s+rev-parse\s+(?:--path-format=(?:absolute|relative)\s+)?"
    r"--(?P<which{n}>git-common-dir|git-dir|absolute-git-dir)"
)
GITDIR_SUBST = re.compile(r"\$\(\s*" + _GITDIR.format(n="") + r"\s*\)|`\s*" + _GITDIR.format(n="2") + r"\s*`")
GITDIR_VARS = {
    "git-common-dir": "OP_GIT_COMMON_DIR__",
    "git-dir": "OP_GIT_DIR__",
    "absolute-git-dir": "OP_GIT_DIR__",
}
# ... and `$(mktemp)` with only -d/-q/-u and an optional `-t <prefix>` (no template path: one would be relative to
# the current directory) a new path in the temp dir, outside any repository: MKTEMP_PATH (TASK-067 final review gate:
# `tmp=$(mktemp -d) && … && rm -rf "$tmp"` was refused in every repo with data/)
MKTEMP_SUBST = re.compile(
    r"\$\(\s*mktemp(?:\s+-[dqu]+)*(?:\s+-t\s+[\w.-]+)?(?:\s+-[dqu]+)*\s*\)"
    r"|`\s*mktemp(?:\s+-[dqu]+)*(?:\s+-t\s+[\w.-]+)?(?:\s+-[dqu]+)*\s*`"
)
MKTEMP_VAR = "OP_MKTEMP__"
LOOP_EXITS = frozenset({"break", "continue", "return", "exit"})  # a for loop with one of these isn't unrolled
MKTEMP_PATH = "/tmp/op-mktemp.XXXXXXXX"
# `$NAME` with a quote right after it: written ${NAME}, so the word after the quote can't join the name
VAR_BEFORE_QUOTE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)(?=[\"'])")
# Brace expansion: `preprocess` marks each unquoted, unescaped `{` `}` `,` with a private-use character, so
# `tokenize` can expand `d{e,}v` (bash: dev dv) while a quoted "d{e,}v" stays literal (TASK-067 review gate).
BRACE_MARK = {"{": "\ue000", "}": "\ue001", ",": "\ue002"}
LB, RB, CM = BRACE_MARK["{"], BRACE_MARK["}"], BRACE_MARK[","]
UNMARK = str.maketrans({v: k for k, v in BRACE_MARK.items()})
# Words one brace expression is read as, and expandable `{` one word may hold: past either, a ParseError, which
# every gate refuses (a truncated list let `rm -rf {x{1..4096},data/snapshots}` through, and deep nesting
# overflowed the recursion and crashed the hook, which fails open: TASK-067 final review gate)
BRACE_LIMIT = 4096
BRACE_GROUPS = 256


def _sequence(body: str) -> list[str] | None:
    """The words of a `{x..y[..incr]}` sequence body (integers, zero-padded as bash pads them, or single
    letters), at most BRACE_LIMIT + 1 of them, or None if `body` isn't one."""
    if m := re.fullmatch(r"(-?\d+)\.\.(-?\d+)(?:\.\.(-?\d+))?", body):
        a, b = int(m.group(1)), int(m.group(2))
        step = abs(int(m.group(3) or 1)) or 1
        pad = any(re.fullmatch(r"-?0\d+", g) for g in m.group(1, 2))
        width = max(len(m.group(1)), len(m.group(2))) if pad else 0
        values = range(a, b + (1 if b >= a else -1), step if b >= a else -step)
        return [f"{v:0{width}d}" for v in values[: BRACE_LIMIT + 1]]
    if m := re.fullmatch(r"([A-Za-z])\.\.([A-Za-z])(?:\.\.(-?\d+))?", body):
        a, b = ord(m.group(1)), ord(m.group(2))
        step = abs(int(m.group(3) or 1)) or 1
        return [chr(v) for v in range(a, b + (1 if b >= a else -1), step if b >= a else -step)]
    return None


def _brace(word: str) -> list[str]:
    """Brace-expand a word whose expandable braces and commas are marked (`BRACE_MARK`), as bash does: the
    leftmost `{…}` with a top-level comma, or a sequence body, becomes one word per alternative, each
    expanded again; a `{` with no match, or a `{…}` that is neither, stays literal. Past BRACE_LIMIT words:
    ParseError."""
    start = 0
    while (s := word.find(LB, start)) >= 0:
        depth, commas, end = 0, [], -1
        for k in range(s, len(word)):
            if word[k] == LB:
                depth += 1
            elif word[k] == RB:
                depth -= 1
                if depth == 0:
                    end = k
                    break
            elif word[k] == CM and depth == 1:
                commas.append(k)
        if end < 0:
            start = s + 1
            continue
        if commas:
            cuts = [s, *commas, end]
            parts = [word[cuts[k] + 1 : cuts[k + 1]] for k in range(len(cuts) - 1)]
        elif (parts := _sequence(word[s + 1 : end])) is None:  # type: ignore[assignment]
            start = s + 1
            continue
        out: list[str] = []
        for part in parts:
            out += _brace(word[:s] + part + word[end + 1 :])
            if len(out) > BRACE_LIMIT:
                raise ParseError(f"a brace expansion makes more than {BRACE_LIMIT} words")
        return out
    return [word]


def tokenize(cmd: str) -> list[str]:
    """The words and operators of `cmd` (`preprocess`ed), each word brace-expanded the way bash does (an empty
    word a brace expansion makes is dropped, as bash drops it: `git push origin {,}` names no refspec). A word with
    more than BRACE_GROUPS expandable `{`, or one that expands past BRACE_LIMIT words, raises ParseError."""
    text = preprocess(cmd)
    lex = shlex.shlex(text, posix=True, punctuation_chars=PUNCT)
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError as exc:
        raise ParseError(str(exc)) from exc
    if any(t.count(LB) > BRACE_GROUPS for t in tokens):
        raise ParseError(f"a word with more than {BRACE_GROUPS} brace groups")
    return [w.translate(UNMARK) for t in tokens for w in (_brace(t) if LB in t else [t]) if w or LB not in t]


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
                if name == "env" and opt in ("-u", "--unset") and value is not None:
                    out.assigns[value] = ""  # unset for what it runs: known empty (review gate round 3)
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
    out.head_word = rest[0] if rest else ""
    name = base(rest[0]) if rest else ""
    if name.startswith("git-") and len(name) > 4:  # `$(git --exec-path)/git-push` is `git push` (TASK-067)
        out[:] = ["git", name[4:], *rest[1:]]
    else:
        out[:] = [name, *rest[1:]] if rest else []
    return out


def note_exports(argv: Argv, state: dict) -> bool:
    """Record what `argv` exports for the commands after it, in `state["exports"]` (TASK-067 review gate:
    `export GIT_DIR=<main>/.git; git commit` reached the main worktree unseen). `VAR=val` alone sets a shell
    variable (exported only once `export VAR` or `declare -x VAR` names it, or if already exported, or while
    `set -a` / `set -o allexport` is on: TASK-067 review gate); `export`, `declare`/`typeset`/`local -x`
    export; `export -n` and `unset` drop; `unset` also leaves the variable known to be empty, so `expand_word`
    never falls back to this hook's environment for it (review gate round 3). True when `argv` was one of
    these, or `set`, which run nothing a gate checks."""
    exports, shell = state.setdefault("exports", {}), state.setdefault("vars", {})
    if not argv:
        for name, value in argv.assigns.items():
            shell[name] = value
            if name in exports or name in os.environ or state.get("allexport"):
                exports[name] = value
        return bool(argv.assigns)
    head, words = argv[0], argv[1:]
    if head == "set":
        k = 0
        while k < len(words) and words[k][:1] in ("-", "+") and words[k] not in ("-", "--"):
            for c in words[k][1:]:
                if c == "a":
                    state["allexport"] = words[k][0] == "-"
                elif c == "o" and k + 1 < len(words):  # `set -o allexport`, `set -euo pipefail`
                    k += 1
                    if words[k] == "allexport":
                        state["allexport"] = words[k - 1][0] == "-"
            k += 1
        return True
    if head == "unset":
        for name in words:
            exports.pop(name, None)
            if not name.startswith("-"):
                shell[name] = ""
        return True
    if head not in EXPORTERS:
        return False
    opts = [w for w in words if w[:1] in ("-", "+")]
    unexport = head == "export" and "-n" in opts
    exporting = not unexport and (
        head == "export" or any(o.startswith("-") and "x" in o for o in opts) or state.get("allexport", False)
    )
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
    for argv, d, _ in walk(cmd, cwd):
        if argv:
            yield argv, d


def redirect_targets(cmd: str, cwd: str) -> Iterator[tuple[str, str, str]]:
    """Yield (operator, target, directory) for every redirection in `cmd`."""
    for _, d, redirects in walk(cmd, cwd):
        for op, target in redirects:
            yield op, target, d


def walk(cmd: str, cwd: str, env_empty: bool = False) -> Iterator[tuple[Argv, str, list[tuple[str, str]]]]:
    """Yield (argv, directory, redirections) for every simple command in `cmd`, in order; argv is empty for a
    command that only redirects (`> file`) or only assigns. Each argv carries what `expand_word` needs.
    `env_empty`: read HOME/TMPDIR/USER as '' wherever the command doesn't set them (`ENV_FALLBACK`): a gate
    walks both ways when a path decides its check. (Nesting too deep for Python, `eval eval … git push`, raises
    RecursionError: every gate refuses an exception it doesn't expect.)"""
    yield from _walk(tokenize(cmd), {"dir": cwd, "env_empty": env_empty})


VAR_REF = re.compile(r"\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|(?P<bare>[A-Za-z_][A-Za-z0-9_]*))")
# The only variables read from this hook's environment when the command doesn't set them: the agent's shell has
# the same ones. Any other is unknown (review gate round 3: `unset TMPDIR; rm -rf "${TMPDIR}data"` was judged
# with the hook's TMPDIR), and each of these is also read as '' (`walk(env_empty=True)`), which the gates
# check too: the agent's shell may not have it.
ENV_FALLBACK = ("HOME", "TMPDIR", "USER")


def _variable(
    name: str, directory: str | None, shell_vars: dict[str, str], olddir: str | None, env_empty: bool
) -> str | None:
    """The value of `$name` when the command runs, or None when it can't be told here."""
    if name == "PWD":
        return directory
    if name == "OLDPWD":
        return olddir or shell_vars.get("OLDPWD")
    if name == TOPLEVEL_VAR:
        return (git(directory, "rev-parse", "--show-toplevel") or None) if directory else None
    if name in GITDIR_VARS.values():
        flag = "--git-common-dir" if name == GITDIR_VARS["git-common-dir"] else "--absolute-git-dir"
        return (git(directory, "rev-parse", "--path-format=absolute", flag) or None) if directory else None
    if name == MKTEMP_VAR:
        # mktemp creates under $TMPDIR: a command that sets (or unsets) it decides where (confirmation pass:
        # `TMPDIR=$PWD/data; t=$(mktemp -d); rm -rf "$t/../snapshots"`), so then the path is unknown
        return None if "TMPDIR" in shell_vars else MKTEMP_PATH
    if name in shell_vars:
        return shell_vars[name]
    if name in ENV_FALLBACK:
        # unset in this environment is unset in the agent's shell too, and bash reads it as '' (CI's runner
        # has no TMPDIR: `rm -f "$TMPDIR/x"` is `rm -f /x`)
        return "" if env_empty else os.environ.get(name, "")
    return None


def _passwd_home() -> str | None:
    """The account's home directory from the passwd database, as bash's `~` reads it when HOME is unset."""
    try:
        import pwd

        return pwd.getpwuid(os.getuid()).pw_dir or None
    except (ImportError, KeyError, OSError):
        return None


def expand_word(
    word: str,
    directory: str | None,
    shell_vars: dict[str, str] | None = None,
    olddir: str | None = None,
    depth: int = 0,
    env_empty: bool = False,
) -> str | None:
    """The text bash makes of `word` by tilde and variable expansion, or None when it can't be told here.
    `~`, `~/…` and `$HOME` are the home directory; `~+` and `$PWD` (and `$(pwd)`, which `preprocess` writes as
    ${PWD}) are `directory`; `$(git rev-parse --show-toplevel)` is the top of its worktree; `~-` and `$OLDPWD`
    are `olddir`; any other `$NAME` / `${NAME}` is a shell variable set (or `unset`: '') earlier in the command
    (`shell_vars`), else, for HOME/TMPDIR/USER only, this hook's environment ('' with `env_empty`). TASK-067
    review gate: `rm -rf ~+/data`, `cd "$PWD" && rm -rf data`. A variable set nowhere, `${…}` with an operator,
    `$1`, `$(…)` or a backquote is None: the caller fails closed. `directory` None: a `cd` before it couldn't
    be followed, so `~+` and `$PWD` are unknown too."""
    shell_vars = shell_vars or {}
    if word.startswith("~"):
        user, sep, rest = word[1:].partition("/")
        if user == "":
            # bash's `~` is $HOME when HOME is set, else the passwd home (never '': `env -u HOME` or `unset
            # HOME` and `~/x` is <passwd home>/x); a HOME set to '' in the command (`HOME=`) can't be told from
            # `unset HOME` here, so that `~` is unknown (TASK-067 CI fix re-check)
            if "HOME" in shell_vars:
                home = shell_vars["HOME"] or None
            elif env_empty or "HOME" not in os.environ:
                home = _passwd_home()
            else:
                home = os.environ["HOME"]
        elif user == "+":
            home = directory  # None: a `cd` this parser couldn't follow
        elif user == "-":
            home = olddir or shell_vars.get("OLDPWD")
        else:
            home = os.path.expanduser("~" + user)
        if home is None:
            return None
        word = home + sep + rest

    def value(m: re.Match[str]) -> str:
        name = m.group("braced") or m.group("bare")
        found = _variable(name, directory, shell_vars, olddir, env_empty)
        if found is not None and ("$" in found or "`" in found) and depth < 3:
            # `f=$TMPDIR/x; rm "$f"`
            found = expand_word(found, directory, shell_vars, olddir, depth + 1, env_empty)
        if found is None:
            raise LookupError(name)
        return found

    try:
        out = VAR_REF.sub(value, word)
    except LookupError:
        return None
    return None if "$" in out or "`" in out else out


def expand_known(word: str, argv: Argv, directory: str | None) -> str:
    """`word` with every variable `expand_word` can tell replaced, the rest left as written (`$G/${d}reviews`
    with d=op- is `$G/op-reviews`): what a gate searches for a path it must not let be written."""

    def value(m: re.Match[str]) -> str:
        found = _variable(
            m.group("braced") or m.group("bare"),
            None if argv.dir_unknown else directory,
            argv.shell_vars,
            argv.olddir,
            argv.env_empty,
        )
        return m.group(0) if found is None else found

    for _ in range(3):  # a value may name another variable
        word = VAR_REF.sub(value, word)
    return word


def _change_dir(head: str, words: list[str], state: dict, assigns: dict[str, str] | None = None) -> None:
    """Follow `cd`/`pushd`/`popd` in `state`: "dir" is the new directory, "olddir" the one before (with
    "olddir_unknown"), "dirstack" pushd's stack; a target this parser can't resolve (an unset variable, `pushd
    +1`, an empty stack) keeps "dir" but sets "dir_unknown" until an absolute `cd` (TASK-067 review gate:
    `pushd data; rm -rf snapshots` was read from the old directory). Review gate round 3: `cd -P` resolves
    symlinks; a target that doesn't exist leaves the directory unknown (the `cd` fails and the shell stays,
    or `&&` stops: this parser can't tell which), and so is the directory before it unless it was already the
    current one; with CDPATH set a relative target is unknown; `cd -` to an unknown directory is unknown.
    `assigns`, the command's own `VAR=val` prefix (`HOME=data cd`), counts first: the shell reads it."""
    opts = [w for w in words if len(w) > 1 and w[0] == "-" and w[1] in "LPen@"]  # cd -P, pushd -n
    words = [w for w in words if w not in opts]
    physical = any("P" in o for o in opts)
    cur, unknown = state["dir"], state.get("dir_unknown", False)
    old, old_unknown = state.get("olddir"), state.get("olddir_unknown", False)
    stack: list[tuple[str, bool]] = state.setdefault("dirstack", [])
    variables = {**state.get("vars", {}), **(assigns or {})}
    env_empty = state.get("env_empty", False)
    target: str | None = None
    if head == "popd":
        if stack and not words:
            cur_new, unknown_new = stack.pop()
            state.update(olddir=cur, olddir_unknown=unknown, dir=cur_new, dir_unknown=unknown_new)
            return
    elif head == "pushd" and not words:
        if stack:  # swaps the top two
            cur_new, unknown_new = stack[-1]
            stack[-1] = (cur, unknown)
            state.update(olddir=cur, olddir_unknown=unknown, dir=cur_new, dir_unknown=unknown_new)
            return
    elif head == "pushd" and words[0][:1] in ("+", "-"):
        pass  # a stack rotation: unknown
    elif not words:
        # a bare `cd` goes to $HOME, unlike `~` never the passwd home: with HOME unset bash stays ("HOME not set")
        # and zsh goes to the passwd home; with HOME '' both stay. So without a HOME the target is unknown
        home = (
            variables.get("HOME") if "HOME" in variables else (None if env_empty else os.environ.get("HOME"))
        )
        target = home or None
    elif words[0] == "-":
        target = None if old_unknown else old
    else:
        target = expand_word(
            words[0], None if unknown else cur, variables, None if old_unknown else old, env_empty=env_empty
        )
        cdpath = variables["CDPATH"] if "CDPATH" in variables else os.environ.get("CDPATH", "")
        if target is not None and cdpath and not re.match(r"(/|\.\.?(/|$))", target):
            target = None  # CDPATH may send it elsewhere
    if head == "pushd" and target is not None:
        stack.append((cur, unknown))
    new = None
    if target is not None:  # -P: symlinks resolved first; else logical, where `x/..` drops x
        new = (os.path.realpath if physical else os.path.normpath)(_resolve(target, cur))
    if new is None or not os.path.isdir(new):
        # the cd may fail (bash keeps OLDPWD) or succeed (OLDPWD becomes cur): known only when both are the same
        # (TASK-067 final review gate: `cd /tmp; cd /nonexistent; cd -; rm -rf data`)
        same = not unknown and not old_unknown and old is not None and old == cur
        state.update(olddir=cur, olddir_unknown=not same, dir_unknown=True)
        return
    state.update(
        olddir=cur, olddir_unknown=unknown, dir=new, dir_unknown=unknown and not os.path.isabs(target or "")
    )


# `git config` keys that change what a later git command in the same command line runs or pushes: an alias,
# an include, a push target, or a branch's upstream, which push.default=upstream pushes to (TASK-067 review
# gate: `git config alias.p push && git p origin HEAD:dev`; round 3: `git config branch.<b>.merge …`)
CONFIG_STEERS_GIT = re.compile(
    r"alias\..+|include(if\..+)?\.path|remote\..+\.(push|mirror)|push\.(default|followtags)|remote\.pushdefault"
    r"|branch\..+\.(merge|remote|pushremote)",
    re.IGNORECASE,
)
CONFIG_READS = {
    "--get",
    "--get-all",
    "--get-regexp",
    "--get-urlmatch",
    "--get-color",
    "--get-colorbool",
    "--list",
    "-l",
    "--unset",
    "--unset-all",
    "get",
    "list",
    "unset",
    "get-color",
    "get-colorbool",
}
CONFIG_VALUE_OPTS = {"-f", "--file", "--blob", "--type", "-t", "--default", "--comment", "--value"}


def config_steers_git(argv: list[str], directory: str) -> bool:
    """Does this `git config …` write a `CONFIG_STEERS_GIT` key (`git config [--add|--replace-all] alias.p
    push`, `git config set …`), or open the file in an editor or rename a section (`--edit`,
    `--rename-section`)? Or does another git command write such config (review gate round 3): `git remote add
    --mirror…` (a mirror remote), `git remote set-branches`, `git branch -u/--set-upstream-to/-t/--track` (an
    upstream). (A `checkout`/`switch`/`worktree add` that writes an upstream is `creates_with_upstream`.)"""
    g = git_subcommand(argv, directory)
    if g is not None and g[0] == "remote" and g[1][:1] == ["add"]:
        return any(a.startswith("--mirror") for a in g[1])
    if g is not None and g[0] == "remote" and g[1][:1] == ["set-branches"]:
        return True
    if g is not None and g[0] == "branch":
        return any(
            a.startswith(("--set-upstream", "--track"))
            or (a.startswith("-") and not a.startswith("--") and ("u" in a[1:] or "t" in a[1:]))
            for a in g[1]
        )
    if g is None or g[0] != "config":
        return False
    positionals, opts, skip = [], [], False
    for a in g[1]:
        if skip:
            skip = False
        elif a in CONFIG_VALUE_OPTS:
            skip = True
        elif a.startswith("-"):
            opts.append(a.partition("=")[0])
        else:
            positionals.append(a)
    verb = (
        positionals[0]
        if positionals and positionals[0] in CONFIG_READS | {"set", "edit", "rename-section"}
        else None
    )
    if {"-e", "--edit", "--rename-section"} & set(opts) or verb in ("edit", "rename-section"):
        return True
    if (verb is not None and verb != "set") or CONFIG_READS & set(opts):
        return False
    keys = positionals[1:] if verb == "set" else positionals
    return len(keys) >= 2 and CONFIG_STEERS_GIT.fullmatch(keys[0]) is not None  # <name> <value>


# options of checkout/switch/worktree add whose value is the next word (so it is no start point)
BRANCH_CREATE_VALUE_OPTS = {
    "-b",
    "-B",
    "-c",
    "-C",
    "--create",
    "--force-create",
    "--orphan",
    "--conflict",
    "--reason",
}


def creates_with_upstream(sub: str, args: list[str], directory: str) -> bool:
    """Does this `git checkout`/`switch`/`worktree add` write a new branch's upstream (`branch.<b>.merge`), which
    push.default=upstream pushes to? `-t`/`--track` (alone or in a short cluster: `-qt`), or a new branch (`-b`,
    `-B`, `-c`, `-C`) from a remote-tracking start point (branch.autoSetupMerge's default), unless `--no-track`
    (TASK-067 final review gate: `git checkout -b x -t origin/dev && git push`)."""
    if sub == "worktree":
        if args[:1] != ["add"]:
            return False
        args = args[1:]
    opts = args[: args.index("--")] if "--" in args else args
    if "--no-track" in opts:
        return False
    if any(
        a == "--track" or a.startswith("--track=") or (a[:1] == "-" and a[1:2] != "-" and "t" in a[1:])
        for a in opts
    ):
        return True
    creates = any(
        a in ("--create", "--force-create")
        or a.startswith(("--create=", "--force-create="))
        or (a[:1] == "-" and a[1:2] != "-" and any(c in "bBcC" for c in a[1:]))
        for a in opts
    )
    if not creates:
        return False
    positionals, skip = [], False
    for a in opts:
        if skip:
            skip = False
        elif a in BRANCH_CREATE_VALUE_OPTS:
            skip = True
        elif a[:1] == "-" and a[1:2] != "-" and a[-1:] in "bBcC":
            skip = True  # `-qb <new>`: the cluster ends in a value-taking letter
        elif not a.startswith("-"):
            positionals.append(a)
    # checkout/switch: [<start>]; worktree add: <path> [<start>]
    start = positionals[1:2] if sub == "worktree" else positionals[:1]
    return any(
        "$" in p
        or p.startswith(("refs/remotes/", "remotes/"))
        or git(directory, "rev-parse", "--verify", "--quiet", f"refs/remotes/{p}") != ""
        for p in start
    )


def _context(argv: Argv, state: dict) -> Argv:
    """`argv` with what the walk knows when it runs (`Argv.shell_vars`, `.olddir`, `.dir_unknown`,
    `.env_empty`)."""
    argv.shell_vars = dict(state.get("vars", {}))
    argv.olddir = None if state.get("olddir_unknown") else state.get("olddir")
    argv.dir_unknown = state.get("dir_unknown", False)
    argv.env_empty = state.get("env_empty", False)
    return argv


FILE_WRITERS_LAST = {"cp", "mv", "ln", "install"}  # the last path word is written


def is_git_config_file(word: str, resolved: str | None) -> bool:
    """Is this written path a git config file: `.git/config`, `.git/config.worktree`, `.git/worktrees/<w>/config*`,
    `~/.gitconfig`, `$XDG_CONFIG_HOME/git/config`? `resolved` is the path as `expand_word` reads it (None when it
    can't), when only the word is known, a `config` file under a directory it can't read counts too."""
    parts = (resolved if resolved is not None else word).replace("\\", "/").rstrip("/").lower().split("/")
    name = parts[-1]
    if name == ".gitconfig" or (len(parts) >= 3 and parts[-3] == "worktrees" and name.startswith("config")):
        return True
    if name not in ("config", "config.worktree"):
        return False
    return resolved is None or (len(parts) >= 2 and parts[-2] in (".git", "git"))


def writes_git_config(argv: Argv, redirects: list[tuple[str, str]], state: dict) -> bool:
    """Does this command write a git config file (`>`/`>>`, tee, sed/perl -i, cp/mv/ln/install, dd of=)? Then
    config a later git command reads was written after this parser read it (review gate round 3: `echo
    "[alias] p = push" >> .git/config; git p origin HEAD:dev`)."""
    targets = [t for op, t in redirects if ">" in op and not (op.endswith("&") and t.isdigit())]
    words = [w for w in argv[1:] if not w.startswith("-")]
    head = argv[0] if argv else ""
    if head == "tee" or (head in ("sed", "perl") and any(w.startswith("-") and "i" in w for w in argv[1:])):
        targets += words
    elif head in FILE_WRITERS_LAST and words:
        targets.append(words[-1])
    elif head == "dd":
        targets += [w[3:] for w in argv[1:] if w.startswith("of=")]
    d = None if state.get("dir_unknown") else state["dir"]
    for t in targets:
        r = expand_word(t, d, state.get("vars"), env_empty=state.get("env_empty", False))
        if is_git_config_file(t, None if r is None else os.path.join(d or "", r)):
            return True
    return False


# a word `eval` would read again as the same one word
PLAIN_WORD = re.compile(r"[\w./:@%+=-]+")

# what a `bash -c` child shell changes without changing its caller's
SUBSHELL_STATE = (
    "exports",
    "vars",
    "dir",
    "dir_unknown",
    "olddir",
    "olddir_unknown",
    "dirstack",
    "allexport",
)


# A `for v in <words>; do …; done` is read as `v=<word>; …` once per word (`_unroll_for`), up to LOOP_WORDS words
# and LOOP_BUDGET tokens of unrolled body per command; past either, or with a LOOP_EXITS word in the body (the
# loop may stop at an earlier word), it is left as written, and `$v` stays unknown.
LOOP_WORDS = 64
LOOP_BUDGET = 20000
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _unroll_for(tokens: list[str], i: int, j: int, state: dict) -> list[str] | None:
    """`tokens` with the `for NAME in WORDS` loop whose header is `tokens[i:j]` written out: `NAME=<word> ;
    <body> ;` for each word, so `$NAME` is each word in turn (TASK-067 final review gate: `for f in /tmp/a /tmp/b;
    do rm -f "$f"; done` was refused). None when `tokens[i:j]` is no such loop header, or it can't be unrolled
    (no `in`, too many words, no matching `done`, a body that can leave the loop early, or past LOOP_BUDGET):
    the loop is then read as written and `$NAME` stays unknown."""
    k = i
    while k < j and tokens[k] in RESERVED:
        k += 1
    if k + 2 >= j or tokens[k] != "for" or not NAME.fullmatch(tokens[k + 1]) or tokens[k + 2] != "in":
        return None
    words = tokens[k + 3 : j]
    if len(words) > LOOP_WORDS:
        return None
    p = j + 1
    while p < len(tokens) and is_separator(tokens[p]):
        p += 1
    depth, end = 0, -1
    for q in range(p, len(tokens)):
        at_start = q == p or is_separator(tokens[q - 1]) or tokens[q - 1] in RESERVED
        if at_start and tokens[q] == "do":
            depth += 1
        elif at_start and tokens[q] == "done":
            depth -= 1
            if depth == 0:
                end = q
                break
    if end < 0 or tokens[p : p + 1] != ["do"]:
        return None
    body = tokens[p:end]
    if any(t in LOOP_EXITS for t in body):
        return None  # a loop left early leaves NAME at an earlier word than the last: unknown (confirmation pass)
    state["unrolled"] = state.get("unrolled", 0) + len(words) * (len(body) + 3)
    if state["unrolled"] > LOOP_BUDGET:
        return None
    out = [t for w in words for t in (f"{tokens[k + 1]}={w}", ";", *body, ";")]
    return [*tokens[:i], *out, *tokens[end + 1 :]]


def _walk(tokens: list[str], state: dict) -> Iterator[tuple[Argv, str, list[tuple[str, str]]]]:
    i = 0
    while i < len(tokens):
        j = i
        while j < len(tokens) and not is_separator(tokens[j]):
            j += 1
        if (unrolled := _unroll_for(tokens, i, j, state)) is not None:
            tokens = unrolled
            continue
        raw, i = tokens[i:j], j + 1
        args, redirects = split_redirects(raw)
        argv = strip_prefixes(args, state)
        if writes_git_config(argv, redirects, state):
            state["config_written"] = True
        if note_exports(argv, state) or not argv:
            if redirects:
                yield _context(Argv([]), state), state["dir"], redirects
            continue
        argv.assigns = {**state.get("exports", {}), **argv.assigns}
        head = argv[0]
        if head == "git":
            if state.get("config_written"):
                # the config this git command reads was written earlier in the same command line, after this
                # hook read it: what it runs can't be told (TASK-067 review gate)
                raise FailClosed(
                    "an earlier `git config` in this command sets an alias, include or push target"
                )
            if state.get("git_c") or state.get("git_dir"):
                # inside a `!shell` alias: git hands its -c settings (GIT_CONFIG_PARAMETERS) and git dir
                # (GIT_DIR) on to the git commands the alias runs; an explicit GIT_DIR= still wins
                gd = {"GIT_DIR": state["git_dir"]} if state.get("git_dir") else {}
                argv = Argv(
                    ["git", *state.get("git_c", []), *argv[1:]], argv.via_xargs, {**gd, **argv.assigns}
                )
            # an alias is replaced by what git runs for it (TASK-067: `git -c alias.p=push p origin x`)
            for expanded, d in expand_git_alias(argv, state["dir"], state.get("depth", 0)):
                state["config_written"] = state.get("config_written") or config_steers_git(expanded, d)
                g = git_subcommand(expanded, d)
                if g is not None and g[0] == "push" and state.get("upstream_written"):
                    # push.default=upstream pushes to the upstream an earlier command wrote (TASK-067 final review)
                    raise FailClosed(
                        "an earlier checkout/switch/worktree add in this command sets an upstream"
                    )
                if g is not None and g[0] in ("checkout", "switch", "worktree"):
                    state["upstream_written"] = state.get("upstream_written") or creates_with_upstream(*g)
                yield _context(expanded, state), d, redirects
            continue
        if head in ("cd", "pushd", "popd"):
            _change_dir(head, argv[1:], state, getattr(argv, "assigns", {}))
            continue
        if head in SHELLS:
            for k, a in enumerate(argv[1:], start=1):
                if a.startswith("-") and not a.startswith("--") and "c" in a and k + 1 < len(argv):
                    # a child shell: it starts with the caller's exports plus the assignments before it
                    # (`GIT_DIR=… bash -c 'git commit'`: review gate round 3), and what it sets or `cd`s to
                    # stays inside it
                    saved = {key: state[key] for key in SUBSHELL_STATE if key in state}
                    state["exports"] = dict(argv.assigns)
                    state["vars"] = {**state.get("vars", {}), **argv.assigns}
                    state["dirstack"] = list(state.get("dirstack", []))
                    try:
                        for inner in _walk(tokenize(argv[k + 1]), state):
                            # `xargs sh -c 'git push origin "$0"'`: the words still come from xargs
                            inner[0].via_xargs = inner[0].via_xargs or argv.via_xargs
                            yield inner
                    finally:
                        for key in SUBSHELL_STATE:
                            state.pop(key, None)
                        state.update(saved)
                    break
            else:
                # `bash script.sh`: a script this parser can't read; a gate may want to know it ran
                yield _context(argv, state), state["dir"], redirects
            continue
        if head == "eval":
            # bash reads the joined words again; words with nothing in them to re-read are taken as they are (an
            # `eval eval … git push` chain stays linear)
            rest = argv[1:]
            plain = all(PLAIN_WORD.fullmatch(w) for w in rest)
            yield from _walk(rest if plain else tokenize(" ".join(rest)), state)
            continue
        yield _context(argv, state), state["dir"], redirects


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


def git_anchored(argv: list[str]) -> bool:
    """Does this `git ...` argv name its repository absolutely (an absolute `-C`, `--git-dir` or `GIT_DIR=`), so
    that a `cd` before it that this parser couldn't follow doesn't matter?"""
    if not argv or argv[0] != "git":
        return False
    gitdir = getattr(argv, "assigns", {}).get("GIT_DIR") or ""
    anchored = os.path.isabs(gitdir)
    j = 1
    while j < len(argv) and argv[j].startswith("-"):
        opt, eq, attached = argv[j].partition("=") if argv[j].startswith("--") else (argv[j], "", "")
        if opt not in GIT_VALUE_OPTS:
            j += 1
            continue
        value = attached if eq else (argv[j + 1] if j + 1 < len(argv) else "")
        j += 1 if eq else 2
        anchored = anchored or (opt in ("-C", "--git-dir") and os.path.isabs(value))
    return anchored


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


# The config a refspec-less `git push` reads to choose what it sends and where
PUSH_CONFIG = r"^(remote\..*\.(push|mirror)|push\.(default|followtags)|remote\.pushdefault)$"


def push_config(argv: list[str], directory: str) -> dict[str, str]:
    """The repo's effective push config for a `git ...` argv (local, global and system files, of its -C /
    --git-dir / GIT_DIR repo), keys lower-cased; a key set without a value is ''. A refspec-less push reads it
    (TASK-067 review gate: `git config remote.origin.push x:refs/heads/dev`, then `git push origin`). Config
    this can't read (GIT_COMMON_DIR, GIT_CONFIG_*, …) is `git_config_opaque`, which the gates refuse first."""
    _, eff, _, gitdir, _ = _git_options(argv, directory)
    out = git(eff, *(["--git-dir", gitdir] if gitdir else []), "config", "--get-regexp", PUSH_CONFIG)
    found = {}
    for line in out.splitlines():
        key, _, value = line.partition(" ")
        found[key.lower()] = value
    return found


def git_bool(value: str) -> bool:
    """git's reading of a boolean config value ('' is a key set with no value: true)."""
    v = value.strip().lower()
    return v in ("", "true", "yes", "on") or (v.lstrip("-").isdigit() and int(v) != 0)


def push_config_risk(config: dict[str, str]) -> str | None:
    """The key of `push_config` that makes a refspec-less push send more than the current branch to its own
    name: `remote.<name>.push` (any refspec), `remote.<name>.mirror` true, or `push.default=matching`."""
    for key, value in config.items():
        if re.fullmatch(r"remote\..+\.push", key) or (
            re.fullmatch(r"remote\..+\.mirror", key) and git_bool(value)
        ):
            return key
        if key == "push.default" and value.strip().lower() == "matching":
            return key
    return None


@functools.lru_cache(maxsize=256)
def repo_root(directory: str) -> str:
    """Top of the git worktree containing `directory` — walking up to the nearest existing ancestor
    first, because a Write may target a directory that doesn't exist yet (data/indexes/<new>/)."""
    d = os.path.abspath(directory)
    while not os.path.isdir(d) and os.path.dirname(d) != d:
        d = os.path.dirname(d)
    return git(d, "rev-parse", "--show-toplevel") or d
