#!/usr/bin/env python3
"""The pr-gates checks for a merge-queue build (the `merge_group` event; decision-027, TASK-161).

    python3 .claude/scripts/merge_group_gate.py review|learnings|attribution \
        --base <merge_group.base_sha> --head <merge_group.head_sha> --head-ref <merge_group.head_ref> \
        --repo <owner/name>

A `merge_group` event has no PR: its head is the queue's temporary commit on
`gh-readonly-queue/dev/pr-<N>-<sha>`. With the queue's MERGE method, `base..head` along first parents is
one two-parent merge commit per queued PR, oldest first: parent 1 is the previous queue commit (the first
one's is `base`), parent 2 is that PR's head. This script resolves every PR in the group from those commits
and runs, for EACH of them, the check the `pull_request` job runs for one PR:

  review       the PR is open, targets dev, its head is still that parent 2, and its CURRENT body (read from
               the API, so no stale event snapshot) carries `<!-- op-review: <parent 2> APPROVE -->`;
  learnings    the PR's own diff (merge-base(parent 1, parent 2)...parent 2) adds or extends a
               `.claude/learnings/YYYY-MM-DD-<slug>.md` entry, unless the PR is labelled `no-learning`;
  attribution  no commit in `base..head` (queue merges included) and no PR title or body carries AI attribution.

It fails closed: anything it can't resolve (a head ref that isn't dev's queue, a range that isn't a chain of
two-parent merges starting at base, a PR it can't name, a failed `gh` call, JSON it can't read) is an error,
never a pass. Like the `pull_request` jobs, it is an honesty check, not an access control (spec 08 §CI).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

SHA = re.compile(r"[0-9a-f]{40}")
QUEUE_REF = re.compile(r"refs/heads/gh-readonly-queue/dev/pr-([1-9][0-9]*)-[0-9a-f]{40}")
MERGE_SUBJECT = re.compile(r"Merge pull request #([1-9][0-9]*) from \S")
LEARNING = re.compile(r"\.claude/learnings/[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]+\.md")
# The pattern pr-gates.yml, block-ai-attribution.sh and the commit-msg hook match (no-ai-attribution skill).
ATTRIBUTION = re.compile(
    r"co-authored-by[:=].*(claude|anthropic)|generated with \[?claude|🤖 generated|noreply@anthropic\.com",
    re.IGNORECASE,
)


class GateError(Exception):
    pass


@dataclass(frozen=True)
class Entry:
    number: int
    merge: str  # the queue's merge commit
    parent: str  # parent 1: the previous queue commit, or base
    pr_head: str  # parent 2: the PR's head as queued


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise GateError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def gh_json(path: str) -> Any:
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if r.returncode != 0:
        raise GateError(f"gh api {path} failed: {(r.stderr or r.stdout).strip()}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise GateError(f"gh api {path} returned something that isn't JSON ({e})") from e


def pr_for_commit(repo: str, merge: str, pr_head: str) -> int:
    """The PR a queue merge brings in: from GitHub's merge subject, else the one open dev PR headed at parent 2."""
    subject = git("log", "-1", "--format=%s", merge).strip()
    if m := MERGE_SUBJECT.match(subject):
        return int(m.group(1))
    pulls = gh_json(f"repos/{repo}/commits/{pr_head}/pulls")
    if not isinstance(pulls, list):
        raise GateError(f"the pulls for {pr_head[:10]} aren't a list")
    hits = [
        p["number"]
        for p in pulls
        if isinstance(p, dict)
        and p.get("state") == "open"
        and (p.get("base") or {}).get("ref") == "dev"
        and (p.get("head") or {}).get("sha") == pr_head
    ]
    if len(hits) != 1 or not isinstance(hits[0], int):
        raise GateError(
            f"queue commit {merge[:10]} names no PR, and {len(hits)} open dev PRs have head {pr_head[:10]}"
        )
    return hits[0]


def entries(base: str, head: str, head_ref: str, repo: str) -> list[Entry]:
    if not (SHA.fullmatch(base) and SHA.fullmatch(head)):
        raise GateError(f"base {base!r} and head {head!r} must be full 40-character shas")
    ref = QUEUE_REF.fullmatch(head_ref)
    if not ref:
        raise GateError(
            f"head ref {head_ref!r} is not dev's merge queue (refs/heads/gh-readonly-queue/dev/pr-N-<sha>)"
        )
    lines = git("rev-list", "--first-parent", "--parents", "--reverse", f"{base}..{head}").split("\n")
    lines = [ln for ln in lines if ln]
    if not lines:
        raise GateError(f"{base[:10]}..{head[:10]} holds no commits")
    out: list[Entry] = []
    prev = base
    for ln in lines:
        commit, *parents = ln.split()
        if len(parents) != 2:
            raise GateError(
                f"{commit[:10]} has {len(parents)} parent(s): every queue commit must be a two-parent merge"
                " (the ruleset's merge_method must be MERGE)"
            )
        if parents[0] != prev:
            raise GateError(
                f"{commit[:10]}'s first parent is not {prev[:10]}: the queue chain doesn't start at base"
            )
        out.append(Entry(pr_for_commit(repo, commit, parents[1]), commit, parents[0], parents[1]))
        prev = commit
    numbers = [e.number for e in out]
    if len(set(numbers)) != len(numbers):
        raise GateError(f"a PR appears twice in the group: {numbers}")
    if numbers[-1] != int(ref.group(1)):
        raise GateError(
            f"the newest queue commit brings in #{numbers[-1]}, but the head ref names #{ref.group(1)}"
        )
    return out


