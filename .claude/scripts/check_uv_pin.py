#!/usr/bin/env python3
"""CI check (TASK-252): every `astral-sh/setup-uv` step in CI installs the uv the api image pins, so CI, local
work and the image run one reviewed uv, under the same 7-day hold (decision-048), instead of setup-uv's newest.

The pin is the tag of `deploy/api.Dockerfile`'s one `FROM ghcr.io/astral-sh/uv:<X.Y.Z>@sha256:…` stage. Every
step under `.github/` (workflows and composite actions) whose `uses:` names `astral-sh/setup-uv@` must have a
`with:` whose `version:` is exactly that release (input names read case-blind, as the runner reads them). It fails
closed: no uv stage, two of them, or a tag that isn't an exact `X.Y.Z`; no setup-uv step at all (so moving the
workflows can't switch the check off); a step with no `version`, a `version-file` or `manifest-file` (a manifest
can point a release at any download), or a `with:` or `version:` it can't read (anchors, aliases, multi-line or
block scalars, an expression, a `#` with no space before it); a step it can't place (a bare `-` line, a flow-style
step). It also refuses the other ways to get uv it knows, anywhere in a workflow or composite action: `pip`,
`pip3` or `pipx` installing or running uv, a package manager's `install … uv` (brew, conda, mamba, cargo, apt and
the like), the astral.sh installer, any `astral-sh/uv` path (a release download, a `docker://` step, a `container:`
or `services:` image, `docker run`), and `uv self update`; and in a workflow job, a `uv` or `uvx` word outside a
`name:` and a trailing comment before the job's first setup-uv step (a runner image's own uv), and a workflow with
no `jobs:` key it can read. Not seen: a `uv` that a called script or `make` runs, an install it has no pattern for,
and a setup-uv step whose `if:` skips it while a later step still runs uv. Steps are read by indentation, as YAML
block sequences are; flow mappings (`with: { … }`) are read on their own line only. Exits 1 listing every
problem."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = "deploy/api.Dockerfile"
UV_FROM = re.compile(r"^FROM\s+(?:--\S+\s+)*ghcr\.io/astral-sh/uv:([^@\s]*)@sha256:", re.IGNORECASE)
RELEASE = re.compile(r"^\d+\.\d+\.\d+$")
# GitHub reads an action ref case-blind
USES = re.compile(r"""^\s*(-\s+)?uses:\s*["']?astral-sh/setup-uv@""", re.IGNORECASE)
MENTION = re.compile(r"astral-sh/setup-uv@", re.IGNORECASE)
# a YAML comment starts only at a `#` after whitespace, so `0.13.0#x` is one (unreadable) value
SCALAR = re.compile(r"""^(?:"([^"\\$]*)"|'([^'$]*)'|([^\s"'#&*!|>{}\[\],$][^\s,{}\[\]$]*))(?:\s+#.*)?\s*$""")
# each install's match stops at a shell separator, so `pip install x && uv sync` is not an install of uv;
# `astral-sh/uv` can't match `astral-sh/setup-uv`
OTHER_UV = re.compile(
    r"\bpip[0-9.]*x?\s+(?:install|run)\b[^;&|#]*\buvx?\b"
    r"|\b(?:brew|conda|mamba|micromamba|cargo|apt|apt-get|snap|npm)\s+install\b[^;&|#]*\buv\b"
    r"|astral\.sh/uv|astral-sh/uv(?![\w-])|\buv\s+self\s+update",
    re.IGNORECASE,
)
NAME = re.compile(r"^\s*(-\s+)?name\s*:")  # a step or job label, not a command
UV_WORD = re.compile(r"(?:^|[\s;&|(`'\"/])uvx?(?=[\s;&|)`'\"]|$)")
JOBS = re.compile(r"""^["']?jobs["']?\s*:\s*(#.*)?$""")
COMMENT = re.compile(r"\s#.*$")


def pinned() -> tuple[str | None, list[str]]:
    """The api image's uv release, or the problems that stop it being read."""
    path = ROOT / DOCKERFILE
    if not path.is_file():
        return None, [f"{DOCKERFILE} is missing"]
    tags = [
        m.group(1) for line in path.read_text(encoding="utf-8-sig").splitlines() if (m := UV_FROM.match(line))
    ]
    if len(tags) != 1:
        return None, [f"{DOCKERFILE}: {len(tags)} ghcr.io/astral-sh/uv stages, want exactly one"]
    if not RELEASE.match(tags[0]):
        return None, [f"{DOCKERFILE}: the uv tag '{tags[0]}' is not an exact X.Y.Z release"]
    return tags[0], []


def indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def key_col(line: str) -> int:
    """The column of a line's mapping key, after any `- ` that opens a sequence item."""
    return len(line) - len(re.sub(r"^\s*(-\s+)?", "", line))


def ignorable(line: str) -> bool:
    return not line.strip() or line.lstrip().startswith("#")


def step_of(lines: list[str], at: int) -> tuple[list[tuple[int, str]], int] | None:
    """The numbered lines of the step (sequence item) whose `uses:` is line `at`, and its keys' column."""
    col = key_col(lines[at])
    start = at
    if not lines[at].lstrip().startswith("-"):  # `uses:` under a `- name:` (or other key) above it
        start = next(
            (j for j in range(at - 1, -1, -1) if not ignorable(lines[j]) and indent(lines[j]) < col), -1
        )
        if start < 0 or not lines[start].lstrip().startswith("-") or key_col(lines[start]) != col:
            return None
    dash = indent(lines[start])
    end = start + 1
    while end < len(lines) and (ignorable(lines[end]) or indent(lines[end]) > dash):
        end += 1
    return [(n + 1, lines[n]) for n in range(start, end)], col


