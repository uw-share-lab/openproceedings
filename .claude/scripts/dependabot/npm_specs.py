#!/usr/bin/env python3
"""Check that the npm manifests and the lock's workspace entries hold the same dependency specs (TASK-212).

    python3 .claude/scripts/dependabot/npm_specs.py [--root DIR]

Every entry in `package.json`'s and `frontend/package.json`'s `dependencies`, `devDependencies`,
`optionalDependencies` and `peerDependencies` must be written exactly as `package-lock.json`'s `packages[""]` and
`packages["frontend"]` hold it (the same string; a value of another JSON type differs too), with nothing missing
and nothing extra. Dependabot's npm updater can write a caret
into the lock's workspace entry while the manifest pins the version (PR #124: `eslint-config-next` `^16.3.8`; PR
#100: Vitest), and `npm ci` accepts the difference, so nothing else fails on it. `make tooling` (CI
`claude-tooling`) runs this on every PR; `npm_lock.py` (/dependabot-review) reports the same mismatches, from the
same `mismatches()`, as FIX lines (a section that isn't an object as a PROBLEM). Fix one by editing the lock's entry to the manifest's string, under the `.nvmrc`
Node (spec 08 §CI, "Dependabot"). It reads the checkout it sits in, or `--root` (/dependabot-review runs dev's copy
with `--root .` on the PR branch).

Prints one line per mismatch and exits 1; exits 1 too when a manifest or the lock can't be read, or a manifest has
no lock entry (or the lock an entry with dependencies and no manifest), a section isn't an object, or the root
`workspaces` names a workspace other than those in `WORKSPACES` (add it there). With neither `package.json` nor
`package-lock.json` there is nothing to check: it says so and exits 0, or 1 under `--root` (the routine's copy
sits in a directory with neither, so a forgotten `--root .` must not read as a match). Standard library only: `make tooling` runs it with the
system python3.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
# the lock's key for each workspace's manifest: "" is the npm workspace root
WORKSPACES = {"": "package.json", "frontend": "frontend/package.json"}
MANIFEST_SECTIONS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
NOT_AN_OBJECT = "is not an object"


def mismatches(path: str, key: str, manifest: Mapping[str, Any], entry: Mapping[str, Any]) -> list[str]:
    """Each dependency spec in `manifest` (the file at `path`) that the lock's `packages[key]` (`entry`) doesn't
    hold as written, and each it holds that the manifest doesn't; a section that isn't an object is one too."""
    out: list[str] = []
    where = f'packages["{key}"]'
    for section in MANIFEST_SECTIONS:
        want, got = manifest.get(section, {}), entry.get(section, {})
        if not isinstance(want, dict) or not isinstance(got, dict):
            out.append(f"{path} {section} or the lock's {where} {section} {NOT_AN_OBJECT}")
            continue
        for dep in sorted(set(want) | set(got)):
            a, b = want.get(dep), got.get(dep)
            if a != b or type(a) is not type(b):  # 1 == 1.0 == true in Python, not in the lock
                out.append(
                    f"{path} {section}.{dep} is {want.get(dep)!r}, the lock's {where} has {got.get(dep)!r}"
                )
    return out


def read(root: Path, name: str) -> dict[str, Any] | None:
    """The JSON object in `root / name`, or None when there is no such file. Raises ValueError when it can't be
    read."""
    path = root / name
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"{name} can't be read as JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"{name} is not a JSON object")
    return data


def check(root: Path, *, required: bool = False) -> list[str] | None:
    """The problems found, or None when `root` holds no manifest and no lock (a problem itself when `required`)."""
    if not root.is_dir():
        return [f"{root} is not a directory"]
    lock = read(root, "package-lock.json")
    manifests = {key: read(root, path) for key, path in WORKSPACES.items()}
    if lock is None:
        if all(m is None for m in manifests.values()):
            return [f"no package.json or package-lock.json in {root}: nothing to compare"] if required else None
        return ["package-lock.json does not exist, but a package.json does"]
    listed = (manifests[""] or {}).get("workspaces", [])
    if not isinstance(listed, list) or set(map(str, listed)) - set(WORKSPACES):
        known = sorted(set(WORKSPACES) - {""})
        return [
            f"package.json workspaces {listed!r}: this check compares only {known} (add it to WORKSPACES)"
        ]
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        return ["package-lock.json has no `packages` object (lockfileVersion 3 is expected)"]
    out: list[str] = []
    for key, path in WORKSPACES.items():
        manifest, entry = manifests[key], packages.get(key)
        if entry is not None and not isinstance(entry, dict):
            out.append(f'package-lock.json packages["{key}"] is not an object')
        elif manifest is None:
            if entry and any(entry.get(s, {}) != {} for s in MANIFEST_SECTIONS):
                out.append(
                    f'package-lock.json packages["{key}"] lists dependencies, but {path} does not exist'
                )
        elif entry is None:
            out.append(f'{path} exists, but package-lock.json has no packages["{key}"] entry')
        else:
            out.extend(mismatches(path, key, manifest, entry))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument(
        "--root", type=Path, help="the checkout to read, which must hold the npm files (default: this script's own)"
    )
    a = ap.parse_args()
    try:
        found = check(a.root or ROOT, required=a.root is not None)
    except ValueError as e:
        found = [str(e)]
    if found is None:
        print(f"npm specs: no package.json or package-lock.json in {ROOT}: nothing compared")
        return 0
    problems = found
    for p in problems:
        print(f"npm specs: {p}", file=sys.stderr)
    if problems:
        print(
            f"npm specs: {len(problems)} mismatch(es); edit package-lock.json's workspace entry to the manifest's"
            " exact string (under the .nvmrc Node), spec 08 §CI",
            file=sys.stderr,
        )
        return 1
    print("npm specs: the manifests' dependency specs match package-lock.json's workspace entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
