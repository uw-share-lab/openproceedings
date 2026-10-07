#!/usr/bin/env python3
"""Supply-chain check of a package-lock.json change (/dependabot-review steps 2 and 3; TASK-211).

    python3 .claude/scripts/dependabot/npm_lock.py [--base REF] [--head REF]

Compares `package-lock.json` at `base` (default: the merge base of origin/dev and HEAD) and `head`
(default HEAD). Every changed `node_modules/…` entry (nested ones included) is checked against the registry's
manifest for its version (`npm view <name>@<version> --json --registry https://registry.npmjs.org/`, run from an
empty directory so no `.npmrc` in the repo can point a scope elsewhere): the lock's integrity equals
`dist.integrity`, `resolved` equals `dist.tarball` on registry.npmjs.org, and the dependencies, optional and peer
dependencies, `os`, `cpu` and `libc` equal the manifest's (so a `libc` an older npm dropped shows up). When the
version moved it also compares, with the previous version's, the publisher (`_npmUser`), the install scripts and
the npm provenance: present before means present now, from the same source repository (the SLSA statement's
`workflow.repository`, read from `dist.attestations.url`). Then it checks that every dependency in
`package.json` and `frontend/package.json` at `head` is written exactly as the lock's `packages[""]` and
`packages["frontend"]` entries hold it (Dependabot's npm updater can write a caret into the lock's workspace
entry; `npm ci` accepts it). A version newer than `COOLDOWN_DAYS` (the registry's `time`) is held back.

The shape of the change is checked too: the lock's top-level fields stay the same; its non-`node_modules/`
entries (the root and the workspace) and the two manifests change only dependency values, each of a package
whose locked version moved, so a script, an override or any other field can't ride along. An entry that moved
within the tree (npm dedupes) is checked against the registry like a changed one, not reported as new.

A PROBLEM, the PR stays open: an added or removed package, an entry that changes its package name (an alias)
or turns into or out of a `link`, a mismatch with the registry, a field dropped from an entry whose version
didn't move, a new install script, a new publisher, provenance the previous version had and this one lacks or
that comes from another repository, a semver-major bump. A FIX, repaired in the PR: a manifest/lock pin that
differs, a dropped `libc`.
"""

from __future__ import annotations

import argparse
import base64
import json
import tempfile
from typing import Any

from _common import (
    COOLDOWN_DAYS,
    Report,
    ToolError,
    age_days,
    git_show,
    http_json,
    is_major,
    main_guard,
    resolve_refs,
    run_json,
    version_tuple,
)

REGISTRY = "https://registry.npmjs.org/"
DEP_FIELDS = ("dependencies", "optionalDependencies", "peerDependencies", "os", "cpu", "libc")
MANIFEST_SECTIONS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
GRAPH_FLAGS = {"dev", "optional", "devOptional", "peer"}  # set by where a package sits in the tree, not by it
INSTALL_SCRIPTS = ("preinstall", "install", "postinstall")
WORKSPACES = {"": "package.json", "frontend": "frontend/package.json"}
SLSA = "https://slsa.dev/provenance/"

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
    """The registry name: an alias entry (`"name": …`) names it; otherwise the path after the last node_modules/."""
    return str(entry.get("name") or key.rsplit("node_modules/", 1)[-1])


def view(name: str, version: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="op-depbot-npm-") as empty:  # no project .npmrc applies here
        data = run_json(["npm", "view", f"{name}@{version}", "--json", "--registry", REGISTRY], cwd=empty)
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


def provenance_repo(manifest: dict[str, Any]) -> str | None:
    """The source repository npm provenance names, or None when the version has no provenance."""
    att = (manifest.get("dist") or {}).get("attestations")
    if not att:
        return None
    url = str(att.get("url", ""))
    if not url.startswith(REGISTRY):
        raise ToolError(f"provenance URL off the registry: {url}")
    for a in http_json(url).get("attestations", []):
        if not str(a.get("predicateType", "")).startswith(SLSA):
            continue
        payload = a["bundle"]["dsseEnvelope"]["payload"]
        statement = json.loads(base64.b64decode(payload))
        predicate = statement.get("predicate", {})
        workflow = (predicate.get("buildDefinition", {}).get("externalParameters", {})).get("workflow", {})
        if workflow.get("repository"):
            return str(workflow["repository"])
        source = predicate.get("invocation", {}).get("configSource", {}).get("uri", "")  # SLSA v0.2
        if source:
            return str(source).removeprefix("git+").split("@", 1)[0]
    raise ToolError(f"{url} holds no SLSA provenance naming a repository")


def norm(value: Any) -> Any:
    return value or None  # [] / {} / missing are the same thing


