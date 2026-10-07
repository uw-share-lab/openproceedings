#!/usr/bin/env python3
"""Case table for the /dependabot-review scripts in .claude/scripts/dependabot/ (TASK-211).

    python3 .claude/scripts/tests/dependabot_cases.py      # run by test-dependabot.sh, so by `make tooling`

Each row builds a throwaway git repo with a base and a head commit, writes the fixtures the fake `curl`,
`npm` and `gh` (dependabot_fake.py, first on PATH) answer from, runs one script there, and checks its exit
status and one line of its output. No row reaches the network. Mutants: .claude/scripts/mutants/dependabot.json.
"""

from __future__ import annotations

import base64
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

    def git(self, *args: str, env: dict[str, str] | None = None) -> str:
        cmd = ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@example.org"]
        cmd += ["-c", "commit.gpgsign=false", *args]
        run_env = {**ENV, **(env or {})}
        return subprocess.run(cmd, capture_output=True, text=True, check=True, env=run_env).stdout.strip()

    def commit(self, files: dict[str, str | None], who: dict[str, str] | None = None) -> str:
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
        self.git("commit", "-q", "--allow-empty", "-m", "c", env=who)
        return self.git("rev-parse", "HEAD")

    def run(self, script: str, *args: str) -> tuple[int, str]:
        for name, data in (("curl.json", self.curl), ("npm.json", self.npm), ("gh.json", self.gh)):
            (self.fix / name).write_text(json.dumps(data))
        env = {**ENV, "PATH": f"{self.bin}{os.pathsep}{ENV.get('PATH', '')}", "DEPBOT_FIX": str(self.fix)}
        env["OP_DEPENDABOT_NOW"] = CLOCK
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


OLD_RELEASE = "2020-01-01T00:00:00.000000Z"  # far past any cooldown
CLOCK = "2026-10-07T12:00:00Z"  # the scripts' now, through OP_DEPENDABOT_NOW: no row reads the wall clock
NOW = "2026-10-07T00:00:00.000000Z"  # half a day before CLOCK


def pypi(
    c: Case, name: str, version: str, *, yanked: bool = False, files: list[str] | None = None,
    uploaded: str = OLD_RELEASE,
) -> None:  # fmt: skip
    urls = [
        {"filename": f, "digests": {"sha256": h(f, "")}, "yanked": yanked, "upload_time_iso_8601": uploaded}
        for f in (files if files is not None else uv_files(name, version))
    ]
    c.curl[f"https://pypi.org/pypi/{name}/{version}/json"] = {"status": 200, "body": {"urls": urls}}


def prov(
    c: Case, name: str, version: str, repo: str | None, *, only: list[str] | None = None, **pub: str
) -> None:
    """PEP 740 provenance for every file of the version (or `only` these), from `repo`."""
    if repo is None:
        return
    for fn in only if only is not None else uv_files(name, version):
        url = f"https://pypi.org/integrity/{name}/{version}/{fn}/provenance"
        body = {"attestation_bundles": [{"publisher": {"kind": "GitHub", "repository": repo, **pub}}]}
        c.curl[url] = [
            {"if": {"Accept": "application/vnd.pypi.integrity.v1+json"}, "status": 200, "body": body}
        ]


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
        "uv_lock.py",
        uv_bump(c),
        OK,
        r'^ok .*ruff 0\.16\.9 -> 0\.16\.10: provenance .*"o/ruff".* on every file, as before$',
    )


@row("uv: no provenance before or after passes")
def _(c: Case) -> None:
    c.expect(
        "uv_lock.py", uv_bump(c, old_repo=None, new_repo=None), OK, r"^ok .*provenance none on every file$"
    )


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
    c.expect(
        "uv_lock.py",
        uv_bump(c, new_repo=None),
        PROBLEM,
        r"^PROBLEM .*tar\.gz has no provenance; 0\.16\.9 had",
    )


@row("uv: a new publisher repository")
def _(c: Case) -> None:
    c.expect("uv_lock.py", uv_bump(c, new_repo="evil/ruff"), PROBLEM, r"^PROBLEM .*publisher changed")


