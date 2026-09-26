"""RIS importer: the Trust-Evals corpus as scholarmend mended it (spec 01 §Sources; task-019).

Reads a `mended.ris` with `scholarmend.parse.parse_file` and the `resolved.json` scholarmend writes beside
it (one entry per RIS record, same order, same title). Only scholarmend's identifying claims decide
anything; Scholar's own metadata never does:

- **scope, id, track, status**: an OpenReview venueid claim (`openreview_api`), a NeurIPS or ICLR
  proceedings URL (`proceedings_url`), or a PMLR URL in an ICML main-conference volume. Anything else is
  out of scope. An in-scope record with no native id (a PMC link with no PMLR key) is skipped and counted,
  never given a minted id.
- **status** comes from a claim only (spec 01): a venueid → its status; a proceedings listing → `accepted`
  (the proceedings decide acceptance, decision-005); nothing else ever says `accepted`.
- **abstract**: OpenReview's, else the proceedings page's; a Scholar or Semantic Scholar abstract is never
  used (`None` instead), since Scholar's is a snippet.
- **authors**: the RIS `AU` lines in order, without Scholar's `...` truncation marker (display only).

Every claim is `source="ris"` with scholarmend's source and evidence in `evidence`, and `fetched_at` from
the RIS `M1  - Query date:` line. PoP writes that as local wall time with no zone; it is stored labelled
UTC. It is provenance only and never hashed. Records with the same id in two files are both returned;
merging them is dedup's job (task-021).
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scholarmend.parse import parse_file

from openproceedings.ingest.classify import Classification, classify_proceedings, classify_venueid
from openproceedings.ingest.record import Claim, ClaimField, ClaimValue, PaperRecord, Urls

log = logging.getLogger("openproceedings.ingest.ris")

_PROCEEDINGS = re.compile(
    r"https://proceedings\.(neurips|iclr)\.cc/paper_files/paper/([0-9]{4})/(?:hash|file)/"
    r"([0-9a-f]{32})-(?:Abstract|Paper)-([A-Za-z_]+)\.(?:html|pdf)"
)
_PMLR = re.compile(r"https://proceedings\.mlr\.press/v([0-9]+)/([A-Za-z0-9_-]+?)(?:\.html|/[^/]*\.pdf)?")
_ICML_VOLUMES = {119: 2020, 139: 2021, 162: 2022, 202: 2023, 235: 2024, 267: 2025}  # main conference only
_PROCEEDINGS_VENUE = {"neurips": "NeurIPS", "iclr": "ICLR"}
_QUERY_DATE = re.compile(r"Query date: ([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})")
_TRUNCATED = "..."  # Scholar's marker for a cut author list
_ABSTRACT_SOURCES = ("openreview_api", "proceedings_page")  # decision-005 order; Scholar/S2 never


@dataclass
class ImportReport:
    """What one file gave; the snapshot manifest (task-022) records it."""

    file: str
    read: int = 0
    imported: int = 0
    skipped: Counter[str] = field(default_factory=Counter)  # reason → count
    abstract_missing: int = 0
    status: Counter[str] = field(default_factory=Counter)


@dataclass(frozen=True)
class _Identity:
    venue: str
    year: int
    native: str
    cls: Classification
    evidence: dict[str, tuple[str, str]]  # claim field → (scholarmend source, evidence)
    urls: Urls


def _claims(entry: dict[str, Any], fld: str, source: str) -> list[dict[str, Any]]:
    return [c for c in entry["claims"] if c["field"] == fld and c["source"] == source]


def _identity(entry: dict[str, Any], urls: list[str]) -> _Identity | str:
    """The record's venue, year, native id and classification, or the reason it can't be imported."""
    venueids = _claims(entry, "venue_id", "openreview_api")
    forums = _claims(entry, "forum_id", "openreview_url")
    proc = [
        m
        for c in entry["claims"]
        if c["source"] == "proceedings_url"
        if (m := _PROCEEDINGS.fullmatch(c["evidence"]))
    ]
    pmlr = [m for u in urls if (m := _PMLR.fullmatch(u)) and int(m.group(1)) in _ICML_VOLUMES]

    if (
        len({c["value"] for c in venueids}) > 1
        or len({m.group(3) for m in proc}) > 1
        or len({m.groups() for m in pmlr}) > 1
    ):
        return "ambiguous"
    if venueids:
        vid = venueids[0]["value"]
        cls = classify_venueid(vid)
        venue, year = cls.venue, cls.year
        if venue is None or year is None:
            return "out_of_scope"  # an unparseable venueid (e.g. another conference's)
        if not forums:
            return "no_id"
        evidence = {k: ("openreview_api", f"venueid={vid}") for k in ("venue", "year", "track", "status")}
        fid = forums[0]["value"]
        forum_url = f"https://openreview.net/forum?id={fid}"
        if proc:  # listed in the proceedings: they decide acceptance (decision-005)
            if cls.status != "accepted":
                log.debug("venueid_proceedings_disagree", extra={"venue_id_raw": vid})
            cls = Classification(cls.track, "accepted", venue, year, vid)
            evidence["status"] = ("proceedings_url", proc[0].group(0))
        return _Identity(venue, year, fid, cls, evidence, Urls(forum=forum_url))
    if proc:
        m = proc[0]
        cls = classify_proceedings(m.group(4))
        ev = ("proceedings_url", m.group(0))
        abstract_url = next((p.group(0) for p in proc if p.group(0).endswith(".html")), None)
        pdf_url = next((p.group(0) for p in proc if p.group(0).endswith(".pdf")), None)
        return _Identity(
            _PROCEEDINGS_VENUE[m.group(1)], int(m.group(2)), f"{'nips' if m.group(1) == 'neurips' else 'iclr'}-{m.group(3)}",
            cls, dict.fromkeys(("venue", "year", "track", "status"), ev), Urls(proceedings=abstract_url, pdf=pdf_url),
        )  # fmt: skip
    if pmlr:
        vol, key = int(pmlr[0].group(1)), pmlr[0].group(2)
        ev = ("pmlr_url", f"https://proceedings.mlr.press/v{vol}/{key}.html")
        cls = Classification("main", "accepted", "ICML", _ICML_VOLUMES[vol])
        return _Identity(
            "ICML", _ICML_VOLUMES[vol], f"pmlr-v{vol}-{key}", cls,
            dict.fromkeys(("venue", "year", "track", "status"), ev), Urls(proceedings=ev[1]),
        )  # fmt: skip
    if any(
        c["field"] == "venue" and c["value"] == "ICML" and c["source"] == "pmlr_index"
        for c in entry["claims"]
    ):
        return "no_id"  # an ICML paper reached through PMC: no PMLR key to build an id from
    return "out_of_scope"


def _record(
    entry: dict[str, Any], ris: dict[str, list[str]], ident: _Identity, fetched: datetime
) -> PaperRecord:
    abstract, abstract_src = None, None
    for src in _ABSTRACT_SOURCES:
        if found := _claims(entry, "abstract", src):
            abstract, abstract_src = " ".join(found[0]["value"].split()) or None, found[0]
            break
    title = " ".join(entry["title"].split())
    authors = tuple(a for a in ris.get("AU", []) if a != _TRUNCATED)

    def claim(
        fld: ClaimField, value: ClaimValue, source: str, evidence: str, url: str | None = None
    ) -> Claim:
        return Claim(
            field=fld,
            value=value,
            source="ris",
            url=url,
            fetched_at=fetched,
            evidence=f"scholarmend:{source} {evidence}",
        )

    values: dict[ClaimField, ClaimValue] = {
        "venue": ident.venue,
        "year": ident.year,
        "track": ident.cls.track,
        "status": ident.cls.status,
    }
    provenance = [claim(k, values[k], *ident.evidence[k]) for k in values]
    provenance += [claim("title", title, "ris", "TI"), claim("authors", authors, "ris", "AU")]
    if abstract_src is not None:
        provenance.append(claim("abstract", abstract, abstract_src["source"], abstract_src["evidence"]))
    if ident.cls.venue_id_raw is not None:
        provenance.append(
            claim(
                "venue_id_raw", ident.cls.venue_id_raw, "openreview_api", f"venueid={ident.cls.venue_id_raw}"
            )
        )
    url_claims: tuple[tuple[ClaimField, str | None], ...] = (
        ("urls.forum", ident.urls.forum),
        ("urls.proceedings", ident.urls.proceedings),
        ("urls.pdf", ident.urls.pdf),
    )
    for fld, u in url_claims:
        if u is not None:
            provenance.append(claim(fld, u, "ris", "UR", url=u))
    return PaperRecord.build(
        id=f"op:{ident.venue.lower()}:{ident.year}:{ident.native}", title=title, abstract=abstract, authors=authors,
        venue=ident.venue, year=ident.year, track=ident.cls.track, status=ident.cls.status,
        venue_id_raw=ident.cls.venue_id_raw, urls=ident.urls, provenance=tuple(provenance),
    )  # fmt: skip


def import_ris(mended: Path, resolved: Path | None = None) -> tuple[list[PaperRecord], ImportReport]:
    """Records and counts from one scholarmend output (`mended.ris` + its `resolved.json`)."""
    ris = parse_file(mended)
    entries = json.loads((resolved or mended.with_name("resolved.json")).read_text(encoding="utf-8"))
    if len(entries) != len(ris):
        raise ValueError(f"{mended.name}: {len(ris)} RIS records but {len(entries)} resolved entries")
    report = ImportReport(file=str(mended.parent.name + "/" + mended.name))
    records: list[PaperRecord] = []
    for i, (rec, entry) in enumerate(zip(ris, entries, strict=True)):
        report.read += 1
        if rec.fields.get("TI", [None])[0] != entry["title"]:
            raise ValueError(f"{mended.name}: record {i} doesn't line up with resolved.json")
        ident = _identity(entry, rec.fields.get("UR", []))
        if isinstance(ident, str):
            report.skipped[ident] += 1
            continue
        dates = [m.group(1) for v in rec.fields.get("M1", []) if (m := _QUERY_DATE.fullmatch(v))]
        if not dates:
            report.skipped["no_query_date"] += 1
            continue
        fetched = datetime.strptime(dates[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        r = _record(entry, rec.fields, ident, fetched)
        records.append(r)
        report.imported += 1
        report.status[r.status] += 1
        report.abstract_missing += r.abstract is None
    log.info(
        "ris_import",
        extra={"file": report.file, "read": report.read, "imported": report.imported,
               "skipped": dict(report.skipped), "abstract_missing": report.abstract_missing},
    )  # fmt: skip
    return records, report