def pull(repo: str, e: Entry) -> dict[str, Any]:
    p = gh_json(f"repos/{repo}/pulls/{e.number}")
    if not isinstance(p, dict):
        raise GateError(f"#{e.number}: the PR isn't a JSON object")
    if p.get("state") != "open":
        raise GateError(f"#{e.number} is {p.get('state')!r}, not open")
    if (p.get("base") or {}).get("ref") != "dev":
        raise GateError(f"#{e.number} targets {(p.get('base') or {}).get('ref')!r}, not dev")
    if (p.get("head") or {}).get("sha") != e.pr_head:
        raise GateError(
            f"#{e.number}'s head is {(p.get('head') or {}).get('sha')!r}, but the queue merged {e.pr_head}"
        )
    return p


def text(p: dict[str, Any], key: str) -> str:
    v = p.get(key)
    if v is None:
        return ""
    if not isinstance(v, str):
        raise GateError(f"#{p.get('number')}: {key} isn't a string")
    return v


def check_review(repo: str, group: list[Entry]) -> list[str]:
    bad = []
    for e in group:
        if f"<!-- op-review: {e.pr_head} APPROVE -->" not in text(pull(repo, e), "body"):
            bad.append(
                f"#{e.number}: no review attestation for head {e.pr_head} — run /review-gate on it, then"
                " record-review.py APPROVE <file> --attest"
            )
        else:
            print(f"#{e.number}: attested for {e.pr_head}")
    return bad


def added_learnings(e: Entry) -> list[str]:
    raw = git(
        "diff",
        "--numstat",
        "-z",
        "--find-renames",
        "--diff-filter=AMR",
        f"{e.parent}...{e.pr_head}",
        "--",
        ".claude/learnings/",
    )
    fields, found, i = raw.split("\0"), [], 0
    while i < len(fields) and fields[i]:
        added, _deleted, path = fields[i].split("\t", 2)
        if path == "":  # a rename: the old and new paths follow as their own fields
            path, i = fields[i + 2], i + 3
        else:
            i += 1
        if added.isdigit() and int(added) > 0 and LEARNING.fullmatch(path):
            found.append(path)
    return found


def check_learnings(repo: str, group: list[Entry]) -> list[str]:
    bad = []
    for e in group:
        labels = pull(repo, e).get("labels")
        if not isinstance(labels, list):
            raise GateError(f"#{e.number}: labels aren't a list")
        if any(isinstance(lb, dict) and lb.get("name") == "no-learning" for lb in labels):
            print(f"#{e.number}: labelled no-learning")
        elif found := added_learnings(e):
            print(f"#{e.number}: {', '.join(found)}")
        else:
            bad.append(f"#{e.number}: no added or extended .claude/learnings/ entry (or label no-learning)")
    return bad


def check_attribution(repo: str, group: list[Entry], base: str, head: str) -> list[str]:
    bad = []
    if any(ATTRIBUTION.search(ln) for ln in git("log", "--format=%B", f"{base}..{head}").splitlines()):
        bad.append("a commit message in the group carries AI attribution")
    for e in group:
        p = pull(repo, e)
        if any(ATTRIBUTION.search(ln) for ln in f"{text(p, 'title')}\n{text(p, 'body')}".splitlines()):
            bad.append(f"#{e.number}: the PR title/body carries AI attribution")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gate", choices=["review", "learnings", "attribution"])
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--head-ref", required=True)
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    try:
        group = entries(a.base, a.head, a.head_ref, a.repo)
        print(f"merge group {a.head[:10]}: " + ", ".join(f"#{e.number} @ {e.pr_head[:10]}" for e in group))
        if a.gate == "review":
            bad = check_review(a.repo, group)
        elif a.gate == "learnings":
            bad = check_learnings(a.repo, group)
        else:
            bad = check_attribution(a.repo, group, a.base, a.head)
    except (GateError, KeyError, IndexError, ValueError, TypeError, AttributeError) as e:
        print(f"::error::{a.gate}: {e}")
        sys.exit(1)
    for msg in bad:
        print(f"::error::{msg}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