def check_entry(rep: Report, key: str, old: Entry | None, new: Entry) -> None:
    name = package_name(key, new)
    old_v, new_v = (old or {}).get("version"), str(new.get("version", ""))
    label = f"{name} {old_v} -> {new_v}" if old_v != new_v else f"{name} {new_v}"
    found = len(rep.problems) + len(rep.fixes)
    if old is not None and package_name(key, old) != name:
        rep.problem(f"{key}: the package changed from {package_name(key, old)} to {name} (a new package)")
        return
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
    if old_v != new_v:
        released = (m.get("time") or {}).get(new_v)
        if not released:
            rep.problem(f"{label}: the registry gives no publish time for {new_v}")
        elif (days := age_days(str(released))) < COOLDOWN_DAYS:
            rep.problem(f"{label}: published {days:.1f} days ago (under {COOLDOWN_DAYS}; decision-048)")
    if old is not None and old_v != new_v:
        before = view(name, str(old_v))
        added = install_scripts(m) - install_scripts(before)
        if added:
            rep.problem(f"{label}: new install script(s): {', '.join(sorted(added))}")
        if npm_user(before) != npm_user(m):
            rep.problem(f"{label}: publisher changed from {npm_user(before)!r} to {npm_user(m)!r}")
        was, now = provenance_repo(before), provenance_repo(m)
        if was and not now:
            rep.problem(f"{label}: {old_v} had npm provenance ({was}), {new_v} has none")
        elif was and now != was:
            rep.problem(f"{label}: provenance repository changed from {was} to {now}")
    if len(rep.problems) + len(rep.fixes) == found:
        rep.ok(f"{label}: matches the registry (publisher {npm_user(m)!r})")


def without_deps(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if k not in MANIFEST_SECTIONS}


def check_dep_values(
    rep: Report, where: str, old: dict[str, Any], new: dict[str, Any], moved: set[str]
) -> None:
    """`new` may differ from `old` only in dependency values of packages whose locked version moved."""
    if without_deps(old) != without_deps(new):
        rep.problem(f"{where}: changed outside its dependency lists")
    for section in MANIFEST_SECTIONS:
        o, n = old.get(section) or {}, new.get(section) or {}
        if set(o) != set(n):
            rep.problem(f"{where} {section}: a dependency was added or removed")
        for dep in sorted(set(o) & set(n)):
            if o[dep] != n[dep] and dep not in moved:
                rep.problem(
                    f"{where} {section}.{dep}: {o[dep]!r} -> {n[dep]!r}, but the lock didn't move {dep}"
                )


def check_manifests(rep: Report, lock: dict[str, Any], base: str, head: str, moved: set[str]) -> None:
    packages = lock.get("packages", {})
    found = len(rep.problems) + len(rep.fixes)
    for key, path in WORKSPACES.items():
        text = git_show(head, path)
        if text is None:
            continue
        manifest = load(text, f"{path} at {head}")
        before = git_show(base, path)
        check_dep_values(rep, path, load(before, f"{path} at {base}") if before else {}, manifest, moved)
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
    if len(rep.problems) + len(rep.fixes) == found:
        rep.ok("package.json and frontend/package.json match the lock's workspace entries")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    a = ap.parse_args()
    base, head = resolve_refs(a.base, a.head)
    old_lock = load(git_show(base, "package-lock.json"), f"package-lock.json at {base}")
    new_lock = load(git_show(head, "package-lock.json"), f"package-lock.json at {head}")
    old, new = old_lock.get("packages", {}), new_lock.get("packages", {})
    rep = Report("package-lock.json")
    for key in sorted((set(old_lock) | set(new_lock)) - {"packages"}):
        if old_lock.get(key) != new_lock.get(key):
            rep.problem(f"package-lock.json: `{key}` changed")
    deps = {k for k in set(old) | set(new) if k.startswith("node_modules/") or "/node_modules/" in k}
    versions: list[dict[str, set[str]]] = [{}, {}]
    for side, packages in enumerate((old, new)):
        for k in deps & set(packages):
            versions[side].setdefault(package_name(k, packages[k]), set()).add(
                str(packages[k].get("version"))
            )
    moved = {
        name for name in set(versions[0]) | set(versions[1]) if versions[0].get(name) != versions[1].get(name)
    }
    for k in sorted((set(old) | set(new)) - deps):
        if old.get(k) != new.get(k):
            check_dep_values(
                rep, f'package-lock.json packages["{k}"]', old.get(k) or {}, new.get(k) or {}, moved
            )
    for k in sorted(deps - set(new)):
        name = package_name(k, old[k])
        if name in versions[1]:
            rep.ok(f"{k}: {name} moved within the tree")
        else:
            rep.problem(f"{k}: removed from the lock")
    for k in sorted(deps - set(old)):
        name = package_name(k, new[k])
        if name not in versions[0]:
            rep.problem(f"{k} {new[k].get('version')}: added to the lock (a new package)")
            continue
        olds = [ok for ok in deps & set(old) if package_name(ok, old[ok]) == name]
        source = max(olds, key=lambda ok: version_tuple(str(old[ok].get("version"))))
        rep.ok(f"{k}: {name} moved within the tree (from {source})")
        check_entry(rep, k, {**old[source], **({"name": name} if "name" in new[k] else {})}, new[k])
    for k in sorted(deps & set(old) & set(new)):
        o, n = old[k], new[k]
        if o == n:
            continue
        if o.get("link") or n.get("link"):  # a workspace symlink; any change to or from one is not an update
            rep.problem(f"{k}: a link entry changed ({o.get('resolved')} -> {n.get('resolved')})")
            continue
        check_entry(rep, k, o, n)
    check_manifests(rep, new_lock, base, head, moved)
    rep.finish()


if __name__ == "__main__":
    main_guard(main)