def version_of(step: list[tuple[int, str]], col: int) -> tuple[str | None, str | None]:
    """The step's `with.version`, or why it can't be read."""
    keys = [(n, line) for n, line in step if re.match(r"^\s*(-\s+)?with\s*:", line) and key_col(line) == col]
    if not keys:
        return None, "has no with: version"
    if len(keys) > 1:
        return None, "has two with: keys"
    n, line = keys[0]
    after = line.split(":", 1)[1]
    if after and not after[0].isspace():
        return None, f"line {n}: can't read this with:"
    rest = after.strip()
    if rest.startswith("{"):
        if not re.fullmatch(r"\{[^{}\[\]&*!|>]*\}(?:\s+#.*)?\s*", rest):
            return None, f"line {n}: can't read this with:"
        body = rest[1 : rest.index("}")]
        entries = [e.strip() for e in body.split(",") if e.strip()]
        pairs = [tuple(p.strip() for p in e.split(":", 1)) for e in entries if ":" in e]
        if len(pairs) != len(entries):
            return None, f"line {n}: can't read this with:"
    elif rest and not rest.startswith("#"):
        return None, f"line {n}: can't read this with:"
    else:
        block: list[tuple[int, str]] = []
        for m, ln in [(m, ln) for m, ln in step if m > n]:
            if ignorable(ln):
                continue
            if indent(ln) <= col:
                break
            block.append((m, ln))
        if not block:
            return None, f"line {n}: with: is empty"
        entry_col = indent(block[0][1])
        pairs = []
        for m, ln in block:
            if indent(ln) != entry_col or not re.match(r"^\s*[A-Za-z0-9_-]+\s*:", ln):
                return None, f"line {m}: can't read this with: entry"
            pairs.append(tuple(p.strip() for p in ln.split(":", 1)))
    found: dict[str, str] = {}
    for key, value in pairs:
        key = key.lower()
        if key in found:
            return None, f"has two '{key}' inputs"
        found[key] = value
    for other in ("version-file", "manifest-file"):
        if other in found:
            return None, f"uses {other}"
    if "version" not in found:
        return None, "has no with: version"
    if not (m := SCALAR.match(found["version"])):
        return None, f"can't read version: {found['version']}"
    return next(g for g in m.groups() if g is not None), None


def uv_before_setup(lines: list[str]) -> list[tuple[str, int]] | None:
    """Each job (and the line) that names `uv` or `uvx` before its first setup-uv step: a runner's own uv. None
    when there is no `jobs:` key to read."""
    try:
        top = next(i for i, ln in enumerate(lines) if JOBS.match(ln))
    except StopIteration:
        return None
    body = [i for i in range(top + 1, len(lines)) if not ignorable(lines[i])]
    end = next((i for i in body if indent(lines[i]) == 0), len(lines))
    body = [i for i in body if i < end]
    if not body:
        return []
    col = indent(lines[body[0]])
    starts = [i for i in body if indent(lines[i]) == col]
    out: list[tuple[str, int]] = []
    for k, start in enumerate(starts):
        stop = starts[k + 1] if k + 1 < len(starts) else end
        for i in range(start + 1, stop):
            if USES.match(lines[i]):
                break
            if (
                not ignorable(lines[i])
                and not NAME.match(lines[i])
                and UV_WORD.search(COMMENT.sub("", lines[i]))
            ):
                out.append((lines[start].strip().rstrip(":"), i + 1))
                break
    return out


def files() -> list[Path]:
    gh = ROOT / ".github"
    workflows = [p for p in (gh / "workflows").glob("*") if p.suffix in (".yml", ".yaml")]
    actions = [p for p in gh.rglob("*") if p.name in ("action.yml", "action.yaml")]
    return sorted({p for p in workflows + actions if p.is_file()})


want, bad = pinned()
steps = 0
for path in files():
    name = path.relative_to(ROOT).as_posix()
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for i, line in enumerate(lines):
        if not ignorable(line) and OTHER_UV.search(line):
            bad.append(f"{name}:{i + 1}: installs uv another way than a pinned setup-uv step")
        if not MENTION.search(line):
            continue
        if not USES.match(line):  # a flow-style step, a comment: nothing this check can read as a pinned step
            bad.append(f"{name}:{i + 1}: names setup-uv outside a block-style uses: line")
            continue
        steps += 1
        if not (found := step_of(lines, i)):
            bad.append(f"{name}:{i + 1}: can't find the step this setup-uv uses: belongs to")
            continue
        got, why = version_of(*found)
        if why:
            bad.append(f"{name}:{i + 1}: the setup-uv step {why}")
        elif want is not None and got != want:
            bad.append(f"{name}:{i + 1}: setup-uv installs uv {got}, {DOCKERFILE} pins {want}")
    if path.parent.name == "workflows":
        if (early := uv_before_setup(lines)) is None:
            bad.append(f"{name}: no jobs: key this check can read")
        else:
            bad += [f"{name}:{n}: job '{job}' runs uv before any setup-uv step" for job, n in early]
if steps == 0:
    bad.append("no astral-sh/setup-uv step under .github/")
for msg in bad:
    print(f"uv pin: {msg} (spec 08 §CI, TASK-252)", file=sys.stderr)
print(f"uv pin: {steps} setup-uv step(s), uv {want or '?'} in {DOCKERFILE}, {len(bad)} problem(s)")
sys.exit(1 if bad else 0)
