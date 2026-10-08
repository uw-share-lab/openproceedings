#!/usr/bin/env python3
"""Set up, list, check, queue and watch the open Dependabot PRs into dev (/dependabot-review; TASK-211, TASK-213).

    python3 .claude/scripts/dependabot/prs.py preflight
    python3 .claude/scripts/dependabot/prs.py list
    python3 .claude/scripts/dependabot/prs.py check <n> --head <sha>
    python3 .claude/scripts/dependabot/prs.py queue <n> --head <sha>
    python3 .claude/scripts/dependabot/prs.py watch <n> [<n> ...] [--interval 45] [--timeout 120] [--hung 40]

Every GitHub call is REST (`gh api repos/...`), because a Claude Code cloud session refuses GraphQL with HTTP 403
("GitHub GraphQL is not available from Claude Code sessions; …") and so every `gh pr` command that uses it
(`gh pr list`, `gh pr view`, `gh pr merge`, `gh pr checks`). The one call that differs by environment is
enabling auto-merge, which `queue` makes after detecting where it runs (`detect_mode`):

- **cloud**: a Claude Code cloud session. GraphQL answers 403 with the message above. Auth is a network secret:
  GH_TOKEN and GITHUB_TOKEN hold placeholders and an egress proxy adds the real credential to requests for
  api.github.com, so no process in the session ever holds the token. Auto-merge goes through the session's CCR
  route, `PUT repos/<repo>/pulls/<n>/ccr/auto_merge` (and `DELETE` to turn it off).
- **local**: a maintainer's clone with a real `gh` login. GraphQL answers; auto-merge is `gh pr merge <n> --auto
  --match-head-commit <sha>`.
- anything else (GraphQL failing another way) is an error: the run stops rather than guess.

`preflight` (step 0) checks `gh api user` answers, prints the mode, and checks the credential: in the cloud gh
must have no stored login (one would be a file dependency code could read, which step 5 can't strip), and a real
token in GH_TOKEN or GITHUB_TOKEN is reported (step 5 strips those). Locally a stored login is allowed: it is the
maintainer's own machine, where `make test` runs with it every day. A checker: ok / PROBLEM; exit 0, 1 or 2.

`list` prints one block per open PR by dependabot[bot] into `dev`: number, ecosystem, head branch (quoted, with a
warning, when it is not a plain `dependabot/<ecosystem>/…` name) and title
(`GET repos/<repo>/pulls?state=open&base=dev`, every page). Exit 0, or 2 when gh fails.

`check` is the hard gate before anything of the PR runs, and it is a checker (ok / PROBLEM; exit 0, 1 or 2). With
the PR's head fetched locally as `<sha>`, it requires: the PR is open, by dependabot[bot], into `dev`, and its
head on GitHub is still `<sha>` (nothing pushed since the fetch); every file changed between the merge base with
origin/dev and `<sha>` (git, renames as two paths) and every file GitHub lists for the PR (a rename's old path
too) is one that PR's ecosystem may touch (uv: `uv.lock` and the two `pyproject.toml`s; npm:
`package-lock.json` and the two `package.json`s; docker: a Dockerfile under `deploy/`; github-actions: a workflow
or a composite action's `action.yml`); git's commits in that range are exactly GitHub's commits for the PR; and
every one is Dependabot's (git author `dependabot[bot]`, committer GitHub, GitHub's author login
`dependabot[bot]`) with a signature GitHub verified. A PR someone else pushed to (the routine itself on an
earlier run included) is left for the owner. The identity is defence in depth only (a writer can set those
names, and GitHub verifies web-flow commits it makes for anyone); what stops a hostile push is that every
checker allows no change beyond versions and pins. A title naming `tantivy` (hand-only,
spec 08 §Release), or a head branch name that isn't plain, is a PROBLEM too.

`queue` turns auto-merge on (on `dev` that puts the PR in the merge queue once its checks pass) only for an open
Dependabot PR into `dev` whose head is still `<sha>` and whose branch name is plain, and never for a github-actions
PR (the routine's token has no `workflows` permission: the owner queues those). A PR GitHub already shows set to
merge is left as it is (a re-queue in step 9). Otherwise it makes the call, reads the PR again, and requires GitHub
to show it set to merge (auto-merge on, or a merge-queue entry in the timeline newer than the request; read once
more after OP_DEPENDABOT_SETTLE seconds, default 5). If the head moved, the call failed although GitHub shows the
PR set to merge, or GitHub accepted the call but shows nothing, it turns auto-merge off again, reads the PR back
and prints a PROBLEM; a PR that closed meanwhile is left alone. If the call or a read after it fails outright (a
timeout), it undoes it the same way and exits 2, saying whether that worked. In the cloud there is no
`--match-head-commit`: a push between the read after the PUT and the queue's build is the residual race, and the
queue's `review-attested` check (the body must attest the head the queue merges) stops it against anyone who
can't also rewrite the body (decision-048). Exit 0 queued (already set, or merged at `<sha>`); 1 not queued (leave
the PR open for the owner); 2 a call failed, and the message says whether auto-merge may still be on or the PR
may still be in the queue.

`watch` polls REST every `--interval` seconds and prints a line whenever a PR's state, auto-merge, queue
presence or check rollup changes. A PR is in the queue while its timeline's latest merge-queue event is
`added_to_merge_queue` (`queue=waiting`) or a `gh-readonly-queue/dev/pr-<n>-<sha>` build branch exists for it
(`queue=building`); an open PR with none of those nor auto-merge, two polls running, has dropped out of the
queue. A queue build run still going after `--hung` minutes is printed once as
`HUNG` with its run id (cancel and rerun it: step 9). Exit 0 when every PR merged; 1 when one was closed unmerged
or dropped out of the queue (the line says which); 2 when gh fails; 4 at `--timeout` minutes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

from _common import Report, ToolError, age_days, main_guard, now, parse_time, resolve_refs, run, run_json

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
BOT_LOGIN = "dependabot[bot]"
DEPENDABOT = (
    "dependabot[bot]",
    "49699333+dependabot[bot]@users.noreply.github.com",
    "GitHub",
    "noreply@github.com",
)
PER_PAGE = 100
MAX_PAGES = 30
# What a Claude Code cloud session answers for any GraphQL call (HTTP 403); its presence is how `cloud` is told.
GRAPHQL_BLOCKED = "GitHub GraphQL is not available from Claude Code sessions"
# A GitHub token's shape (classic, OAuth, app, refresh, fine-grained): a placeholder doesn't have it.
TOKEN_SHAPE = re.compile(r"gh[opsur]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}")
# what gh may hold as a stored login: a token of today's shape, or a classic 40-hex one (still valid if old)
STORED_SHAPE = re.compile(rf"{TOKEN_SHAPE.pattern}|\b[0-9a-f]{{40}}\b")
TOKEN_VARS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
FAILED = {"failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale"}
QUEUE_EVENTS = ("added_to_merge_queue", "removed_from_merge_queue")
# A Dependabot head branch: the PR's text reaches git commands the procedure writes, so its name must be plain.
HEAD_SHAPE = re.compile(r"dependabot/[a-z_]+/[A-Za-z0-9._/@+-]+")


def ecosystem(head: str) -> str:
    parts = head.split("/")
    return parts[1] if len(parts) > 2 and parts[0] == "dependabot" else "?"


def api(path: str) -> Any:
    """GET one REST resource (`gh api` prints the body; a non-2xx exits non-zero → ToolError)."""
    return run_json(["gh", "api", path])


def api_pages(path: str, key: str | None = None) -> list[Any]:
    """Every page of a REST list (`key`: the list's field in an object answer, as check-runs has)."""
    sep = "&" if "?" in path else "?"
    items: list[Any] = []
    for page in range(1, MAX_PAGES + 1):
        got = api(f"{path}{sep}per_page={PER_PAGE}&page={page}")
        batch = got.get(key) if key and isinstance(got, dict) else got
        if not isinstance(batch, list):
            raise ToolError(f"gh api {path}: not a list")
        items += batch
        if len(batch) < PER_PAGE:
            return items
    raise ToolError(f"gh api {path}: more than {MAX_PAGES} pages")


def get_pr(number: int) -> dict[str, Any]:
    pr = api(f"repos/{REPO}/pulls/{number}")
    if not isinstance(pr, dict):
        raise ToolError(f"gh api repos/{REPO}/pulls/{number}: not an object")
    return pr


def detect_mode() -> str:
    """`cloud` when GraphQL is refused the way a Claude Code cloud session refuses it, `local` when it answers."""
    r = run(["gh", "api", "graphql", "-f", "query={viewer{login}}"], ok_codes=(0, 1))
    if r.returncode == 0:
        try:
            login = json.loads(r.stdout)["data"]["viewer"]["login"]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise ToolError(f"GraphQL answered without a login: {r.stdout.strip()[:200]}") from e
        if login:
            return "local"
        raise ToolError("GraphQL answered an empty login")
    if GRAPHQL_BLOCKED in r.stdout + r.stderr:
        return "cloud"
    raise ToolError(
        f"GraphQL failed, but not as a Claude Code session refuses it: {(r.stdout + r.stderr).strip()[:300]}"
    )


def preflight() -> None:
    rep = Report("preflight")
    login = run(["gh", "api", "user", "--jq", ".login"]).stdout.strip()
    if not login:
        raise ToolError("gh api user answered no login")
    rep.ok(f"gh api user: {login}")
    mode = detect_mode()
    rep.ok(f"mode: {mode}")
    held = [v for v in TOKEN_VARS if TOKEN_SHAPE.search(os.environ.get(v, ""))]
    clean = {k: v for k, v in os.environ.items() if k not in TOKEN_VARS}
    stored = run(["gh", "auth", "token"], ok_codes=(0, 1), env=clean)
    has_stored = stored.returncode == 0 and bool(STORED_SHAPE.search(stored.stdout))
    if held:
        rep.ok(f"credential: a token in {', '.join(held)}; step 5 strips it from what runs dependency code")
    if mode == "cloud":
        if has_stored:
            rep.problem(
                "gh has a stored login in this cloud session: a file dependency code could read, which step 5 "
                "can't strip; remove it from the environment's setup (the token belongs in the network secret)"
            )
        elif not held:
            rep.ok(
                "credential: a network secret (the proxy adds it for api.github.com; no process here holds it, "
                "and gh has no stored login)"
            )
    elif has_stored:
        rep.ok("credential: gh's stored login (a maintainer's own machine; step 5 hides gh's config)")
    rep.finish()


def list_prs() -> None:
    prs = [
        pr
        for pr in api_pages(f"repos/{REPO}/pulls?state=open&base=dev")
        if (pr.get("user") or {}).get("login") == BOT_LOGIN
    ]
    print(f"{len(prs)} open Dependabot PR(s) into dev")
    for pr in sorted(prs, key=lambda p: p["number"]):
        head = pr["head"]["ref"]
        if HEAD_SHAPE.fullmatch(head):
            shown = head
        else:  # printed quoted, never pasted into a command: `check` stops it
            shown = f"{head!r} (not a plain Dependabot branch name: don't fetch it; `check` stops it)"
        print(f"#{pr['number']} [{ecosystem(head)}] {shown}\n    {pr['title']}")


def pr_problems(rep: Report, pr: dict[str, Any], sha: str) -> None:
    """What `check` and `queue` both require of the PR as GitHub has it now."""
    if pr["state"] != "open" or pr["base"]["ref"] != "dev":
        rep.problem(f"the PR is {pr['state']} into {pr['base']['ref']}, not an open PR into dev")
    if (pr.get("user") or {}).get("login") != BOT_LOGIN:
        rep.problem(f"the PR was opened by {(pr.get('user') or {}).get('login')}, not Dependabot")
    if pr["head"]["sha"] != sha:
        rep.problem(f"GitHub's head is {pr['head']['sha'][:12]}, not the fetched {sha[:12]}: fetch again")
    if not HEAD_SHAPE.fullmatch(pr["head"]["ref"]):
        rep.problem(f"the head branch {pr['head']['ref']!r} is not a plain Dependabot branch name")
    if any(w in pr["title"].lower() for w in HAND_ONLY_WORDS):
        rep.problem("the title names a hand-only dependency (tantivy, spec 08 §Release)")


def check_pr(number: int, head: str) -> None:
    rep = Report(f"PR #{number}")
    sha = run(["git", "rev-parse", "--verify", f"{head}^{{commit}}"]).stdout.strip()
    pr = get_pr(number)
    pr_problems(rep, pr, sha)
    eco = ecosystem(pr["head"]["ref"])
    allowed = ALLOWED.get(eco)
    base, _ = resolve_refs(None, sha)
    diff = run(["git", "diff", "--name-only", "--no-renames", "-z", f"{base}..{sha}"]).stdout
    paths = {p for p in diff.split("\0") if p}
    for f in api_pages(f"repos/{REPO}/pulls/{number}/files"):
        paths.add(f["filename"])
        if f.get("previous_filename"):
            paths.add(f["previous_filename"])
    if allowed is None:
        rep.problem(f"ecosystem {eco!r} is not one the routine reviews")
    else:
        for path in sorted(paths):
            if not allowed.fullmatch(path):
                rep.problem(f"{path} is outside what a {eco} update touches")
    commits = run(["git", "rev-list", f"{base}..{sha}"]).stdout.split()
    if not commits:
        rep.problem("no commits between the merge base and the head")
    remote = {c["sha"]: c for c in api_pages(f"repos/{REPO}/pulls/{number}/commits")}
    if set(remote) != set(commits):
        rep.problem(
            f"GitHub lists {len(remote)} commit(s) for the PR and git {len(commits)} past the merge base, not the "
            "same ones: fetch origin dev and the head again"
        )
    for c in commits:
        who = tuple(
            run(["git", "log", "-1", "--format=%an%x00%ae%x00%cn%x00%ce", c]).stdout.strip().split("\0")
        )
        if who != DEPENDABOT:
            rep.problem(
                f"commit {c[:12]} is by {who[0]} <{who[1]}>, committed by {who[2]}: not Dependabot's alone"
            )
            continue
        if c not in remote:
            continue  # the set comparison above already stopped the PR
        if (remote[c].get("author") or {}).get("login") != BOT_LOGIN:
            rep.problem(f"commit {c[:12]}: GitHub doesn't attribute it to {BOT_LOGIN}")
        verification = remote[c]["commit"]["verification"]
        if verification.get("verified") is not True:
            rep.problem(
                f"commit {c[:12]}: GitHub doesn't verify its signature ({verification.get('reason')})"
            )
    if not rep.problems:
        rep.ok(f"{eco}: {len(paths)} file(s) and {len(commits)} commit(s), all Dependabot's, at {sha[:12]}")
    rep.finish()


def auto_merge(mode: str, number: int, on: bool, sha: str) -> tuple[bool, str]:
    """Turn auto-merge on (at `sha`) or off. (succeeded, what gh said)."""
    if mode == "cloud":
        path = f"repos/{REPO}/pulls/{number}/ccr/auto_merge"
        cmd = ["gh", "api", "-X", "PUT" if on else "DELETE", path]
    elif on:
        cmd = ["gh", "pr", "merge", str(number), "--repo", REPO, "--auto", "--match-head-commit", sha]
    else:
        cmd = ["gh", "pr", "merge", str(number), "--repo", REPO, "--disable-auto"]
    r = run(cmd, ok_codes=(0, 1))
    return r.returncode == 0, (r.stderr.strip() or r.stdout.strip())[:300]


def settle_seconds() -> float:
    """How long `queue` waits before reading once more when GitHub doesn't yet show what it accepted."""
    raw = os.environ.get("OP_DEPENDABOT_SETTLE", "5")
    try:
        return float(raw)
    except ValueError as e:
        raise ToolError(f"OP_DEPENDABOT_SETTLE is {raw!r}, not a number of seconds") from e


def queue_pr(number: int, head: str) -> None:
    rep = Report(f"queue #{number}")
    settle = settle_seconds()
    sha = run(["git", "rev-parse", "--verify", f"{head}^{{commit}}"]).stdout.strip()
    pr = get_pr(number)
    pr_problems(rep, pr, sha)
    if ecosystem(pr["head"]["ref"]) == "github_actions":
        rep.problem("a github-actions PR is queued by the owner (the token has no `workflows` permission)")
    if rep.problems:
        rep.finish()
    if taken(number, pr):
        # a re-queue (step 9) of a PR that is still set to merge: a second PUT could fail, and its undo would
        # take a reviewed PR out of the queue
        rep.ok(f"#{number} is already set to merge at {sha[:12]}: nothing to do")
        rep.finish()
    mode = detect_mode()
    rep.ok(f"mode: {mode}")
    since = now() - dt.timedelta(minutes=2)  # a queue event older than this predates the request (clock skew)
    try:
        enabled, said = auto_merge(mode, number, True, sha)
        after = get_pr(number)
        visible = taken(number, after, since)
        if not visible and not after.get("merged"):  # a refused call can take effect late too
            time.sleep(settle)  # GitHub can take a moment to show what it accepted
            after = get_pr(number)
            visible = taken(number, after, since)
        state, after_sha, merged = after["state"], after["head"]["sha"], bool(after.get("merged"))
    except Exception as e:  # a timeout, an odd exit, a failed or odd read: the PUT may have taken effect
        failure = e if isinstance(e, ToolError) else f"{type(e).__name__}: {e}"
        why = undo(mode, number, sha, since, settle)
        if why is None:
            raise ToolError(
                f"queueing #{number} failed partway ({failure}); auto-merge turned off again"
            ) from e
        raise ToolError(
            f"queueing #{number} failed partway ({failure}); auto-merge may still be on for #{number}, or it may "
            f"still be in the merge queue ({why}): the owner must check it by hand"
        ) from e
    if merged:
        if after_sha == sha:
            rep.ok(f"#{number} merged already, at {sha[:12]}")
        else:
            rep.problem(f"#{number} merged at {after_sha[:12]}, not the reviewed {sha[:12]}: tell the owner")
        rep.finish()
    moved = state != "open" or after_sha != sha
    if not enabled:
        rep.problem(f"turning auto-merge on failed: {said}")
    elif not visible:
        rep.problem("GitHub accepted the request but shows neither auto-merge nor a merge-queue entry")
    if moved:
        rep.problem(f"the PR changed while it was queued: {state} at {after_sha[:12]}")
    if rep.problems:
        # a closed PR can't merge, so there is nothing to undo; otherwise undo whatever may be on
        if state == "open" and (moved or enabled or visible):
            why = undo(mode, number, sha, since, settle)
            if why is not None:
                raise ToolError(
                    f"auto-merge may still be on for #{number}, or it may still be in the merge queue ({why}): "
                    "the owner must check it by hand"
                )
            rep.ok("auto-merge turned off again")
        rep.finish()
    rep.ok(f"auto-merge on at {sha[:12]} ({mode}); the queue takes it once its checks pass")
    rep.finish()


def undo(mode: str, number: int, sha: str, since: dt.datetime, settle: float) -> str | None:
    """Turn auto-merge off, then read the PR back: None when GitHub no longer shows it set to merge, else why
    not (turning auto-merge off doesn't take an entry out of the merge queue)."""
    try:
        off, why = auto_merge(mode, number, False, sha)
        if not off:
            return why
        time.sleep(settle)  # let GitHub catch up before reading it back
        pr = get_pr(number)
        if pr["state"] == "open" and taken(number, pr, since):
            return "GitHub still shows it set to merge after turning auto-merge off"
    except Exception as e:  # any failure here leaves the state unknown, which the caller reports
        return str(e)
    return None


def in_queue(number: int, since: dt.datetime | None = None) -> bool:
    """The PR's latest merge-queue event in its timeline is `added_to_merge_queue` (an entry waiting behind
    others has no build branch yet, and `auto_merge` can read null while it waits), and, with `since`, no older
    than that (an event from before a request is not the request's)."""
    events = [
        e for e in api_pages(f"repos/{REPO}/issues/{number}/timeline") if e.get("event") in QUEUE_EVENTS
    ]
    if not events or events[-1]["event"] != "added_to_merge_queue":
        return False
    return since is None or parse_time(events[-1]["created_at"]) >= since


def taken(number: int, pr: dict[str, Any], since: dt.datetime | None = None) -> bool:
    """GitHub shows the PR set to merge: auto-merge on, or an entry in the merge queue."""
    return bool(pr.get("auto_merge")) or in_queue(number, since)


@dataclass
class Snap:
    state: str  # open | closed | merged
    auto: bool
    queue: list[str]  # the queue's build branches for this PR
    listed: bool  # the timeline's latest merge-queue event is `added_to_merge_queue`
    checks: str
    runs: list[dict[str, Any]]  # the queue's build runs still going

    def line(self) -> str:
        queue = "queue=building" if self.queue else "queue=waiting" if self.listed else "queue=-"
        auto = " auto-merge" if self.auto else ""
        return f"{self.state} {queue}{auto} checks={self.checks}"


def rollup(runs: list[dict[str, Any]]) -> str:
    if not runs:
        return "-"
    if any(r.get("conclusion") in FAILED for r in runs):
        return "failure"
    if any(r.get("status") != "completed" for r in runs):
        return "pending"
    return "success"


def snap(number: int) -> Snap:
    pr = get_pr(number)
    state = "merged" if pr.get("merged") or pr.get("merged_at") else pr["state"]
    refs = api(f"repos/{REPO}/git/matching-refs/heads/gh-readonly-queue/dev/pr-{number}-")
    if not isinstance(refs, list):
        raise ToolError("gh api git/matching-refs: not a list")
    own = re.compile(rf"refs/heads/gh-readonly-queue/dev/pr-{number}-[0-9a-f]{{40}}")
    branches = [r["ref"].removeprefix("refs/heads/") for r in refs if own.fullmatch(r["ref"])]
    sha = pr["head"]["sha"]
    checks = rollup(api_pages(f"repos/{REPO}/commits/{sha}/check-runs", key="check_runs"))
    going: list[dict[str, Any]] = []
    for b in branches:
        branch = urllib.parse.quote(b, safe="/")
        got = api(f"repos/{REPO}/actions/runs?event=merge_group&branch={branch}&per_page={PER_PAGE}")
        going += [r for r in got["workflow_runs"] if r.get("status") != "completed"]
    listed = state == "open" and in_queue(number)
    return Snap(state, bool(pr.get("auto_merge")), branches, listed, checks, going)


def watch(numbers: list[int], interval: float, timeout_min: float, hung_min: float) -> None:
    deadline = time.monotonic() + timeout_min * 60
    last: dict[int, str] = {}
    unqueued: dict[int, int] = {}
    told: set[int] = set()
    while True:
        states = {n: snap(n) for n in numbers}
        for n, s in states.items():
            line = s.line()
            if last.get(n) != line:
                print(f"#{n} {line}", flush=True)
                last[n] = line
            waiting = s.auto or s.queue or s.listed
            unqueued[n] = unqueued.get(n, 0) + 1 if s.state == "open" and not waiting else 0
            for r in s.runs:
                if r["id"] not in told and age_days(r["created_at"]) * 1440 >= hung_min:
                    told.add(r["id"])
                    print(
                        f"#{n} HUNG run {r['id']} ({r.get('name')}) still {r.get('status')} after {hung_min:g} min: "
                        "cancel and rerun it (step 9)",
                        flush=True,
                    )
        closed = [n for n, s in states.items() if s.state == "closed"]
        dropped = [n for n, c in unqueued.items() if c >= 2]
        if closed or dropped:
            for n in closed:
                print(f"#{n} was closed without merging")
            for n in dropped:
                print(f"#{n} is open but out of the merge queue: read its queue run, fix or rerun, re-queue")
            sys.exit(1)
        if all(s.state == "merged" for s in states.values()):
            print("all merged")
            sys.exit(0)
        if time.monotonic() >= deadline:
            left = [n for n in numbers if states[n].state != "merged"]
            print(f"timed out after {timeout_min:g} min; still waiting: {left}")
            sys.exit(4)
        time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    sub.add_parser("list")
    for name in ("check", "queue"):
        c = sub.add_parser(name)
        c.add_argument("number", type=int)
        c.add_argument("--head", required=True, help="the PR head as fetched and reviewed (a sha or a ref)")
    w = sub.add_parser("watch")
    w.add_argument("numbers", type=int, nargs="+")
    w.add_argument("--interval", type=float, default=45)
    w.add_argument("--timeout", type=float, default=120, help="minutes")
    w.add_argument("--hung", type=float, default=40, help="minutes a queue build may run before HUNG")
    a = ap.parse_args()
    if a.cmd == "preflight":
        preflight()
    elif a.cmd == "list":
        list_prs()
    elif a.cmd == "check":
        check_pr(a.number, a.head)
    elif a.cmd == "queue":
        queue_pr(a.number, a.head)
    else:
        watch(a.numbers, a.interval, a.timeout, a.hung)


if __name__ == "__main__":
    main_guard(main)
