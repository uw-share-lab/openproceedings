#!/usr/bin/env python3
"""CI check (skill: task-hygiene): a task whose status is Done must have been moved to backlog/completed/
with `backlog task complete <id>`. Exits 1 listing every Done task still sitting in backlog/tasks/."""

from __future__ import annotations

import re
import sys
from pathlib import Path

TASKS = Path(__file__).resolve().parents[2] / "backlog" / "tasks"
STATUS = re.compile(r"^status:\s*['\"]?([^'\"\n]+)", re.MULTILINE)

stale = []
for p in sorted(TASKS.glob("*.md")):
    m = STATUS.search(p.read_text(encoding="utf-8"))
    if m and m.group(1).strip().lower() == "done":
        stale.append(p.name)
for name in stale:
    print(
        f"backlog: '{name}' is Done but still in backlog/tasks/ — run `backlog task complete <id>`",
        file=sys.stderr,
    )
print(f"backlog: {len(list(TASKS.glob('*.md')))} open task files, {len(stale)} Done-but-not-completed")
sys.exit(1 if stale else 0)
