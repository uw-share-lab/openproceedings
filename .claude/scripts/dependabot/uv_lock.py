#!/usr/bin/env python3
"""Supply-chain check of a uv.lock change (/dependabot-review step 2; TASK-211).

    python3 .claude/scripts/dependabot/uv_lock.py [--base REF] [--head REF]

Compares `uv.lock`, `pyproject.toml` and `backend/pyproject.toml` at `base` (default: the merge base of
origin/dev and HEAD) and `head` (default HEAD).

For every package whose version changed it checks, against PyPI's JSON API, that each sdist and wheel the lock
names is on files.pythonhosted.org with PyPI's sha256, that the release is not yanked and is at least
`COOLDOWN_DAYS` old, and compares the PEP 740 provenance publisher (the whole record: kind, repository,
workflow, environment) of every file of the new version with the previous version's (every file of it that
has one; they must agree). The previous version is the old one with the same major, else the newest old one.

The shape of the change is checked too: everything in `uv.lock` but the package list stays the same; a
registry package whose version didn't move stays byte-for-byte the same; a workspace member changes only its
dependency fields; and each `pyproject.toml` changes only dependency specifiers (`[project] dependencies`,
`optional-dependencies`, `[dependency-groups]`) of packages whose locked version moved, so nothing else (a
build requirement, an index, a tool setting) can ride along.

A PROBLEM, the PR stays open: any of the above failing, an added or removed package, a semver-major bump, a
new publisher, a file without the provenance the previous version had (PyPI accepts files added to a release
later), files of one release that disagree on provenance, or any `tantivy` change (hand-only, spec 08 §Release).
It fails safe on one known legal case: when the lock holds a package at two versions and one moves, uv rewrites the
`dependencies` of packages that name it, and those unmoved entries read as changed; such a PR is left open.
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from typing import Any

from _common import (
    COOLDOWN_DAYS,
    Report,
    ToolError,
    age_days,
    git_show,
    http,
    http_json,
    is_major,
    main_guard,
    resolve_refs,
    version_tuple,
)

PYPI = "https://pypi.org"
FILES_HOST = "https://files.pythonhosted.org/"
REGISTRY = "https://pypi.org/simple"
HAND_ONLY = {"tantivy"}  # spec 08 §Release: upgraded by hand with SCHEMA_VERSION, never by Dependabot
PYPROJECTS = ("pyproject.toml", "backend/pyproject.toml")
MEMBER_FIELDS = {"dependencies", "optional-dependencies", "dev-dependencies", "metadata"}
REQ_NAME = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)")

Pkg = dict[str, Any]


def load(text: str | None, where: str) -> dict[str, Any]:
    if text is None:
        raise ToolError(f"{where} does not exist")
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ToolError(f"{where} is not TOML: {e}") from e


def by_name(lock: dict[str, Any]) -> dict[str, dict[str, Pkg]]:
    """name → version → entry (a lock can hold one name at several versions, split by markers)."""
    out: dict[str, dict[str, Pkg]] = {}
    for p in lock.get("package", []):
        out.setdefault(p["name"], {})[str(p.get("version", ""))] = p
    return out


def files(p: Pkg) -> list[dict[str, Any]]:
    return ([p["sdist"]] if "sdist" in p else []) + list(p.get("wheels", []))


def filename(f: dict[str, Any]) -> str:
    return str(f.get("url", "")).rsplit("/", 1)[-1]


def norm_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def publisher(name: str, version: str, fn: str) -> str | None:
    """One file's PEP 740 provenance publisher as canonical JSON (every field), or None when PyPI has none."""
    r = http(
        f"{PYPI}/integrity/{name}/{version}/{fn}/provenance",
        {"Accept": "application/vnd.pypi.integrity.v1+json"},
    )
    if r.status == 404:
        return None
    if r.status != 200:
        raise ToolError(f"provenance of {fn}: HTTP {r.status}")
    bundles = r.json().get("attestation_bundles") or []
    pubs = {json.dumps(b.get("publisher") or {}, sort_keys=True) for b in bundles}
    if len(pubs) > 1:
        raise ToolError(f"provenance of {fn} names {len(pubs)} publishers")
    return pubs.pop() if pubs else None