@row("uv: a wheel without the provenance the sdist and the previous version have")
def _(c: Case) -> None:
    pypi(c, "ruff", "0.16.10")
    prov(c, "ruff", "0.16.9", "o/ruff")
    prov(c, "ruff", "0.16.10", "o/ruff", only=["ruff-0.16.10.tar.gz"])
    args = uv_case(c, [uv_pkg("ruff", "0.16.9")], [uv_pkg("ruff", "0.16.10")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM .*any\.whl has no provenance")


@row("uv: the whole publisher record is compared (a new workflow)")
def _(c: Case) -> None:
    pypi(c, "ruff", "0.16.10")
    prov(c, "ruff", "0.16.9", "o/ruff", workflow="release.yml")
    prov(c, "ruff", "0.16.10", "o/ruff", workflow="evil.yml")
    args = uv_case(c, [uv_pkg("ruff", "0.16.9")], [uv_pkg("ruff", "0.16.10")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM .*publisher changed .*evil\.yml")


@row("uv: files of one release that disagree on provenance")
def _(c: Case) -> None:
    pypi(c, "ruff", "0.16.10")
    prov(c, "ruff", "0.16.10", "o/ruff", only=["ruff-0.16.10.tar.gz"])
    args = uv_case(c, [uv_pkg("ruff", "0.16.9")], [uv_pkg("ruff", "0.16.10")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM .*disagree on provenance")


@row("uv: one package at two versions, each bumped within its major")
def _(c: Case) -> None:
    for v in ("1.26.5", "2.1.1"):
        pypi(c, "numpy", v)
    old = [uv_pkg("numpy", "1.26.4"), uv_pkg("numpy", "2.1.0")]
    args = uv_case(c, old, [uv_pkg("numpy", "1.26.5"), uv_pkg("numpy", "2.1.1")])
    c.expect("uv_lock.py", args, OK, r"^ok .*numpy 1\.26\.4 -> 1\.26\.5: 2 file")


@row("uv: a PyPI answer of the wrong shape is an error, not a crash")
def _(c: Case) -> None:
    args = uv_bump(c)
    c.curl["https://pypi.org/pypi/ruff/0.16.10/json"] = {"status": 200, "body": {"urls": [{"filename": "x"}]}}
    c.expect("uv_lock.py", args, ERROR, r"^ERROR +KeyError")


@row("uv: a release younger than the cooldown")
def _(c: Case) -> None:
    args = uv_bump(c)
    pypi(c, "ruff", "0.16.10", uploaded=NOW)
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM .*uploaded 0\.\d days ago \(under 7")


@row("uv: an sdist without provenance doesn't hide the old wheel's publisher")
def _(c: Case) -> None:
    pypi(c, "ruff", "0.16.10")
    prov(c, "ruff", "0.16.9", "o/ruff", only=["ruff-0.16.9-py3-none-any.whl"])
    prov(c, "ruff", "0.16.10", "evil/ruff")
    args = uv_case(c, [uv_pkg("ruff", "0.16.9")], [uv_pkg("ruff", "0.16.10")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM .*publisher changed .*o/ruff.*evil/ruff")


@row("uv: provenance on the previous wheel only, none now")
def _(c: Case) -> None:
    pypi(c, "ruff", "0.16.10")
    prov(c, "ruff", "0.16.9", "o/ruff", only=["ruff-0.16.9-py3-none-any.whl"])
    args = uv_case(c, [uv_pkg("ruff", "0.16.9")], [uv_pkg("ruff", "0.16.10")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM .*has no provenance; 0\.16\.9 had")


@row("uv: same version, another source")
def _(c: Case) -> None:
    args = uv_case(c, [uv_pkg("a", "1.0")], [uv_pkg("a", "1.0", source="https://evil.example/simple")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM a 1\.0: same version, different source")


@row("uv: a lock setting outside the package list changes")
def _(c: Case) -> None:
    base = c.commit({"uv.lock": uv_lock(uv_pkg("a", "1.0"))})
    head = c.commit(
        {
            "uv.lock": uv_lock(uv_pkg("a", "1.0")).replace(
                "revision = 3", 'revision = 3\n[options]\nexclude-newer = "2030-01-01T00:00:00Z"\n'
            )
        }
    )
    c.expect("uv_lock.py", ["--base", base, "--head", head], PROBLEM, r"^PROBLEM uv\.lock: `options` changed")


PYPROJECT = '[project]\nname = "root"\ndependencies = ["ruff>={v}"]\n[dependency-groups]\ndev = ["mypy>=2.3"]\n{extra}'


def pyproject_case(c: Case, new_spec: str, extra: str = "") -> list[str]:
    pypi(c, "ruff", "0.16.10")
    base = c.commit(
        {
            "uv.lock": uv_lock(uv_pkg("ruff", "0.16.9")),
            "pyproject.toml": PYPROJECT.format(v="0.16.9", extra=""),
        }
    )
    head = c.commit(
        {
            "uv.lock": uv_lock(uv_pkg("ruff", "0.16.10")),
            "pyproject.toml": PYPROJECT.format(v=new_spec, extra=extra),
        }
    )
    return ["--base", base, "--head", head]


@row("uv: a pyproject specifier of a package the lock moved passes")
def _(c: Case) -> None:
    c.expect(
        "uv_lock.py", pyproject_case(c, "0.16.10"), OK, r"^ok +pyproject\.toml: checked against the lock"
    )


@row("uv: a pyproject change outside the dependency lists (a build requirement)")
def _(c: Case) -> None:
    args = pyproject_case(c, "0.16.10", '[build-system]\nrequires = ["evil-build-helper"]\n')
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM pyproject\.toml: changed outside its dependency lists")


@row("uv: a pyproject specifier of a package the lock didn't move")
def _(c: Case) -> None:
    pypi(c, "ruff", "0.16.10")
    base = c.commit(
        {
            "uv.lock": uv_lock(uv_pkg("ruff", "0.16.9")),
            "pyproject.toml": PYPROJECT.format(v="0.16.9", extra=""),
        }
    )
    text = PYPROJECT.format(v="0.16.10", extra="").replace("mypy>=2.3", "mypy>=2.4")
    head = c.commit({"uv.lock": uv_lock(uv_pkg("ruff", "0.16.10")), "pyproject.toml": text})
    c.expect(
        "uv_lock.py",
        ["--base", base, "--head", head],
        PROBLEM,
        r"^PROBLEM pyproject\.toml dependency-groups\.dev: .*didn't move mypy",
    )


def member(source: str, deps: str) -> str:
    return f'[[package]]\nname = "openproceedings"\nversion = "0.0.0"\nsource = {{ editable = "{source}" }}\ndependencies = [{deps}]\n'


@row("uv: a workspace member's dependency list may change")
def _(c: Case) -> None:
    args = uv_case(
        c,
        [member("backend", '{ name = "a" }'), uv_pkg("a", "1.0")],
        [member("backend", '{ name = "a", marker = "x" }'), uv_pkg("a", "1.0")],
    )
    c.expect("uv_lock.py", args, OK, r"^uv\.lock: 0 problems")


@row("uv: a workspace member's source may not")
def _(c: Case) -> None:
    args = uv_case(c, [member("backend", ""), uv_pkg("a", "1.0")], [member("evil", ""), uv_pkg("a", "1.0")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM openproceedings 0\.0\.0: same version, different source")


@row("uv: the cooldown reads the newest file, not the oldest")
def _(c: Case) -> None:
    args = uv_bump(c)
    url = "https://pypi.org/pypi/ruff/0.16.10/json"
    c.curl[url]["body"]["urls"][1]["upload_time_iso_8601"] = NOW
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM .*uploaded 0\.5 days ago")


@row("uv: an unmoved registry package's dependencies change")
def _(c: Case) -> None:
    deps = 'dependencies = [{{ name = "{}" }}]\n'
    old = uv_pkg("a", "1.0") + deps.format("b")
    new = uv_pkg("a", "1.0") + deps.format("evil")
    args = uv_case(
        c, [old, uv_pkg("b", "1.0"), uv_pkg("evil", "1.0")], [new, uv_pkg("b", "1.0"), uv_pkg("evil", "1.0")]
    )
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM a 1\.0: same version, different dependencies")


@row("uv: a direct dependency added to a pyproject (already locked)")
def _(c: Case) -> None:
    args = pyproject_case(c, "0.16.10")
    text = PYPROJECT.format(v="0.16.10", extra="").replace(
        '"ruff>=0.16.10"]', '"ruff>=0.16.10", "mypy>=2.3"]'
    )
    args[3] = c.commit({"pyproject.toml": text})
    c.expect(
        "uv_lock.py",
        args,
        PROBLEM,
        r"^PROBLEM pyproject\.toml project\.dependencies: a dependency was added or removed",
    )


@row("uv: a dependency list added to a pyproject")
def _(c: Case) -> None:
    args = pyproject_case(c, "0.16.10")
    text = PYPROJECT.format(v="0.16.10", extra="") + '[project.optional-dependencies]\nx = ["mypy>=2.3"]\n'
    args[3] = c.commit({"pyproject.toml": text.replace("[dependency-groups]", "[dependency-groups]", 1)})
    c.expect(
        "uv_lock.py",
        args,
        PROBLEM,
        r"^PROBLEM pyproject\.toml: its dependency lists were added, removed or renamed",
    )


@row("uv: the previous version's files name two publishers")
def _(c: Case) -> None:
    pypi(c, "ruff", "0.16.10")
    prov(c, "ruff", "0.16.9", "o/ruff", only=["ruff-0.16.9.tar.gz"])
    prov(c, "ruff", "0.16.9", "other/ruff", only=["ruff-0.16.9-py3-none-any.whl"])
    prov(c, "ruff", "0.16.10", "o/ruff")
    args = uv_case(c, [uv_pkg("ruff", "0.16.9")], [uv_pkg("ruff", "0.16.10")])
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM .*the files of 0\.16\.9 name 2 publishers")


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
    c.expect("uv_lock.py", args, PROBLEM, r"^PROBLEM a 1\.0: same version, different sdist, wheels")


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


def view(
    c: Case, name: str, v: str, *, user: str = "alice", released: str = OLD_RELEASE, **extra: Any
) -> None:
    e = entry(name, v)
    dist: dict[str, Any] = {"integrity": e["integrity"], "tarball": e["resolved"]}
    repo = extra.pop("attest", None)
    if repo:  # npm provenance: the attestations URL serves an SLSA statement naming the source repository
        url = f"{REG}-/npm/v1/attestations/{name}@{v}"
        dist["attestations"] = {"url": url, "provenance": {"predicateType": "https://slsa.dev/provenance/v1"}}
        stmt = {"predicate": {"buildDefinition": {"externalParameters": {"workflow": {"repository": repo}}}}}
        payload = base64.b64encode(json.dumps(stmt).encode()).decode()
        c.curl[url] = {"status": 200, "body": {"attestations": [
            {"predicateType": "https://github.com/npm/attestation/tree/main/specs/publish/v0.1"},
            {"predicateType": "https://slsa.dev/provenance/v1", "bundle": {"dsseEnvelope": {"payload": payload}}},
        ]}}  # fmt: skip
    c.npm[f"{name}@{v}"] = {
        "name": name,
        "version": v,
        "dist": dist,
        "_npmUser": f"{user} <{user}@example.org>",
        "time": {"created": OLD_RELEASE, v: released},
        **extra,
    }


def lock(entries: dict[str, dict[str, Any]], front: dict[str, str] | None = None) -> str:
    front = front if front is not None else {"next": "16.3.8"}
    packages = {
        "": {"name": "root", "workspaces": ["frontend"]},
        "frontend": {"version": "0.1.0", "dependencies": front},
        "node_modules/frontend": {"resolved": "frontend", "link": True},
        **{(k if k.startswith("frontend/") else f"node_modules/{k}"): v for k, v in entries.items()},
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
    view(c, "next", "16.3.7", attest="https://github.com/vercel/next.js")
    c.expect(
        "npm_lock.py", args, PROBLEM, r"^PROBLEM .*had npm provenance \(https://github\.com/vercel/next\.js\)"
    )


@row("npm: provenance kept passes")
def _(c: Case) -> None:
    args = npm_bump(c)
    view(c, "next", "16.3.7", attest="https://github.com/vercel/next.js")
    view(c, "next", "16.3.8", attest="https://github.com/vercel/next.js")
    c.expect("npm_lock.py", args, OK, r"^package-lock\.json: 0 problems")


@row("npm: provenance from another source repository")
def _(c: Case) -> None:
    args = npm_bump(c)
    view(c, "next", "16.3.7", attest="https://github.com/vercel/next.js")
    view(c, "next", "16.3.8", attest="https://github.com/evil/next.js")
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM .*provenance repository changed .*evil/next\.js")


@row("npm: an entry that switches to another package (an alias)")
def _(c: Case) -> None:
    view(c, "evil", "1.0.1")
    args = npm_case(c, {"foo": entry("foo", "1.0.0")}, {"foo": {**entry("evil", "1.0.1"), "name": "evil"}})
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM node_modules/foo: the package changed from foo to evil")


@row("npm: a registry entry turned into a link")
def _(c: Case) -> None:
    args = npm_case(c, {"x": entry("x", "1.0.0")}, {"x": {"resolved": "frontend", "link": True}})
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM node_modules/x: a link entry changed")


@row("npm: a nested node_modules entry is checked")
def _(c: Case) -> None:
    view(c, "x", "1.0.0")
    view(c, "x", "1.0.1")
    old = {"frontend/node_modules/x": entry("x", "1.0.0")}
    new = {"frontend/node_modules/x": entry("x", "1.0.1", integrity="sha512-bad")}
    c.expect(
        "npm_lock.py", npm_case(c, old, new), PROBLEM, r"^PROBLEM x 1\.0\.0 -> 1\.0\.1: integrity differs"
    )


@row("npm: npm view runs outside the repo, so its .npmrc can't redirect a scope")
def _(c: Case) -> None:
    c.commit({".npmrc": "@vercel:registry=https://evil.example/\n"})
    c.expect("npm_lock.py", npm_bump(c), OK, r"^package-lock\.json: 0 problems")


@row("npm: a semver-major bump")
def _(c: Case) -> None:
    view(c, "next", "16.3.8")
    view(c, "next", "17.0.0")
    args = npm_case(c, {"next": entry("next", "16.3.8")}, {"next": entry("next", "17.0.0")})
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM .*16\.3\.8 -> 17\.0\.0: semver-major")
    _, out = c.run("npm_lock.py", *args)
    assert not re.search(r"^ok .*next .*matches the registry", out, re.MULTILINE), out
    assert re.search(r"^ok .*match the lock's workspace entries", out, re.MULTILINE), out


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


def front(next_version: str) -> str:
    return json.dumps({"name": "frontend", "dependencies": {"next": next_version}})


@row("npm: a caret in the lock's frontend entry is a FIX")
def _(c: Case) -> None:
    view(c, "next", "16.3.7")
    view(c, "next", "16.3.8")
    old = lock({"next": entry("next", "16.3.7")}, {"next": "16.3.7"})
    base = c.commit({**MANIFESTS, "frontend/package.json": front("16.3.7"), "package-lock.json": old})
    new = lock({"next": entry("next", "16.3.8")}, {"next": "^16.3.8"})
    head = c.commit({"frontend/package.json": front("16.3.8"), "package-lock.json": new})
    c.expect(
        "npm_lock.py",
        ["--base", base, "--head", head],
        FIX,
        r"""^FIX .*frontend/package\.json dependencies\.next is '16\.3\.8'.*'\^16\.3\.8'""",
    )


@row("npm: a moved package's manifest value that isn't a locked version (a URL)")
def _(c: Case) -> None:
    view(c, "next", "16.3.7")
    view(c, "next", "16.3.8")
    old = lock({"next": entry("next", "16.3.7")}, {"next": "16.3.7"})
    base = c.commit({**MANIFESTS, "frontend/package.json": front("16.3.7"), "package-lock.json": old})
    url = "git+https://evil.example/next.git"
    new = lock({"next": entry("next", "16.3.8")}, {"next": url})
    head = c.commit({"frontend/package.json": front(url), "package-lock.json": new})
    c.expect(
        "npm_lock.py",
        ["--base", base, "--head", head],
        PROBLEM,
        r"^PROBLEM frontend/package\.json dependencies\.next: 'git\+https://evil\.example/next\.git' is not a version the lock now holds",
    )


@row("npm: a range in a manifest is not an exact pin")
def _(c: Case) -> None:
    view(c, "next", "16.3.7")
    view(c, "next", "16.3.8")
    old = lock({"next": entry("next", "16.3.7")}, {"next": "16.3.7"})
    base = c.commit({**MANIFESTS, "frontend/package.json": front("16.3.7"), "package-lock.json": old})
    new = lock({"next": entry("next", "16.3.8")}, {"next": "^16.3.8"})
    head = c.commit({"frontend/package.json": front("^16.3.8"), "package-lock.json": new})
    c.expect(
        "npm_lock.py",
        ["--base", base, "--head", head],
        PROBLEM,
        r"^PROBLEM frontend/package\.json dependencies\.next: '\^16\.3\.8' is not a version",
    )


@row("npm: an entry moved within the tree with a tampered integrity")
def _(c: Case) -> None:
    view(c, "x", "1.0.0")
    args = npm_case(
        c,
        {"frontend/node_modules/x": entry("x", "1.0.0")},
        {"x": entry("x", "1.0.0", integrity="sha512-bad")},
    )
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM x 1\.0\.0: integrity differs from the registry's")


@row("npm: a field added to the lock's workspace entry")
def _(c: Case) -> None:
    base = c.commit({**MANIFESTS, "package-lock.json": lock({})})
    text = lock({}).replace('"version": "0.1.0",', '"version": "0.1.0", "bin": {"x": "evil.js"},')
    head = c.commit({"package-lock.json": text})
    c.expect(
        "npm_lock.py",
        ["--base", base, "--head", head],
        PROBLEM,
        r'^PROBLEM package-lock\.json packages\["frontend"\]: changed outside its dependency lists',
    )


@row("npm: a version the registry gives no publish time for")
def _(c: Case) -> None:
    args = npm_bump(c)
    del c.npm["next@16.3.8"]["time"]["16.3.8"]
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM .*the registry gives no publish time for 16\.3\.8")


@row("npm: a dependency added to the root manifest")
def _(c: Case) -> None:
    base = c.commit({**MANIFESTS, "package-lock.json": lock({})})
    head = c.commit(
        {
            "package.json": json.dumps(
                {"name": "root", "workspaces": ["frontend"], "devDependencies": {"prettier": "3.0.0"}}
            )
        }
    )
    c.expect(
        "npm_lock.py",
        ["--base", base, "--head", head],
        PROBLEM,
        r"^PROBLEM package\.json devDependencies: a dependency was added",
    )


@row("npm: a manifest script changed")
def _(c: Case) -> None:
    args = npm_bump(c)
    c.commit(
        {
            "frontend/package.json": json.dumps(
                {"name": "frontend", "scripts": {"test": "curl x | sh"}, "dependencies": {"next": "16.3.8"}}
            )
        }
    )
    args[3] = c.git("rev-parse", "HEAD")
    c.expect(
        "npm_lock.py", args, PROBLEM, r"^PROBLEM frontend/package\.json: changed outside its dependency lists"
    )


@row("npm: a manifest pin moved for a package the lock didn't move")
def _(c: Case) -> None:
    view(c, "x", "1.0.0")
    base = c.commit({**MANIFESTS, "package-lock.json": lock({"next": entry("next", "16.3.8")})})
    head = c.commit(
        {
            "frontend/package.json": front("16.3.9"),
            "package-lock.json": lock({"next": entry("next", "16.3.8")}, {"next": "16.3.9"}),
        }
    )
    c.expect(
        "npm_lock.py",
        ["--base", base, "--head", head],
        PROBLEM,
        r"^PROBLEM frontend/package\.json dependencies\.next: .*didn't move next",
    )


@row("npm: a lock field outside packages changes")
def _(c: Case) -> None:
    base = c.commit({**MANIFESTS, "package-lock.json": lock({})})
    head = c.commit({"package-lock.json": lock({}).replace('"lockfileVersion": 3', '"lockfileVersion": 2')})
    c.expect(
        "npm_lock.py",
        ["--base", base, "--head", head],
        PROBLEM,
        r"^PROBLEM package-lock\.json: `lockfileVersion` changed",
    )


@row("npm: a version younger than the cooldown")
def _(c: Case) -> None:
    args = npm_bump(c)
    view(c, "next", "16.3.8", released=NOW)
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM .*published 0\.\d days ago \(under 7")


@row("npm: resolved on the registry but another tarball")
def _(c: Case) -> None:
    args = npm_bump(c, resolved=f"{REG}next/-/next-16.3.6.tgz")
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM .*resolved differs from the registry's tarball URL")


@row("npm: same version, another resolved on the registry")
def _(c: Case) -> None:
    view(c, "x", "1.0.0")
    args = npm_case(
        c, {"x": entry("x", "1.0.0")}, {"x": entry("x", "1.0.0", resolved=f"{REG}x/-/x-0.9.0.tgz")}
    )
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM x 1\.0\.0: same version, different resolved")


@row("npm: a field other than libc dropped from an unchanged entry")
def _(c: Case) -> None:
    view(c, "x", "1.0.0")
    args = npm_case(c, {"x": entry("x", "1.0.0", engines={"node": ">=18"})}, {"x": entry("x", "1.0.0")})
    c.expect("npm_lock.py", args, PROBLEM, r"^PROBLEM x 1\.0\.0: field\(s\) dropped: engines")


@row("npm: an install script both versions have passes")
def _(c: Case) -> None:
    view(c, "sharp", "0.35.4", scripts={"install": "node install.js"})
    view(c, "sharp", "0.35.5", scripts={"install": "node install.js"})
    old = {"sharp": entry("sharp", "0.35.4", hasInstallScript=True)}
    new = {"sharp": entry("sharp", "0.35.5", hasInstallScript=True)}
    c.expect("npm_lock.py", npm_case(c, old, new), OK, r"^package-lock\.json: 0 problems")


@row("npm: an entry moved within the tree is checked, not called new")
def _(c: Case) -> None:
    view(c, "x", "1.0.0")
    args = npm_case(c, {"frontend/node_modules/x": entry("x", "1.0.0")}, {"x": entry("x", "1.0.0")})
    c.expect(
        "npm_lock.py",
        args,
        OK,
        r"^ok +node_modules/x: x moved within the tree \(from frontend/node_modules/x\)",
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
        {"if": {"Authorization": "Bearer T", "Accept": INDEX}, "status": status, "proxy": True,
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


@row("docker: a Docker Hub image says it has no GitHub attestation to verify")
def _(c: Case) -> None:
    c.expect(
        "docker_digest.py", node_case(c), OK, r"^ok .*registry-1\.docker\.io publishes no GitHub attestations"
    )


@row("docker: a COPY --from image pin is checked like a FROM")
def _(c: Case) -> None:
    new = digest("uv-new")
    c.curl["https://ghcr.io/v2/astral-sh/uv/manifests/0.12.24"] = [
        {
            "if": {"Accept": INDEX},
            "status": 200,
            "headers": {"docker-content-digest": new, "content-type": INDEX},
        }
    ]
    c.gh[f"attestation oci://ghcr.io/astral-sh/uv@{new} astral-sh"] = 0
    text = (
        "FROM python:3.12.15-slim-bookworm@{}\nCOPY --from=ghcr.io/astral-sh/uv:{}@{} /uv /usr/local/bin/uv\n"
    )
    py = digest("py")
    base = c.commit(
        {
            "deploy/api.Dockerfile": text.format(py, "0.12.23", digest("uv-old")),
            ".python-version": "3.12.15\n",
        }
    )
    head = c.commit({"deploy/api.Dockerfile": text.format(py, "0.12.24", new)})
    c.expect(
        "docker_digest.py", ["--base", base, "--head", head], OK, r"^ok .*uv:0\.12\.24.*attestation verified"
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


@row("docker: a new Python patch is left for the owner")
def _(c: Case) -> None:
    args = python_case(c, "3.12.16-slim-bookworm", "3.12.16\n")
    c.expect("docker_digest.py", args, PROBLEM, r"^PROBLEM .*a new Python patch from 3\.12\.15")


@row("docker: a new digest for the same Python tag passes")
def _(c: Case) -> None:
    args = python_case(c, "3.12.15-slim-bookworm", "3.12.15\n")
    c.expect("docker_digest.py", args, OK, r"^docker pins: 0 problems")


@row("docker: a fully qualified docker.io image resolves on Docker Hub")
def _(c: Case) -> None:
    new = digest("node-new")
    registry(c, "registry-1.docker.io", "library/node", "22-bookworm-slim", new)
    args = docker_case(
        c,
        f"docker.io/library/node:22-bookworm-slim@{digest('n')}",
        f"docker.io/library/node:22-bookworm-slim@{new}",
    )
    c.expect("docker_digest.py", args, OK, r"^docker pins: 0 problems")


@row("docker: a line other than a pin changes")
def _(c: Case) -> None:
    new = digest("node-new")
    registry(c, "registry-1.docker.io", "library/node", "22-bookworm-slim", new)
    base = c.commit({"deploy/web.Dockerfile": f"FROM node:22-bookworm-slim@{digest('n')}\n"})
    head = c.commit({"deploy/web.Dockerfile": f"FROM node:22-bookworm-slim@{new}\nRUN curl x | sh\n"})
    c.expect(
        "docker_digest.py",
        ["--base", base, "--head", head],
        PROBLEM,
        r"^PROBLEM deploy/web\.Dockerfile: changed outside its image pins",
    )


@row("docker: a challenge that isn't Bearer is an error")
def _(c: Case) -> None:
    args = node_case(c)
    c.curl["https://registry-1.docker.io/v2/library/node/manifests/22-bookworm-slim"][-1]["headers"][
        "www-authenticate"
    ] = "Basic realm=x"
    c.expect("docker_digest.py", args, ERROR, r"^ERROR .*unexpected auth challenge")


@row("docker: a Python minor is hand-only")
def _(c: Case) -> None:
    args = python_case(c, "3.13.0-slim-bookworm", "3.13.0\n")
    c.expect("docker_digest.py", args, PROBLEM, r"^PROBLEM .*a new Python minor")


# --- GitHub Actions ------------------------------------------------------------------------------------


def sha(*parts: str) -> str:
    return h(*parts)[:40]


def wf(*uses: str) -> str:
    return "jobs:\n  j:\n    steps:\n" + "".join(f"      - uses: {u}\n" for u in uses)


def tag_ref(c: Case, repo: str, tag: str, commit: str) -> None:
    c.gh[f"api repos/{repo}/git/ref/tags/{tag}"] = {"object": {"type": "commit", "sha": commit}}


def actions_case(c: Case, old: str, new: str) -> list[str]:
    base = c.commit({".github/workflows/lint.yml": wf(old)})
    head = c.commit({".github/workflows/lint.yml": wf(new)})
    return ["--base", base, "--head", head]


@row("actions: a pin whose tag is that commit passes")
def _(c: Case) -> None:
    tag_ref(c, "actions/checkout", "v7.0.2", sha("b"))
    args = actions_case(c, f"actions/checkout@{sha('a')} # v7.0.1", f"actions/checkout@{sha('b')} # v7.0.2")
    c.expect("actions_pins.py", args, OK, r"^ok .*tag v7\.0\.2 is the pinned commit")


@row("actions: an annotated tag is peeled to its commit")
def _(c: Case) -> None:
    c.gh["api repos/actions/checkout/git/ref/tags/v7.0.2"] = {"object": {"type": "tag", "sha": sha("t")}}
    c.gh[f"api repos/actions/checkout/git/tags/{sha('t')}"] = {"object": {"type": "commit", "sha": sha("b")}}
    args = actions_case(c, f"actions/checkout@{sha('a')} # v7.0.1", f"actions/checkout@{sha('b')} # v7.0.2")
    c.expect("actions_pins.py", args, OK, r"^ok .*tag v7\.0\.2 is the pinned commit")


@row("actions: a name that is only a branch, not a tag, is an error")
def _(c: Case) -> None:
    c.gh["api repos/actions/checkout/commits/v7.0.2"] = {"sha": sha("b")}
    args = actions_case(c, f"actions/checkout@{sha('a')} # v7.0.1", f"actions/checkout@{sha('b')} # v7.0.2")
    c.expect("actions_pins.py", args, ERROR, r"^ERROR .*git/ref/tags/v7\.0\.2 exited 1")


@row("actions: a flow-style uses that isn't pinned")
def _(c: Case) -> None:
    base = c.commit({".github/workflows/lint.yml": wf(f"actions/checkout@{sha('a')} # v7.0.1")})
    head = c.commit({".github/workflows/lint.yml": "jobs:\n  j:\n    steps:\n      - {uses: evil/x@v1}\n"})
    c.expect(
        "actions_pins.py",
        ["--base", base, "--head", head],
        PROBLEM,
        r"^PROBLEM .*`uses: evil/x@v1` is not pinned",
    )


@row("actions: a composite action's pins are checked")
def _(c: Case) -> None:
    tag_ref(c, "actions/checkout", "v7.0.2", sha("b"))
    path = ".github/actions/setup/action.yml"
    steps = "runs:\n  using: composite\n  steps:\n    - uses: actions/checkout@{} # {}\n"
    base = c.commit({path: steps.format(sha("a"), "v7.0.1")})
    head = c.commit({path: steps.format(sha("b"), "v7.0.2")})
    c.expect(
        "actions_pins.py", ["--base", base, "--head", head], OK, r"^ok .*tag v7\.0\.2 is the pinned commit"
    )


@row("actions: a run line changes beside the pin")
def _(c: Case) -> None:
    tag_ref(c, "actions/checkout", "v7.0.2", sha("b"))
    base = c.commit({".github/workflows/lint.yml": wf(f"actions/checkout@{sha('a')} # v7.0.1")})
    head = c.commit(
        {
            ".github/workflows/lint.yml": wf(f"actions/checkout@{sha('b')} # v7.0.2")
            + "      - run: curl x | sh\n"
        }
    )
    c.expect(
        "actions_pins.py",
        ["--base", base, "--head", head],
        PROBLEM,
        r"^PROBLEM .*lint\.yml: changed outside its action pins",
    )


@row("actions: a flow-style with: changed on the pinned line")
def _(c: Case) -> None:
    tag_ref(c, "actions/checkout", "v7.0.2", sha("b"))
    flow = "jobs:\n  j:\n    steps:\n      - {{uses: actions/checkout@{}, with: {{x: {}}}}}\n"
    base = c.commit({".github/workflows/lint.yml": flow.format(sha("a"), 1)})
    head = c.commit({".github/workflows/lint.yml": flow.format(sha("b"), 2)})
    c.expect(
        "actions_pins.py",
        ["--base", base, "--head", head],
        PROBLEM,
        r"^PROBLEM .*changed outside its action pins",
    )


@row("actions: one used action swapped for another")
def _(c: Case) -> None:
    tag_ref(c, "actions/setup-node", "v7.0.1", sha("b"))
    old = wf(f"actions/checkout@{sha('a')} # v7.0.1", f"actions/setup-node@{sha('c')} # v7.0.0")
    new = wf(f"actions/setup-node@{sha('b')} # v7.0.1", f"actions/setup-node@{sha('c')} # v7.0.0")
    base = c.commit({".github/workflows/lint.yml": old})
    head = c.commit({".github/workflows/lint.yml": new})
    c.expect(
        "actions_pins.py",
        ["--base", base, "--head", head],
        PROBLEM,
        r"^PROBLEM .*changed outside its action pins",
    )


@row("actions: no earlier tag to compare the major with")
def _(c: Case) -> None:
    tag_ref(c, "actions/checkout", "v8.0.0", sha("b"))
    args = actions_case(c, f"actions/checkout@{sha('a')}", f"actions/checkout@{sha('b')} # v8.0.0")
    c.expect("actions_pins.py", args, PROBLEM, r"^PROBLEM .*no earlier `# <tag>` to compare the major with")


@row("actions: a tag that is another commit")
def _(c: Case) -> None:
    tag_ref(c, "actions/checkout", "v7.0.2", sha("other"))
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
    tag_ref(c, "actions/checkout", "v8.0.0", sha("b"))
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


@row("restore_libc: repairs every entry, not just the first")
def _(c: Case) -> None:
    keys = ["@img/sharp-linux-x64", "@img/sharp-linux-arm64"]
    base = c.commit({"package-lock.json": lock({k: {"version": "1", "libc": ["glibc"]} for k in keys})})
    c.commit({"package-lock.json": lock({k: {"version": "2"} for k in keys})})
    c.expect("restore_libc.py", ["--base", base], OK, r"^2 entries repaired")
    got = json.loads((c.repo / "package-lock.json").read_text())["packages"]
    assert all(got[f"node_modules/{k}"]["libc"] == ["glibc"] for k in keys), got


@row("restore_libc: a lock that lost nothing is left byte-for-byte")
def _(c: Case) -> None:
    text = lock({"x": entry("x", "1.0.0")})
    base = c.commit({"package-lock.json": text})
    c.expect("restore_libc.py", ["--base", base], OK, r"^0 entries repaired")
    assert (c.repo / "package-lock.json").read_text() == text


# --- prs.py --------------------------------------------------------------------------------------------


BOT = {
    "GIT_AUTHOR_NAME": "dependabot[bot]", "GIT_AUTHOR_EMAIL": "49699333+dependabot[bot]@users.noreply.github.com",
    "GIT_COMMITTER_NAME": "GitHub", "GIT_COMMITTER_EMAIL": "noreply@github.com",
}  # fmt: skip


def check_case(c: Case, head: str, files: dict[str, str | None], *, who: dict[str, str] | None = None,
               title: str = "deps: bump x", verified: bool = True, gh_head: str | None = None,
               **pr: Any) -> list[str]:  # fmt: skip
    base = c.commit({"uv.lock": "a\n", "README.md": "r\n"})
    c.git("update-ref", "refs/remotes/origin/dev", base)
    sha_ = c.commit(files, who=BOT if who is None else who)
    c.gh["pr view 7"] = {"state": "OPEN", "author": {"login": "app/dependabot"}, "baseRefName": "dev",
                         "headRefName": head, "headRefOid": gh_head or sha_, "title": title, **pr}  # fmt: skip
    c.gh[f"api repos/uw-share-lab/openproceedings/commits/{sha_}"] = {
        "commit": {"verification": {"verified": verified, "reason": "valid" if verified else "unsigned"}}
    }
    return ["check", "7", "--head", sha_]


@row("prs check: a Dependabot-only uv PR passes")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/uv/g", {"uv.lock": "b\n", "backend/pyproject.toml": "x\n"})
    c.expect("prs.py", args, OK, r"^ok +uv: 2 file\(s\) and 1 commit\(s\), all Dependabot's")


@row("prs check: a composite action's action.yml is an actions file")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/github_actions/g", {".github/actions/setup/action.yml": "x\n"})
    c.expect("prs.py", args, OK, r"^ok +github_actions: 1 file")


@row("prs check: a uv PR touching the Makefile")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/uv/g", {"uv.lock": "b\n", "Makefile": "x\n"})
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM Makefile is outside what a uv update touches")


@row("prs check: a file named like an allowed one is matched whole")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/uv/g", {"uv.lock.orig": "x\n"})
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM uv\.lock\.orig is outside")


@row("prs check: an actions PR touching dependabot.yml")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/github_actions/g", {".github/dependabot.yml": "x\n"})
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM \.github/dependabot\.yml is outside")


@row("prs check: a docker PR touching a deploy script")
def _(c: Case) -> None:
    args = check_case(
        c, "dependabot/docker/deploy/g", {"deploy/api.Dockerfile": "x\n", "deploy/smoke-test.sh": "x\n"}
    )
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM deploy/smoke-test\.sh is outside")


@row("prs check: an npm PR adding an .npmrc")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/npm_and_yarn/g", {"package-lock.json": "x\n", ".npmrc": "x\n"})
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM \.npmrc is outside")


@row("prs check: an ecosystem the routine doesn't review")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/cargo/g", {"Cargo.lock": "x\n"})
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM ecosystem 'cargo'")


@row("prs check: a commit someone else pushed")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/uv/g", {"uv.lock": "b\n"}, who={})
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM commit .* is by t <t@example\.org>.*not Dependabot's alone")


@row("prs check: a commit GitHub doesn't verify")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/uv/g", {"uv.lock": "b\n"}, verified=False)
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM commit .*doesn't verify its signature \(unsigned\)")


@row("prs check: the head moved on GitHub since the fetch")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/uv/g", {"uv.lock": "b\n"}, gh_head="f" * 40)
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM GitHub's head is ffffffffffff, not the fetched")


@row("prs check: a closed PR")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/uv/g", {"uv.lock": "b\n"}, state="CLOSED")
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM the PR is CLOSED into dev")


@row("prs check: a PR into main")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/uv/g", {"uv.lock": "b\n"}, baseRefName="main")
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM the PR is OPEN into main")


@row("prs check: a PR someone else opened with Dependabot's commits")
def _(c: Case) -> None:
    args = check_case(c, "dependabot/uv/g", {"uv.lock": "b\n"}, author={"login": "mallory"})
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM the PR was opened by mallory")


@row("prs check: a title naming tantivy")
def _(c: Case) -> None:
    args = check_case(
        c, "dependabot/uv/g", {"uv.lock": "b\n"}, title="deps: bump tantivy from 0.26.2 to 0.26.3"
    )
    c.expect("prs.py", args, PROBLEM, r"^PROBLEM the title names a hand-only dependency")


@row("prs list: prints each PR with its ecosystem")
def _(c: Case) -> None:
    c.gh["pr list"] = [{"number": 3, "title": "deps: bump x", "headRefName": "dependabot/uv/g", "url": "u"}]
    c.expect("prs.py", ["list"], OK, r"^#3 \[uv\] dependabot/uv/g$")


@row("prs list: a PR of the wrong shape is an error, not a crash")
def _(c: Case) -> None:
    c.gh["pr list"] = [{"number": 1, "title": "t"}]
    c.expect("prs.py", ["list"], ERROR, r"^ERROR +KeyError")


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


@row("prs watch: one PR merged while another still waits is not a drop")
def _(c: Case) -> None:
    c.gh["graphql"] = [
        gql(("OPEN", QUEUED, None), ("OPEN", QUEUED, None)),
        gql(("MERGED", None, None), ("OPEN", QUEUED, None)),
        gql(("MERGED", None, None), ("OPEN", QUEUED, None)),
        gql(("MERGED", None, None), ("MERGED", None, None)),
    ]
    c.expect("prs.py", ["watch", "1", "2", "--interval", "0"], 0, r"^all merged")


@row("prs watch: gh failing is an error")
def _(c: Case) -> None:
    c.expect("prs.py", ["watch", "1", "--interval", "0"], ERROR, r"^ERROR .*gh api graphql")


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
