#!/usr/bin/env python3
"""Supply-chain check of a uv.lock change (/dependabot-review step 2; TASK-211).

    python3 .claude/scripts/dependabot/uv_lock.py [--base REF] [--head REF]

Compares `uv.lock` at `base` (default: the merge base of origin/dev and HEAD) and `head` (default HEAD).
For every package whose version changed it checks, against PyPI's JSON API, that each sdist and wheel the
lock names is on files.pythonhosted.org with PyPI's sha256, and compares the PEP 740 provenance publisher
of every file of the new version with the previous version's (its first file's; the whole publisher record:
kind, repository, workflow, environment). The previous version is the old one with the same major, else the
newest old one. A PROBLEM, the PR stays open: an added or removed package, a hash or URL that disagrees, a
file PyPI doesn't list, a yanked release, a non-PyPI source, a semver-major bump, a new publisher, a file
without the provenance the previous version had (PyPI accepts files added to a release later), files of one
release that disagree on provenance, a changed `requires-python`, any `tantivy` change (hand-only, spec 08
§Release), or changed files for an unchanged version.
"""

from __future__ import annotations

import argparse
import json
import tomllib
from typing import Any

from _common import (
    Report,
    ToolError,
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

Pkg = dict[str, Any]


def load(text: str | None, where: str) -> dict[str, Any]:
    if text is None:
        raise ToolError(f"uv.lock does not exist at {where}")
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ToolError(f"uv.lock at {where} is not TOML: {e}") from e


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
    old_files = files(old) if old is not None and old_v is not None else []
    before = publisher(name, str(old_v), filename(old_files[0])) if old_files else None
    now = {filename(f): publisher(name, new_v, filename(f)) for f in files(new)}
    problems = len(rep.problems)
    for fn, pub in now.items():
        if before and not pub:
            rep.problem(f"{label}: {fn} has no provenance; {old_v} had {before}")
        elif before and pub != before:
            rep.problem(f"{label}: {fn} publisher changed from {before} to {pub}")
    if not before and len(set(now.values())) > 1:
        rep.problem(
            f"{label}: the files of {new_v} disagree on provenance: {sorted(map(str, set(now.values())))}"
        )
    if len(rep.problems) == problems:
        pub = next(iter(now.values()), None)
        rep.ok(f"{label}: provenance {pub or 'none'} on every file" + (", as before" if before else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    a = ap.parse_args()
    base, head = resolve_refs(a.base, a.head)
    old_lock = load(git_show(base, "uv.lock"), base)
    new_lock = load(git_show(head, "uv.lock"), head)
    rep = Report("uv.lock")
    if old_lock.get("requires-python") != new_lock.get("requires-python"):
        rep.problem(
            f"requires-python changed: {old_lock.get('requires-python')} -> {new_lock.get('requires-python')}"
            " (the Python minor is hand-only, spec 08 §Monorepo layout)"
        )
    old, new = by_name(old_lock), by_name(new_lock)
    for name in sorted(set(old) - set(new)):
        rep.problem(f"{name}: removed from the lock")
    for name in sorted(set(new) - set(old)):
        rep.problem(f"{name} {', '.join(new[name])}: added to the lock (a new package)")
    for name in sorted(set(old) & set(new)):
        o, n = old[name], new[name]
        for v in sorted(set(o) & set(n)):
            if files(o[v]) != files(n[v]) or o[v].get("source") != n[v].get("source"):
                rep.problem(f"{name} {v}: same version, different files or source")
        for v in sorted(set(n) - set(o)):
            prev = previous(list(o), v)
            check_version(rep, name, prev, v, o.get(prev) if prev else None, n[v])
    rep.finish()


if __name__ == "__main__":
    main_guard(main)
