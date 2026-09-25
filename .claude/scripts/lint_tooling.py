#!/usr/bin/env python3
"""Lint the .claude/ roster (CI job `claude-tooling`). Exit 1 on any error.

Checks:
  agents/*.md        frontmatter name == filename, description says when to use it ("Use …"),
                     tools ⊆ KNOWN_TOOLS, reviewers/auditors/guardians are read-only, body non-trivial
  skills/*/SKILL.md  frontmatter name == directory, description says when to use it
  commands/*.md      frontmatter description
  references         every `.claude/skills/<x>/SKILL.md` and `.claude/agents/<x>.md` path mentioned
                     anywhere under .claude/ (and in CLAUDE.md) exists; every skill is referenced by at
                     least one agent or command (no orphans)
  settings.json      every hook command points at an executable file under .claude/hooks/
  roster floor       ≥ 25 agents and ≥ 25 skills (project target 25–150 of each)
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
C = ROOT / ".claude"
KNOWN_TOOLS = {
    "Read", "Write", "Edit", "MultiEdit", "Grep", "Glob", "Bash", "WebFetch", "WebSearch",
    "NotebookEdit", "Task", "Agent", "TodoWrite", "Skill",
}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
READ_ONLY_SUFFIXES = ("-reviewer", "-auditor", "-guardian", "-methodologist")
FLOOR = 25
REF = re.compile(r"\.claude/(skills/([a-z0-9-]+)/SKILL\.md|agents/([a-z0-9-]+)\.md)")

errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        err(f"{path.relative_to(ROOT)}: missing YAML frontmatter")
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        err(f"{path.relative_to(ROOT)}: unterminated frontmatter")
        return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, text[end + 4 :]


def lint_agents() -> set[str]:
    names = set()
    for p in sorted((C / "agents").glob("*.md")):
        meta, body = frontmatter(p)
        rel = p.relative_to(ROOT)
        names.add(p.stem)
        if meta.get("name") != p.stem:
            err(f"{rel}: name '{meta.get('name')}' != filename '{p.stem}'")
        desc = meta.get("description", "")
        if len(desc) < 60 or "Use " not in desc:
            err(f"{rel}: description must be ≥60 chars and say when to use it ('Use …')")
        tools = {t.strip() for t in meta.get("tools", "").split(",") if t.strip()}
        if not tools:
            err(f"{rel}: tools: list is required (least privilege)")
        if unknown := tools - KNOWN_TOOLS:
            err(f"{rel}: unknown tools {sorted(unknown)}")
        if p.stem.endswith(READ_ONLY_SUFFIXES) and tools & WRITE_TOOLS:
            err(f"{rel}: reviewer/auditor agents are read-only — drop {sorted(tools & WRITE_TOOLS)}")
        if len(body.split()) < 80:
            err(f"{rel}: body is too thin ({len(body.split())} words) — say how it works and what it outputs")
    return names


def lint_skills() -> set[str]:
    names = set()
    for d in sorted(p for p in (C / "skills").iterdir() if p.is_dir()):
        skill = d / "SKILL.md"
        rel = skill.relative_to(ROOT)
        names.add(d.name)
        if not skill.exists():
            err(f"{d.relative_to(ROOT)}: no SKILL.md")
            continue
        meta, body = frontmatter(skill)
        if meta.get("name") != d.name:
            err(f"{rel}: name '{meta.get('name')}' != directory '{d.name}'")
        desc = meta.get("description", "")
        if len(desc) < 60 or "Use " not in desc:
            err(f"{rel}: description must be ≥60 chars and say when to use it ('Use …')")
        if len(body.split()) < 120:
            err(f"{rel}: body is too thin ({len(body.split())} words)")
    return names


def lint_commands() -> None:
    for p in sorted((C / "commands").glob("*.md")):
        meta, _ = frontmatter(p)
        if not meta.get("description"):
            err(f"{p.relative_to(ROOT)}: description is required")


def lint_refs(agents: set[str], skills: set[str]) -> None:
    referenced: set[str] = set()
    sources = list(C.rglob("*.md")) + [ROOT / "CLAUDE.md"]
    for p in sources:
        if not p.exists() or "learnings" in p.parts:
            continue
        for m in REF.finditer(p.read_text(encoding="utf-8")):
            skill, agent = m.group(2), m.group(3)
            if skill and skill not in skills:
                err(f"{p.relative_to(ROOT)}: references missing skill '{skill}'")
            if agent and agent not in agents:
                err(f"{p.relative_to(ROOT)}: references missing agent '{agent}'")
            if skill and (p.parent.name != skill):  # a skill citing itself doesn't count
                referenced.add(skill)
    for s in sorted(skills - referenced):
        err(f".claude/skills/{s}: orphan — no agent, command or CLAUDE.md references it")


def lint_settings() -> None:
    settings = json.loads((C / "settings.json").read_text(encoding="utf-8"))
    for event, groups in settings.get("hooks", {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                cmd = h.get("command", "")
                m = re.search(r"\.claude/hooks/([\w.-]+)", cmd)
                if not m:
                    err(f"settings.json {event}: hook command outside .claude/hooks: {cmd}")
                    continue
                f = C / "hooks" / m.group(1)
                if not f.exists() or not os.access(f, os.X_OK):
                    err(f"settings.json {event}: {f.relative_to(ROOT)} missing or not executable")


def main() -> None:
    agents, skills = lint_agents(), lint_skills()
    lint_commands()
    lint_refs(agents, skills)
    lint_settings()
    if len(agents) < FLOOR:
        err(f"roster: {len(agents)} agents < floor {FLOOR}")
    if len(skills) < FLOOR:
        err(f"roster: {len(skills)} skills < floor {FLOOR}")
    for e in errors:
        print(f"✗ {e}", file=sys.stderr)
    n_cmd = len(list((C / "commands").glob("*.md")))
    print(f"{len(agents)} agents · {len(skills)} skills · {n_cmd} commands · {len(errors)} errors")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
