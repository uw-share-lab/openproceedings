#!/usr/bin/env python3
"""Check the base-image pins a Dependabot `docker` PR moved (/dependabot-review step 2; TASK-211).

    python3 .claude/scripts/dependabot/docker_digest.py [--base REF] [--head REF]

Reads every `name:tag@sha256:<digest>` pin in the files under `deploy/` that changed between `base` (default:
the merge base of origin/dev and HEAD) and `head` (default HEAD). For each pin that is new at `head`, it asks
the image's registry anonymously (the token its 401 challenge names), with a HEAD request for
`/v2/<repository>/manifests/<tag>` and the OCI-index `Accept` header, and requires `Docker-Content-Digest` to
equal the pinned digest and the answer to be an index (a multi-arch pin, spec 08 §Deploy). An image on ghcr.io
must also pass `gh attestation verify oci://<image>@<digest> --owner <its owner>`, be attested by the
publisher that attested the previous pin (source repository and signing workflow, its ref aside), and the
earliest verified (Rekor or timestamp-authority) timestamp of those attestations must be at least
`COOLDOWN_DAYS` old. Dependabot dates a docker tag or digest only on Docker Hub and skips its `cooldown` for
every other registry (dependabot-core's docker update checker), so every ghcr.io PR carries its "Cooldown
could not be applied" notice and `prs.py check` leaves it for the owner; this age is the evidence the owner
decides on, and the hold should Dependabot ever date ghcr.io. Each changed file must differ only in its pins'
`:tag@digest` (the image names and every other line stay the same).

A PROBLEM, the PR stays open: a change outside the pins, a digest that doesn't resolve or differs, a non-index
answer, a failed attestation, a ghcr.io image attested under `COOLDOWN_DAYS` ago (or with no verified
timestamp), or not by the previous pin's publisher (or whose previous pin has no verified attestation), an
image on a registry other than Docker Hub and ghcr.io (nothing dates it: neither Dependabot's cooldown nor an
attestation), an image that wasn't pinned before, a semver-major tag change, a 0.x minor (`0.12.x` → `0.13.0`:
a breaking release while a project is 0.x), or any change of the `python` image's tag (decision-048: a new
Python release changes how the crawlers parse pages, spec 08 §Monorepo layout "Python pin", and the replay
that shows records unchanged needs the owner's `data/`; a new digest for the same tag is fine). An image
reference that lost its digest is not this script's to find: `check_digest_pins.py` (in `make tooling`, which
the command runs and CI's `claude-tooling` check runs) refuses any unpinned image a `deploy/` build pulls.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from dataclasses import dataclass

from _common import (
    COOLDOWN_DAYS,
    Report,
    ToolError,
    age_days,
    changed_files,
    git_show,
    http,
    http_json,
    is_major,
    is_minor_or_more,
    main_guard,
    parse_time,
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
    """(registry host, repository): `node` and `docker.io/library/node` → (registry-1.docker.io, library/node)."""
    first, _, rest = image.partition("/")
    if first in ("docker.io", "index.docker.io") and rest:
        image, (first, _, rest) = rest, rest.partition("/")
    elif rest and ("." in first or ":" in first or first == "localhost"):
        return first, rest
    return "registry-1.docker.io", image if rest else f"library/{image}"


def outside_pins(text: str | None) -> str:
    """The file with each pin's `:tag@digest` blanked: what must stay the same."""
    return PIN.sub(lambda m: f"{m.group(1)}:<pin>", text or "")


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


Publisher = tuple[str, str]  # (source repository URI, build signer workflow URI without its @ref)


def attestations(output: str) -> list[tuple[Publisher, list[str]]]:
    """Each verified attestation in `gh attestation verify --format json`'s output: its publisher and its verified
    (Rekor or timestamp-authority) timestamps."""
    try:
        found = []
        for a in json.loads(output):
            result = a["verificationResult"]
            cert = result["signature"]["certificate"]
            publisher = (str(cert["sourceRepositoryURI"]), str(cert["buildSignerURI"]).split("@", 1)[0])
            stamps = [str(t["timestamp"]) for t in result.get("verifiedTimestamps") or []]
            found.append((publisher, stamps))
    except (ValueError, KeyError, TypeError, AttributeError) as e:  # JSONDecodeError is a ValueError
        raise ToolError("gh attestation verify --format json printed no attestation list") from e
    for _, stamps in found:
        for t in stamps:
            try:
                parse_time(t)
            except ValueError as e:
                raise ToolError(
                    f"gh attestation verify printed a timestamp that isn't ISO 8601: {t[:40]!r}"
                ) from e
    return found


