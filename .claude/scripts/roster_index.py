#!/usr/bin/env python3
"""Regenerate .claude/README.md — the roster of every agent, skill and command, grouped by area.

    python3 .claude/scripts/roster_index.py           # rewrite .claude/README.md
    python3 .claude/scripts/roster_index.py --check   # CI: fail if stale or an item has no area

The README is how people and agents discover the roster (the Kreate `.claude/README.md` pattern). It is
generated from each file's frontmatter so it cannot drift; the area comes from AREAS below — a new agent,
skill or command must be given an area here, or --check fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

C = Path(__file__).resolve().parents[1]

AREAS: dict[str, dict[str, list[str]]] = {
    "Global roles & process": {
        "agents": [
            "senior-engineer",
            "code-reviewer",
            "pr-reviewer",
            "security-reviewer",
            "qa-auditor",
            "docs-writer",
            "docs-reviewer",
            "project-manager",
            "learning-recorder",
        ],
        "skills": [
            "review-gates",
            "learnings",
            "repo-conventions",
            "pr-workflow",
            "no-ai-attribution",
            "spec-writing",
            "decision-records",
            "task-hygiene",
        ],
        "commands": [
            "review-gate",
            "open-pr",
            "record-learnings",
            "review-pr",
            "plan",
            "new-spec",
            "security-review",
            "audit",
            "write-docs",
            "review-docs",
        ],
    },
    "Engineering standards": {
        "agents": ["observability-reviewer"],
        "skills": [
            "python-standards",
            "typescript-standards",
            "testing-standards",
            "property-testing",
            "error-diagnostics",
            "autolint",
            "logging-standards",
        ],
        "commands": [],
    },
    "Ingestion (spec 01)": {
        "agents": [
            "openreview-crawler",
            "proceedings-miner",
            "ris-importer",
            "track-classifier-auditor",
            "dedup-auditor",
            "coverage-auditor",
        ],
        "skills": [
            "openreview-api",
            "openreview-venueids",
            "pmlr-proceedings",
            "neurips-proceedings",
            "record-schema",
            "track-taxonomy",
            "dedup-rules",
            "snapshots",
        ],
        "commands": ["coverage"],
    },
    "Query language (spec 02)": {
        "agents": [
            "grammar-engineer",
            "query-compat-translator",
            "parser-fuzzer",
            "query-semantics-reviewer",
        ],
        "skills": [
            "token-contract",
            "query-grammar",
            "wildcards-and-expansion",
            "scholar-syntax-compat",
            "default-filters",
        ],
        "commands": [],
    },
    "Search engine (spec 03)": {
        "agents": [
            "index-engineer",
            "exactness-guardian",
            "reference-oracle-keeper",
            "differential-tester",
            "ranking-engineer",
            "performance-profiler",
        ],
        "skills": [
            "tantivy-indexing",
            "ast-compilation",
            "reference-oracle",
            "field-weighted-bm25",
            "index-versioning",
        ],
        "commands": ["exactness-check"],
    },
    "Backend API (spec 04)": {
        "agents": [
            "api-engineer",
            "api-contract-reviewer",
            "export-format-validator",
            "search-records-keeper",
        ],
        "skills": ["fastapi-conventions", "api-contract", "ris-format", "bibtex-format", "search-records"],
        "commands": ["review-export"],
    },
    "Frontend (spec 05)": {
        "agents": [
            "frontend-engineer",
            "query-editor-engineer",
            "query-builder-engineer",
            "ux-reviewer",
            "accessibility-auditor",
            "e2e-tester",
        ],
        "skills": ["nextjs-conventions", "codemirror-lezer", "ui-design-system", "accessibility"],
        "commands": ["ux-review"],
    },
    "Human-centred design & HCI": {
        "agents": [
            "ux-designer",
            "hci-researcher",
            "usability-tester",
            "usability-auditor",
            "user-researcher",
            "ux-writer",
            "dataviz-designer",
        ],
        "skills": [
            "ux-design",
            "hci-methods",
            "usability-testing",
            "heuristic-evaluation",
            "user-research",
            "ux-writing",
            "research-dataviz",
        ],
        "commands": ["design-feature", "usability-study"],
    },
    "Semantic layer (spec 06)": {
        "agents": ["embedding-engineer", "near-miss-evaluator"],
        "skills": ["specter2-embeddings"],
        "commands": [],
    },
    "Evaluation & research (spec 07)": {
        "agents": ["scholar-comparison-analyst", "review-methodologist"],
        "skills": ["prisma-reporting", "scholar-comparison-protocol", "coverage-reporting"],
        "commands": ["scholar-compare"],
    },
    "Ops (spec 08)": {
        "agents": ["ci-engineer", "release-manager"],
        "skills": [],
        "commands": [],
    },
}

HEADER = """# `.claude/` — openproceedings agent tooling

