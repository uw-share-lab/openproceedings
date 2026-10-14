#!/usr/bin/env python3
"""Set up, list, check, queue and watch the open Dependabot PRs into dev (/dependabot-review; TASK-211, TASK-213).

    python3 .claude/scripts/dependabot/prs.py preflight
    python3 .claude/scripts/dependabot/prs.py uv-release
    python3 .claude/scripts/dependabot/prs.py list
    python3 .claude/scripts/dependabot/prs.py check <n> --head <sha>
    python3 .claude/scripts/dependabot/prs.py ci <n> --head <sha> [--interval 60] [--timeout 60]
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

`preflight` (step 0) checks that `gh api repos/uw-share-lab/openproceedings` answers (a repository-scoped call: the
cloud proxy refuses paths outside `repos/...`, so `gh api user` may fail there, and `gh auth status` calls the
session's placeholder token invalid), prints the mode, and checks the credential's reach. In the cloud that is the
session binding: `gh api user/installations` must be refused with the proxy's HTTP 403 "This GitHub API path is not
available: sessions are bound to their configured repositories", and `gh api repos/astral-sh/uv` (a public
repository the session isn't bound to) with its HTTP 403 "GitHub access to this repository is not enabled for this
session"; any other answer, a 200 included, is a PROBLEM (the 2026-10-13 probe showed the installation API can't
answer there; decision-048, TASK-243 AC6). Locally it reads `gh api orgs/uw-share-lab/installations` (an org
owner's call; it fails, exit 2, for anyone else, or when the number it lists isn't its `total_count`) and
prints the Claude App installation's repository selection and permissions; a selection other than `selected`, or no
installation by the `claude` app at all, is a PROBLEM. Then the credential itself: in the cloud gh
must have no stored login (one would be a file dependency code could read, which step 5 can't strip), and a real
token in GH_TOKEN or GITHUB_TOKEN is reported (step 5 strips those). Locally a stored login is allowed: it is the
maintainer's own machine, where `make test` runs with it every day. In the cloud it also writes the clone's
no-dependency-code marker, `op-no-dep-code` in git's common directory: a cloud run executes none of a PR's
dependency code (decision-048, 2026-10-13), and while the marker is there `make sync`, `fmt`, `lint`, `test`, `e2e`
and `openapi` refuse, `scripts/setup-dev.sh` skips its `uv sync`, and `.githooks/pre-push` skips its `make lint`.
Locally it removes a marker it finds. A checker: ok / PROBLEM; exit 0, 1 or 2.

`uv-release` (step 0) compares the api image's uv (`deploy/api.Dockerfile` on origin/dev) with uv's latest release
(`gh api repos/astral-sh/uv/releases/latest`). It prints `ok` lines, and an `OWNER` line for the summary's "for the
owner" when the release is a newer minor, or when the call is refused by the cloud session binding (HTTP 403 "GitHub
access to this repository is not enabled for this session": check uv's latest release by hand). Exit 0; 2 when the
pin can't be read or the call fails any other way.

`ci` reads, over REST, CI's results for the PR's head `<sha>`, which in the cloud stand in for every local run of
the PR's dependencies (step 5): the latest GitHub Actions check run of each of `lint`, `test`, `claude-tooling`,
`playwright` and `bench`, and `web-image` when the PR touches a path that workflow runs on. A check run by any
other app doesn't count (the session's App can write checks). It requires the PR as `queue` does (open,
Dependabot's, into `dev`, still at `<sha>`), then polls every `--interval` seconds while a check is still running
or not yet listed, for up to `--timeout` minutes (default 9, under the Bash tool's 10-minute limit). Every check
`success` is exit 0; any other conclusion is a PROBLEM (exit 1: leave the PR open; no local rerun in the cloud),
with the run's URL; gh failing is exit 2; a check still running or not yet listed at the timeout, with none red, is
exit 4: run it again on the same head, up to an hour of waiting in all, then leave the PR open.

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
spec 08 §Release), a head branch name that isn't plain, or a body with Dependabot's "Cooldown could not be
applied" notice (it found no publication date, so nothing held the release back 7 days), is a PROBLEM too.

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
import math
import os
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _common import (
    NOT_ENABLED,
    SESSION_BOUND,
    Report,
    ToolError,
    age_days,
    detect_mode,
    git_show,
    main_guard,
    now,
    parse_time,
    refusal,
    refused,
    resolve_refs,
    run,
    run_json,
    version_tuple,
)

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
# The notice Dependabot puts in a PR's body when it found no publication date and so skipped `cooldown` (for docker,
# any registry but Docker Hub, and a Docker Hub lookup that failed): nothing held the release back 7 days.
COOLDOWN_SKIPPED = "cooldown could not be applied"
BOT_LOGIN = "dependabot[bot]"
DEPENDABOT = (
    "dependabot[bot]",
    "49699333+dependabot[bot]@users.noreply.github.com",
    "GitHub",
    "noreply@github.com",
)
PER_PAGE = 100
MAX_PAGES = 30
# A GitHub token's shape (classic, OAuth, app, refresh, fine-grained): a placeholder doesn't have it.
TOKEN_SHAPE = re.compile(r"gh[opsur]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}")
# what gh may hold as a stored login: a token of today's shape, or a classic 40-hex one (still valid if old)
STORED_SHAPE = re.compile(rf"{TOKEN_SHAPE.pattern}|\b[0-9a-f]{{40}}\b")
TOKEN_VARS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
FAILED = {"failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale"}
QUEUE_EVENTS = ("added_to_merge_queue", "removed_from_merge_queue")
# A Dependabot head branch: the PR's text reaches git commands the procedure writes, so its name must be plain.
HEAD_SHAPE = re.compile(r"dependabot/[a-z_]+/(?!.*\.\.)[A-Za-z0-9._/@+-]+")  # git forbids ".." too
# In git's common directory of a cloud clone: make's dependency targets, setup-dev.sh's uv sync and the pre-push
# hook's make lint stand down while it exists (decision-048, 2026-10-13: a cloud run executes no PR dependency code).
NO_DEP_CODE = "op-no-dep-code"
# What a tree honours the marker with. A PR based on an older dev lacks them, and git runs the checked-out tree's
# Makefile and pre-push hook, so in a cloud clone `check` stops such a head (the routine asks Dependabot to rebase).
GUARDED = {
    "Makefile": "dep-code-allowed",
    ".githooks/pre-push": NO_DEP_CODE,
    "scripts/setup-dev.sh": NO_DEP_CODE,
}
# CI's checks that stand in for step 5's local runs in the cloud (GitHub Actions runs them, without the session's
# credential), and the paths `web-image.yml` runs on, which add `web-image`.
CI_CHECKS = ("lint", "test", "claude-tooling", "playwright", "bench")
CI_APP = "github-actions"
WEB_IMAGE_PATHS = re.compile(
    r"(?:deploy|frontend)/.+|package\.json|package-lock\.json|\.dockerignore|\.github/workflows/web-image\.yml"
)
ORG = "uw-share-lab"
APP_SLUG = "claude"
# step 0's session-binding check (cloud): a path outside `repos/...` and a public repository the session isn't bound
# to, each of which the proxy must refuse with its own 403 (decision-048, TASK-243 AC6 addendum)
UNBOUND_PATH = "user/installations"
OTHER_REPO = "astral-sh/uv"
# the api image's uv stage, whose minors come by hand (step 0; `.github/dependabot.yml` ignores them while uv is 0.x)
UV_DOCKERFILE = "deploy/api.Dockerfile"
UV_PIN = re.compile(r"ghcr\.io/astral-sh/uv:(\d+(?:\.\d+)+)@sha256:[0-9a-f]{64}")


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


def marker_path() -> Path:
    """The no-dependency-code marker, in git's common directory (shared by every worktree of the clone)."""
    common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"]).stdout.strip()
    return Path(common) / NO_DEP_CODE


