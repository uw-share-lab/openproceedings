#!/usr/bin/env python3
"""Supply-chain check of a package-lock.json change (/dependabot-review steps 2 and 3; TASK-211).

    python3 .claude/scripts/dependabot/npm_lock.py [--base REF] [--head REF]

Compares `package-lock.json` at `base` (default: the merge base of origin/dev and HEAD) and `head`
(default HEAD). Every changed `node_modules/…` entry is checked against the registry's manifest for its
version (`npm view <name>@<version> --json`, always against registry.npmjs.org): the lock's integrity
equals `dist.integrity`, `resolved` equals `dist.tarball` on registry.npmjs.org, and the dependencies,
optional and peer dependencies, `os`, `cpu` and `libc` equal the manifest's (so a `libc` an older npm
dropped shows up). When the version moved it also compares the publisher (`_npmUser`) and npm provenance
(`dist.attestations`) with the previous version's, and the install scripts. Then it checks that every
dependency in `package.json` and `frontend/package.json` at `head` is written exactly as the lock's
`packages[""]` and `packages["frontend"]` entries hold it (Dependabot's npm updater can write a caret
into the lock's workspace entry; `npm ci` accepts it).

A PROBLEM, the PR stays open: an added or removed package, a mismatch with the registry, a field dropped
from an entry whose version didn't move, a new install script, a new publisher, provenance the previous
version had and this one lacks, a semver-major bump, or a manifest/lock pin that differs.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from _common import Report, ToolError, git_show, is_major, main_guard, resolve_refs, run_json

REGISTRY = "https://registry.npmjs.org/"
DEP_FIELDS = ("dependencies", "optionalDependencies", "peerDependencies", "os", "cpu", "libc")
MANIFEST_SECTIONS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
GRAPH_FLAGS = {"dev", "optional", "devOptional", "peer"}  # set by where a package sits in the tree, not by it
INSTALL_SCRIPTS = ("preinstall", "install", "postinstall")
WORKSPACES = {"": "package.json", "frontend": "frontend/package.json"}

Entry = dict[str, Any]


def load(text: str | None, what: str) -> dict[str, Any]:
    if text is None:
        raise ToolError(f"{what} does not exist")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ToolError(f"{what} is not JSON: {e}") from e
    if not isinstance(data, dict):
        raise ToolError(f"{what} is not a JSON object")
    return data


def package_name(key: str, entry: Entry) -> str:
    return str(entry.get("name") or key.rsplit("node_modules/", 1)[-1])


def view(name: str, version: str) -> dict[str, Any]:
    data = run_json(["npm", "view", f"{name}@{version}", "--json", "--registry", REGISTRY])
    if isinstance(data, list):  # npm prints a list when a range matches several versions
        data = data[-1] if data else {}
    if not isinstance(data, dict) or data.get("version") != version:
        raise ToolError(f"npm view {name}@{version} did not return that version")
    return data


def npm_user(manifest: dict[str, Any]) -> str:
    u = manifest.get("_npmUser")
    if isinstance(u, dict):
        return str(u.get("name", ""))
    return str(u or "").split(" <", 1)[0]


def install_scripts(manifest: dict[str, Any]) -> set[str]:
    scripts = manifest.get("scripts") or {}
    found = {s for s in INSTALL_SCRIPTS if s in scripts}
    return found | ({"gypfile"} if manifest.get("gypfile") else set())


def norm(value: Any) -> Any:
    return value or None  # [] / {} / missing are the same thing


def check_entry(rep: Report, key: str, old: Entry | None, new: Entry) -> None:
    name = package_name(key, new)
    old_v, new_v = (old or {}).get("version"), str(new.get("version", ""))
    label = f"{name} {old_v} -> {new_v}" if old_v != new_v else f"{name} {new_v}"
    if old is not None and old_v == new_v:
        dropped = sorted(set(old) - set(new) - GRAPH_FLAGS)
        if dropped == ["libc"]:
            rep.fix(f"{label}: libc dropped (restore_libc.py, or edit the lock under the .nvmrc Node)")
        elif dropped:
            rep.problem(f"{label}: field(s) dropped: {', '.join(dropped)}")
        for f in ("integrity", "resolved"):
            if old.get(f) != new.get(f):
                rep.problem(f"{label}: same version, different {f}")
    if old_v is not None and old_v != new_v and is_major(str(old_v), new_v):
        rep.problem(f"{label}: semver-major")
    resolved = str(new.get("resolved", ""))
    if not resolved.startswith(REGISTRY):
        rep.problem(f"{label}: resolved is not on registry.npmjs.org: {resolved}")
    m = view(name, new_v)
    dist = m.get("dist") or {}
    problems = len(rep.problems) + len(rep.fixes)
    if dist.get("integrity") != new.get("integrity"):
        rep.problem(f"{label}: integrity differs from the registry's")
    if dist.get("tarball") != resolved:
        rep.problem(f"{label}: resolved differs from the registry's tarball URL")
    for f in DEP_FIELDS:
        if norm(m.get(f)) == norm(new.get(f)):
            continue
        if f != "libc" or "libc" in new:
            rep.problem(f"{label}: {f} in the lock differs from the registry manifest")
        elif old_v != new_v:  # an unchanged version's dropped libc is reported above
            rep.fix(f"{label}: libc missing (restore_libc.py, or edit the lock under the .nvmrc Node)")
    if bool(new.get("hasInstallScript")) != bool(install_scripts(m)):
        rep.problem(f"{label}: hasInstallScript disagrees with the registry manifest")
    if old is not None and old_v != new_v:
        before = view(name, str(old_v))
        added = install_scripts(m) - install_scripts(before)
        if added:
            rep.problem(f"{label}: new install script(s): {', '.join(sorted(added))}")
        if npm_user(before) != npm_user(m):
            rep.problem(f"{label}: publisher changed from {npm_user(before)!r} to {npm_user(m)!r}")
        if (before.get("dist") or {}).get("attestations") and not dist.get("attestations"):
            rep.problem(f"{label}: {old_v} had npm provenance, {new_v} has none")
    if len(rep.problems) + len(rep.fixes) == problems:
        rep.ok(f"{label}: matches the registry (publisher {npm_user(m)!r})")


def check_manifests(rep: Report, lock: dict[str, Any], head: str) -> None:
    packages = lock.get("packages", {})
    for key, path in WORKSPACES.items():
        text = git_show(head, path)
        if text is None:
            continue
        manifest = load(text, f"{path} at {head}")
        entry = packages.get(key, {})
        for section in MANIFEST_SECTIONS:
            want, got = manifest.get(section) or {}, entry.get(section) or {}
            for dep in sorted(set(want) | set(got)):
                if want.get(dep) != got.get(dep):
                    where = f'packages["{key}"]'
                    rep.fix(
                        f"{path} {section}.{dep} is {want.get(dep)!r}, the lock's {where} has {got.get(dep)!r}"
                        " (edit the lock by hand to match the manifest)"
                    )
    rep.ok("package.json and frontend/package.json checked against the lock's workspace entries")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    a = ap.parse_args()
    base, head = resolve_refs(a.base, a.head)
    old = load(git_show(base, "package-lock.json"), f"package-lock.json at {base}").get("packages", {})
    new_lock = load(git_show(head, "package-lock.json"), f"package-lock.json at {head}")
    new = new_lock.get("packages", {})
    rep = Report("package-lock.json")
    deps = {k for k in set(old) | set(new) if k.startswith("node_modules/") or "/node_modules/" in k}
    for k in sorted(deps - set(new)):
        rep.problem(f"{k}: removed from the lock")
    for k in sorted(deps - set(old)):
        rep.problem(f"{k} {new[k].get('version')}: added to the lock (a new package)")
    for k in sorted(deps & set(old) & set(new)):
        if old[k] != new[k] and not new[k].get("link"):
            check_entry(rep, k, old[k], new[k])
    check_manifests(rep, new_lock, head)
    rep.finish()


if __name__ == "__main__":
    main_guard(main)
