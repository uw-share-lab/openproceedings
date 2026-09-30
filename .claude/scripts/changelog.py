#!/usr/bin/env python3
"""Generate CHANGELOG.md from merged pull requests (spec 08 §Release, decision-022).

    python3 .claude/scripts/changelog.py                   # rewrite CHANGELOG.md (make changelog)
    python3 .claude/scripts/changelog.py --check           # exit 1 when CHANGELOG.md differs
    python3 .claude/scripts/changelog.py --release 0.1.0   # title the untagged PRs in HEAD as release 0.1.0
    python3 .claude/scripts/changelog.py --notes 0.1.0     # print one release's section; write nothing
    python3 .claude/scripts/changelog.py --prs prs.json    # read the PR list from a file, not GitHub

The output is a pure function of the merged PRs, the `vX.Y.Z` tags and `docs/releases.toml`: no dates,
no authors, no build clock, so the same inputs give the same bytes. A PR belongs to the oldest release
tag whose history holds its merge commit; with `--release`, HEAD counts as that version's tag (so run it
on the release branch, or on `main` after the promotion). A PR no tag holds is Unreleased.
Counted: PRs merged into `dev`, and into `main` except the `dev → main` promotions (they repeat what dev
already lists) and `release/*` branches (their only change is the changelog and the version bump).
Grouped by the Conventional Commits type in the title, else the head branch's `<type>/` prefix.

A release's Data section comes from its `[releases."X.Y.Z"]` table in `docs/releases.toml`; a release whose
TOKENIZER_VERSION, SCHEMA_VERSION or QUERY_VERSION differs from the previous release's makes saved search
records replay as `drifted`, is called out at the top of its section, and may not be a patch release.
Refuses (exit 1, nothing written) on bad input, and on any AI-attribution marker in the output.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = "CHANGELOG.md"
DATA_FILE = "docs/releases.toml"

SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
TITLE = re.compile(r"(?P<type>[a-z]+)(?:\((?P<scope>[^()]*)\))?(?P<bang>!)?:\s*(?P<desc>\S.*)")
BRANCH = re.compile(r"(?P<type>[a-z]+)/")
GROUPS = ("Added", "Changed", "Fixed", "Internal")
TYPES = {
    "feat": "Added",
    "fix": "Fixed",
    "docs": "Changed",
    "refactor": "Changed",
    "perf": "Changed",
    "revert": "Changed",
    "chore": "Internal",
    "test": "Internal",
    "ci": "Internal",
    "build": "Internal",
    "style": "Internal",
}
# The shared no-AI-attribution pattern (block-ai-attribution.sh, .githooks/commit-msg, pr-gates.yml).
ATTRIBUTION = re.compile(
    r"co-authored-by[:=][^\n]*(claude|anthropic)|generated with \[?claude|🤖 generated|noreply@anthropic\.com",
    re.IGNORECASE,
)
VERSIONS = ("tokenizer_version", "schema_version", "query_version")
DATA_KEYS = {"index_version", "snapshot_hash", *VERSIONS, "notes"}
HEX = {"index_version": re.compile(r"[0-9a-f]{12}"), "snapshot_hash": re.compile(r"[0-9a-f]{64}")}
MD_SPECIAL = re.compile(r"([\\*\[\]<>])")


class Refusal(Exception):
    pass


@dataclass(frozen=True)
class PR:
    number: int
    title: str
    merged_at: str
    merge_commit_sha: str
    base: str
    head: str
    head_repo: str | None


def version_key(v: str) -> tuple[int, int, int]:
    m = SEMVER.fullmatch(v)
    if not m:
        raise Refusal(f"not a MAJOR.MINOR.PATCH version: {v!r}")
    return int(m[1]), int(m[2]), int(m[3])


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def repo_from_origin() -> str:
    r = git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", r.stdout.strip())
    if r.returncode != 0 or not m:
        raise Refusal("can't read owner/name from the origin remote: pass --repo OWNER/NAME")
    return m[1]


def parse_prs(rows: Any) -> list[PR]:
    if not isinstance(rows, list):
        raise Refusal("the PR list must be a JSON array")
    prs = []
    for row in rows:
        try:
            pr = PR(
                number=int(row["number"]),
                title=str(row["title"]),
                merged_at=str(row["merged_at"]),
                merge_commit_sha=str(row["merge_commit_sha"]),
                base=str(row["base"]),
                head=str(row["head"]),
                head_repo=None if row.get("head_repo") is None else str(row["head_repo"]),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise Refusal(f"malformed PR entry {row!r}: {e}") from None
        if not re.fullmatch(r"[0-9a-f]{40}", pr.merge_commit_sha):
            raise Refusal(f"PR #{pr.number}: merge_commit_sha is not a full sha")
        prs.append(pr)
    numbers = [p.number for p in prs]
    if len(set(numbers)) != len(numbers):
        raise Refusal("the PR list repeats a PR number")
    return prs


def fetch_prs(repo: str) -> list[PR]:
    """Every merged PR, from the REST API (`gh pr list` uses GraphQL; REST is what this repo scripts)."""
    jq = (
        ".[] | select(.merged_at != null) | {number, title, merged_at, merge_commit_sha, "
        "base: .base.ref, head: .head.ref, head_repo: .head.repo.full_name}"
    )
    try:
        r = subprocess.run(
            ["gh", "api", "--paginate", "--jq", jq, f"repos/{repo}/pulls?state=closed&per_page=100"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise Refusal("gh is not installed: install it, or pass --prs <file>") from None
    if r.returncode != 0:
        raise Refusal(f"gh api failed: {r.stderr.strip()}")
    return parse_prs([json.loads(line) for line in r.stdout.splitlines() if line.strip()])


def counted(pr: PR, repo: str) -> bool:
    if pr.head.startswith("release/"):
        return False
    if pr.base == "dev":
        return True
    promotion = pr.head == "dev" and pr.head_repo == repo
    return pr.base == "main" and not promotion


def release_tags() -> list[str]:
    r = git("tag", "--list", "v*")
    if r.returncode != 0:
        raise Refusal(f"git tag failed: {r.stderr.strip()}")
    tags = [t for t in r.stdout.split() if SEMVER.fullmatch(t[1:])]
    return sorted(tags, key=lambda t: version_key(t[1:]))


def release_of(pr: PR, bounds: list[tuple[str, str]]) -> str | None:
    """The version of the oldest (version, ref) bound whose history holds the PR's merge commit; None if
    none does. The bounds are the tags, oldest first, then ("<--release>", "HEAD")."""
    for version, ref in bounds:
        r = git("merge-base", "--is-ancestor", pr.merge_commit_sha, ref)
        if r.returncode == 0:
            return version
        if r.returncode != 1:
            raise Refusal(
                f"PR #{pr.number}: can't place merge commit {pr.merge_commit_sha[:12]} "
                "(run `git fetch origin --tags` first)"
            )
    return None


def load_data(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise Refusal(f"{DATA_FILE}: {e}") from None
    extra = set(doc) - {"releases"}
    if extra:
        raise Refusal(f"{DATA_FILE}: unknown top-level keys {sorted(extra)}")
    releases = doc.get("releases", {})
    out: dict[str, dict[str, str]] = {}
    for version, entry in releases.items():
        version_key(version)
        if not isinstance(entry, dict):
            raise Refusal(f"{DATA_FILE}: releases.{version} is not a table")
        unknown = set(entry) - DATA_KEYS
        missing = DATA_KEYS - {"notes"} - set(entry)
        if unknown or missing:
            raise Refusal(
                f"{DATA_FILE}: releases.{version}: unknown {sorted(unknown)}, missing {sorted(missing)}"
            )
        for key, value in entry.items():
            if not isinstance(value, str) or not value.strip():
                raise Refusal(f"{DATA_FILE}: releases.{version}.{key} must be a non-empty string")
            if key in HEX and not HEX[key].fullmatch(value):
                raise Refusal(f"{DATA_FILE}: releases.{version}.{key} is not a {key} ({value!r})")
        out[version] = entry
    return out


def check_manifests(version: str) -> None:
    """The backend and frontend carry the release's version (decision-022: one app version)."""
    backend = tomllib.loads((ROOT / "backend/pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    frontend = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))["version"]
    if backend != version or frontend != version:
        raise Refusal(
            f"--release {version}: backend/pyproject.toml says {backend}, frontend/package.json says "
            f"{frontend}; bump both first (spec 08 §Release)"
        )


def entry(pr: PR, repo: str) -> tuple[str, str]:
    """(group, markdown line) for one PR."""
    m = TITLE.fullmatch(pr.title.strip())
    if m and m["type"] in TYPES:
        group, desc = TYPES[m["type"]], m["desc"]
        desc = f"{m['scope']}: {desc}" if m["scope"] else desc
        breaking = bool(m["bang"])
    else:
        b = BRANCH.match(pr.head)
        group, desc, breaking = TYPES.get(b["type"] if b else "", "Changed"), pr.title.strip(), False
    text = MD_SPECIAL.sub(r"\\\1", " ".join(desc.split()))
    if breaking:
        text = f"**Breaking:** {text}"
    return group, f"- {text} ([#{pr.number}](https://github.com/{repo}/pull/{pr.number}))"


def data_block(version: str, data: dict[str, dict[str, str]]) -> tuple[list[str], list[str]]:
    """(callout lines for the top of the section, the Data section) for a release."""
    if version not in data:
        raise Refusal(f'release {version} has no [releases."{version}"] table in {DATA_FILE}')
    d = data[version]
    earlier = sorted((v for v in data if version_key(v) < version_key(version)), key=version_key)
    prev = earlier[-1] if earlier else None
    changed = [k for k in VERSIONS if prev and data[prev][k] != d[k]]
    callout: list[str] = []
    if prev is None:
        replay = "First release: no earlier search records."
    elif changed:
        if version_key(version)[:2] == version_key(prev)[:2]:
            raise Refusal(f"{version} changes {', '.join(k.upper() for k in changed)}: not a patch release")
        moves = ", ".join(f"{k.upper()} {data[prev][k]} → {d[k]}" for k in changed)
        callout = [f"**Search records saved on {prev} replay as `drifted`: {moves}.**", ""]
        replay = f"Search records saved on {prev} replay as `drifted` ({moves})."
    else:
        replay = (
            f"Search records saved on {prev} replay as `reproduced` on the index_version they pin, "
            "while it is kept."
        )
    lines = [
        "### Data",
        "",
        f"- index_version `{d['index_version']}`, snapshot `{d['snapshot_hash']}`",
        f"- TOKENIZER_VERSION {d['tokenizer_version']} · SCHEMA_VERSION {d['schema_version']} · "
        f"QUERY_VERSION {d['query_version']}",
        f"- {replay}",
    ]
    if "notes" in d:
        lines.append(f"- {' '.join(d['notes'].split())}")
    return callout, [*lines, ""]


def render(
    prs: list[PR],
    placed: dict[int, str | None],
    data: dict[str, dict[str, str]],
    repo: str,
    release: str | None,
) -> str:
    sections: dict[str | None, list[PR]] = {}
    for pr in prs:
        sections.setdefault(placed[pr.number], []).append(pr)
    versions = sorted((v for v in sections if v is not None), key=version_key, reverse=True)
    order: list[str | None] = [None, *versions] if None in sections else [*versions]
    if release and release not in sections:
        raise Refusal(f"--release {release}: no merged PR since the last release")
    out = [
        "# Changelog",
        "",
        "<!-- Generated by .claude/scripts/changelog.py (make changelog) from merged pull requests,",
        f"     release tags and {DATA_FILE}. Don't edit by hand: spec 08 §Release, decision-022. -->",
        "",
        "Every pull request merged into `dev`, by release. Versions are one semver for the backend and the",
        "frontend, tagged `vX.Y.Z` on `main`. A release's Data section names the index it was verified on: the",
        "code version never decides which papers a query matches; `index_version` and `query_version` do.",
        "",
    ]
    for version in order:
        out += [f"## {version or 'Unreleased'}", ""]
        callout, data_lines = data_block(version, data) if version else ([], [])
        out += callout
        grouped: dict[str, list[str]] = {g: [] for g in GROUPS}
        for pr in sorted(sections[version], key=lambda p: (p.merged_at, p.number)):
            group, line = entry(pr, repo)
            grouped[group].append(line)
        for group in GROUPS:
            if grouped[group]:
                out += [f"### {group}", "", *grouped[group], ""]
        out += data_lines
    text = "\n".join(out).rstrip("\n") + "\n"
    if hit := ATTRIBUTION.search(text):
        lineno = text[: hit.start()].count("\n") + 1
        raise Refusal(f"line {lineno} carries an AI-attribution marker ({hit[0]!r}): fix the PR title")
    return text


def section(text: str, version: str) -> str:
    """One release's section of the rendered changelog, without its heading: the GitHub release notes."""
    parts = re.split(r"^## ", text, flags=re.MULTILINE)
    for part in parts[1:]:
        heading, _, body = part.partition("\n")
        if heading == version:
            return body.strip("\n") + "\n"
    raise Refusal(f"--notes {version}: no such release in the changelog")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--release", metavar="X.Y.Z", help="title the untagged PRs in HEAD as this release")
    ap.add_argument(
        "--notes", metavar="X.Y.Z", help="print this release's section (release notes); write nothing"
    )
    ap.add_argument("--prs", type=Path, help="a JSON array of merged PRs instead of asking GitHub")
    ap.add_argument("--repo", help="OWNER/NAME for PR links (default: the origin remote)")
    ap.add_argument("--check", action="store_true", help="exit 1 when CHANGELOG.md differs; write nothing")
    a = ap.parse_args(argv)
    try:
        repo = a.repo or repo_from_origin()
        tags = release_tags()
        if a.release:
            version_key(a.release)
            if tags and version_key(a.release) <= version_key(tags[-1][1:]):
                raise Refusal(f"--release {a.release} is not newer than the latest tag {tags[-1]}")
            check_manifests(a.release)
        if a.prs:
            try:
                prs = parse_prs(json.loads(a.prs.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError) as e:
                raise Refusal(f"--prs {a.prs}: {e}") from None
        else:
            prs = fetch_prs(repo)
        prs = [p for p in prs if counted(p, repo)]
        bounds = [(t[1:], t) for t in tags] + ([(a.release, "HEAD")] if a.release else [])
        placed = {p.number: release_of(p, bounds) for p in prs}
        text = render(prs, placed, load_data(ROOT / DATA_FILE), repo, a.release)
        if a.notes:
            text = section(text, a.notes)
    except Refusal as e:
        print(f"changelog: {e}", file=sys.stderr)
        return 1
    if a.notes:
        sys.stdout.write(text)
        return 0
    target = ROOT / CHANGELOG
    if a.check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != text:
            print(f"changelog: {CHANGELOG} is stale: run `make changelog`", file=sys.stderr)
            return 1
        print(f"changelog: {CHANGELOG} is current")
        return 0
    target.write_text(text, encoding="utf-8")
    print(f"changelog: wrote {CHANGELOG} ({len(prs)} PRs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
