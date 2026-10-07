#!/usr/bin/env python3
"""Check the action pins a Dependabot `github-actions` PR moved (/dependabot-review step 2; TASK-211).

    python3 .claude/scripts/dependabot/actions_pins.py [--base REF] [--head REF]

Reads every `uses: <owner>/<repo>[/<path>]@<40-hex sha> # <tag>` line in the files under `.github/` that
changed between `base` (default: the merge base of origin/dev and HEAD) and `head` (default HEAD). For each
pin that is new at `head`, `gh api repos/<owner>/<repo>/commits/<tag>` must return the pinned sha (the
version comment is the tag the sha came from).

A PROBLEM, the PR stays open: a tag that resolves to another commit, an action that wasn't used before, a
semver-major tag change, or a `uses:` line in a changed file that isn't pinned to a full sha.
"""

from __future__ import annotations

import argparse
import re
import urllib.parse
from dataclasses import dataclass

from _common import Report, ToolError, changed_files, git_show, is_major, main_guard, resolve_refs, run_json

USES = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^\s'\"#]+)['\"]?\s*(?:#\s*(\S+))?", re.MULTILINE)
PINNED = re.compile(r"^([\w.-]+/[\w.-]+)(/[^@]*)?@([0-9a-f]{40})$")


@dataclass(frozen=True)
class Use:
    repo: str
    sha: str
    tag: str

    def __str__(self) -> str:
        return f"{self.repo}@{self.sha[:12]} ({self.tag or 'no tag comment'})"


def uses(text: str | None, rep: Report | None = None, path: str = "") -> set[Use]:
    out: set[Use] = set()
    for m in USES.finditer(text or ""):
        target, tag = m.group(1), m.group(2) or ""
        if target.startswith(("./", "docker://")):
            continue
        pin = PINNED.match(target)
        if pin is None:
            if rep is not None:
                rep.problem(f"{path}: `uses: {target}` is not pinned to a full commit sha")
            continue
        out.add(Use(pin.group(1).lower(), pin.group(3), tag))
    return out


def tag_sha(repo: str, tag: str) -> str:
    data = run_json(["gh", "api", f"repos/{repo}/commits/{urllib.parse.quote(tag, safe='')}"])
    sha = data.get("sha") if isinstance(data, dict) else None
    if not isinstance(sha, str):
        raise ToolError(f"gh api repos/{repo}/commits/{tag} returned no sha")
    return sha


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    a = ap.parse_args()
    base, head = resolve_refs(a.base, a.head)
    rep = Report("action pins")
    paths = [p for p in changed_files(base, head) if p.startswith(".github/")]
    before: set[Use] = set()
    after: set[Use] = set()
    for path in paths:
        before |= uses(git_show(base, path))
        after |= uses(git_show(head, path), rep, path)
    if not after - before:
        rep.ok(f"no new pins in {len(paths)} changed .github/ file(s)")
    for use in sorted(after - before, key=str):
        olds = sorted({u.tag for u in before if u.repo == use.repo})
        if not olds:
            rep.problem(f"{use}: {use.repo} was not used before (a new action)")
            continue
        if not use.tag:
            rep.problem(f"{use}: no `# <tag>` comment to check the sha against")
            continue
        if any(is_major(o, use.tag) for o in olds if o):
            rep.problem(f"{use}: semver-major from {', '.join(olds)}")
        got = tag_sha(use.repo, use.tag)
        if got != use.sha:
            rep.problem(f"{use}: tag {use.tag} is commit {got[:12]}, not the pinned sha")
        else:
            rep.ok(f"{use}: tag {use.tag} is the pinned commit")
    rep.finish()


if __name__ == "__main__":
    main_guard(main)