def previous(old_versions: list[str], new_v: str) -> str | None:
    """The old version a new one is compared with: the newest with the same major, else the newest."""
    same = [v for v in old_versions if version_tuple(v)[:1] == version_tuple(new_v)[:1]]
    return max(same or old_versions, key=version_tuple, default=None)


def check_version(rep: Report, name: str, old_v: str | None, new_v: str, old: Pkg | None, new: Pkg) -> None:
    label = f"{name} {old_v or '(new)'} -> {new_v}"
    if name in HAND_ONLY:
        rep.problem(f"{label}: {name} is upgraded by hand only (spec 08 §Release)")
    if old_v is not None and is_major(old_v, new_v):
        rep.problem(f"{label}: semver-major")
    source = new.get("source", {})
    if source.get("registry") != REGISTRY:
        rep.problem(f"{label}: source is not PyPI: {source}")
        return
    listed = http_json(f"{PYPI}/pypi/{name}/{new_v}/json").get("urls", [])
    if any(u.get("yanked") for u in listed):
        rep.problem(f"{label}: PyPI marks {new_v} as yanked")
    uploads = [str(u["upload_time_iso_8601"]) for u in listed]
    if uploads and (days := age_days(max(uploads))) < COOLDOWN_DAYS:
        rep.problem(f"{label}: a file was uploaded {days:.1f} days ago (under {COOLDOWN_DAYS}; decision-048)")
    pypi = {u["filename"]: u["digests"]["sha256"] for u in listed}
    bad = 0
    for f in files(new):
        fn, url = filename(f), str(f.get("url", ""))
        if not url.startswith(FILES_HOST):
            rep.problem(f"{label}: {fn} is not on files.pythonhosted.org: {url}")
            bad += 1
        if fn not in pypi:
            rep.problem(f"{label}: {fn} is not listed by PyPI")
            bad += 1
        elif str(f.get("hash", "")).removeprefix("sha256:") != pypi[fn]:
            rep.problem(f"{label}: {fn} sha256 differs from PyPI's")
            bad += 1
    if not files(new):
        rep.problem(f"{label}: the lock lists no files")
    elif not bad:
        rep.ok(f"{label}: {len(files(new))} file(s) match PyPI")
    olds = {publisher(name, str(old_v), filename(f)) for f in files(old)} if old and old_v else set()
    olds.discard(None)
    if len(olds) > 1:
        rep.problem(f"{label}: the files of {old_v} name {len(olds)} publishers; compare by hand")
        return
    before = olds.pop() if olds else None
    now = {filename(f): publisher(name, new_v, filename(f)) for f in files(new)}
    found = len(rep.problems)
    for fn, pub in now.items():
        if before and not pub:
            rep.problem(f"{label}: {fn} has no provenance; {old_v} had {before}")
        elif before and pub != before:
            rep.problem(f"{label}: {fn} publisher changed from {before} to {pub}")
    if not before and len(set(now.values())) > 1:
        rep.problem(
            f"{label}: the files of {new_v} disagree on provenance: {sorted(map(str, set(now.values())))}"
        )
    if len(rep.problems) == found:
        pub = next(iter(now.values()), None)
        rep.ok(f"{label}: provenance {pub or 'none'} on every file" + (", as before" if before else ""))


