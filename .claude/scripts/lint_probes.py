#!/usr/bin/env python3
"""Lint the case tables: a hook probe reaches the hook only as data (TASK-169).

    python3 .claude/scripts/lint_probes.py [table.sh ...]   # default: every .claude/{hooks,scripts}/tests/*.sh

A probe is a hostile string by design (2026-10-02: a probe's own `rm -rf data` ran in the home folder). The
tables hand each one to a `payload*` helper or a `check*` row, which builds the hook's JSON in Python from its
argv, so bash never runs it. What bash would still run is an argument holding a command substitution: a `$(` or a
backquote in double quotes or unquoted (in a probe, a row's label or its command) is run by the shell while the
table runs. The one allowed is the `"$(payload_… …)"` a row wraps its payload in, whose own arguments are linted.
Write a probe in single quotes, or as `$'…'` when it needs a newline or a backslash, compute a value the row
needs into a variable on the line before, or read the probe from a data file. Exit 1 on any finding.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# a call of a payload helper or a case-table row (not a definition: `payload_bash() {`)
CALL = re.compile(r"(?<![\w-])(?:payload|check)\w*(?![\w(=-])(?!\s*\(\))")
WRAPPER = re.compile(
    r"\$\(\s*payload\w*\s"
)  # a row's `"$(payload_… …)"`: the payload call is linted on its own
# what may come before a call on its line: nothing, a separator, or the `$(` a row wraps it in, then any
# `NAME=value` prefixes (`HOME=… check …`)
COMMAND_START = re.compile(r"(?:^|[;&|(]|\$\()\s*(?:\w+=(?:\"[^\"]*\"|'[^']*'|[^\s\"'])*\s+)*$")
ENDS = set(";&|\n")  # outside quotes, these end the call's words


def _single_end(text: str, k: int) -> int:
    """Just past the `'` closing a single-quoted string whose text starts at `text[k]` (or the end)."""
    e = text.find("'", k)
    return len(text) if e < 0 else e + 1


def _ansi_end(text: str, k: int) -> int:
    """Just past the `'` closing a `$'…'` string whose text starts at `text[k]` (`\\'` doesn't close it)."""
    while k < len(text) and text[k] != "'":
        k += 2 if text[k] == "\\" else 1
    return min(k + 1, len(text))


def _wrapper_end(text: str, k: int) -> int:
    """Just past the `)` closing the `$(payload_… …)` at `text[k]` (quotes skipped), or the end."""
    k, depth = k + 2, 1
    while k < len(text) and depth:
        c = text[k]
        if c == "\\":
            k += 2
            continue
        if c == "'":
            k = _single_end(text, k + 1)
            continue
        if text.startswith("$'", k):
            k = _ansi_end(text, k + 2)
            continue
        if c == '"':
            k += 1
            while k < len(text) and text[k] != '"':
                if text.startswith("$(", k):
                    k = _wrapper_end(text, k)  # a substitution inside: its own quotes (`"$(printf '"')"`)
                else:
                    k += 2 if text[k] == "\\" else 1
        depth += 1 if c == "(" else -1 if c == ")" else 0
        k += 1
    return k


def findings(text: str) -> list[int]:
    """The offsets in `text` where an argument of a payload helper or a row (its label, its command) holds a
    command substitution bash would run while the table runs; a row's `$(payload_… …)` is the one allowed."""
    out = []
    for m in CALL.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        if not COMMAND_START.search(text[line_start : m.start()]):
            continue  # not where a command goes: a comment, or a word in a label ("empty payload")
        k, n, depth, dq = m.end(), len(text), 0, False
        while k < n:
            c = text[k]
            if c == "\\":
                if not dq and text.startswith("\\\n", k):
                    k += 2  # a continuation: the call goes on
                    continue
                k += 2
                continue
            if WRAPPER.match(text, k):
                k = _wrapper_end(text, k)
                continue
            if dq:
                if c == '"':
                    dq = False
                elif c == "`" or text.startswith("$(", k):
                    out.append(k)
                    break
                k += 1
                continue
            if c == '"':
                dq = True
            elif c == "'":
                k = _single_end(text, k + 1)
                continue
            elif text.startswith("$'", k):
                k = _ansi_end(text, k + 2)
                continue
            elif c == "`" or text.startswith("$(", k):
                out.append(k)
                break
            elif c == "(":
                depth += 1
            elif c == ")":
                if depth == 0:
                    break  # the end of the `$(payload_… …)` the row wraps the call in
                depth -= 1
            elif c in ENDS or (c == "#" and text[k - 1] in " \t"):
                break
            k += 1
    return out


def main(argv: list[str]) -> int:
    tables = [Path(a) for a in argv] or sorted(
        [*ROOT.glob(".claude/hooks/tests/*.sh"), *ROOT.glob(".claude/scripts/tests/*.sh")]
    )
    bad = 0
    for t in tables:
        text = t.read_text(encoding="utf-8")
        for at in findings(text):
            bad += 1
            line = text.count("\n", 0, at) + 1
            print(
                f"{t}:{line}: bash runs this command substitution while the table runs; write the probe in "
                "single quotes or $'…', compute the value on the line before, or read it from a file (TASK-169)",
                file=sys.stderr,
            )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