def session_binding(rep: Report) -> None:
    """Cloud: the proxy confines the session's credential to this repository. Both refusals must be the proxy's own
    403s, word for word; any other answer (a 200 included) is a PROBLEM that stops the run."""
    for cmd, message, what in (
        (["gh", "api", UNBOUND_PATH], SESSION_BOUND, f"gh api {UNBOUND_PATH} (outside repos/...)"),
        (
            ["gh", "api", f"repos/{OTHER_REPO}"],
            NOT_ENABLED,
            f"gh api repos/{OTHER_REPO} (another repository)",
        ),
    ):
        got = refused(cmd, message)
        if got is None:
            rep.ok(f"session binding: {what} refused: {message!r}")
        else:
            rep.problem(
                f"session binding: {what} was not refused with {message!r} (HTTP 403): {got}; the session's "
                f"credential may reach beyond {REPO}"
            )


def installations(rep: Report) -> None:
    """Local: the Claude App's installation on the org must cover selected repositories only (the owner limited it to
    openproceedings, 2026-10-13). `orgs/<org>/installations` needs an org owner's credential; the repository list of
    a selected installation isn't readable with a gh login, so the selection is what is checked."""
    got = run_json(["gh", "api", f"orgs/{ORG}/installations?per_page=100"])
    if got["total_count"] != len(got["installations"]):
        raise ToolError(
            f"gh api orgs/{ORG}/installations listed {len(got['installations'])} of {got['total_count']} installations"
        )
    found = [i for i in got["installations"] if i["app_slug"] == APP_SLUG]
    if not found:
        seen = ", ".join(sorted(str(i["app_slug"]) for i in got["installations"])) or "none"
        rep.problem(
            f"installation: no {APP_SLUG!r} App installation on {ORG} (apps installed: {seen}); its selection can't "
            "be checked: if the Claude App was renamed or removed, say so to the owner (decision-048)"
        )
    for inst in found:
        perms = ", ".join(f"{k} {v}" for k, v in sorted((inst.get("permissions") or {}).items()))
        selection = inst["repository_selection"]
        rep.ok(f"installation: Claude App {inst['id']} on {ORG}, repository_selection {selection}; {perms}")
        if selection != "selected":
            rep.problem(
                f"installation: the Claude App installation {inst['id']} covers {selection} of {ORG}'s repositories; "
                f"limit it to openproceedings (org Settings > GitHub Apps > Claude > Configure; decision-048)"
            )


