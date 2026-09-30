#!/usr/bin/env python3
"""Generate CHANGELOG.md from merged pull requests (spec 08 §Release, decision-023).

    python3 .claude/scripts/changelog.py                   # rewrite CHANGELOG.md (make changelog)
    python3 .claude/scripts/changelog.py --check           # exit 1 when CHANGELOG.md differs
    python3 .claude/scripts/changelog.py --release 0.1.0   # title the untagged PRs in HEAD as release 0.1.0
    python3 .claude/scripts/changelog.py --notes 0.1.0     # print one release's section; write nothing
    python3 .claude/scripts/changelog.py --prs prs.json    # read the PR list from a file, not GitHub

The output is a pure function of the merged PRs, the `vX.Y.Z` tags and `docs/releases.toml`: no dates,
no authors, no build clock, so the same inputs give the same bytes. A PR belongs to the oldest release
tag whose history holds its merge commit; with `--release`, HEAD counts as that version's tag (so run it
on the release branch, or on `main` after the promotion). A PR no tag holds is Unreleased.
Counted: PRs merged into `dev`, and into `main` except this repo's `dev → main` promotions (they repeat what
dev already lists); never this repo's `release/*` branches (release bookkeeping: the version bump, the data
table and this file before the promotion, the main → dev back-merge after the tag).
Grouped by the Conventional Commits type in the title, else the head branch's `<type>/` prefix.

A release's Data section comes from its `[releases."X.Y.Z"]` table in `docs/releases.toml`. With
`--release`, that table must match the code at HEAD (TOKENIZER_VERSION, SCHEMA_VERSION, QUERY_VERSION and the
locked Tantivy) and the manifest of the index it names under `--data-dir`. A release whose versions differ
from the previous release's makes saved search records replay as `drifted`: it is called out at the top of
its section, and may not be a patch release.
Refuses (exit 1, nothing written) on bad input; on a PR title or note that carries an AI-attribution marker,
an @-mention or a URL; and on any AI-attribution marker in the output.
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
REPO = re.compile(r"[a-z0-9_.-]+/[a-z0-9_.-]+")
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
# Release notes name roles, not people, and link only PRs: a GitHub @-mention or a URL in a title is refused.
MENTION_OR_URL = re.compile(r"(?<![\w.])@[A-Za-z0-9-]|://|\bwww\.", re.IGNORECASE)
# What decides whether a search record replays as `reproduced` (spec 08 §Release): the index's build inputs
# the engine checks before serving it (engine/tantivy_engine.py `unservable`), and the query semantics.
COMPAT = {
    "tokenizer_version": "TOKENIZER_VERSION",
    "schema_version": "SCHEMA_VERSION",
    "tantivy_version": "Tantivy",
    "query_version": "QUERY_VERSION",
}
# Where the code at HEAD defines each: (file, pattern); Tantivy is the version uv.lock pins.
CODE = {
    "tokenizer_version": (
        "backend/src/openproceedings/query/normalize.py",
        r'^TOKENIZER_VERSION = "([^"]+)"',
    ),
    "schema_version": ("backend/src/openproceedings/engine/index.py", r'^SCHEMA_VERSION = "([^"]+)"'),
    "query_version": ("backend/src/openproceedings/query/__init__.py", r'^QUERY_VERSION = "([^"]+)"'),
}
MANIFEST_KEYS = ("index_version", "snapshot_hash", "tokenizer_version", "schema_version", "tantivy_version")
DATA_KEYS = {"index_version", "snapshot_hash", *COMPAT, "notes"}
HEX = {"index_version": re.compile(r"[0-9a-f]{12}"), "snapshot_hash": re.compile(r"[0-9a-f]{64}")}
# Markdown that would change how a title renders; a run of `_` only where it touches a word edge (intraword
# `_` never emphasises, so `venue_name` stays readable and `__init__` is escaped).
MD_SPECIAL = re.compile(r"[\\*\[\]<>`]|(?<!\w)_+|_+(?!\w)")


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


def normalize_repo(repo: str) -> str:
    """OWNER/NAME, lower-cased: GitHub names are case-insensitive, and every clone must give the same bytes."""
    repo = repo.lower()
    if not REPO.fullmatch(repo):
        raise Refusal(f"not an OWNER/NAME repository: {repo!r}")
    return repo


def repo_from_origin() -> str:
    r = git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", r.stdout.strip())
    if r.returncode != 0 or not m:
        raise Refusal("can't read owner/name from the origin remote: pass --repo OWNER/NAME")
    return m[1]


def check_text(what: str, text: str) -> None:
    """Refuse text that would put an AI-attribution marker, a person or a link into the release notes. Run on
    the raw text: escaping could hide a marker (`\\[Claude`) from the pattern."""
    if hit := ATTRIBUTION.search(text):
        raise Refusal(f"{what} carries an AI-attribution marker ({hit[0]!r}): fix it")
    if hit := MENTION_OR_URL.search(text):
        raise Refusal(
            f"{what} carries an @-mention or a URL ({hit[0]!r}): release notes name roles and link PRs"
        )


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
                head_repo=None if row.get("head_repo") is None else str(row["head_repo"]).lower(),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise Refusal(f"malformed PR entry {row!r}: {e}") from None
        if not re.fullmatch(r"[0-9a-f]{40}", pr.merge_commit_sha):
            raise Refusal(f"PR #{pr.number}: merge_commit_sha is not a full sha")
        prs.append(pr)
    numbers = [p.number for p in prs]
    if len(set(numbers)) != len(numbers):
        raise Refusal("the PR list repeats a PR number")
    return prs


def fetch_prs(repo: str) -> list[PR]:
    """Every merged PR, from the REST API (`gh pr edit` fails here on the retired Projects API; the repo's
    scripts use REST)."""
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
    try:
        return parse_prs([json.loads(line) for line in r.stdout.splitlines() if line.strip()])
    except json.JSONDecodeError as e:
        raise Refusal(f"gh api returned something that isn't JSON lines: {e}") from None


def counted(pr: PR, repo: str) -> bool:
    ours = pr.head_repo == repo
    if pr.head.startswith("release/") and ours:
        return False
    if pr.base == "dev":
        return True
    return pr.base == "main" and not (pr.head == "dev" and ours)


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
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise Refusal(f"{DATA_FILE}: {e}") from None
    extra = set(doc) - {"releases"}
    if extra:
        raise Refusal(f"{DATA_FILE}: unknown top-level keys {sorted(extra)}")
    releases = doc.get("releases", {})
    if not isinstance(releases, dict):
        raise Refusal(f'{DATA_FILE}: `releases` must hold one [releases."X.Y.Z"] table per release')
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
        if "notes" in entry:
            check_text(f"{DATA_FILE}: releases.{version}.notes", entry["notes"])
        out[version] = entry
    return out


def read(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise Refusal(f"can't read {rel}: {e}") from None


def check_manifests(version: str) -> None:
    """The backend and frontend carry the release's version (decision-023: one app version)."""
    try:
        backend = tomllib.loads(read("backend/pyproject.toml"))["project"]["version"]
        frontend = json.loads(read("frontend/package.json"))["version"]
    except (KeyError, TypeError, tomllib.TOMLDecodeError, json.JSONDecodeError) as e:
        raise Refusal(
            f"can't read the version from backend/pyproject.toml or frontend/package.json: {e!r}"
        ) from None
    if backend != version or frontend != version:
        raise Refusal(
            f"--release {version}: backend/pyproject.toml says {backend}, frontend/package.json says "
            f"{frontend}; bump both first (spec 08 §Release)"
        )


