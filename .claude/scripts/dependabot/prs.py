#!/usr/bin/env python3
"""List the open Dependabot PRs into dev, and watch queued PRs until they merge (/dependabot-review; TASK-211).

    python3 .claude/scripts/dependabot/prs.py list
    python3 .claude/scripts/dependabot/prs.py watch <n> [<n> ...] [--interval 45] [--timeout 120]

`list` prints one block per open PR by app/dependabot into `dev`: number, ecosystem, head branch and title,
then a PROBLEM line for any file outside what that ecosystem's PR may touch (uv: `uv.lock` and the
`pyproject.toml`s; npm: the lock and the `package.json`s; docker: `deploy/`; github-actions: `.github/`), an
ecosystem the routine doesn't know, or a title naming `tantivy`. Exit 0 always (it is a listing); the
command reads the PROBLEM lines.

`watch` polls GitHub's GraphQL API every `--interval` seconds and prints a line whenever a PR's state,
merge-queue entry or check rollup changes. While a PR waits in the merge queue its `autoMergeRequest` reads
null and `mergeQueueEntry` holds its place, so a PR with neither, two polls running, has dropped out of the
queue. Exit 0 when every PR merged; 1 when one was closed unmerged or dropped out of the queue (the line
says which: see its queue run, then re-queue it); 4 at `--timeout` minutes.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
import time
from typing import Any

from _common import ToolError, main_guard, run_json

REPO = "uw-share-lab/openproceedings"
ALLOWED = {
    "uv": ("uv.lock", "pyproject.toml", "backend/pyproject.toml"),
    "npm_and_yarn": ("package-lock.json", "package.json", "frontend/package.json"),
    "docker": ("deploy/*",),
    "github_actions": (".github/workflows/*", ".github/actions/*"),
}
HAND_ONLY_WORDS = ("tantivy",)


def ecosystem(head: str) -> str:
    parts = head.split("/")
    return parts[1] if len(parts) > 2 and parts[0] == "dependabot" else "?"


def list_prs() -> None:
    prs = run_json(
        [
            "gh", "pr", "list", "--repo", REPO, "--author", "app/dependabot", "--base", "dev",
            "--state", "open", "--limit", "100", "--json", "number,title,headRefName,files,url",
        ]
    )  # fmt: skip
    if not isinstance(prs, list):
        raise ToolError("gh pr list did not return a list")
    print(f"{len(prs)} open Dependabot PR(s) into dev")
    for pr in sorted(prs, key=lambda p: p["number"]):
        eco = ecosystem(pr["headRefName"])
        print(f"#{pr['number']} [{eco}] {pr['headRefName']}\n    {pr['title']}")
        allowed = ALLOWED.get(eco)
        if allowed is None:
            print(f"PROBLEM #{pr['number']}: ecosystem {eco!r} is not one the routine reviews")
            continue
        for f in pr.get("files") or []:
            if not any(fnmatch.fnmatchcase(f["path"], pat) for pat in allowed):
                print(f"PROBLEM #{pr['number']}: {f['path']} is outside what a {eco} update touches")
        if any(w in pr["title"].lower() for w in HAND_ONLY_WORDS):
            print(f"PROBLEM #{pr['number']}: names a hand-only dependency (tantivy, spec 08 §Release)")


QUERY = """query{repository(owner:"%s",name:"%s"){%s}}"""
FIELDS = (
    "state mergeQueueEntry{state position} autoMergeRequest{enabledAt} "
    "commits(last:1){nodes{commit{statusCheckRollup{state}}}}"
)


def poll(numbers: list[int]) -> dict[int, dict[str, Any]]:
    owner, name = REPO.split("/")
    body = " ".join(f"p{n}:pullRequest(number:{n}){{{FIELDS}}}" for n in numbers)
    data = run_json(["gh", "api", "graphql", "-f", f"query={QUERY % (owner, name, body)}"])
    try:
        repo = data["data"]["repository"]
        return {n: repo[f"p{n}"] for n in numbers}
    except (KeyError, TypeError) as e:
        raise ToolError(f"unexpected GraphQL answer: {str(data)[:200]}") from e


def describe(pr: dict[str, Any]) -> str:
    entry = pr.get("mergeQueueEntry") or {}
    nodes = (pr.get("commits") or {}).get("nodes") or [{}]
    rollup = ((nodes[-1].get("commit") or {}).get("statusCheckRollup") or {}).get("state")
    queue = f"queue={entry.get('state')}#{entry.get('position')}" if entry else "queue=-"
    auto = " auto-merge" if pr.get("autoMergeRequest") else ""
    return f"{pr.get('state')} {queue}{auto} checks={rollup or '-'}"


def watch(numbers: list[int], interval: float, timeout_min: float) -> None:
    deadline = time.monotonic() + timeout_min * 60
    last: dict[int, str] = {}
    unqueued: dict[int, int] = {}
    while True:
        states = poll(numbers)
        for n, pr in states.items():
            line = describe(pr)
            if last.get(n) != line:
                print(f"#{n} {line}", flush=True)
                last[n] = line
            open_ = pr.get("state") == "OPEN"
            unqueued[n] = (
                unqueued.get(n, 0) + 1
                if open_ and not pr.get("mergeQueueEntry") and not pr.get("autoMergeRequest")
                else 0
            )
        closed = [n for n, pr in states.items() if pr.get("state") == "CLOSED"]
        dropped = [n for n, c in unqueued.items() if c >= 2]
        if closed or dropped:
            for n in closed:
                print(f"#{n} was closed without merging")
            for n in dropped:
                print(f"#{n} is open but out of the merge queue: read its queue run, fix or rerun, re-queue")
            sys.exit(1)
        if all(pr.get("state") == "MERGED" for pr in states.values()):
            print("all merged")
            sys.exit(0)
        if time.monotonic() >= deadline:
            print(
                f"timed out after {timeout_min:g} min; still waiting: {[n for n in numbers if states[n].get('state') != 'MERGED']}"
            )
            sys.exit(4)
        time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    w = sub.add_parser("watch")
    w.add_argument("numbers", type=int, nargs="+")
    w.add_argument("--interval", type=float, default=45)
    w.add_argument("--timeout", type=float, default=120, help="minutes")
    a = ap.parse_args()
    if a.cmd == "list":
        list_prs()
    else:
        watch(a.numbers, a.interval, a.timeout)


if __name__ == "__main__":
    main_guard(main)
