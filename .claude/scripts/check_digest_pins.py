#!/usr/bin/env python3
"""CI check (spec 08 §Deploy, TASK-149): every image a Dockerfile under deploy/ pulls is named
`name:tag@sha256:<digest>`, so a rebuild uses the image that was reviewed. That covers each `FROM` (whose
digests Dependabot's `docker` entry bumps), and a `# syntax=` parser directive (the BuildKit frontend),
`COPY --from=` and `RUN --mount=…,from=` (bumped by hand: Dependabot reads only `FROM`). An earlier build
stage (by name in `FROM`, by name or index in `--from`), or `scratch`, has no registry image to pin.
Instructions are read as BuildKit reads them: a leading BOM dropped, the known parser directives read until the
first other line, continuation lines glued with no separator, comments between them dropped. A heredoc body is
read as instructions too, which can only refuse more. Exits 1 listing every unpinned image."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
DIRECTIVE = re.compile(r"^#\s*([a-zA-Z][a-zA-Z0-9]*)\s*=\s*(.+?)\s*$")
KNOWN = {"syntax", "escape", "check"}  # BuildKit stops reading directives at any other
# FROM [--platform=…] <image> [AS <stage>]; the image may not hold an ARG, which no reviewer can see resolved
FROM = re.compile(r"^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?$", re.IGNORECASE)
COPY_FROM = re.compile(r"^COPY\s.*?--from=(\S+)", re.IGNORECASE)
MOUNT_FROM = re.compile(r"--mount=\S*?\bfrom=([^,\s]+)", re.IGNORECASE)
# a tag after the last `/` (a registry port is not a tag), then the 64-hex digest
PINNED = re.compile(r"^[^@\s$]+:[^@\s$/:]+@sha256:[0-9a-f]{64}$")


def instructions(text: str) -> tuple[dict[str, tuple[int, str]], list[tuple[int, str]]]:
    """The leading parser directives and each instruction, with the line each starts on."""
    lines = text.splitlines()
    directives: dict[str, tuple[int, str]] = {}
    i = 0
    while i < len(lines) and (m := DIRECTIVE.match(lines[i])) and m.group(1).lower() in KNOWN:
        directives[m.group(1).lower()] = (i + 1, m.group(2))
        i += 1
    escape = directives.get("escape", (0, "\\"))[1]
    out: list[tuple[int, str]] = []
    start, parts = 0, list[str]()
    for n, line in enumerate(lines[i:], i + 1):
        stripped = line.strip()
        if stripped.startswith("#") or (parts and not stripped):
            continue  # a comment, or a blank line inside a continuation
        if not parts:
            start = n
        if (body := line.rstrip()).endswith(escape):
            parts.append(body[: -len(escape)])  # glued to the next line as is, as BuildKit does
            continue
        parts.append(line)
        if joined := "".join(parts).strip():
            out.append((start, joined))
        parts = []
    if joined := "".join(parts).strip():
        out.append((start, joined))
    return directives, out


def check(path: Path) -> list[str]:
    bad: list[str] = []
    name = path.relative_to(ROOT).as_posix()
    directives, insts = instructions(path.read_text(encoding="utf-8-sig"))
    if "syntax" in directives and not PINNED.match(syntax := directives["syntax"][1]):
        bad.append(f"{name}:{directives['syntax'][0]}: the syntax directive '{syntax}' is not pinned")
    stages: set[str] = set()  # FROM names an earlier stage by name only
    indexes: set[str] = set()  # --from also by index
    count = 0

    def pinned_or_stage(n: int, image: str, what: str, known: set[str]) -> None:
        if image.lower() not in known and image != "scratch" and not PINNED.match(image):
            bad.append(f"{name}:{n}: {what} '{image}' is not pinned as name:tag@sha256:<digest>")

    for n, inst in insts:
        if re.match(r"^FROM\s", inst, re.IGNORECASE):
            if not (m := FROM.match(inst)):
                bad.append(f"{name}:{n}: can't read this FROM: {inst}")
                continue
            pinned_or_stage(n, m.group(1), "FROM", stages)
            indexes.add(str(count))
            count += 1
            if m.group(2):
                stages.add(m.group(2).lower())
        elif m := COPY_FROM.match(inst):
            pinned_or_stage(n, m.group(1), "--from", stages | indexes)
        elif re.match(r"^RUN\s", inst, re.IGNORECASE):
            for m in MOUNT_FROM.finditer(inst):
                pinned_or_stage(n, m.group(1), "--mount from", stages | indexes)
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