def code_versions() -> dict[str, str]:
    """TOKENIZER_VERSION, SCHEMA_VERSION and QUERY_VERSION as the code at HEAD defines them, and the Tantivy
    uv.lock pins."""
    out = {}
    for key, (rel, pattern) in CODE.items():
        m = re.search(pattern, read(rel), re.MULTILINE)
        if not m:
            raise Refusal(f"{rel} defines no {COMPAT[key]}")
        out[key] = m[1]
    try:
        packages = tomllib.loads(read("uv.lock")).get("package", [])
        out["tantivy_version"] = next(p["version"] for p in packages if p.get("name") == "tantivy")
    except (tomllib.TOMLDecodeError, StopIteration, KeyError, TypeError, AttributeError):
        raise Refusal("uv.lock pins no tantivy version") from None
    return out


def check_release_data(version: str, data: dict[str, dict[str, str]], data_dir: Path) -> None:
    """The release's table states the code's versions and the index it names (its manifest, spec 03)."""
    if version not in data:
        raise Refusal(f'release {version} has no [releases."{version}"] table in {DATA_FILE}')
    d = data[version]
    wrong = [f"{COMPAT[k]} {d[k]} (the code says {v})" for k, v in code_versions().items() if d[k] != v]
    path = data_dir / "indexes" / d["index_version"] / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        wrong += [
            f"{k} {d[k]} (its manifest says {manifest.get(k)})"
            for k in MANIFEST_KEYS
            if manifest.get(k) != d[k]
        ]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError) as e:
        raise Refusal(
            f"release {version}: can't read the manifest of index {d['index_version']} ({e})"
        ) from None
    if wrong:
        raise Refusal(f'{DATA_FILE}: releases."{version}" has ' + "; ".join(wrong))