def verify(pin: Pin, owner: str) -> tuple[list[tuple[Publisher, list[str]]] | None, str]:
    """(the pin's verified attestations, or None when verification fails; gh's message)."""
    r = run(
        [
            "gh",
            "attestation",
            "verify",
            f"oci://{pin.image}@{pin.digest}",
            "--owner",
            owner,
            "--format",
            "json",
        ],
        ok_codes=(0, 1),
    )
    if r.returncode:
        return None, r.stderr.strip()[:200]
    return attestations(r.stdout), ""


def check_age(
    rep: Report,
    pin: Pin,
    found: list[tuple[Publisher, list[str]]],
    publishers: set[Publisher],
    why: str = "",
) -> None:
    """The 7-day hold for a ghcr.io image: its age is the earliest verified timestamp of an attestation by the
    previous pin's publisher, so an old attestation from another workflow of the org can't make a new image look
    old."""
    if not publishers:
        rep.problem(
            f"{pin}: the previous pin has no verified attestation, so its publisher can't be compared"
            + (f" (gh: {why})" if why else "")
        )
        return
    ours = [stamps for publisher, stamps in found if publisher in publishers]
    if not ours:
        others = sorted({" ".join(publisher) for publisher, _ in found})
        rep.problem(
            f"{pin}: attested only by {others}, not by the previous pin's publisher (a new publisher)"
        )
        return
    stamps = [t for group in ours for t in group]
    if not stamps:
        rep.problem(f"{pin}: the attestation has no verified timestamp, so nothing dates the image")
    elif (days := age_days(min(stamps, key=parse_time))) < COOLDOWN_DAYS:
        rep.problem(
            f"{pin}: first attested {days:.1f} days ago (under {COOLDOWN_DAYS}; Dependabot's cooldown doesn't"
            " date ghcr.io images; decision-048)"
        )
    else:
        rep.ok(f"{pin}: first attested {days:.1f} days ago, past the {COOLDOWN_DAYS}-day cooldown")


def check_pin(rep: Report, pin: Pin, before: set[Pin]) -> None:
    olds = sorted({p.tag for p in before if p.image == pin.image})
    if not olds:
        rep.problem(f"{pin}: {pin.image} was not pinned before (a new image)")
        return
    old_tag = max(olds, key=version_tuple)
    if pin.tag != old_tag and is_major(old_tag, pin.tag):
        rep.problem(f"{pin}: semver-major tag change from {old_tag}")
    elif version_tuple(old_tag)[:1] == (0,) and is_minor_or_more(old_tag, pin.tag):
        rep.problem(f"{pin}: a 0.x minor from {old_tag} is a breaking release; it is upgraded by hand")
    if is_python(pin.image) and pin.tag != old_tag:
        what = "minor" if is_minor_or_more(old_tag, pin.tag) else "patch"
        rep.problem(
            f"{pin}: a new Python {what} from {old_tag}; the owner merges it after the crawl-cache replay"
            " (spec 08 §Monorepo layout, decision-048)"
        )
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
        found, message = verify(pin, owner)
        if found is None:
            rep.problem(f"{pin}: gh attestation verify --owner {owner} failed: {message}")
            return
        rep.ok(f"{pin}: GitHub attestation verified for owner {owner}")
        publishers: set[Publisher] = set()
        why = ""
        for old in before:
            if old.image == pin.image:
                old_found, old_message = verify(old, owner)
                publishers |= {publisher for publisher, _ in old_found or []}
                why = why or old_message
        check_age(rep, pin, found, publishers, why)
    elif host == "registry-1.docker.io":
        rep.ok(
            f"{pin}: {host} publishes no GitHub attestations; the digest check is the check, and Dependabot's"
            " cooldown dates Docker Hub tags"
        )
    else:
        rep.problem(
            f"{pin}: nothing dates an image on {host} (Dependabot's cooldown skips it and it has no attestation"
            " this script reads); the owner decides"
        )


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
        old_text, new_text = git_show(base, path), git_show(head, path)
        if outside_pins(old_text) != outside_pins(new_text):
            rep.problem(f"{path}: changed outside its image pins")
        before |= pins(old_text)
        after |= pins(new_text)
    if not after - before:
        rep.ok(f"no new pins in {len(paths)} changed deploy/ file(s)")
    for pin in sorted(after - before, key=str):
        check_pin(rep, pin, before)
    rep.finish()


if __name__ == "__main__":
    main_guard(main)