def preflight() -> None:
    rep = Report("preflight")
    # a repository-scoped call: a cloud session's proxy refuses paths outside repos/... (`gh api user` may fail there)
    name = run(["gh", "api", f"repos/{REPO}", "--jq", ".full_name"]).stdout.strip()
    if name != REPO:
        raise ToolError(f"gh api repos/{REPO} answered {name!r}, not {REPO}")
    rep.ok(f"gh api repos/{REPO}: answers")
    mode = detect_mode()
    rep.ok(f"mode: {mode}")
    marker = marker_path()
    if mode == "cloud":
        marker.write_text(
            "cloud mode (prs.py preflight): this run executes none of a PR's dependency code (decision-048)\n"
        )
        rep.ok(
            f"no dependency code: {marker} written; make sync, fmt, lint, test, e2e and openapi refuse here, "
            "setup-dev.sh skips uv sync and the pre-push hook skips make lint (CI's checks stand in: prs.py ci)"
        )
        session_binding(rep)
    else:
        if marker.exists():
            marker.unlink()
            rep.ok(f"removed {marker}: a local clone runs the PR's tests itself")
        installations(rep)
    held = [v for v in TOKEN_VARS if STORED_SHAPE.search(os.environ.get(v, ""))]
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


def uv_release() -> None:
    """Step 0: the api image's uv against uv's latest release. A newer minor is for the owner (`OWNER` line); in the
    cloud the call is refused by the session binding, and checking by hand is for the owner. Exit 0, or 2 when the pin
    can't be read or the call fails any other way."""
    text = git_show("origin/dev", UV_DOCKERFILE)
    pins = UV_PIN.findall(text or "")
    if len(set(pins)) != 1:
        raise ToolError(f"{UV_DOCKERFILE} on origin/dev pins uv {len(set(pins))} ways, not one")
    pinned = pins[0]
    print(f"ok      pinned: uv {pinned} ({UV_DOCKERFILE} on origin/dev)")
    r = run(["gh", "api", f"repos/{OTHER_REPO}/releases/latest"], ok_codes=(0, 1))
    if (why := refusal(r, NOT_ENABLED)) is None:
        print(
            f"OWNER   check uv's latest release by hand (https://github.com/{OTHER_REPO}/releases/latest; pinned "
            f"{pinned}): this cloud session isn't bound to {OTHER_REPO} ({NOT_ENABLED!r}, HTTP 403)"
        )
        return
    if r.returncode:
        raise ToolError(f"gh api repos/{OTHER_REPO}/releases/latest failed: {why}")
    try:
        tag = str(json.loads(r.stdout)["tag_name"])
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ToolError(f"gh api repos/{OTHER_REPO}/releases/latest answered no tag_name") from e
    latest, have = version_tuple(tag), version_tuple(pinned)
    if not latest:
        raise ToolError(f"uv's latest release has no version in its tag {tag!r}")
    if latest[:2] > have[:2]:
        print(
            f"OWNER   uv {tag} is a newer minor than the pinned {pinned}: upgrade the api image's uv by hand"
        )
    else:
        print(f"ok      latest: uv {tag}, no newer minor than the pinned {pinned}")


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
    if COOLDOWN_SKIPPED in (pr.get("body") or "").lower():
        rep.problem(
            "Dependabot says its cooldown could not be applied (no publication date): nothing held this release"
            " back 7 days (decision-048)"
        )
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
    if marker_path().exists():  # a cloud clone: the head's own Makefile and hooks must honour the marker
        old = [f for f, word in GUARDED.items() if word not in (git_show(sha, f) or "")]
        if old:
            rep.problem(
                f"the head's {', '.join(old)} predate the no-dependency-code guard (a base older than it): comment "
                "`@dependabot rebase` and list the PR as not reviewed"
            )
    if not rep.problems:
        rep.ok(f"{eco}: {len(paths)} file(s) and {len(commits)} commit(s), all Dependabot's, at {sha[:12]}")
    rep.finish()