def entry(pr: PR, repo: str) -> tuple[str, str]:
    """(group, markdown line) for one PR."""
    check_text(f"PR #{pr.number}'s title", pr.title)
    m = TITLE.fullmatch(pr.title.strip())
    if m and m["type"] in TYPES:
        group, desc = TYPES[m["type"]], m["desc"]
        desc = f"{m['scope']}: {desc}" if m["scope"] else desc
        breaking = bool(m["bang"])
    else:
        b = BRANCH.match(pr.head)
        group, desc, breaking = TYPES.get(b["type"] if b else "", "Changed"), pr.title.strip(), False
    text = MD_SPECIAL.sub(lambda c: "".join("\\" + ch for ch in c[0]), " ".join(desc.split()))
    if breaking:
        text = f"**Breaking:** {text}"
    return group, f"- {text} ([#{pr.number}](https://github.com/{repo}/pull/{pr.number}))"


def data_block(version: str, data: dict[str, dict[str, str]]) -> tuple[list[str], list[str]]:
    """(callout lines for the top of the section, the Data section) for a release."""
    if version not in data:
        raise Refusal(f'release {version} has no [releases."{version}"] table in {DATA_FILE}')
    d = data[version]
    earlier = sorted((v for v in data if version_key(v) < version_key(version)), key=version_key)
    callout: list[str] = []
    if not earlier:
        replay = "First release: no earlier search records."
    else:
        prev = earlier[-1]
        changed = [k for k in COMPAT if data[prev][k] != d[k]]
        if changed:
            if version_key(version)[:2] == version_key(prev)[:2]:
                raise Refusal(
                    f"{version} changes {', '.join(COMPAT[k] for k in changed)}: not a patch release"
                )
            moves = ", ".join(f"{COMPAT[k]} {data[prev][k]} → {d[k]}" for k in changed)
            callout = [
                f"**Search records saved under {prev} or earlier replay as `drifted`: {moves}. To reproduce "
                "one, run the release it was saved under on the index it pins.**",
                "",
            ]
            replay = f"Search records saved under {prev} or earlier replay as `drifted` ({moves})."
        else:
            run: list[str] = []  # the releases just before this one with the same versions, oldest first
            for v in reversed(earlier):
                if any(data[v][k] != d[k] for k in COMPAT):
                    break
                run.insert(0, v)
            span = run[0] if len(run) == 1 else f"{run[0]} to {run[-1]}"
            replay = (
                f"Search records saved under {span} replay as `reproduced` on the index_version they pin, "
                "while it is kept"
            )
            replay += "; those saved earlier replay as `drifted`." if len(run) < len(earlier) else "."
    lines = [
        "### Data",
        "",
        f"- index_version `{d['index_version']}`, snapshot `{d['snapshot_hash']}`",
        "- " + " · ".join(f"{COMPAT[k]} {d[k]}" for k in COMPAT),
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
        f"     release tags and {DATA_FILE}. Don't edit by hand: spec 08 §Release, decision-023. -->",
        "",
        "Every pull request merged into `dev` (or, outside a promotion, into `main`), by release. The backend",
        "and the frontend share one semver version, tagged `vX.Y.Z` on `main`. The version never decides which",
        "papers a query matches: a search record pins its `index_version`, `tokenizer_version` and",
        "`query_version`, and replays as `reproduced` while its index is kept and the running release can serve",
        "it with the same QUERY_VERSION; otherwise as `drifted`, naming what changed. Each release's Data section",
        "names the index it was verified on and which saved records still reproduce.",
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
        raise Refusal(f"line {lineno} carries an AI-attribution marker ({hit[0]!r})")
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
    ap.add_argument("--prs", type=Path, help="a JSON array of merged PRs instead of asking GitHub")
    ap.add_argument("--repo", help="OWNER/NAME for PR links (default: the origin remote)")
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data", help="holds indexes/ (default: data)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="exit 1 when CHANGELOG.md differs; write nothing")
    mode.add_argument("--notes", metavar="X.Y.Z", help="print this release's section; write nothing")
    a = ap.parse_args(argv)
    try:
        repo = normalize_repo(a.repo or repo_from_origin())
        tags = release_tags()
        data = load_data(ROOT / DATA_FILE)
        if a.notes:
            version_key(a.notes)
        if a.release:
            version_key(a.release)
            if tags and version_key(a.release) <= version_key(tags[-1][1:]):
                raise Refusal(f"--release {a.release} is not newer than the latest tag {tags[-1]}")
            check_manifests(a.release)
            check_release_data(a.release, data, a.data_dir)
        if a.prs:
            try:
                prs = parse_prs(json.loads(a.prs.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
                raise Refusal(f"--prs {a.prs}: {e}") from None
        else:
            prs = fetch_prs(repo)
        prs = [p for p in prs if counted(p, repo)]
        bounds = [(t[1:], t) for t in tags] + ([(a.release, "HEAD")] if a.release else [])
        placed = {p.number: release_of(p, bounds) for p in prs}
        text = render(prs, placed, data, repo, a.release)
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
