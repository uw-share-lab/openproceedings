"""Proceedings URLs → native ids (record-schema skill §Native ids), shared by the RIS importer and dedup, and
OpenReview forum URLs → forum ids (dedup's forum link, TASK-105).

The grammar follows scholarmend 0.1.3's miners: any host case, `papers.nips.cc`, `http`, a query string
or fragment (one real URL carries `?utm_source=chatgpt.com`), PMLR's two hosts and its raw GitHub assets.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

from openproceedings.ingest import acm_table
from openproceedings.ingest import volumes as _volumes
from openproceedings.ingest.classify import NEURIPS_DB_2021_HOST, NEURIPS_DB_2021_ROUNDS
from openproceedings.ingest.ojs_table import TABLE as OJS_TABLE
from openproceedings.ingest.record import FORUM_ID

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


def proceedings_site(url: str) -> str | None:
    """Whose proceedings site `url` is on, by its host alone: `NeurIPS`, `ICLR` or `PMLR`, else None (the
    results list's attribution names it; TASK-134)."""
    host = urlparse(url).netloc.lower()
    return _PROCEEDINGS_HOSTS.get(host) or ("PMLR" if host in _PMLR_HOSTS else None)


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


def proceedings_native(url: str) -> str | None:
    """The native id a NeurIPS or ICLR proceedings URL names, or None: `nips-`/`iclr-<32 hex>`, and on the 2021
    D&B host `nips-<32 hex>-round1|round2`. The hash is md5 of the paper's number, and that host numbers each
    round (and the main track) separately, so there the hash alone names up to three papers (TASK-118). A D&B
    link without a known round, or dated other than 2021 (the host lists 2021 only), names none of them. The
    miners, the RIS importer and dedup all call this, so a URL and its record always agree on the id."""
    parts = proceedings_parts(url)
    if parts is None or len(parts[2]) != 32:
        return None
    venue, year, sha, token = parts
    base = f"{PREFIX[venue]}-{sha}"
    if urlparse(url).netloc.lower() == NEURIPS_DB_2021_HOST:  # the same rule as classify_neurips_listing
        return f"{base}-{token}" if year == 2021 and token in NEURIPS_DB_2021_ROUNDS else None
    return base


_HASH_TAIL = re.compile(r"/hash/([0-9a-fA-F]{32})/?")


def names_native(url: str, native_id: str) -> bool:
    """Whether `url` is the page of the paper whose native id is `native_id`: the id `native` reads from it, or,
    for a NeurIPS or ICLR proceedings page cut after its hash (`…/paper/2024/hash/<32 hex>`, as some RIS
    evidence records it), that hash with the host's prefix. Never by hash alone on the 2021 D&B host, where a
    hash names up to three papers (TASK-118). The results list links an RIS abstract's evidence url only then
    (TASK-134)."""
    if native(url) == native_id:
        return True
    parsed = urlparse(url)
    venue = _PROCEEDINGS_HOSTS.get(parsed.netloc.lower())
    m = re.fullmatch(r"(?:/paper_files)?/paper/[0-9]{4}" + _HASH_TAIL.pattern, parsed.path)
    if venue is None or m is None or parsed.netloc.lower() == NEURIPS_DB_2021_HOST:
        return False
    return native_id == f"{PREFIX[venue]}-{m.group(1).lower()}"


def native(url: str) -> str | None:
    """The proceedings native id a URL names (`proceedings_native`, `pmlr-v<N>-<key>` for an ingested PMLR volume (ICML, FAccT 2018),
    `dblp-<key>` for an ICML or AAAI (1980-2008) record's dblp page, `ojs-<id>` for an ojs.aaai.org article, or
    `doi-<toc>.<n>` for a listed ACM paper's doi.org link), or None."""
    if proceedings(url) is not None:
        return proceedings_native(url)
    if (q := pmlr(url)) is not None and q[0] in _volumes.PMLR_NATIVE_VOLUMES:
        return f"pmlr-v{q[0]}-{q[1]}"
    if (key := dblp_icml(url)) is not None:
        return f"dblp-{key}"
    if (key := dblp_aaai(url)) is not None:
        return f"dblp-{key}"
    if (article := ojs_article(url)) is not None:
        return f"ojs-{article}"
    if (doi := acm_doi(url)) is not None:
        return "doi-" + doi.split("/", 1)[1]
    return None


_DOI_HOSTS = frozenset({"doi.org", "dx.doi.org"})


def acm_doi(url: str) -> str | None:
    """The ACM paper DOI a doi.org link names (`10.1145/<toc>.<n>`, lower-case), when its proceedings are a row of
    acm_proceedings.toml (FAccT, AIES; decision-049), else None. Only doi.org: the DOI is the paper's name."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() not in _DOI_HOSTS:
        return None
    doi = unquote(parsed.path.removeprefix("/"))
    if doi != doi.strip():
        return None
    doi = doi.lower()
    parts = acm_table.paper_doi(doi)
    if parts is None or acm_table.TABLE.by_toc(parts[0]) is None:
        return None
    return doi


_OJS_HOST = "ojs.aaai.org"
# the journals are the table's (`ojs_sections.toml`), so a journal added there is a journal whose URLs name articles
_OJS_PATH = re.compile(
    r"/index\.php/(?:" + "|".join(map(re.escape, sorted(OJS_TABLE.journals))) + r")/article/view/([0-9]+)"
    r"(?:/[0-9]+)?/?"
)


def ojs_article(url: str) -> int | None:
    """The article id of an ojs.aaai.org article or galley URL (AAAI, AIES, IASEAI; decision-049), or None. The
    URL's journal is deliberately not matched to a record's venue: article ids are unique across the site's
    journals, so the id alone names the paper (a record's self-naming check compares ids)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != _OJS_HOST:
        return None
    m = _OJS_PATH.fullmatch(parsed.path)
    return int(m.group(1)) if m else None


_DBLP_REC = re.compile(r"/rec/conf/icml/([A-Za-z0-9_-]+)(?:\.html)?")


def dblp_record_url(key: str) -> str:
    """The dblp page of a record (`https://dblp.org/rec/conf/icml/<key>`): a link for people and the dblp
    records' `urls.proceedings` (sources/dblp.py), never fetched (dblp.org forbids crawling; decision-047)."""
    return f"https://dblp.org/rec/{key}"


def dblp_icml(url: str) -> str | None:
    """The key after `conf/icml/` of a dblp record page URL (any scheme and host case, `dblp.org`), or None."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != "dblp.org":
        return None
    m = _DBLP_REC.fullmatch(parsed.path)
    return m.group(1) if m else None


_DBLP_REC_AAAI = re.compile(r"/rec/conf/aaai/([A-Za-z0-9_-]+)(?:\.html)?")


def dblp_aaai(url: str) -> str | None:
    """The key after `conf/aaai/` of a dblp record page URL (AAAI 1980-2008; decision-049), or None."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != "dblp.org":
        return None
    m = _DBLP_REC_AAAI.fullmatch(parsed.path)
    return m.group(1) if m else None


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
