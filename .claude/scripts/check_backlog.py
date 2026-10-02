#!/usr/bin/env python3
"""CI check (skill: task-hygiene). Exits 1 listing every problem it finds:

- a task whose status is Done but still sits in backlog/tasks/ (move it with `backlog task complete <id>`);
- two files in backlog/tasks/ + backlog/completed/ with the same task id, or two files in backlog/decisions/
  with the same decision id. `dev` merges through a queue without the up-to-date rule (decision-027), so two
  PRs that each ran `backlog task create` get different filenames, no git conflict, and the same id;
- a file in those directories with no frontmatter, with frontmatter YAML it doesn't read line by line (a
  `{` flow mapping, a `?` key), with an id it can't read or more than one `id:`, or whose frontmatter id
  disagrees with its filename prefix (the CLI always writes them equal, so any of these is a hand edit that
  could hide a duplicate). A missing tasks/ or completed/ directory fails too.

The id comes from the frontmatter `id:` field, else (no `id:` in the frontmatter) the filename prefix, and is compared by number:
TASK-075, task-75 and 'task-075' are one id, and a subtask 12.1 is not 12. backlog/archive/ is not compared:
Backlog.md 1.53 hands an archived task's id to the next `backlog task create` (task-075 twice, 2026-09-26;
skill task-hygiene), nothing in a PR can renumber an archived file, and archiving one copy of a duplicate is
a deliberate act that takes it off the board."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

BACKLOG = Path(__file__).resolve().parents[2] / "backlog"
STATUS = re.compile(r"""^[ \t]*['"]?status['"]?[ \t]*:\s*['"]?([^'"\n]+)""", re.MULTILINE)
FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
# an `id` key, however a hand edit spells it: quoted ("id"), or with a space before the colon (id :); the
# value is checked in read_id, so a value of any other shape fails instead of hiding the line
ID_FIELD = re.compile(r"""^[ \t]*['"]?id['"]?[ \t]*:(.*)$""", re.MULTILINE)
# YAML this check doesn't read line by line: a flow mapping ({id: …}) or an explicit key (? id)
UNREAD_YAML = re.compile(r"^[ \t]*[{?]", re.MULTILINE)
# GROUPS: the directories whose files must not share an id, and the id prefix their files carry
GROUPS = {"task": ("tasks", "completed"), "decision": ("decisions",)}
REQUIRED = ("tasks", "completed")


def id_pattern(kind: str) -> re.Pattern[str]:
    return re.compile(rf"{kind}-([0-9]+(?:\.[0-9]+)*)(?![0-9A-Za-z]|\.[0-9])", re.IGNORECASE)


def number(m: re.Match[str] | None) -> tuple[int, ...] | None:
    return tuple(int(n) for n in m.group(1).split(".")) if m else None


def read_id(kind: str, text: str, name: str) -> tuple[tuple[int, ...] | None, str]:
    """(the id's number, "") or (None, why it can't be read). The number is a tuple: 12.1 is not 12."""
    pattern = id_pattern(kind)
    from_name = number(pattern.match(name))
    fm = FRONTMATTER.match(text)
    if fm is None:
        return None, "has no frontmatter (it must start with a `---` line)"
    if UNREAD_YAML.search(fm.group(1)):
        return None, "has frontmatter this check can't read (a `{` flow mapping or a `?` key)"
    fields = ID_FIELD.findall(fm.group(1))
    if len(fields) > 1:
        return None, f"has {len(fields)} `id:` fields in its frontmatter"
    if not fields:
        if from_name is None:
            return None, f"has no readable {kind} id (frontmatter `id:` or filename)"
        return from_name, ""
    value = fields[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1].strip()
    from_field = number(pattern.fullmatch(value))
    if from_field is None:
        return None, f"has no readable {kind} id in its frontmatter `id:`"
    if from_name is not None and from_name != from_field:
        return None, "has a frontmatter `id:` that disagrees with its filename prefix"
    return from_field, ""


def main() -> int:
    problems = [f"backlog/{d}/ is missing" for d in REQUIRED if not (BACKLOG / d).is_dir()]

    texts: dict[Path, str] = {}
    for d in sorted({d for dirs in GROUPS.values() for d in dirs}):
        for p in sorted((BACKLOG / d).glob("*.md")):
            try:
                texts[p] = p.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as e:
                problems.append(f"'{d}/{p.name}' can't be read as UTF-8 ({type(e).__name__})")

    tasks = sorted((BACKLOG / "tasks").glob("*.md"))
    for p in tasks:
        m = STATUS.search(texts.get(p, ""))
        if m and m.group(1).strip().lower() == "done":
            problems.append(
                f"'{p.name}' is Done but still in backlog/tasks/ — run `backlog task complete <id>`"
            )

    clashes = 0
    for kind, dirs in GROUPS.items():
        seen: defaultdict[tuple[int, ...], list[str]] = defaultdict(list)
        for d in dirs:
            for p in sorted((BACKLOG / d).glob("*.md")):
                if p not in texts:
                    continue  # already reported as unreadable
                num, why = read_id(kind, texts[p], p.name)
                if num is None:
                    problems.append(f"'{d}/{p.name}' {why}")
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
