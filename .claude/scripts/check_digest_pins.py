#!/usr/bin/env python3
"""CI check (spec 08 §Deploy, TASK-149): every image a Dockerfile under deploy/ pulls is named
`name:tag@sha256:<digest>`, so a rebuild uses the image that was reviewed; Dependabot's `docker` entry bumps
the digests. That covers each `FROM`, a `# syntax=` parser directive (the BuildKit frontend), `COPY --from=`
and `RUN --mount=…,from=`. An earlier build stage (by name or index), or `scratch`, has no registry image to
pin. Instructions are read as Docker reads them: continuation lines joined, comments between them dropped.
Exits 1 listing every unpinned image."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
DIRECTIVE = re.compile(r"^#\s*([a-zA-Z]+)\s*=\s*(\S+)\s*$")
# FROM [--platform=…] <image> [AS <stage>]; the image may not hold an ARG, which no reviewer can see resolved
FROM = re.compile(r"^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?$", re.IGNORECASE)
COPY_FROM = re.compile(r"^COPY\s.*?--from=(\S+)", re.IGNORECASE)
MOUNT_FROM = re.compile(r"--mount=\S*?\bfrom=([^,\s]+)", re.IGNORECASE)
# a tag after the last `/` (a registry port is not a tag), then the 64-hex digest
PINNED = re.compile(r"^[^@\s$]+:[^@\s$/:]+@sha256:[0-9a-f]{64}$")


def instructions(text: str) -> tuple[dict[str, str], list[tuple[int, str]]]:
    """The leading parser directives, and each instruction with the line it starts on."""
    lines = text.splitlines()
    directives: dict[str, str] = {}
    i = 0
    while i < len(lines) and (m := DIRECTIVE.match(lines[i])):
        directives[m.group(1).lower()] = m.group(2)
        i += 1
    escape = directives.get("escape", "\\")
    out: list[tuple[int, str]] = []
    start, parts = 0, list[str]()
    for n, line in enumerate(lines[i:], i + 1):
        stripped = line.strip()
        if stripped.startswith("#") or (parts and not stripped):
            continue  # a comment, or a blank line inside a continuation
        if not parts:
            start = n
        if stripped.endswith(escape):
            parts.append(stripped[: -len(escape)].strip())
            continue
        parts.append(stripped)
        if joined := " ".join(p for p in parts if p):
            out.append((start, joined))
        parts = []
    if parts:
        out.append((start, " ".join(p for p in parts if p)))
    return directives, out


def check(path: Path) -> list[str]:
    bad: list[str] = []
    name = path.relative_to(ROOT).as_posix()
    directives, insts = instructions(path.read_text(encoding="utf-8"))
    if "syntax" in directives and not PINNED.match(directives["syntax"]):
        bad.append(f"{name}:1: the syntax directive '{directives['syntax']}' is not pinned")
    stages: set[str] = set()
    count = 0

    def pinned_or_stage(n: int, image: str, what: str) -> None:
        if image.lower() not in stages and image != "scratch" and not PINNED.match(image):
            bad.append(f"{name}:{n}: {what} '{image}' is not pinned as name:tag@sha256:<digest>")

    for n, inst in insts:
        if re.match(r"^FROM\s", inst, re.IGNORECASE):
            if not (m := FROM.match(inst)):
                bad.append(f"{name}:{n}: can't read this FROM: {inst}")
                continue
            pinned_or_stage(n, m.group(1), "FROM")
            stages.add(str(count))  # a stage is also named by its index
            count += 1
            if m.group(2):
                stages.add(m.group(2).lower())
        elif m := COPY_FROM.match(inst):
            pinned_or_stage(n, m.group(1), "--from")
        elif re.match(r"^RUN\s", inst, re.IGNORECASE):
            for m in MOUNT_FROM.finditer(inst):
                pinned_or_stage(n, m.group(1), "--mount from")
    return bad


files = sorted(
    p
    for p in DEPLOY.rglob("*")
    if p.is_file() and re.search(r"dockerfile|containerfile", p.name, re.IGNORECASE)
)
bad = [msg for path in files for msg in check(path)]
for msg in bad:
    print(f"digest pins: {msg} (spec 08 §Deploy)", file=sys.stderr)
print(f"digest pins: {len(files)} Dockerfile(s) under deploy/, {len(bad)} unpinned image(s)")
sys.exit(1 if bad else 0)