def split_deps(doc: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    """(the document without its dependency lists, [(list path, its items)])."""
    rest = json.loads(json.dumps(doc))
    lists: list[tuple[str, Any]] = []
    project = rest.get("project", {})
    if "dependencies" in project:
        lists.append(("project.dependencies", project.pop("dependencies")))
    for extra, items in sorted((project.pop("optional-dependencies", None) or {}).items()):
        lists.append((f"project.optional-dependencies.{extra}", items))
    for group, items in sorted((rest.pop("dependency-groups", None) or {}).items()):
        lists.append((f"dependency-groups.{group}", items))
    return rest, lists


def check_pyproject(rep: Report, path: str, base: str, head: str, moved: set[str]) -> None:
    old_text, new_text = git_show(base, path), git_show(head, path)
    if old_text == new_text:
        return
    found = len(rep.problems)
    if old_text is None or new_text is None:
        rep.problem(f"{path}: added or removed")
        return
    (old_rest, old_lists), (new_rest, new_lists) = (
        split_deps(load(old_text, f"{path} at {base}")),
        split_deps(load(new_text, f"{path} at {head}")),
    )
    if old_rest != new_rest:
        rep.problem(f"{path}: changed outside its dependency lists")
    if [k for k, _ in old_lists] != [k for k, _ in new_lists]:
        rep.problem(f"{path}: its dependency lists were added, removed or renamed")
        return
    for (where, olds), (_, news) in zip(old_lists, new_lists, strict=True):
        if len(olds) != len(news):
            rep.problem(f"{path} {where}: a dependency was added or removed")
            continue
        for o, n in zip(olds, news, strict=True):
            if o == n:
                continue
            on = REQ_NAME.match(o) if isinstance(o, str) else None
            nn = REQ_NAME.match(n) if isinstance(n, str) else None
            if not on or not nn or norm_name(on.group(1)) != norm_name(nn.group(1)):
                rep.problem(f"{path} {where}: {o!r} became {n!r}")
            elif norm_name(nn.group(1)) not in moved:
                rep.problem(f"{path} {where}: {n!r} changed, but the lock didn't move {nn.group(1)}")
    if len(rep.problems) == found:
        rep.ok(f"{path}: checked against the lock")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    a = ap.parse_args()
    base, head = resolve_refs(a.base, a.head)
    old_lock = load(git_show(base, "uv.lock"), f"uv.lock at {base}")
    new_lock = load(git_show(head, "uv.lock"), f"uv.lock at {head}")
    rep = Report("uv.lock")
    if old_lock.get("requires-python") != new_lock.get("requires-python"):
        rep.problem(
            f"requires-python changed: {old_lock.get('requires-python')} -> {new_lock.get('requires-python')}"
            " (the Python minor is hand-only, spec 08 §Monorepo layout)"
        )
    for key in sorted((set(old_lock) | set(new_lock)) - {"package", "requires-python"}):
        if old_lock.get(key) != new_lock.get(key):
            rep.problem(f"uv.lock: `{key}` changed")
    old, new = by_name(old_lock), by_name(new_lock)
    for name in sorted(set(old) - set(new)):
        rep.problem(f"{name}: removed from the lock")
    for name in sorted(set(new) - set(old)):
        rep.problem(f"{name} {', '.join(new[name])}: added to the lock (a new package)")
    moved: set[str] = set()
    for name in sorted(set(old) & set(new)):
        o, n = old[name], new[name]
        for v in sorted(set(o) & set(n)):
            if o[v] == n[v]:
                continue
            member = not o[v].get("source", {}).get("registry")
            differ = sorted(k for k in set(o[v]) | set(n[v]) if o[v].get(k) != n[v].get(k))
            if not member or set(differ) - MEMBER_FIELDS:
                rep.problem(f"{name} {v}: same version, different {', '.join(differ)}")
        if set(o) != set(n):
            moved.add(norm_name(name))
        for v in sorted(set(n) - set(o)):
            prev = previous(list(o), v)
            check_version(rep, name, prev, v, o.get(prev) if prev else None, n[v])
    for path in PYPROJECTS:
        check_pyproject(rep, path, base, head, moved)
    rep.finish()


if __name__ == "__main__":
    main_guard(main)
