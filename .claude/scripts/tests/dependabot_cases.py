#!/usr/bin/env python3
"""Case table for the /dependabot-review scripts in .claude/scripts/dependabot/ (TASK-211).

    python3 .claude/scripts/tests/dependabot_cases.py      # run by test-dependabot.sh, so by `make tooling`

Each row builds a throwaway git repo with a base and a head commit, writes the fixtures the fake `curl`,
`npm` and `gh` (dependabot_fake.py, first on PATH) answer from, runs one script there, and checks its exit
status and one line of its output. No row reaches the network. Mutants: .claude/scripts/mutants/dependabot.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "dependabot"
FAKE = HERE / "dependabot_fake.py"
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ROWS: list[tuple[str, Callable[[Case], None]]] = []

OK, PROBLEM, ERROR, FIX = 0, 1, 2, 3


def row(label: str) -> Callable[[Callable[[Case], None]], Callable[[Case], None]]:
    def add(fn: Callable[[Case], None]) -> Callable[[Case], None]:
        ROWS.append((label, fn))
        return fn

    return add


def h(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


class Case:
    def __init__(self, tmp: Path) -> None:
        self.repo, self.fix, self.bin = tmp / "repo", tmp / "fix", tmp / "bin"
        for d in (self.repo, self.fix, self.bin):
            d.mkdir()
        for tool in ("curl", "npm", "gh"):
            shim = self.bin / tool
            shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" {tool} "$@"\n')
            shim.chmod(0o755)
        self.curl: dict[str, Any] = {}
        self.npm: dict[str, Any] = {}
        self.gh: dict[str, Any] = {}
        self.git("init", "-q", "-b", "work")
        self.files: dict[str, str] = {}

    def git(self, *args: str) -> str:
        cmd = ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@example.org"]
        cmd += ["-c", "commit.gpgsign=false", *args]
        return subprocess.run(cmd, capture_output=True, text=True, check=True, env=ENV).stdout.strip()

    def commit(self, files: dict[str, str | None]) -> str:
        for path, text in files.items():
            p = self.repo / path
            if text is None:
                p.unlink()
                self.files.pop(path, None)
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            self.files[path] = text
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "c")
        return self.git("rev-parse", "HEAD")

    def run(self, script: str, *args: str) -> tuple[int, str]:
        for name, data in (("curl.json", self.curl), ("npm.json", self.npm), ("gh.json", self.gh)):
            (self.fix / name).write_text(json.dumps(data))
        env = {**ENV, "PATH": f"{self.bin}{os.pathsep}{ENV.get('PATH', '')}", "DEPBOT_FIX": str(self.fix)}
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            cwd=self.repo, capture_output=True, text=True, env=env, timeout=120,
        )  # fmt: skip
        return r.returncode, r.stdout + r.stderr

    def expect(self, script: str, args: list[str], code: int, pattern: str) -> None:
        got, out = self.run(script, *args)
        assert got == code, f"exit {got}, want {code}\n{out}"
        assert re.search(pattern, out, re.MULTILINE), f"no line matches {pattern!r}\n{out}"


# --- uv.lock -------------------------------------------------------------------------------------------

PYPI_FILES = "https://files.pythonhosted.org/packages/ab/cd/"


def uv_files(name: str, version: str) -> list[str]:
    return [f"{name}-{version}.tar.gz", f"{name}-{version}-py3-none-any.whl"]


def uv_pkg(name: str, version: str, *, source: str = "https://pypi.org/simple", host: str = PYPI_FILES,
           salt: str = "") -> str:  # fmt: skip
    sdist, wheel = uv_files(name, version)
    return (
        f'[[package]]\nname = "{name}"\nversion = "{version}"\nsource = {{ registry = "{source}" }}\n'
        f'sdist = {{ url = "{host}{sdist}", hash = "sha256:{h(sdist, salt)}" }}\n'
        f'wheels = [\n    {{ url = "{host}{wheel}", hash = "sha256:{h(wheel, salt)}" }},\n]\n'
    )


def uv_lock(*pkgs: str, requires: str = ">=3.12") -> str:
    return f'version = 1\nrevision = 3\nrequires-python = "{requires}"\n\n' + "\n".join(pkgs)


def pypi(c: Case, name: str, version: str, *, yanked: bool = False, files: list[str] | None = None) -> None:
    urls = [
        {"filename": f, "digests": {"sha256": h(f, "")}, "yanked": yanked}
        for f in (files if files is not None else uv_files(name, version))
    ]
    c.curl[f"https://pypi.org/pypi/{name}/{version}/json"] = {"status": 200, "body": {"urls": urls}}


def prov(c: Case, name: str, version: str, repo: str | None) -> None:
    if repo is None:
        return
    url = f"https://pypi.org/integrity/{name}/{version}/{name}-{version}.tar.gz/provenance"
    body = {"attestation_bundles": [{"publisher": {"kind": "GitHub", "repository": repo}}]}
    c.curl[url] = [{"if": {"Accept": "application/vnd.pypi.integrity.v1+json"}, "status": 200, "body": body}]


def uv_case(c: Case, old: list[str], new: list[str], **kw: str) -> list[str]:
    base = c.commit({"uv.lock": uv_lock(*old)})
    head = c.commit({"uv.lock": uv_lock(*new, **kw)})
    return ["--base", base, "--head", head]


def uv_bump(
    c: Case, *, old_repo: str | None = "o/ruff", new_repo: str | None = "o/ruff", **kw: str
) -> list[str]:
    pypi(c, "ruff", "0.16.10")
    prov(c, "ruff", "0.16.9", old_repo)
    prov(c, "ruff", "0.16.10", new_repo)
    return uv_case(c, [uv_pkg("ruff", "0.16.9")], [uv_pkg("ruff", "0.16.10", **kw)])


@row("uv: a clean bump with the same publisher passes")
def _(c: Case) -> None:
    c.expect(
        "uv_lock.py", uv_bump(c), OK, r"^ok .*ruff 0\.16\.9 -> 0\.16\.10: provenance GitHub o/ruff \(same"
    )


@row("uv: no provenance before or after passes")
def _(c: Case) -> None:
    c.expect("uv_lock.py", uv_bump(c, old_repo=None, new_repo=None), OK, r"no provenance, none before either")


@row("uv: a sha256 PyPI doesn't have")
def _(c: Case) -> None:
    c.expect("uv_lock.py", uv_bump(c, salt="x"), PROBLEM, r"^PROBLEM .*tar\.gz sha256 differs")


@row("uv: a file off files.pythonhosted.org")
def _(c: Case) -> None:
    args = uv_bump(c, host="https://evil.example/")
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM .*is not on files\.pythonhosted\.org")


@row("uv: a file PyPI doesn't list")
def _(c: Case) -> None:
    args = uv_bump(c)
    pypi(c, "ruff", "0.16.10", files=["ruff-0.16.10.tar.gz"])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM .*any\.whl is not listed by PyPI")


@row("uv: a yanked release")
def _(c: Case) -> None:
    args = uv_bump(c)
    pypi(c, "ruff", "0.16.10", yanked=True)
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM .*yanked")


@row("uv: a non-PyPI source")
def _(c: Case) -> None:
    c.expect("uv_lock.py", uv_bump(c, source="https://evil.example/simple"), PROBLEM, r"^PROBLEM .*not PyPI")


@row("uv: provenance the previous version had is gone")
def _(c: Case) -> None:
    c.expect("uv_lock.py", uv_bump(c, new_repo=None), PROBLEM, r"^PROBLEM .*had provenance .* has none")


@row("uv: a new publisher repository")
def _(c: Case) -> None:
    c.expect("uv_lock.py", uv_bump(c, new_repo="evil/ruff"), PROBLEM, r"^PROBLEM .*publisher changed")


@row("uv: an added package")
def _(c: Case) -> None:
    pypi(c, "ruff", "0.16.10")
    args = uv_case(c, [uv_pkg("ruff", "0.16.9")], [uv_pkg("ruff", "0.16.10"), uv_pkg("newdep", "1.0")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM newdep 1\.0: added")


@row("uv: a removed package")
def _(c: Case) -> None:
    args = uv_case(c, [uv_pkg("a", "1.0"), uv_pkg("b", "1.0")], [uv_pkg("a", "1.0")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM b: removed")


@row("uv: a minor bump is not a major")
def _(c: Case) -> None:
    pypi(c, "mypy", "2.4.0")
    args = uv_case(c, [uv_pkg("mypy", "2.3.1")], [uv_pkg("mypy", "2.4.0")])
    c.expect("uv_lock.py", args, OK, r"^uv\.lock: 0 problems")


@row("uv: a semver-major bump")
def _(c: Case) -> None:
    pypi(c, "mypy", "3.0.0")
    args = uv_case(c, [uv_pkg("mypy", "2.4.0")], [uv_pkg("mypy", "3.0.0")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM mypy 2\.4\.0 -> 3\.0\.0: semver-major")


@row("uv: a tantivy bump is hand-only")
def _(c: Case) -> None:
    pypi(c, "tantivy", "0.26.3")
    args = uv_case(c, [uv_pkg("tantivy", "0.26.2")], [uv_pkg("tantivy", "0.26.3")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM tantivy .*by hand only")


@row("uv: a changed requires-python")
def _(c: Case) -> None:
    args = uv_case(c, [uv_pkg("a", "1.0")], [uv_pkg("a", "1.0")], requires=">=3.13")
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM requires-python changed")


@row("uv: same version, different hashes")
def _(c: Case) -> None:
    args = uv_case(c, [uv_pkg("a", "1.0")], [uv_pkg("a", "1.0", salt="x")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM a 1\.0: same version, different files")


@row("uv: PyPI failing is an error, not a pass")
def _(c: Case) -> None:
    args = uv_bump(c)
    c.curl["https://pypi.org/pypi/ruff/0.16.10/json"] = {"status": 500, "body": ""}
    c.expect("uv_lock.py", args, ERROR, r"^ERROR .*HTTP 500")


@row("uv: the default base is the merge base with origin/dev, not dev's tip")
def _(c: Case) -> None:
    pypi(c, "ruff", "0.16.10")
    for v in ("0.16.9", "0.16.10"):
        prov(c, "ruff", v, "o/ruff")
    base = c.commit({"uv.lock": uv_lock(uv_pkg("ruff", "0.16.9"))})
    c.commit({"uv.lock": uv_lock(uv_pkg("ruff", "0.16.10"))})
    c.git("checkout", "-q", "-b", "dev", base)
    dev = c.commit({"uv.lock": uv_lock(uv_pkg("ruff", "0.16.9"), uv_pkg("later", "1.0"))})
    c.git("update-ref", "refs/remotes/origin/dev", dev)
    c.git("checkout", "-q", "work")
    c.expect("uv_lock.py", [], OK, r"^uv\.lock: 0 problems")


# --- package-lock.json ---------------------------------------------------------------------------------

REG = "https://registry.npmjs.org/"


def entry(name: str, v: str, **extra: Any) -> dict[str, Any]:
    short = name.rsplit("/", 1)[-1]
    return {
        "version": v,
        "resolved": f"{REG}{name}/-/{short}-{v}.tgz",
        "integrity": f"sha512-{h(name, v)}",
        **extra,
    }


def view(c: Case, name: str, v: str, *, user: str = "alice", **extra: Any) -> None:
    e = entry(name, v)
    dist: dict[str, Any] = {"integrity": e["integrity"], "tarball": e["resolved"]}
    if extra.pop("attest", False):
        dist["attestations"] = {"provenance": {"predicateType": "https://slsa.dev/provenance/v1"}}
    c.npm[f"{name}@{v}"] = {
        "name": name,
        "version": v,
        "dist": dist,
        "_npmUser": f"{user} <{user}@example.org>",
        **extra,
    }


def lock(entries: dict[str, dict[str, Any]], front: dict[str, str] | None = None) -> str:
    front = front if front is not None else {"next": "16.3.8"}
    packages = {
        "": {"name": "root", "workspaces": ["frontend"]},
        "frontend": {"version": "0.1.0", "dependencies": front},
        "node_modules/frontend": {"resolved": "frontend", "link": True},
        **{f"node_modules/{k}": v for k, v in entries.items()},
    }
    return json.dumps(
        {"name": "root", "lockfileVersion": 3, "requires": True, "packages": packages}, indent=2
    )


MANIFESTS = {
    "package.json": json.dumps({"name": "root", "workspaces": ["frontend"]}),
    "frontend/package.json": json.dumps({"name": "frontend", "dependencies": {"next": "16.3.8"}}),
}


def npm_case(
    c: Case, old: dict[str, Any], new: dict[str, Any], front: dict[str, str] | None = None
) -> list[str]:
    base = c.commit({**MANIFESTS, "package-lock.json": lock(old)})
    head = c.commit({"package-lock.json": lock(new, front)})
    return ["--base", base, "--head", head]


def npm_bump(c: Case, **new_extra: Any) -> list[str]:
    view(c, "next", "16.3.7")
    view(c, "next", "16.3.8")
    return npm_case(c, {"next": entry("next", "16.3.7")}, {"next": entry("next", "16.3.8", **new_extra)})


@row("npm: a clean bump passes")
def _(c: Case) -> None:
    c.expect("npm_lock.py", npm_bump(c), OK, r"^ok .*next 16\.3\.7 -> 16\.3\.8: matches the registry")


@row("npm: integrity the registry doesn't have")
def _(c: Case) -> None:
    c.expect("npm_lock.py", npm_bump(c, integrity="sha512-x"), PROBLEM, r"^PROBLEM .*integrity differs")


@row("npm: resolved off registry.npmjs.org")
def _(c: Case) -> None:
    args = npm_bump(c, resolved="https://evil.example/next-16.3.8.tgz")
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM .*resolved is not on registry\.npmjs\.org")


@row("npm: dependencies that differ from the manifest")
def _(c: Case) -> None:
    args = npm_bump(c, dependencies={"evil": "1.0.0"})
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM .*dependencies in the lock differs")


@row("npm: an added package")
def _(c: Case) -> None:
    view(c, "next", "16.3.8")
    args = npm_case(
        c, {"next": entry("next", "16.3.8")}, {"next": entry("next", "16.3.8"), "x": entry("x", "1.0.0")}
    )
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM node_modules/x 1\.0\.0: added")


@row("npm: a removed package")
def _(c: Case) -> None:
    args = npm_case(
        c, {"next": entry("next", "16.3.8"), "x": entry("x", "1.0.0")}, {"next": entry("next", "16.3.8")}
    )
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM node_modules/x: removed")


@row("npm: an install script the previous version didn't have")
def _(c: Case) -> None:
    args = npm_bump(c, hasInstallScript=True)
    view(c, "next", "16.3.8", scripts={"postinstall": "node x.js"})
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM .*new install script\(s\): postinstall")


@row("npm: hasInstallScript the manifest doesn't back")
def _(c: Case) -> None:
    c.expect(
        "npm_lock.py", npm_bump(c, hasInstallScript=True), PROBLEM, r"^PROBLEM .*hasInstallScript disagrees"
    )


@row("npm: a new publisher")
def _(c: Case) -> None:
    args = npm_bump(c)
    view(c, "next", "16.3.8", user="mallory")
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM .*publisher changed from 'alice' to 'mallory'")


@row("npm: provenance the previous version had is gone")
def _(c: Case) -> None:
    args = npm_bump(c)
    view(c, "next", "16.3.7", attest=True)
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM .*had npm provenance")


@row("npm: provenance kept passes")
def _(c: Case) -> None:
    args = npm_bump(c)
    view(c, "next", "16.3.7", attest=True)
    view(c, "next", "16.3.8", attest=True)
    c.expect("npm_lock.py", args, OK, r"^package-lock\.json: 0 problems")


@row("npm: a semver-major bump")
def _(c: Case) -> None:
    view(c, "next", "16.3.8")
    view(c, "next", "17.0.0")
    args = npm_case(c, {"next": entry("next", "16.3.8")}, {"next": entry("next", "17.0.0")})
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM .*16\.3\.8 -> 17\.0\.0: semver-major")


@row("npm: same version, different integrity")
def _(c: Case) -> None:
    view(c, "x", "1.0.0")
    args = npm_case(c, {"x": entry("x", "1.0.0")}, {"x": entry("x", "1.0.0", integrity="sha512-y")})
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM x 1\.0\.0: same version, different integrity")


@row("npm: libc dropped from an unchanged entry is a FIX")
def _(c: Case) -> None:
    view(c, "@img/sharp-linux-x64", "0.35.5", libc=["glibc"])
    old = {"@img/sharp-linux-x64": entry("@img/sharp-linux-x64", "0.35.5", libc=["glibc"], dev=True)}
    new = {"@img/sharp-linux-x64": entry("@img/sharp-linux-x64", "0.35.5")}
    c.expect("npm_lock.py", npm_case(c, old, new), FIX, r"^FIX .*sharp-linux-x64 0\.35\.5: libc dropped")


@row("npm: libc missing from a bumped entry is a FIX")
def _(c: Case) -> None:
    view(c, "@img/sharp-linux-x64", "0.35.4", libc=["glibc"])
    view(c, "@img/sharp-linux-x64", "0.35.5", libc=["glibc"])
    old = {"@img/sharp-linux-x64": entry("@img/sharp-linux-x64", "0.35.4", libc=["glibc"])}
    new = {"@img/sharp-linux-x64": entry("@img/sharp-linux-x64", "0.35.5")}
    c.expect("npm_lock.py", npm_case(c, old, new), FIX, r"^FIX .*0\.35\.4 -> 0\.35\.5: libc missing")


@row("npm: a wrong libc is a PROBLEM, not a FIX")
def _(c: Case) -> None:
    view(c, "@img/sharp-linux-x64", "0.35.4", libc=["glibc"])
    view(c, "@img/sharp-linux-x64", "0.35.5", libc=["glibc"])
    old = {"@img/sharp-linux-x64": entry("@img/sharp-linux-x64", "0.35.4", libc=["glibc"])}
    new = {"@img/sharp-linux-x64": entry("@img/sharp-linux-x64", "0.35.5", libc=["musl"])}
    c.expect("npm_lock.py", npm_case(c, old, new), PROBLEM, r"^PROBLEM .*libc in the lock differs")


@row("npm: a dev flag dropped from an unchanged entry passes")
def _(c: Case) -> None:
    view(c, "x", "1.0.0")
    args = npm_case(c, {"x": entry("x", "1.0.0", dev=True)}, {"x": entry("x", "1.0.0")})
    c.expect("npm_lock.py", args, OK, r"^package-lock\.json: 0 problems")


@row("npm: a caret in the lock's frontend entry is a FIX")
def _(c: Case) -> None:
    view(c, "x", "1.0.0")
    args = npm_case(c, {"x": entry("x", "1.0.0")}, {"x": entry("x", "1.0.0")}, front={"next": "^16.3.8"})
    c.expect(
        "npm_lock.py",
        args,
        FIX,
        r"""^FIX .*frontend/package\.json dependencies\.next is '16\.3\.8'.*'\^16\.3\.8'""",
    )


@row("npm: the root manifest is compared too")
def _(c: Case) -> None:
    base = c.commit({**MANIFESTS, "package-lock.json": lock({})})
    head = c.commit({"package.json": json.dumps({"name": "root", "devDependencies": {"prettier": "3.0.0"}})})
    c.expect(
        "npm_lock.py", ["--base", base, "--head", head], FIX, r"^FIX +package\.json devDependencies\.prettier"
    )


@row("npm: the registry failing is an error, not a pass")
def _(c: Case) -> None:
    args = npm_bump(c)
    del c.npm["next@16.3.8"]
    c.expect("npm_lock.py", args, ERROR, r"^ERROR .*npm view next@16\.3\.8 .*exited 1")


# --- docker --------------------------------------------------------------------------------------------

INDEX = "application/vnd.oci.image.index.v1+json"
TOKEN_AUTH = 'Bearer realm="https://auth.docker.io/token",service="registry.docker.io"'


def digest(*parts: str) -> str:
    return f"sha256:{h(*parts)}"


def registry(
    c: Case, host: str, repo: str, tag: str, dig: str, *, ctype: str = INDEX, status: int = 200
) -> None:
    c.curl[f"https://{host}/v2/{repo}/manifests/{tag}"] = [
        {"if": {"Authorization": "Bearer T", "Accept": INDEX}, "status": status,
         "headers": {"docker-content-digest": dig, "content-type": ctype}},
        {"if": {"Authorization": "Bearer T"}, "status": 200,
         "headers": {"docker-content-digest": digest("platform"), "content-type": "application/vnd.oci.image.manifest.v1+json"}},
        {"status": 401, "headers": {"www-authenticate": TOKEN_AUTH}},
    ]  # fmt: skip
    scope = urllib.parse.urlencode({"service": "registry.docker.io", "scope": f"repository:{repo}:pull"})
    c.curl[f"https://auth.docker.io/token?{scope}"] = {"status": 200, "body": {"token": "T"}}


def docker_case(c: Case, old: str, new: str, path: str = "deploy/web.Dockerfile", **extra: str) -> list[str]:
    base = c.commit({path: f"FROM {old}\n", ".python-version": "3.12.15\n"})
    head = c.commit({path: f"FROM {new}\n", **extra})
    return ["--base", base, "--head", head]


def node_case(c: Case, **kw: Any) -> list[str]:
    old, new = digest("node-old"), digest("node-new")
    registry(c, "registry-1.docker.io", "library/node", "22-bookworm-slim", kw.pop("served", new), **kw)
    return docker_case(c, f"node:22-bookworm-slim@{old}", f"node:22-bookworm-slim@{new}")


@row("docker: a Docker Hub digest bump that resolves passes")
def _(c: Case) -> None:
    c.expect(
        "docker_digest.py", node_case(c), OK, r"^ok .*resolves 22-bookworm-slim to the pinned index digest"
    )


@row("docker: a digest the registry doesn't serve")
def _(c: Case) -> None:
    c.expect(
        "docker_digest.py", node_case(c, served=digest("other")), PROBLEM, r"^PROBLEM .*not the pinned digest"
    )


@row("docker: a pinned digest that isn't an index")
def _(c: Case) -> None:
    args = node_case(c, ctype="application/vnd.oci.image.manifest.v1+json")
    c.expect("docker_digest.py", args, PROBLEM, r"^PROBLEM .*not a multi-arch index")


@row("docker: a registry failure is an error, not a pass")
def _(c: Case) -> None:
    c.expect("docker_digest.py", node_case(c, status=500), ERROR, r"^ERROR .*HTTP 500")


@row("docker: a token realm that isn't https is refused before any request")
def _(c: Case) -> None:
    args = node_case(c)
    url = "https://registry-1.docker.io/v2/library/node/manifests/22-bookworm-slim"
    c.curl[url][-1]["headers"]["www-authenticate"] = TOKEN_AUTH.replace("https://", "http://")
    c.expect(
        "docker_digest.py", args, ERROR, r"^ERROR +refusing a non-https URL: http://auth\.docker\.io/token"
    )


def uv_image_case(c: Case, attested: bool) -> list[str]:
    new = digest("uv-new")
    c.curl["https://ghcr.io/v2/astral-sh/uv/manifests/0.12.24"] = [
        {
            "if": {"Accept": INDEX},
            "status": 200,
            "headers": {"docker-content-digest": new, "content-type": INDEX},
        }
    ]
    if attested:
        c.gh[f"attestation oci://ghcr.io/astral-sh/uv@{new} astral-sh"] = 0
    return docker_case(
        c, f"ghcr.io/astral-sh/uv:0.12.23@{digest('uv-old')}", f"ghcr.io/astral-sh/uv:0.12.24@{new}",
        path="deploy/api.Dockerfile",
    )  # fmt: skip


@row("docker: a ghcr.io image with a verified attestation passes")
def _(c: Case) -> None:
    c.expect(
        "docker_digest.py", uv_image_case(c, True), OK, r"^ok .*attestation verified for owner astral-sh"
    )


@row("docker: a ghcr.io image whose attestation fails")
def _(c: Case) -> None:
    c.expect(
        "docker_digest.py",
        uv_image_case(c, False),
        PROBLEM,
        r"^PROBLEM .*gh attestation verify --owner astral-sh",
    )


@row("docker: an image that wasn't pinned before")
def _(c: Case) -> None:
    new = digest("evil")
    registry(c, "registry-1.docker.io", "library/evil", "1", new)
    args = docker_case(c, f"node:22-bookworm-slim@{digest('n')}", f"evil:1@{new}")
    c.expect("docker_digest.py", args, PROBLEM, r"^PROBLEM .*evil was not pinned before")


@row("docker: a semver-major tag change")
def _(c: Case) -> None:
    new = digest("caddy3")
    registry(c, "registry-1.docker.io", "library/caddy", "3.0.0-alpine", new)
    args = docker_case(c, f"caddy:2.11.4-alpine@{digest('c')}", f"caddy:3.0.0-alpine@{new}")
    c.expect("docker_digest.py", args, PROBLEM, r"^PROBLEM .*semver-major tag change from 2\.11\.4-alpine")


def python_case(c: Case, tag: str, pin: str) -> list[str]:
    new = digest("py", tag)
    registry(c, "registry-1.docker.io", "library/python", tag, new)
    return docker_case(
        c, f"python:3.12.15-slim-bookworm@{digest('py')}", f"python:{tag}@{new}",
        path="deploy/api.Dockerfile", **{".python-version": pin},
    )  # fmt: skip


@row("docker: a Python patch bump with .python-version moved passes")
def _(c: Case) -> None:
    c.expect(
        "docker_digest.py",
        python_case(c, "3.12.16-slim-bookworm", "3.12.16\n"),
        OK,
        r"^docker pins: 0 problems",
    )


@row("docker: a Python patch bump without .python-version is a FIX")
def _(c: Case) -> None:
    args = python_case(c, "3.12.16-slim-bookworm", "3.12.15\n")
    c.expect("docker_digest.py", args, FIX, r"^FIX .*\.python-version is '3\.12\.15'; move it to '3\.12\.16'")


@row("docker: a Python minor is hand-only")
def _(c: Case) -> None:
    args = python_case(c, "3.13.0-slim-bookworm", "3.13.0\n")
    c.expect("docker_digest.py", args, PROBLEM, r"^PROBLEM .*a new Python minor")


# --- GitHub Actions ------------------------------------------------------------------------------------


def sha(*parts: str) -> str:
    return h(*parts)[:40]


def wf(*uses: str) -> str:
    return "jobs:\n  j:\n    steps:\n" + "".join(f"      - uses: {u}\n" for u in uses)


def actions_case(c: Case, old: str, new: str) -> list[str]:
    base = c.commit({".github/workflows/lint.yml": wf(old)})
    head = c.commit({".github/workflows/lint.yml": wf(new)})
    return ["--base", base, "--head", head]


@row("actions: a pin whose tag is that commit passes")
def _(c: Case) -> None:
    c.gh["api repos/actions/checkout/commits/v7.0.2"] = {"sha": sha("b")}
    args = actions_case(c, f"actions/checkout@{sha('a')} # v7.0.1", f"actions/checkout@{sha('b')} # v7.0.2")
    c.expect("actions_pins.py", args, OK, r"^ok .*tag v7\.0\.2 is the pinned commit")


@row("actions: a tag that is another commit")
def _(c: Case) -> None:
    c.gh["api repos/actions/checkout/commits/v7.0.2"] = {"sha": sha("other")}
    args = actions_case(c, f"actions/checkout@{sha('a')} # v7.0.1", f"actions/checkout@{sha('b')} # v7.0.2")
    c.expect("actions_pins.py", args, PROBLEM, r"^PROBLEM .*tag v7\.0\.2 is commit")


@row("actions: an action not used before")
def _(c: Case) -> None:
    args = actions_case(c, f"actions/checkout@{sha('a')} # v7.0.1", f"evil/thing@{sha('b')} # v1.0.0")
    c.expect("actions_pins.py", args, PROBLEM, r"^PROBLEM .*evil/thing was not used before")


@row("actions: an unpinned uses line")
def _(c: Case) -> None:
    args = actions_case(c, f"actions/checkout@{sha('a')} # v7.0.1", "actions/checkout@v7")
    c.expect("actions_pins.py", args, PROBLEM, r"^PROBLEM .*not pinned to a full commit sha")


@row("actions: a semver-major tag")
def _(c: Case) -> None:
    c.gh["api repos/actions/checkout/commits/v8.0.0"] = {"sha": sha("b")}
    args = actions_case(c, f"actions/checkout@{sha('a')} # v7.0.1", f"actions/checkout@{sha('b')} # v8.0.0")
    c.expect("actions_pins.py", args, PROBLEM, r"^PROBLEM .*semver-major")


@row("actions: a pin with no tag comment")
def _(c: Case) -> None:
    args = actions_case(c, f"actions/checkout@{sha('a')} # v7.0.1", f"actions/checkout@{sha('b')}")
    c.expect("actions_pins.py", args, PROBLEM, r"^PROBLEM .*no `# <tag>` comment")


# --- restore_libc.py -----------------------------------------------------------------------------------


@row("restore_libc: puts libc back in the base entry's key order, nothing else")
def _(c: Case) -> None:
    k = "@img/sharp-linux-x64"
    old_entry = {"version": "0.35.4", "cpu": ["x64"], "libc": ["glibc"], "os": ["linux"], "optional": True}
    base = c.commit({"package-lock.json": lock({k: old_entry, "x": entry("x", "1.0.0")})})
    new_entry = {"version": "0.35.5", "cpu": ["x64"], "os": ["linux"], "optional": True, "funding": "u"}
    c.commit({"package-lock.json": lock({k: new_entry, "x": entry("x", "1.0.0")})})
    c.expect("restore_libc.py", ["--base", base], OK, r"^restored libc: node_modules/@img/sharp-linux-x64$")
    got = json.loads((c.repo / "package-lock.json").read_text())["packages"]
    assert list(got[f"node_modules/{k}"]) == ["version", "cpu", "libc", "os", "optional", "funding"], got
    assert got[f"node_modules/{k}"]["libc"] == ["glibc"] and got[f"node_modules/{k}"]["version"] == "0.35.5"
    assert got["node_modules/x"] == entry("x", "1.0.0")


@row("restore_libc: a lock that lost nothing is left byte-for-byte")
def _(c: Case) -> None:
    text = lock({"x": entry("x", "1.0.0")})
    base = c.commit({"package-lock.json": text})
    c.expect("restore_libc.py", ["--base", base], OK, r"^0 entries repaired")
    assert (c.repo / "package-lock.json").read_text() == text


# --- prs.py --------------------------------------------------------------------------------------------


def pr(n: int, head: str, title: str, *paths: str) -> dict[str, Any]:
    return {
        "number": n,
        "title": title,
        "headRefName": head,
        "url": "u",
        "files": [{"path": p} for p in paths],
    }


@row("prs list: names files outside the ecosystem, unknown ecosystems and tantivy")
def _(c: Case) -> None:
    c.gh["pr list"] = [
        pr(1, "dependabot/npm_and_yarn/g", "deps: bump next", "package-lock.json", "frontend/package.json"),
        pr(2, "dependabot/npm_and_yarn/h", "deps: bump x", "package-lock.json", ".npmrc"),
        pr(3, "dependabot/cargo/i", "deps: bump y", "Cargo.lock"),
        pr(4, "dependabot/uv/j", "deps: bump tantivy", "uv.lock"),
        pr(5, "dependabot/docker/deploy/k", "build: bump uv", "deploy/api.Dockerfile"),
    ]
    got, out = c.run("prs.py", "list")
    assert got == 0, out
    problems = re.findall(r"^PROBLEM #(\d+)", out, re.MULTILINE)
    assert problems == ["2", "3", "4"], out
    assert ".npmrc is outside" in out and "'cargo'" in out and "tantivy" in out, out


def gql(*states: tuple[str, dict[str, Any] | None, dict[str, Any] | None]) -> dict[str, Any]:
    prs: dict[str, Any] = {
        f"p{n}": {"state": s, "mergeQueueEntry": q, "autoMergeRequest": a, "commits": {"nodes": []}}
        for n, (s, q, a) in enumerate(states, start=1)
    }
    return {"data": {"repository": prs}}


QUEUED = {"state": "AWAITING_CHECKS", "position": 1}


@row("prs watch: exits 0 once every PR merged")
def _(c: Case) -> None:
    c.gh["graphql"] = [gql(("OPEN", QUEUED, None), ("OPEN", None, {"enabledAt": "t"})),
                       gql(("MERGED", None, None), ("MERGED", None, None))]  # fmt: skip
    c.expect("prs.py", ["watch", "1", "2", "--interval", "0"], 0, r"^all merged")


@row("prs watch: a PR out of the queue two polls running exits 1")
def _(c: Case) -> None:
    c.gh["graphql"] = [gql(("OPEN", QUEUED, None)), gql(("OPEN", None, None))]
    c.expect("prs.py", ["watch", "1", "--interval", "0"], 1, r"^#1 is open but out of the merge queue")


@row("prs watch: one poll between queue states is not a drop")
def _(c: Case) -> None:
    c.gh["graphql"] = [gql(("OPEN", None, None)), gql(("OPEN", QUEUED, None)), gql(("MERGED", None, None))]
    c.expect("prs.py", ["watch", "1", "--interval", "0"], 0, r"^all merged")


@row("prs watch: a PR closed unmerged exits 1")
def _(c: Case) -> None:
    c.gh["graphql"] = [gql(("CLOSED", None, None))]
    c.expect("prs.py", ["watch", "1", "--interval", "0"], 1, r"^#1 was closed without merging")


@row("prs watch: the timeout exits 4")
def _(c: Case) -> None:
    c.gh["graphql"] = [gql(("OPEN", QUEUED, None))]
    c.expect("prs.py", ["watch", "1", "--interval", "0", "--timeout", "0"], 4, r"^timed out")


def one(label: str, fn: Callable[[Case], None]) -> str | None:
    """Run one row in its own temp dir; None when it passes, else the failure text."""
    tmp = Path(tempfile.mkdtemp(prefix="op-depbot-case-"))
    try:
        fn(Case(tmp))
        return None
    except Exception as e:  # a row's failure is reported, and the table goes on
        return str(e) if isinstance(e, AssertionError) else traceback.format_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as ex:
        results = list(ex.map(lambda r: one(*r), ROWS))
    for (label, _), failure in zip(ROWS, results, strict=True):
        if failure is None:
            print(f"  ok   {label}")
        else:
            print(f"  FAIL {label}\n" + "\n".join(f"       {line}" for line in failure.splitlines()[:30]))
    failed = sum(r is not None for r in results)
    print(f"passed: {len(ROWS) - failed}  failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
