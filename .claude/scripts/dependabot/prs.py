#!/usr/bin/env python3
"""List, check and watch the open Dependabot PRs into dev (/dependabot-review steps 1 and 9; TASK-211).

    python3 .claude/scripts/dependabot/prs.py list
    python3 .claude/scripts/dependabot/prs.py check <n> --head <sha>
    python3 .claude/scripts/dependabot/prs.py watch <n> [<n> ...] [--interval 45] [--timeout 120]

`list` prints one block per open PR by app/dependabot into `dev`: number, ecosystem, head branch and title. It
exits 0 (a listing), or 2 when gh fails.

`check` is the hard gate before anything of the PR runs, and it is a checker (ok / PROBLEM; exit 0, 1 or 2). With
the PR's head fetched locally as `<sha>`, it requires: the PR is open, by app/dependabot, into `dev`, and its head
on GitHub is still `<sha>` (nothing pushed since the fetch); every file changed between the merge base with
origin/dev and `<sha>`, computed by git rather than read from GitHub's file list, is one that PR's ecosystem may
touch (uv: `uv.lock` and the two `pyproject.toml`s; npm: `package-lock.json` and the two `package.json`s; docker:
a Dockerfile under `deploy/`; github-actions: a workflow or a composite action's `action.yml`); and every commit
in that range is Dependabot's (author `dependabot[bot]`, committer GitHub) with a signature GitHub verified. A PR
someone else pushed to (the routine itself on an earlier run included) is left for the owner. A title naming
`tantivy` is a PROBLEM too (hand-only, spec 08 §Release).

`watch` polls GitHub's GraphQL API every `--interval` seconds and prints a line whenever a PR's state,
merge-queue entry or check rollup changes. While a PR waits in the merge queue its `autoMergeRequest` reads
null and `mergeQueueEntry` holds its place, so an open PR with neither, two polls running, has dropped out of
the queue. Exit 0 when every PR merged; 1 when one was closed unmerged or dropped out of the queue (the line
says which: see its queue run, then re-queue it); 2 when gh fails; 4 at `--timeout` minutes.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Any

from _common import Report, ToolError, changed_files, main_guard, resolve_refs, run, run_json

REPO = "uw-share-lab/openproceedings"
ALLOWED = {
    "uv": re.compile(r"uv\.lock|pyproject\.toml|backend/pyproject\.toml"),
    "npm_and_yarn": re.compile(r"package-lock\.json|package\.json|frontend/package\.json"),
    "docker": re.compile(r"deploy/(?:[^/]+/)*[^/]*(?:dockerfile|containerfile)[^/]*", re.IGNORECASE),
    "github_actions": re.compile(
        r"\.github/workflows/[^/]+\.ya?ml|\.github/actions/(?:[^/]+/)+action\.ya?ml"
    ),
}
HAND_ONLY_WORDS = ("tantivy",)
DEPENDABOT = (
    "dependabot[bot]",
    "49699333+dependabot[bot]@users.noreply.github.com",
    "GitHub",
    "noreply@github.com",
)


def ecosystem(head: str) -> str:
    parts = head.split("/")
    return parts[1] if len(parts) > 2 and parts[0] == "dependabot" else "?"


def list_prs() -> None:
    prs = run_json(
        [
            "gh", "pr", "list", "--repo", REPO, "--author", "app/dependabot", "--base", "dev",
            "--state", "open", "--limit", "100", "--json", "number,title,headRefName,url",
        ]
    )  # fmt: skip
    if not isinstance(prs, list):
        raise ToolError("gh pr list did not return a list")
    print(f"{len(prs)} open Dependabot PR(s) into dev")
    for pr in sorted(prs, key=lambda p: p["number"]):
        print(f"#{pr['number']} [{ecosystem(pr['headRefName'])}] {pr['headRefName']}\n    {pr['title']}")


def check_pr(number: int, head: str) -> None:
    rep = Report(f"PR #{number}")
    sha = run(["git", "rev-parse", "--verify", f"{head}^{{commit}}"]).stdout.strip()
    fields = "state,author,baseRefName,headRefName,headRefOid,title"
    pr = run_json(["gh", "pr", "view", str(number), "--repo", REPO, "--json", fields])
    if pr["state"] != "OPEN" or pr["baseRefName"] != "dev":
        rep.problem(f"the PR is {pr['state']} into {pr['baseRefName']}, not an open PR into dev")
    if pr["author"]["login"] not in ("app/dependabot", "dependabot[bot]"):
        rep.problem(f"the PR was opened by {pr['author']['login']}, not Dependabot")
    if pr["headRefOid"] != sha:
        rep.problem(f"GitHub's head is {pr['headRefOid'][:12]}, not the fetched {sha[:12]}: fetch again")
    if any(w in pr["title"].lower() for w in HAND_ONLY_WORDS):
        rep.problem("the title names a hand-only dependency (tantivy, spec 08 §Release)")
    eco = ecosystem(pr["headRefName"])
    allowed = ALLOWED.get(eco)
    base, _ = resolve_refs(None, sha)
    paths = changed_files(base, sha)
    if allowed is None:
        rep.problem(f"ecosystem {eco!r} is not one the routine reviews")
    else:
        for path in paths:
            if not allowed.fullmatch(path):
                rep.problem(f"{path} is outside what a {eco} update touches")
    commits = run(["git", "rev-list", f"{base}..{sha}"]).stdout.split()
    if not commits:
        rep.problem("no commits between the merge base and the head")
    for c in commits:
        who = tuple(
            run(["git", "log", "-1", "--format=%an%x00%ae%x00%cn%x00%ce", c]).stdout.strip().split("\0")
        )
        if who != DEPENDABOT:
            rep.problem(
                f"commit {c[:12]} is by {who[0]} <{who[1]}>, committed by {who[2]}: not Dependabot's alone"
            )
            continue
        verification = run_json(["gh", "api", f"repos/{REPO}/commits/{c}"])["commit"]["verification"]
        if verification.get("verified") is not True:
            rep.problem(
                f"commit {c[:12]}: GitHub doesn't verify its signature ({verification.get('reason')})"
            )
    if not rep.problems:
        rep.ok(f"{eco}: {len(paths)} file(s) and {len(commits)} commit(s), all Dependabot's, at {sha[:12]}")
    rep.finish()


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
    c = sub.add_parser("check")
    c.add_argument("number", type=int)
    c.add_argument("--head", required=True, help="the PR head as fetched (a sha or a ref)")
    w = sub.add_parser("watch")
    w.add_argument("numbers", type=int, nargs="+")
    w.add_argument("--interval", type=float, default=45)
    w.add_argument("--timeout", type=float, default=120, help="minutes")
    a = ap.parse_args()
    if a.cmd == "list":
        list_prs()
    elif a.cmd == "check":
        check_pr(a.number, a.head)
    else:
        watch(a.numbers, a.interval, a.timeout)


if __name__ == "__main__":
    main_guard(main)
