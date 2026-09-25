"""Shared command-string parsing for the openproceedings PreToolUse(Bash) gates.

Splits a Bash tool command into simple commands (argv lists), tracking `cd <dir>` and recursing into
`bash -c "..."` / `sh -lc '...'` / `eval "..."` the same way enforce-pr-workflow.sh does. Each simple
command is yielded with the directory it would run in, so a gate can ask git about the right worktree.

Threat model (same as enforce-pr-workflow.sh): a guardrail against honest mistakes, not an adversarial
control. `$(...)`, variables and script files are opaque to a static parser.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from collections.abc import Iterator

SEPARATORS = {"&&", "||", ";", "|", "&"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


class ParseError(Exception):
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


def _resolve(candidate: str, base: str) -> str:
    return candidate if os.path.isabs(candidate) else os.path.normpath(os.path.join(base, candidate))


def simple_commands(cmd: str, cwd: str) -> Iterator[tuple[list[str], str]]:
    """Yield (argv, directory) for every simple command in `cmd`. Raises ParseError on bad quoting."""
    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError as exc:
        raise ParseError(str(exc)) from exc
    state = {"dir": cwd}
    yield from _walk(tokens, state)


def _walk(tokens: list[str], state: dict) -> Iterator[tuple[list[str], str]]:
    i = 0
    while i < len(tokens):
        j = i
        while j < len(tokens) and tokens[j] not in SEPARATORS:
            j += 1
        argv, i = tokens[i:j], j + 1
        if not argv:
            continue
        head = argv[0]
        if head == "cd" and len(argv) > 1 and not argv[1].startswith("-"):
            state["dir"] = _resolve(argv[1], state["dir"])
            continue
        if head in SHELLS:
            for k, a in enumerate(argv[1:], start=1):
                if a.startswith("-") and not a.startswith("--") and "c" in a and k + 1 < len(argv):
                    try:
                        inner = shlex.split(argv[k + 1], posix=True)
                    except ValueError as exc:
                        raise ParseError(str(exc)) from exc
                    yield from _walk(inner, state)
                    break
            continue
        if head == "eval":
            try:
                inner = shlex.split(" ".join(argv[1:]), posix=True)
            except ValueError as exc:
                raise ParseError(str(exc)) from exc
            yield from _walk(inner, state)
            continue
        yield argv, state["dir"]


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
    """For `gh <group> <verb> ...` return (group, verb, args); else None."""
    if len(argv) >= 3 and argv[0] == "gh":
        return argv[1], argv[2], argv[3:]
    return None


def opt_value(args: list[str], *names: str) -> str | None:
    """Value of the first matching option, supporting `--opt value` and `--opt=value`."""
    for k, a in enumerate(args):
        for n in names:
            if a == n and k + 1 < len(args):
                return args[k + 1]
            if n.startswith("--") and a.startswith(n + "="):
                return a.split("=", 1)[1]
    return None


def opt_values(args: list[str], *names: str) -> list[str]:
    out = []
    for k, a in enumerate(args):
        for n in names:
            if a == n and k + 1 < len(args):
                out.append(args[k + 1])
            elif n.startswith("--") and a.startswith(n + "="):
                out.append(a.split("=", 1)[1])
    return out


def git(directory: str, *args: str) -> str:
    """Run git in `directory`; return stripped stdout, or '' on any failure."""
    try:
        r = subprocess.run(["git", "-C", directory, *args], capture_output=True, text=True, timeout=10)
    except Exception:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""
