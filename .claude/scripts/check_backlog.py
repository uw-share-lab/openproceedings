#!/usr/bin/env python3
"""CI check (skill: task-hygiene). Exits 1 listing every problem it finds:

- a task whose status is Done but still sits in backlog/tasks/ (move it with `backlog task complete <id>`);
- two files in backlog/tasks/ + backlog/completed/ with the same task id, or two files in backlog/decisions/
  with the same decision id. `dev` merges through a queue without the up-to-date rule (decision-027), so two
  PRs that each ran `backlog task create` get different filenames, no git conflict, and the same id;
- a file in those directories whose id it can't read (fails closed).

The id comes from the frontmatter `id:` field, else the filename prefix, and is compared by number:
TASK-075, task-75 and 'task-075' are one id. backlog/archive/ is not compared: Backlog.md 1.53 hands an
archived task's id to the next `backlog task create` (task-075 twice, 2026-09-26; skill task-hygiene), and
nothing in a PR can renumber an archived file."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

BACKLOG = Path(__file__).resolve().parents[2] / "backlog"
STATUS = re.compile(r"^status:\s*['\"]?([^'\"\n]+)", re.MULTILINE)
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.DOTALL)
ID_FIELD = re.compile(r"^id:\s*['\"]?([^'\"\n]*?)['\"]?\s*$", re.MULTILINE)
# GROUPS: the directories whose files must not share an id, and the id prefix their files carry
GROUPS = {"task": ("tasks", "completed"), "decision": ("decisions",)}


def parse_id(kind: str, text: str, name: str) -> tuple[int, ...] | None:
    """The id's number (a tuple, so a subtask 12.1 differs from 12) or None if neither source reads as `kind`."""
    pattern = re.compile(rf"{kind}-(\d+(?:\.\d+)*)", re.IGNORECASE)
    fm = FRONTMATTER.match(text.replace("\r\n", "\n").lstrip("﻿"))
    field = ID_FIELD.search(fm.group(1)) if fm else None
    m = pattern.fullmatch(field.group(1).strip()) if field else pattern.match(name)
    return tuple(int(n) for n in m.group(1).split(".")) if m else None


def main() -> int:
    problems: list[str] = []

    tasks = sorted((BACKLOG / "tasks").glob("*.md"))
    for p in tasks:
        m = STATUS.search(p.read_text(encoding="utf-8"))
        if m and m.group(1).strip().lower() == "done":
            problems.append(f"'{p.name}' is Done but still in backlog/tasks/ — run `backlog task complete <id>`")

    clashes = 0
    for kind, dirs in GROUPS.items():
        seen: defaultdict[tuple[int, ...], list[str]] = defaultdict(list)
        for d in dirs:
            for p in sorted((BACKLOG / d).glob("*.md")):
                num = parse_id(kind, p.read_text(encoding="utf-8"), p.name)
                if num is None:
                    problems.append(f"'{d}/{p.name}' has no readable {kind} id (frontmatter `id:` or filename)")
                else:
                    seen[num].append(f"{d}/{p.name}")
        for num, files in sorted(seen.items()):
            if len(files) > 1:
                clashes += 1
                ident = f"{kind}-{'.'.join(map(str, num))}"
                problems.append(
                    f"{ident} is used by {len(files)} files: {'; '.join(files)} — the later PR rebases onto dev "
                    f"and creates its copy again with the CLI (skill task-hygiene, §Ids)"
                )

    for line in problems:
        print(f"backlog: {line}", file=sys.stderr)
    print(f"backlog: {len(tasks)} open task files, {len(problems)} problem(s), {clashes} duplicate id(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
