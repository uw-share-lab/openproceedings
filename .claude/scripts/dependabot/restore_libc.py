#!/usr/bin/env python3
"""Put back the `libc` fields an older npm dropped from package-lock.json (/dependabot-review step 3; TASK-211).

    python3 .claude/scripts/dependabot/restore_libc.py [--base REF]

npm before the `.nvmrc` Node's (22) drops `libc` from the lock entries of platform packages (sharp's
`@img/sharp-linux*`, Next's `@next/swc-linux*`) when it rewrites the lock. The fix is to edit the lock under
Node 22; this is the repair when that wasn't possible. For every entry of the working tree's
`package-lock.json` that lacks `libc` while the same key at `base` (default: the merge base of origin/dev and
HEAD) has it, it copies `libc` back, in the key order the base entry had. It changes nothing else, and prints
each entry it repaired. Run `npm_lock.py` afterwards: it compares every changed entry's `libc` with the
registry's manifest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from _common import ToolError, git_show, main_guard, resolve_refs

LOCK = Path("package-lock.json")


def restore(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Copy `libc` from old entries into new ones that lack it, in place. Returns the keys repaired."""
    repaired = []
    packages = new.get("packages", {})
    for key, entry in packages.items():
        before = old.get("packages", {}).get(key)
        if not before or "libc" not in before or "libc" in entry:
            continue
        merged: dict[str, Any] = {}
        for k in before:  # the base entry's key order, libc in its old place
            if k in entry:
                merged[k] = entry[k]
            elif k == "libc":
                merged[k] = before[k]
        for k in entry:  # keys the base entry didn't have, at the end
            merged.setdefault(k, entry[k])
        packages[key] = merged
        repaired.append(key)
    return repaired


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base")
    a = ap.parse_args()
    base, _ = resolve_refs(a.base, "HEAD")
    text = git_show(base, str(LOCK))
    if text is None:
        raise ToolError(f"package-lock.json does not exist at {base}")
    if not LOCK.is_file():
        raise ToolError("run from the repository root: package-lock.json not found")
    try:
        old, new = json.loads(text), json.loads(LOCK.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ToolError(f"package-lock.json is not JSON: {e}") from e
    repaired = restore(old, new)
    if repaired:
        LOCK.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for key in repaired:
        print(f"restored libc: {key}")
    print(f"{len(repaired)} entr{'y' if len(repaired) == 1 else 'ies'} repaired")


if __name__ == "__main__":
    main_guard(main)
