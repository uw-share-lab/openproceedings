"""Proceedings URLs → native ids (record-schema skill §Native ids), shared by the RIS importer and dedup, and
OpenReview forum URLs → forum ids (dedup's forum link, TASK-105).

The grammar follows scholarmend 0.1.3's miners: any host case, `papers.nips.cc`, `http`, a query string
or fragment (one real URL carries `?utm_source=chatgpt.com`), PMLR's two hosts and its raw GitHub assets.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from openproceedings.ingest.record import FORUM_ID
from openproceedings.ingest.volumes import ICML_PMLR_VOLUMES

_PROCEEDINGS_HOSTS = {
    "proceedings.neurips.cc": "NeurIPS",
    "papers.nips.cc": "NeurIPS",
    # NeurIPS 2021 Datasets and Benchmarks only (its index lists 2021 alone): `-Abstract-round1/2.html`
    "datasets-benchmarks-proceedings.neurips.cc": "NeurIPS",
    "proceedings.iclr.cc": "ICLR",
}
# 2022+: /paper_files/paper/<y>/hash/<h>-Abstract-<Track>.html; up to 2021: /paper/<y>/hash/<h>-Abstract.html;
# the 2021 D&B host's tokens carry a digit (`round1`, `round2`)
_PROCEEDINGS_PATH = re.compile(
    r"(?:/paper_files)?/paper/([0-9]{4})/(?:hash|file)/([0-9a-fA-F]+)-(?:Abstract|Paper)(?:-([A-Za-z0-9_]+))?\.(?:html|pdf)"
)
_PMLR_HOSTS = {"proceedings.mlr.press", "mlr.press"}
_PMLR_PATH = re.compile(r"/v([0-9]+)/([A-Za-z0-9_-]+?)(?:\.html|\.pdf|/.*)?")
_PMLR_GITHUB_PATH = re.compile(r"/mlresearch/v([0-9]+)/[^/]+/assets/([A-Za-z0-9_-]+)/.*")
PREFIX = {"NeurIPS": "nips", "ICLR": "iclr"}


def proceedings(url: str) -> tuple[str, str] | None:
    """(venue, hash) from a NeurIPS or ICLR proceedings URL; the hash may be any length (check it)."""
    parts = proceedings_parts(url)
    return (parts[0], parts[2]) if parts else None


def proceedings_parts(url: str) -> tuple[str, int, str, str | None] | None:
    """(venue, year, hash, track token or None) from a NeurIPS or ICLR proceedings URL: what the page's own
    address says, to check a claim against (`…/paper/2025/hash/<h>-Abstract-Creative_AI_Track.html`)."""
    parsed = urlparse(url)
    venue = _PROCEEDINGS_HOSTS.get(parsed.netloc.lower())
    m = _PROCEEDINGS_PATH.fullmatch(parsed.path)
    return (venue, int(m.group(1)), m.group(2).lower(), m.group(3)) if venue and m else None


def pmlr(url: str) -> tuple[int, str] | None:
    """(volume, key) from a PMLR URL or its raw GitHub asset; any volume (check it against the table)."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host in _PMLR_HOSTS:
        m = _PMLR_PATH.fullmatch(parsed.path)
    elif host == "raw.githubusercontent.com":
        m = _PMLR_GITHUB_PATH.fullmatch(parsed.path)
    else:
        return None
    return (int(m.group(1)), m.group(2)) if m else None


def native(url: str) -> str | None:
    """The proceedings native id a URL names (`nips-`/`iclr-<32 hex>`, `pmlr-v<N>-<key>` for an ICML
    volume), or None."""
    if (p := proceedings(url)) is not None:
        return f"{PREFIX[p[0]]}-{p[1]}" if len(p[1]) == 32 else None
    if (q := pmlr(url)) is not None and q[0] in ICML_PMLR_VOLUMES:
        return f"pmlr-v{q[0]}-{q[1]}"
    return None


def forum_id(url: str) -> str | None:
    """The forum id an OpenReview forum URL names (`https://openreview.net/forum?id=<id>`, any host case, one
    `id` only, a valid forum id), or None. PMLR's index links (v235), OpenReview notes and the RIS importer all
    write `urls.forum` in this form."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != "openreview.net":
        return None
    if parsed.path != "/forum":
        return None
    ids = parse_qs(parsed.query).get("id", [])
    return ids[0] if len(ids) == 1 and FORUM_ID.fullmatch(ids[0]) else None


def iclr_archive_target(url: str) -> tuple[str, str] | None:
    """The stable native id and canonical target of a paper link on an official ICLR archive page.

    Old archive pages link accepted papers to arXiv or the former beta OpenReview host rather than an
    ICLR proceedings path. An OpenReview link keeps its forum id; every other HTTP target gets an
    `iclr-<32 hex>` id from the canonical URL. This is identity evidence only when the claim source is
    `iclr_archive`; an arbitrary arXiv URL is not globally an ICLR paper.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    host = parsed.hostname.lower().removeprefix("www.")
    if host in {"openreview.net", "beta.openreview.net"} and parsed.path == "/forum":
        ids = parse_qs(parsed.query).get("id", [])
        if len(ids) != 1 or not FORUM_ID.fullmatch(ids[0]):
            return None
        canonical = f"https://openreview.net/forum?{urlencode({'id': ids[0]})}"
        return ids[0], canonical
    canonical = urlunparse(("https", host, parsed.path or "/", "", parsed.query, ""))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"iclr-{digest}", canonical
