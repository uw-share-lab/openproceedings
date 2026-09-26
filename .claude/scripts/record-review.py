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
import os
import re
import subprocess
import sys
from pathlib import Path

# A finding line: optional indent, a `-` or `*` bullet, a [must|should|nit] tag in any case. The
# disposition is whatever follows the LAST arrow, so a summary may itself contain "->".
FINDING_START = re.compile(r"^\s*[-*]\s*\[\s*(must|should|nit)\s*\]", re.IGNORECASE)
TAG_ANYWHERE = re.compile(r"\[\s*(must|should|nit)\s*\]", re.IGNORECASE)
ARROW = re.compile(r"\s(?:→|->)\s")


BASE = "origin/dev"  # a `fixed` commit must be new relative to this (overridable for tests: OP_REVIEW_BASE)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def fail(msg: str) -> None:
    print(f"record-review: {msg}", file=sys.stderr)
    sys.exit(1)


def check_disposition(level: str, disp: str, root: Path, head: str) -> str | None:
    """Return an error string, or None if the disposition is valid."""
    if m := re.fullmatch(r"fixed\s+([0-9a-f]{7,40})", disp, re.IGNORECASE):
        sha = m.group(1)
        ok = (
            subprocess.run(["git", "merge-base", "--is-ancestor", sha, head], capture_output=True).returncode
            == 0
        )
        if not ok:
            return f"fixed {sha}: not an ancestor of HEAD"
        on_base = (
            subprocess.run(["git", "merge-base", "--is-ancestor", sha, BASE], capture_output=True).returncode
            == 0
        )
        return f"fixed {sha}: already on {BASE}, so it predates this review" if on_base else None
    if m := re.fullmatch(r"(task-\d+)", disp, re.IGNORECASE):
        task = m.group(1).lower()
        hits = list((root / "backlog" / "tasks").glob(f"{task} - *.md")) + list(
            (root / "backlog" / "completed").glob(f"{task} - *.md")
        )
        return None if hits else f"{task}: no such Backlog task (create it with `backlog task create`)"
    if m := re.fullmatch(r"rejected:\s*(.+)", disp, re.IGNORECASE):
        if level == "must":
            return "a [must] finding cannot be rejected — fix it or escalate"
        words = re.findall(r"[A-Za-z]{2,}", m.group(1))
        return None if len(words) >= 3 else "a rejection needs a real reason (at least three words)"
    return f"unrecognised disposition '{disp}' (use: fixed <sha> | task-NNN | rejected: <reason of at least three words>)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("verdict", choices=["APPROVE", "REQUEST_CHANGES"])
    ap.add_argument("dispositions", type=Path)
    ap.add_argument("--attest", action="store_true")
    a = ap.parse_args()

    global BASE
    BASE = os.environ.get("OP_REVIEW_BASE", BASE)
    try:
        root = Path(git("rev-parse", "--show-toplevel"))
        head = git("rev-parse", "HEAD")
    except subprocess.CalledProcessError:
        fail("not inside a git repository with at least one commit")
    if git("status", "--porcelain", "--untracked-files=normal"):
        fail("working tree is not clean — commit (or stash) first; an approval covers committed bytes only")

    text = a.dispositions.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    lines = text.splitlines()
    findings = [ln for ln in lines if FINDING_START.match(ln)]
    # A tag outside a well-formed bullet is a finding the parser would otherwise skip — refuse it.
    stray = [ln for ln in lines if TAG_ANYWHERE.search(ln) and not FINDING_START.match(ln)]
    says_none = any(ln.strip() == "No findings." for ln in lines)
    if not findings and not stray and not says_none:
        fail("no findings listed and no 'No findings.' line — state one or the other explicitly")
    if says_none and (findings or stray):
        fail("the file says 'No findings.' but also lists findings — remove one")

    errors, open_must = (
        [f"malformed finding line (use '- [must|should|nit] … → <disposition>'): {ln}" for ln in stray],
        0,
    )
    for ln in findings:
        level = FINDING_START.match(ln).group(1).lower()
        parts = ARROW.split(ln)
        if len(parts) < 2 or not parts[-1].strip():
            errors.append(f"undispositioned: {ln}")
            if level == "must":
                open_must += 1
            continue
        disp = parts[-1].strip()
        if level == "must" and not disp.lower().startswith("fixed"):
            open_must += 1
        if err := check_disposition(level, disp, root, head):
            errors.append(f"{err}: {ln}")
    if errors:
        fail("dispositions invalid:\n  " + "\n  ".join(errors))
    if a.verdict == "APPROVE" and open_must:
        fail(f"{open_must} [must] finding(s) not fixed — APPROVE refused")

    store = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir")) / "op-reviews"
    store.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    (store / head).write_text(
        f"{a.verdict}\nsha: {head}\nbranch: {branch}\nrecorded: {stamp}\nfindings: {len(findings)}\n\n{text}",
        encoding="utf-8",
    )
    print(f"recorded {a.verdict} for {head[:10]} ({len(findings)} findings) → {store / head}")

    if a.attest and a.verdict == "APPROVE":
        view = subprocess.run(
            ["gh", "pr", "view", "--json", "number,body", "-q", '"\\(.number)\\n\\(.body)"'],
            capture_output=True,
            text=True,
        )
        if view.returncode != 0:
            print("no open PR for this branch yet — re-run with --attest after `gh pr create`")
            return
        number, _, body = view.stdout.partition("\n")
        body = re.sub(r"\n?<!-- op-review: [0-9a-f]+ APPROVE -->", "", body.rstrip())
        body += f"\n\n<!-- op-review: {head} APPROVE -->"
        # REST, not `gh pr edit`: gh pr edit queries the retired Projects (classic) API and fails
        # (PR #1, 2026-09-25). {owner}/{repo} is filled in by gh from the current repository.
        subprocess.run(
            [
                "gh",
                "api",
                "-X",
                "PATCH",
                f"repos/{{owner}}/{{repo}}/pulls/{number.strip()}",
                "-f",
                f"body={body}",
            ],
            check=True,
            capture_output=True,
        )
        print(f"PR #{number.strip()} body attested for {head[:10]}")


if __name__ == "__main__":
    main()