Generated by `.claude/scripts/roster_index.py` from each file's frontmatter — do not edit by hand. The rules
live in [`CLAUDE.md`](../CLAUDE.md); the review routing table in
[`skills/review-gates/SKILL.md`](skills/review-gates/SKILL.md).

- **Agents** (`agents/`) do work; reviewer/auditor/guardian agents are read-only.
- **Skills** (`skills/`) hold the standards and domain knowledge agents cite.
- **Commands** (`commands/`) are the entry points.
- **Hooks** (`hooks/`, case tables in `hooks/tests/`) enforce the gates; **learnings** (`learnings/`) is the
  journal every session starts from.

"""


def describe(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^description:\s*(.*)$", text, re.MULTILINE)
    d = (m.group(1) if m else "").strip().strip('"')
    first = re.split(r"(?<=[.;—])\s", d, maxsplit=1)[0]
    return first.rstrip(" —;")


def build() -> tuple[str, list[str]]:
    have = {
        "agents": {p.stem: p for p in (C / "agents").glob("*.md")},
        "skills": {p.parent.name: p for p in (C / "skills").glob("*/SKILL.md")},
        "commands": {p.stem: p for p in (C / "commands").glob("*.md")},
    }
    problems, placed = [], {k: set() for k in have}
    out = [HEADER]
    counts = {k: len(v) for k, v in have.items()}
    out.append(f"**{counts['agents']} agents · {counts['skills']} skills · {counts['commands']} commands**\n")
    for area, groups in AREAS.items():
        out.append(f"\n## {area}\n")
        for kind in ("agents", "skills", "commands"):
            names = groups[kind]
            if not names:
                continue
            out.append(f"\n| {kind[:-1].capitalize()} | What it's for |\n|---|---|")
            for n in names:
                if n not in have[kind]:
                    problems.append(f"AREAS lists {kind[:-1]} '{n}' but no such file exists")
                    continue
                placed[kind].add(n)
                link = {
                    "agents": f"agents/{n}.md",
                    "skills": f"skills/{n}/SKILL.md",
                    "commands": f"commands/{n}.md",
                }[kind]
                label = f"/{n}" if kind == "commands" else n
                out.append(f"| [`{label}`]({link}) | {describe(have[kind][n])} |")
            out.append("")
    for kind in have:
        for n in sorted(set(have[kind]) - placed[kind]):
            problems.append(
                f"{kind[:-1]} '{n}' has no area — add it to AREAS in .claude/scripts/roster_index.py"
            )
    return "\n".join(out).rstrip() + "\n", problems


def main() -> None:
    content, problems = build()
    target = C / "README.md"
    for p in problems:
        print(f"roster: {p}", file=sys.stderr)
    if "--check" in sys.argv:
        stale = not target.exists() or target.read_text(encoding="utf-8") != content
        if stale:
            print(
                "roster: .claude/README.md is stale — run python3 .claude/scripts/roster_index.py",
                file=sys.stderr,
            )
        sys.exit(1 if (problems or stale) else 0)
    target.write_text(content, encoding="utf-8")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
