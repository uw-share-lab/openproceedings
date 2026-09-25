#!/usr/bin/env python3
"""Record the outcome of a /review-gate round for the current HEAD. The ONLY writer of review records.

    python3 .claude/scripts/record-review.py APPROVE|REQUEST_CHANGES <dispositions.md> [--attest]

The record lives at  <git-common-dir>/op-reviews/<HEAD sha>  (inside .git, never committed), and is what
.claude/hooks/require-review.sh checks before a push or `gh pr create`.

Refuses to record unless:
  * the working tree is clean — the approval must cover exactly the committed bytes;
  * every finding line in <dispositions.md> is dispositioned (a Kreate lesson, 2026-09-17: findings
    "noted as non-blocking" were lost, because deferring creates no artifact):
        - [must|should|nit] <file:line> <summary> → fixed <sha>          (sha must be an ancestor of HEAD)
        - [must|should|nit] <file:line> <summary> → task-NNN             (the Backlog task must exist)
        - [should|nit]      <file:line> <summary> → rejected: <reason>   (must-fix cannot be rejected)
    or the file states "No findings." on its own line;
  * APPROVE is not recorded while any [must] finding is anything other than fixed.

--attest also writes `<!-- op-review: <sha> APPROVE -->` into the open PR's body, which CI's
`review-attested` check compares against the PR head sha.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

LINE = re.compile(r"^- \[(must|should|nit)\]\s+(?P<what>.+?)\s+(?:→|->)\s+(?P<disp>.+)$")
FINDING_START = re.compile(r"^- \[(must|should|nit)\]")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def fail(msg: str) -> None:
    print(f"record-review: {msg}", file=sys.stderr)
    sys.exit(1)


def check_disposition(level: str, disp: str, root: Path, head: str) -> str | None:
    """Return an error string, or None if the disposition is valid."""
    if m := re.fullmatch(r"fixed\s+([0-9a-f]{7,40})", disp):
        sha = m.group(1)
        ok = subprocess.run(["git", "merge-base", "--is-ancestor", sha, head], capture_output=True).returncode == 0
        return None if ok else f"fixed {sha}: not an ancestor of HEAD"
    if m := re.fullmatch(r"(task-\d+)", disp, re.IGNORECASE):
        task = m.group(1).lower()
        hits = list((root / "backlog" / "tasks").glob(f"{task} - *.md")) + list(
            (root / "backlog" / "completed").glob(f"{task} - *.md")
        )
        return None if hits else f"{task}: no such Backlog task (create it with `backlog task create`)"
    if m := re.fullmatch(r"rejected:\s*(.{10,})", disp):
        return "a [must] finding cannot be rejected — fix it or escalate" if level == "must" else None
    return f"unrecognised disposition '{disp}' (use: fixed <sha> | task-NNN | rejected: <reason ≥10 chars>)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("verdict", choices=["APPROVE", "REQUEST_CHANGES"])
    ap.add_argument("dispositions", type=Path)
    ap.add_argument("--attest", action="store_true")
    a = ap.parse_args()

    root = Path(git("rev-parse", "--show-toplevel"))
    head = git("rev-parse", "HEAD")
    if git("status", "--porcelain", "--untracked-files=normal"):
        fail("working tree is not clean — commit (or stash) first; an approval covers committed bytes only")

    text = a.dispositions.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings = [ln for ln in lines if FINDING_START.match(ln)]
    if not findings and not any(ln.strip() == "No findings." for ln in lines):
        fail("no findings listed and no 'No findings.' line — state one or the other explicitly")

    errors, open_must = [], 0
    for ln in findings:
        m = LINE.match(ln)
        if not m:
            errors.append(f"undispositioned: {ln}")
            continue
        level = ln[3:ln.index("]")]
        disp = m.group("disp").strip()
        if level == "must" and not disp.startswith("fixed"):
            open_must += 1
        if err := check_disposition(level, disp, root, head):
            errors.append(f"{err}: {ln}")
    if errors:
        fail("dispositions invalid:\n  " + "\n  ".join(errors))
    if a.verdict == "APPROVE" and open_must:
        fail(f"{open_must} [must] finding(s) not fixed — APPROVE refused")

    store = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir")) / "op-reviews"
    store.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    (store / head).write_text(
        f"{a.verdict}\nsha: {head}\nbranch: {branch}\nrecorded: {stamp}\nfindings: {len(findings)}\n\n{text}",
        encoding="utf-8",
    )
    print(f"recorded {a.verdict} for {head[:10]} ({len(findings)} findings) → {store / head}")

    if a.attest and a.verdict == "APPROVE":
        view = subprocess.run(["gh", "pr", "view", "--json", "body", "-q", ".body"], capture_output=True, text=True)
        if view.returncode != 0:
            print("no open PR for this branch yet — re-run with --attest after `gh pr create`")
            return
        body = re.sub(r"\n?<!-- op-review: [0-9a-f]+ APPROVE -->", "", view.stdout.rstrip())
        body += f"\n\n<!-- op-review: {head} APPROVE -->"
        subprocess.run(["gh", "pr", "edit", "--body", body], check=True)
        print("PR body attested")


if __name__ == "__main__":
    main()
