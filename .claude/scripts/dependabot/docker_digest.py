#!/usr/bin/env python3
"""Check the base-image pins a Dependabot `docker` PR moved (/dependabot-review step 2; TASK-211).

    python3 .claude/scripts/dependabot/docker_digest.py [--base REF] [--head REF]

Reads every `name:tag@sha256:<digest>` pin in the files under `deploy/` that changed between `base` (default:
the merge base of origin/dev and HEAD) and `head` (default HEAD). For each pin that is new at `head`, it asks
the image's registry anonymously (the token its 401 challenge names), with a HEAD request for
`/v2/<repository>/manifests/<tag>` and the OCI-index `Accept` header, and requires `Docker-Content-Digest` to
equal the pinned digest and the answer to be an index (a multi-arch pin, spec 08 §Deploy). An image on
ghcr.io must also pass `gh attestation verify oci://<image>@<digest> --owner <its owner>`. When the
`python` image's tag moves, `.python-version` at `head` must name the same patch release (TASK-208).

A PROBLEM, the PR stays open: a digest that doesn't resolve or differs, a non-index answer, a failed
attestation, an image that wasn't pinned before, a semver-major tag change, or a `python` minor change
(hand-only, spec 08 §Monorepo layout). A `.python-version` that doesn't match is a FIX.
"""

from __future__ import annotations

import argparse
import re
import urllib.parse
from dataclasses import dataclass

from _common import (
    Report,
    ToolError,
    changed_files,
    git_show,
    http,
    http_json,
    is_major,
    is_minor_or_more,
    main_guard,
    resolve_refs,
    run,
    version_tuple,
)

PIN = re.compile(
    r"(?<![\w./:@-])([a-z0-9][a-z0-9._-]*(?::[0-9]+)?(?:/[a-z0-9._-]+)*):([A-Za-z0-9_][A-Za-z0-9_.-]{0,127})"
    r"@(sha256:[0-9a-f]{64})\b"
)
INDEX_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
)
CHALLENGE = re.compile(r'(\w+)="([^"]*)"')


@dataclass(frozen=True)
class Pin:
    image: str
    tag: str
    digest: str

    def __str__(self) -> str:
        return f"{self.image}:{self.tag}@{self.digest[:19]}…"


def pins(text: str | None) -> set[Pin]:
    return {Pin(*m.groups()) for m in PIN.finditer(text or "")}


def registry(image: str) -> tuple[str, str]:
    """(registry host, repository): `node` → (registry-1.docker.io, library/node)."""
    first, _, rest = image.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        return first, rest
    return "registry-1.docker.io", image if rest else f"library/{image}"


def resolve(image: str, tag: str) -> tuple[str, str]:
    """(digest, content type) the registry gives for `image:tag`, asked anonymously for an index."""
    host, repo = registry(image)
    url = f"https://{host}/v2/{repo}/manifests/{urllib.parse.quote(tag)}"
    headers = {"Accept": ", ".join(INDEX_TYPES)}
    r = http(url, headers, head=True)
    if r.status == 401:
        challenge = r.headers.get("www-authenticate", "")
        if not challenge.lower().startswith("bearer "):
            raise ToolError(f"{host}: unexpected auth challenge {challenge!r}")
        params = dict(CHALLENGE.findall(challenge))
        query = urllib.parse.urlencode(
            {"service": params.get("service", host), "scope": f"repository:{repo}:pull"}
        )
        token_answer = http_json(f"{params.get('realm', '')}?{query}")
        token = token_answer.get("token") or token_answer.get("access_token")
        if not token:
            raise ToolError(f"{host}: the token endpoint returned no token")
        r = http(url, {**headers, "Authorization": f"Bearer {token}"}, head=True)
    if r.status != 200:
        raise ToolError(f"HEAD {url}: HTTP {r.status}")
    return r.headers.get("docker-content-digest", ""), r.headers.get("content-type", "").split(";")[0]


def is_python(image: str) -> bool:
    return registry(image) == ("registry-1.docker.io", "library/python")


def check_pin(rep: Report, pin: Pin, before: set[Pin], head: str) -> None:
    olds = sorted({p.tag for p in before if p.image == pin.image})
    if not olds:
        rep.problem(f"{pin}: {pin.image} was not pinned before (a new image)")
        return
    old_tag = olds[-1]
    if pin.tag != old_tag and is_major(old_tag, pin.tag):
        rep.problem(f"{pin}: semver-major tag change from {old_tag}")
    if is_python(pin.image) and pin.tag != old_tag and is_minor_or_more(old_tag, pin.tag):
        rep.problem(f"{pin}: a new Python minor from {old_tag} is done by hand (spec 08 §Monorepo layout)")
    if is_python(pin.image):
        want = ".".join(str(n) for n in version_tuple(pin.tag))
        have = (git_show(head, ".python-version") or "").strip()
        if have != want:
            rep.fix(f"{pin}: .python-version is {have!r}; move it to {want!r} with the image (TASK-208)")
    digest, ctype = resolve(pin.image, pin.tag)
    if digest != pin.digest:
        rep.problem(f"{pin}: the registry resolves {pin.tag} to {digest or 'nothing'}, not the pinned digest")
        return
    if ctype not in INDEX_TYPES:
        rep.problem(f"{pin}: the digest is a {ctype or 'manifest of unknown type'}, not a multi-arch index")
        return
    rep.ok(f"{pin}: the registry resolves {pin.tag} to the pinned index digest")
    host, repo = registry(pin.image)
    if host == "ghcr.io":
        owner = repo.split("/", 1)[0]
        r = run(
            ["gh", "attestation", "verify", f"oci://{pin.image}@{pin.digest}", "--owner", owner],
            ok_codes=(0, 1),
        )
        if r.returncode:
            rep.problem(f"{pin}: gh attestation verify --owner {owner} failed: {r.stderr.strip()[:200]}")
        else:
            rep.ok(f"{pin}: GitHub attestation verified for owner {owner}")
    else:
        rep.ok(f"{pin}: {host} publishes no GitHub attestations; the digest check is the check")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    a = ap.parse_args()
    base, head = resolve_refs(a.base, a.head)
    rep = Report("docker pins")
    paths = [p for p in changed_files(base, head) if p.startswith("deploy/")]
    before: set[Pin] = set()
    after: set[Pin] = set()
    for path in paths:
        before |= pins(git_show(base, path))
        after |= pins(git_show(head, path))
    if not after - before:
        rep.ok(f"no new pins in {len(paths)} changed deploy/ file(s)")
    for pin in sorted(after - before, key=str):
        check_pin(rep, pin, before, head)
    rep.finish()


if __name__ == "__main__":
    main_guard(main)
