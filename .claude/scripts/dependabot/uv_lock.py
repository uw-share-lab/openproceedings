#!/usr/bin/env python3
"""Supply-chain check of a uv.lock change (/dependabot-review step 2; TASK-211).

    python3 .claude/scripts/dependabot/uv_lock.py [--base REF] [--head REF]

Compares `uv.lock` at `base` (default: the merge base of origin/dev and HEAD) and `head` (default HEAD).
For every package whose version changed it checks, against PyPI's JSON API, that each sdist and wheel the
lock names is on files.pythonhosted.org with PyPI's sha256, and compares the PEP 740 provenance publisher
(kind and repository) with the previous version's. A PROBLEM, the PR stays open: an added or removed
package, a hash or URL that disagrees, a file PyPI doesn't list, a yanked release, a non-PyPI source, a
semver-major bump, a new publisher or provenance the previous version had and this one lacks, a changed
`requires-python`, any `tantivy` change (hand-only, spec 08 §Release), or changed files for an unchanged
version.
"""

from __future__ import annotations

import argparse
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


def publisher(name: str, version: str, p: Pkg) -> tuple[str, str] | None:
    """(kind, repository) of the first file's PEP 740 provenance, or None when PyPI has none."""
    fs = files(p)
    if not fs:
        return None
    r = http(
        f"{PYPI}/integrity/{name}/{version}/{filename(fs[0])}/provenance",
        {"Accept": "application/vnd.pypi.integrity.v1+json"},
    )
    if r.status == 404:
        return None
    if r.status != 200:
        raise ToolError(f"provenance of {name} {version}: HTTP {r.status}")
    bundles = r.json().get("attestation_bundles") or []
    if not bundles:
        return None
    pub = bundles[0].get("publisher") or {}
    return str(pub.get("kind", "")), str(pub.get("repository", ""))


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
    now = publisher(name, new_v, new)
    before = publisher(name, old_v, old) if old is not None and old_v is not None else None
    if before and not now:
        rep.problem(f"{label}: {old_v} had provenance ({before[1]}), {new_v} has none")
    elif before and now and before != now:
        rep.problem(f"{label}: publisher changed from {before} to {now}")
    elif now:
        rep.ok(f"{label}: provenance {now[0]} {now[1]}" + (" (same as before)" if before else ""))
    else:
        rep.ok(f"{label}: no provenance, none before either")


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
        added = sorted(set(n) - set(o))
        if not added:
            continue
        prev = max(o, key=version_tuple) if o else None
        for v in added:
            check_version(rep, name, prev, v, o.get(prev) if prev else None, n[v])
    rep.finish()


if __name__ == "__main__":
    main_guard(main)
