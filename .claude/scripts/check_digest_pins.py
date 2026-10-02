#!/usr/bin/env python3
"""CI check (spec 08 §Deploy, TASK-149): every `FROM` in a Dockerfile under deploy/ names its base image as
`name:tag@sha256:<digest>`, so a rebuild uses the image that was reviewed; Dependabot's `docker` entry bumps
the digests. A `FROM` that names an earlier build stage, or `scratch`, has no registry image to pin. Exits 1
listing every unpinned `FROM`."""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
# FROM [--platform=…] <image> [AS <stage>]; the image may not be an ARG, which no reviewer can see resolved
FROM = re.compile(r"^\s*FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?\s*$", re.IGNORECASE)
PINNED = re.compile(r"^[^@\s$]+:[^@\s$]+@sha256:[0-9a-f]{64}$")

bad = []
files = sorted(p for p in DEPLOY.rglob("*") if p.is_file() and "dockerfile" in p.name.lower())
for path in files:
    stages: set[str] = set()
    lines = path.read_text(encoding="utf-8").splitlines()
    for n, line in enumerate(lines, 1):
        if not re.match(r"^\s*FROM\s", line, re.IGNORECASE):
            continue
        m = FROM.match(line)
        if not m:
            bad.append(f"{path.name}:{n}: can't read this FROM: {line.strip()}")
            continue
        image, stage = m.group(1), m.group(2)
        if image.lower() not in stages and image != "scratch" and not PINNED.match(image):
            bad.append(f"{path.name}:{n}: '{image}' is not pinned as name:tag@sha256:<digest>")
        if stage:
            stages.add(stage.lower())
for msg in bad:
    print(f"digest pins: {msg} (spec 08 §Deploy)", file=sys.stderr)
print(f"digest pins: {len(files)} Dockerfile(s) under deploy/, {len(bad)} unpinned FROM")
sys.exit(1 if bad else 0)
