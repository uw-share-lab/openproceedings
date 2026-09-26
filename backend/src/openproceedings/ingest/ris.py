"""RIS importer: the Trust-Evals corpus as scholarmend mended it (spec 01 §Sources; task-019).

The corpus is two Scholar searches (2025–26 and 2020–24), one scholarmend output each: a `mended.ris`,
read with `scholarmend.parse.parse_file`, and the `resolved.json` beside it (one entry per RIS record,
same order, same title). Only scholarmend's identifying claims decide anything; Scholar's own metadata
never does:

- **Identity** (venue, year, native id): an OpenReview venueid claim plus its forum id; a NeurIPS or
  ICLR `proceedings_url` claim (`nips-`/`iclr-<hash>`); or a `pmlr_url` claim in an ICML volume
  (`pmlr-v<N>-<key>`, `volumes.py`). The id is never minted: a record that points at an in-scope venue but
  yields no id is skipped as `unresolved` (or `no_id`), and one that points nowhere is `out_of_scope`.
- **Track**: the venueid; else scholarmend's proceedings track; else the PMLR volume table.
- **Status** comes from a claim only (spec 01): a venueid → its status; a proceedings listing →
  `accepted`. When both exist they must name the same venue, year and track (else the record is skipped as
  a `conflict`); the proceedings then decide acceptance (decision-005), counted in `status_overrides`.
- **Abstract**: OpenReview's, else the proceedings page's, else `None`; never Scholar's or Semantic
  Scholar's (Scholar's is a snippet).
- **Authors**: the RIS `AU` lines in order, without Scholar's `...` truncation marker (display only).

Every claim has `source="ris"`; `evidence` names where it came from (`scholarmend:<source> <evidence>`, or
`mended.ris:TI` for the RIS text); `fetched_at` is the RIS `M1  - Query date:`. PoP writes that as local
wall time with no zone; it is stored labelled UTC (provenance only, never hashed). A record in both files
is returned twice; dedup merges them (task-021).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scholarmend.parse import parse_file

from openproceedings.ingest.classify import Classification, classify_proceedings, classify_venueid
from openproceedings.ingest.record import Claim, ClaimField, ClaimValue, PaperRecord, Urls
from openproceedings.ingest.volumes import ICML_PMLR_VOLUMES

log = logging.getLogger("openproceedings.ingest.ris")

_PROCEEDINGS_HOSTS = {
    "proceedings.neurips.cc": "NeurIPS",
    "papers.nips.cc": "NeurIPS",
    "proceedings.iclr.cc": "ICLR",
}
_PROCEEDINGS_PATH = re.compile(r"/paper_files/paper/[0-9]{4}/(?:hash|file)/([0-9a-f]+)-(?:Abstract|Paper)-")
_PMLR_HOSTS = {"proceedings.mlr.press", "mlr.press"}
_PMLR_PATH = re.compile(r"/v([0-9]+)/([A-Za-z0-9_-]+?)(?:\.html|\.pdf|/.*)?")
_PMLR_GITHUB_PATH = re.compile(r"/mlresearch/v([0-9]+)/[^/]+/assets/([A-Za-z0-9_-]+)/.*")
_IN_SCOPE_HOST = re.compile(r"(?:.+\.)?(?:neurips\.cc|nips\.cc|iclr\.cc|icml\.cc|openreview\.net)")
_IN_SCOPE_VENUEID = re.compile(r"(?:NeurIPS|ICLR|ICML)\.cc/.*")
_QUERY_DATE = re.compile(r"Query date: ([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})")
_TRUNCATED = "..."  # Scholar's marker for a cut author list
_ABSTRACT_SOURCES = ("openreview_api", "proceedings_page")  # decision-005 order; Scholar/S2 never
SKIP_REASONS = ("out_of_scope", "unresolved", "no_id", "ambiguous", "conflict", "no_query_date")


@dataclass(frozen=True)
class ImportReport:
    """What one file gave; the snapshot manifest (task-022) records `to_manifest()`."""

    file: str
    mended_sha256: str
    resolved_sha256: str
    scholarmend_version: str
    read: int
    imported: int
    skipped: dict[str, int]  # reason → count, every reason in SKIP_REASONS
    abstract_missing: int
    unknown_track: int
    status_overrides: int  # venueid status replaced by a proceedings listing
    track_status: dict[str, dict[str, int]]  # track → status → count

    def __post_init__(self) -> None:
        if self.read != self.imported + sum(self.skipped.values()):
            raise ValueError(f"{self.file}: {self.read} read != {self.imported} imported + {self.skipped}")

    def to_manifest(self) -> dict[str, Any]:
        """Plain, key-sorted JSON values."""
        out = {k: getattr(self, k) for k in self.__dataclass_fields__}
        out["skipped"] = dict(sorted(self.skipped.items()))
        out["track_status"] = {t: dict(sorted(s.items())) for t, s in sorted(self.track_status.items())}
        return dict(sorted(out.items()))


@dataclass(frozen=True)
class _Identity:
    venue: str
    year: int
    native: str
    cls: Classification
    evidence: dict[str, tuple[str, str]]  # venue/year/track/status → (scholarmend source, evidence)
    urls: tuple[tuple[ClaimField, str, str], ...]  # (field, url, scholarmend source)
    status_override: bool = False


def _claims(entry: dict[str, Any], fld: str, source: str) -> list[dict[str, Any]]:
    return [c for c in entry["claims"] if c["field"] == fld and c["source"] == source]


def _proceedings(url: str) -> tuple[str, str] | None:
    """(venue, hash) from a NeurIPS/ICLR proceedings URL, any host case or query (scholarmend's grammar)."""
    parsed = urlparse(url)
    venue = _PROCEEDINGS_HOSTS.get(parsed.netloc.lower())
    m = _PROCEEDINGS_PATH.match(parsed.path)
    return (venue, m.group(1)) if venue and m else None


def _pmlr(url: str) -> tuple[int, str] | None:
    """(volume, key) from a PMLR URL, or its raw GitHub asset (the two hosts Scholar links to)."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host in _PMLR_HOSTS:
        m = _PMLR_PATH.fullmatch(parsed.path)
    elif host == "raw.githubusercontent.com":
        m = _PMLR_GITHUB_PATH.fullmatch(parsed.path)
    else:
        return None
    return (int(m.group(1)), m.group(2)) if m else None


def _listing(
    entry: dict[str, Any],
) -> tuple[str, int, str, Classification, tuple[str, str], list[str]] | str | None:
    """The proceedings listing (NeurIPS/ICLR page or ICML PMLR volume): venue, year, native id, track
    classification, evidence and every URL; a skip reason if it's unusable; None if there is none."""
    proc = [
        (c, p)
        for c in entry["claims"]
        if c["source"] == "proceedings_url"
        if (p := _proceedings(c["evidence"]))
    ]
    if proc:
        if len({p for _, p in proc}) > 1:
            return "ambiguous"
        (venue, sha), url = proc[0][1], proc[0][0]["evidence"]
        prefix = "nips" if venue == "NeurIPS" else "iclr"
        years = {c["value"] for c, _ in proc if c["field"] == "year"}
        tracks = {c["value"] for c, _ in proc if c["field"] == "track"}
        if len(sha) != 32 or len(years) != 1 or len(tracks) != 1:
            return "unresolved"
        return (venue, int(years.pop()), f"{prefix}-{sha}", classify_proceedings(tracks.pop()),
                ("proceedings_url", url), sorted({c["evidence"] for c, _ in proc}))  # fmt: skip
    pmlr = [
        (c["evidence"], vk) for c in _claims(entry, "pmlr_volume", "pmlr_url") if (vk := _pmlr(c["evidence"]))
    ]
    icml = [(u, p) for u, p in pmlr if p[0] in ICML_PMLR_VOLUMES]
    if not icml:
        if _claims(entry, "pmlr_volume", "pmlr_url") and not pmlr:
            return "unresolved"
        return None
    if len({p for _, p in icml}) > 1:
        return "ambiguous"
    url, (vol, key) = icml[0]
    year, track = ICML_PMLR_VOLUMES[vol]
    return ("ICML", year, f"pmlr-v{vol}-{key}", Classification(track, "accepted", "ICML", year),
            ("pmlr_url", url), sorted({u for u, _ in icml}))  # fmt: skip


def _url_fields(urls: list[str], source: str) -> tuple[tuple[ClaimField, str, str], ...]:
    """The listing's page and PDF URLs, exactly as they appear (sorted, so the choice is stable)."""
    html = next((u for u in urls if not urlparse(u).path.endswith(".pdf")), None)
    pdf = next((u for u in urls if urlparse(u).path.endswith(".pdf")), None)
    pairs: tuple[tuple[ClaimField, str | None], ...] = (("urls.proceedings", html), ("urls.pdf", pdf))
    return tuple((f, u, source) for f, u in pairs if u)


def _identity(entry: dict[str, Any], urls: list[str]) -> _Identity | str:
    """The record's identity, or the reason it can't be imported (one of SKIP_REASONS)."""
    venueids = {c["value"] for c in _claims(entry, "venue_id", "openreview_api")}
    forums = {c["value"] for c in _claims(entry, "forum_id", "openreview_url")}
    listing = _listing(entry)
    if len(venueids) > 1 or len(forums) > 1 or listing == "ambiguous":
        return "ambiguous"
    if isinstance(listing, str):
        return listing
    four = ("venue", "year", "track", "status")
    if venueids:
        vid = venueids.pop()
        cls = classify_venueid(vid)
        venue, year = cls.venue, cls.year
        if venue is None or year is None:
            return "unresolved" if _IN_SCOPE_VENUEID.fullmatch(vid) else "out_of_scope"
        if not forums:
            return "no_id"
        fid = forums.pop()
        evidence = dict.fromkeys(four, ("openreview_api", f"venueid={vid}"))
        url_claims: tuple[tuple[ClaimField, str, str], ...] = (
            ("urls.forum", f"https://openreview.net/forum?id={fid}", "openreview_url"),
        )
        override = False
        if listing is not None:
            l_venue, l_year, _, l_cls, l_ev, l_urls = listing
            if (l_venue, l_year) != (venue, year) or l_cls.track not in (cls.track, "unknown"):
                return "conflict"  # decision-005: never silently resolved
            override = cls.status != "accepted"
            cls = Classification(cls.track, "accepted", venue, year, vid)  # the proceedings decide acceptance
            evidence["status"] = l_ev
            url_claims += _url_fields(l_urls, l_ev[0])
        return _Identity(venue, year, fid, cls, evidence, url_claims, override)
    if listing is not None:
        venue, year, native, cls, ev, l_urls = listing
        return _Identity(venue, year, native, cls, dict.fromkeys(four, ev), _url_fields(l_urls, ev[0]))
    if forums:
        return "unresolved"  # an OpenReview forum scholarmend couldn't resolve (hidden, or not fetched)
    if any(
        c["source"] == "pmlr_index" and c["field"] == "venue" and c["value"] == "ICML"
        for c in entry["claims"]
    ):
        return "no_id"  # an ICML paper reached through PMC: no PMLR key to build an id from
    if any(_IN_SCOPE_HOST.fullmatch(urlparse(u).netloc.lower()) for u in urls):
        return "unresolved"  # e.g. a neurips.cc/media link: in scope, but nothing to build an id from
    return "out_of_scope"


def _abstract(entry: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for src in _ABSTRACT_SOURCES:
        for c in _claims(entry, "abstract", src):
            if isinstance(c["value"], str) and (text := " ".join(c["value"].split())):
                return text, c
    return None


def _record(
    entry: dict[str, Any], ris: dict[str, list[str]], ident: _Identity, fetched: datetime
) -> PaperRecord:
    title = " ".join(entry["title"].split())
    authors = tuple(a for a in ris.get("AU", []) if a != _TRUNCATED)
    abstract = _abstract(entry)

    def claim(fld: ClaimField, value: ClaimValue, evidence: str, url: str | None = None) -> Claim:
        return Claim(field=fld, value=value, source="ris", url=url, fetched_at=fetched, evidence=evidence)

    values: dict[ClaimField, ClaimValue] = {
        "venue": ident.venue,
        "year": ident.year,
        "track": ident.cls.track,
        "status": ident.cls.status,
    }
    provenance = [claim(k, v, "scholarmend:{} {}".format(*ident.evidence[k])) for k, v in values.items()]
    provenance += [claim("title", title, "mended.ris:TI"), claim("authors", authors, "mended.ris:AU")]
    if abstract is not None:
        provenance.append(
            claim("abstract", abstract[0], f"scholarmend:{abstract[1]['source']} {abstract[1]['evidence']}")
        )
    if ident.cls.venue_id_raw is not None:
        provenance.append(
            claim(
                "venue_id_raw",
                ident.cls.venue_id_raw,
                f"scholarmend:openreview_api venueid={ident.cls.venue_id_raw}",
            )
        )
    urls = {f: u for f, u, _ in ident.urls}
    for f, u, src in ident.urls:
        provenance.append(claim(f, u, f"scholarmend:{src} {u}", url=u))
    return PaperRecord.build(
        id=f"op:{ident.venue.lower()}:{ident.year}:{ident.native}", title=title,
        abstract=None if abstract is None else abstract[0], authors=authors, venue=ident.venue, year=ident.year,
        track=ident.cls.track, status=ident.cls.status, venue_id_raw=ident.cls.venue_id_raw,
        urls=Urls(forum=urls.get("urls.forum"), proceedings=urls.get("urls.proceedings"), pdf=urls.get("urls.pdf")),
        provenance=tuple(provenance),
    )  # fmt: skip


def import_ris(mended: Path, resolved: Path | None = None) -> tuple[list[PaperRecord], ImportReport]:
    """Records and counts from one scholarmend output (`mended.ris` + its `resolved.json`)."""
    resolved = resolved or mended.with_name("resolved.json")
    ris = parse_file(mended)
    resolved_bytes = resolved.read_bytes()
    entries = json.loads(resolved_bytes.decode("utf-8"))
    name = f"{mended.parent.name}/{mended.name}"
    if len(entries) != len(ris):
        raise ValueError(f"{name}: {len(ris)} RIS records but {len(entries)} resolved entries")
    skipped: Counter[str] = Counter(dict.fromkeys(SKIP_REASONS, 0))
    track_status: dict[str, Counter[str]] = {}
    overrides = 0
    records: list[PaperRecord] = []
    for i, (rec, entry) in enumerate(zip(ris, entries, strict=True)):
        if rec.fields.get("TI", [None])[0] != entry["title"]:
            raise ValueError(f"{name}: record {i} doesn't line up with resolved.json")
        ident = _identity(entry, rec.fields.get("UR", []))
        if isinstance(ident, str):
            skipped[ident] += 1
            log.debug("ris_skip", extra={"file": name, "index": i, "reason": ident})
            continue
        dates = [m.group(1) for v in rec.fields.get("M1", []) if (m := _QUERY_DATE.fullmatch(v))]
        if not dates:
            skipped["no_query_date"] += 1
            log.debug("ris_skip", extra={"file": name, "index": i, "reason": "no_query_date"})
            continue
        r = _record(
            entry, rec.fields, ident, datetime.strptime(dates[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        )
        records.append(r)
        overrides += ident.status_override
        track_status.setdefault(r.track, Counter())[r.status] += 1
    report = ImportReport(
        file=name,
        mended_sha256=hashlib.sha256(mended.read_bytes()).hexdigest(),
        resolved_sha256=hashlib.sha256(resolved_bytes).hexdigest(),
        scholarmend_version=version("scholarmend"),
        read=len(ris),
        imported=len(records),
        skipped=dict(skipped),
        abstract_missing=sum(r.abstract is None for r in records),
        unknown_track=sum(r.track == "unknown" for r in records),
        status_overrides=overrides,
        track_status={t: dict(c) for t, c in track_status.items()},
    )
    counts = {k: v for k, v in report.to_manifest().items() if k not in ("track_status",)}
    log.info("ris_import", extra=counts)
    attention = {
        k: skipped[k] for k in ("unresolved", "ambiguous", "conflict", "no_query_date") if skipped[k]
    }
    if attention or report.unknown_track or report.status_overrides:
        log.warning(
            "ris_import_attention",
            extra={
                "file": name,
                **attention,
                "unknown_track": report.unknown_track,
                "status_overrides": overrides,
            },
        )
    return records, report