def ci_state(sha: str, names: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    """Each named check's (state, run URL) on `sha`: its latest GitHub Actions run's conclusion, `pending` while
    it runs, or `missing` when no such run is listed (no URL)."""
    latest: dict[str, dict[str, Any]] = {}
    for r in api_pages(f"repos/{REPO}/commits/{sha}/check-runs", key="check_runs"):
        name = r.get("name")
        if (r.get("app") or {}).get("slug") != CI_APP or name not in names:
            continue
        if name not in latest or r["id"] > latest[name]["id"]:
            latest[name] = r
    state: dict[str, tuple[str, str]] = {}
    for name in names:
        r = latest.get(name)
        if r is None:
            state[name] = ("missing", "")
        elif r.get("status") != "completed":
            state[name] = ("pending", r.get("html_url") or "")
        else:
            state[name] = (r.get("conclusion") or "no conclusion", r.get("html_url") or "")
    return state


def ci_pr(number: int, head: str, interval: float, timeout_min: float) -> None:
    rep = Report(f"CI #{number}")
    sha = run(["git", "rev-parse", "--verify", f"{head}^{{commit}}"]).stdout.strip()
    pr_problems(rep, get_pr(number), sha)
    if rep.problems:
        rep.finish()
    paths: set[str] = set()
    for f in api_pages(f"repos/{REPO}/pulls/{number}/files"):
        paths.add(f["filename"])
        if f.get("previous_filename"):
            paths.add(f["previous_filename"])
    names = CI_CHECKS + (("web-image",) if any(WEB_IMAGE_PATHS.fullmatch(p) for p in paths) else ())
    deadline = time.monotonic() + timeout_min * 60
    while True:
        state = ci_state(sha, names)
        red = [n for n in names if state[n][0] not in ("success", "pending", "missing")]
        waiting = [n for n in names if state[n][0] in ("pending", "missing")]
        if red or not waiting or time.monotonic() >= deadline:
            break
        print(f"waiting for {', '.join(waiting)} at {sha[:12]}", flush=True)
        time.sleep(interval)
    for n in names:
        got, url = state[n]
        at = f"at {sha[:12]}" + (f" ({url})" if url else "")
        if got == "success":
            rep.ok(f"{n}: success {at}")
        elif n in red:
            rep.problem(f"{n}: {got} {at}: CI's result stands; no local rerun in the cloud")
        elif red:
            rep.problem(f"{n}: {got} {at} (not waited for: another check is red)")
        else:
            print(f"waiting {n}: {got} {at}", flush=True)
    if waiting and not red:
        print(
            f"CI #{number}: still waiting for {', '.join(waiting)} after {timeout_min:g} min: run this again on the "
            "same head, up to an hour of waiting in all; then leave the PR open for the owner"
        )
        sys.exit(4)
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
        seconds = float(raw)
    except ValueError as e:
        raise ToolError(f"OP_DEPENDABOT_SETTLE is {raw!r}, not a number of seconds") from e
    if not math.isfinite(seconds) or seconds < 0:  # time.sleep refuses these, after the PUT
        raise ToolError(f"OP_DEPENDABOT_SETTLE is {raw!r}, not a number of seconds")
    return seconds


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
        return str(e) if isinstance(e, ToolError) else f"{type(e).__name__}: {e}"
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
    sub.add_parser("uv-release")
    for name in ("check", "queue", "ci"):
        c = sub.add_parser(name)
        c.add_argument("number", type=int)
        c.add_argument("--head", required=True, help="the PR head as fetched and reviewed (a sha or a ref)")
        if name == "ci":
            c.add_argument("--interval", type=float, default=60, help="seconds between reads")
            c.add_argument("--timeout", type=float, default=9, help="minutes to wait for running checks")
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
    elif a.cmd == "uv-release":
        uv_release()
    elif a.cmd == "check":
        check_pr(a.number, a.head)
    elif a.cmd == "queue":
        queue_pr(a.number, a.head)
    elif a.cmd == "ci":
        ci_pr(a.number, a.head, a.interval, a.timeout)
    else:
        watch(a.numbers, a.interval, a.timeout, a.hung)


if __name__ == "__main__":
    main_guard(main)
