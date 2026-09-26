#!/usr/bin/env python3
"""Mutation-test the gates and tooling: every mutant must make at least one case table fail.

    python3 .claude/scripts/mutate.py              # all mutants (nightly CI, or after changing a gate)
    python3 .claude/scripts/mutate.py --changed    # only mutants in files changed vs origin/dev (reviews)
    python3 .claude/scripts/mutate.py --jobs 8     # parallelism (default: CPU count, max 8)
    python3 .claude/scripts/mutate.py --match glob # only mutants whose label contains "glob"

Mutants live in .claude/scripts/mutants/*.json as {label, file, old, new[, equivalent]}: `old` is replaced
by `new` once in `file`. A mutant marked "equivalent" is expected to survive (documented reason in the
label). A mutant whose `old` text no longer exists fails the run — update it, so the list never rots.
This is THE way to mutation-test here; don't hand-roll a serial loop (review round 3: ~33 min serial vs ~5
min parallel). Standard: .claude/skills/testing-standards/SKILL.md and .claude/agents/qa-auditor.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLES = sorted(
    str(p.relative_to(ROOT))
    for p in [*ROOT.glob(".claude/hooks/tests/*.sh"), *ROOT.glob(".claude/scripts/tests/*.sh")]
)
IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "node_modules", "__pycache__", "data", ".ruff_cache", ".mypy_cache"
)
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}  # never touch the real repo


def copy_tree(dest: Path) -> None:
    shutil.copytree(ROOT, dest, ignore=IGNORE)
    if (ROOT / ".venv").exists():
        os.symlink(ROOT / ".venv", dest / ".venv")


def failing_tables(tree: Path) -> list[str]:
    def run(t: str) -> str | None:
        r = subprocess.run(["bash", str(tree / t)], capture_output=True, text=True, env=ENV)
        return None if r.returncode == 0 else Path(t).name

    with ThreadPoolExecutor(max_workers=len(TABLES)) as ex:
        return [x for x in ex.map(run, TABLES) if x]


def changed_files() -> set[str]:
    r = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--name-only", "origin/dev...HEAD"], capture_output=True, text=True
    )
    s = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only"], capture_output=True, text=True)
    return set((r.stdout + s.stdout).split())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--changed", action="store_true")
    ap.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 4))
    ap.add_argument("--match", help="only mutants whose label contains this text (case-insensitive)")
    a = ap.parse_args()
    mutants = [
        m
        for f in sorted((ROOT / ".claude/scripts/mutants").glob("*.json"))
        for m in json.loads(f.read_text())
    ]
    if a.match:
        mutants = [m for m in mutants if a.match.lower() in m["label"].lower()]
    if a.changed:
        files = changed_files()
        mutants = [m for m in mutants if m["file"] in files]
    work = Path(tempfile.mkdtemp(prefix="op-mutate-"))
    try:
        base = work / "baseline"
        copy_tree(base)
        if bad := failing_tables(base):
            sys.exit(f"baseline is not green ({bad}) — fix the tables before mutation-testing")
        shutil.rmtree(base)

        def one(item: tuple[int, dict]) -> tuple[dict, str, list[str]]:
            i, m = item
            tree = work / f"m{i}"
            copy_tree(tree)
            p = tree / m["file"]
            text = p.read_text()
            if m["old"] not in text:
                shutil.rmtree(tree)
                return m, "STALE", []
            p.write_text(text.replace(m["old"], m["new"], 1))
            bad = failing_tables(tree)
            shutil.rmtree(tree)
            return m, ("KILLED" if bad else "SURVIVED"), bad

        problems = 0
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            for m, status, bad in ex.map(one, enumerate(mutants)):
                equivalent = m.get("equivalent", False)
                ok = status == "KILLED" or (status == "SURVIVED" and equivalent)
                problems += not ok
                mark = "ok  " if ok else "FAIL"
                print(
                    f"  {mark} {status:8} {m['label']}" + (f"  ({', '.join(bad)})" if bad else ""), flush=True
                )
        print(
            f"{len(mutants)} mutants: {problems} problem(s) (survivors not marked equivalent, or stale patterns)"
        )
        sys.exit(1 if problems else 0)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
