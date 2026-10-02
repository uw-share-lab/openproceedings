"""RIS importer: the Trust-Evals corpus as scholarmend mended it (spec 01 §Sources; task-019).

The corpus is two Scholar searches (2025–26 and 2020–24), one scholarmend output each: a `mended.ris`,
read with `scholarmend.parse.parse_file`, and the `resolved.json` beside it (one entry per RIS record,
same order, same title). Only scholarmend's identifying claims decide anything; Scholar's own metadata
never does:

- **Identity** (venue, year, native id): an OpenReview venueid claim plus its forum id; a NeurIPS or
  ICLR `proceedings_url` claim (`nips-`/`iclr-<hash>`, or `nips-<hash>-round1`/`-round2` on the 2021 D&B host;
  `urls.proceedings_native`); or a `pmlr_url` claim in an ICML volume
  (`pmlr-v<N>-<key>`, `volumes.py`). The id is never minted: a record that points at an in-scope venue but
  yields no id is skipped as `unresolved` (or `no_id`), and one that points nowhere is `out_of_scope`.
- **Track**: the venueid (for ICLR 2013/2017's `other` venueid, the venue string: below); else scholarmend's
  proceedings track; else the PMLR volume table.
- **Status** comes from a claim only (spec 01): a venueid → its status, except that an API v1 venue-year's
  venueid (ICLR ≤2023, NeurIPS 2021–2022) is venue/year/track evidence only, since v1 puts the bare path on
  rejected papers too (TASK-095). There the status comes from scholarmend's `venue_string` claim (OpenReview's
  `content.venue` verbatim, scholarmend 0.1.4; TASK-098) through `classify_v1_venue`, used only when its
  evidence names the record's venueid and the string names the venueid's venue, year and track (ICLR
  2013/2017's lower-case `conference` venueid names no track, `V1_TRACK_FROM_VENUE`: there only venue and year,
  and the string gives the track too; TASK-142); otherwise, or without one, it is `unknown` and the status
  evidence says why. scholarmend 0.1.5's `invitation` claim (the note's top-level OpenReview invitation, verbatim,
  evidence `venueid=<id>`; TASK-157) names the listing the note was submitted to: a main-track outcome on a note
  of a non-main submission listing, where the venueid names no track, is its conference twin's, so the record
  takes the listing's track and an `unknown` status (the crawler's rule, `openreview_v1.is_twin_outcome`; ICLR
  2017's 18 workshop copies of rejected papers). The claim is kept as an `invitation` claim; an entry without one
  (cached before 0.1.5) is read as before. Outside v1 years the claim is ignored. A proceedings listing → `accepted`. When both exist they must name the same venue, year and track (else the record is skipped as
  a `conflict`); the proceedings then decide acceptance (decision-005), counted in `status_overrides`.
- **Abstract**: OpenReview's, else the proceedings page's, else `None`; never Scholar's or Semantic
  Scholar's (Scholar's is a snippet).
- **Authors**: the RIS `AU` lines in order, without Scholar's `...` truncation marker (display only).

Every claim has `source="ris"`; `evidence` names where it came from (`scholarmend:<source> <evidence>`, or
`mended.ris:TI` for the RIS text); `fetched_at` is the RIS `M1  - Query date:`. PoP writes that as local
wall time with no zone. A cache entry listed in `ris_offsets.toml` has it converted to UTC with the entry's
recorded offset; any other keeps the wall time, stored labelled UTC, and its report's `utc_offset` is null
("local, offset unknown"; TASK-077, decision-025). It is provenance only: never in `content_hash`, though it
is in the snapshot's bytes. A record in both files is returned twice; dedup merges them (task-021).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import tomllib
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse

from scholarmend.parse import parse_file

from openproceedings.ingest.classify import (
    V1_TRACK_FROM_VENUE,
    Classification,
    classify_neurips_listing,
    classify_proceedings,
    classify_v1_venue,
    classify_venueid,
    is_v1,
)
from openproceedings.ingest.record import FORUM_ID, Claim, ClaimField, ClaimValue, PaperRecord, Urls, is_url
from openproceedings.ingest.urls import pmlr, proceedings, proceedings_native, proceedings_parts
from openproceedings.ingest.volumes import ICML_PMLR_VOLUMES
from openproceedings.vocab import venue_name

log = logging.getLogger(__name__)

_IN_SCOPE_HOST = re.compile(r"(?:.+\.)?(?:neurips\.cc|nips\.cc|iclr\.cc|icml\.cc|openreview\.net)")
_IN_SCOPE_VENUEID = re.compile(r"(?:NeurIPS|ICLR|ICML)\.cc/.*")
_QUERY_DATE = re.compile(r"Query date: ([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})")
_TRUNCATED = "..."  # Scholar's marker for a cut author list
_ABSTRACT_SOURCES = ("openreview_api", "proceedings_page")  # decision-005 order; Scholar/S2 never
SKIP_REASONS = ("out_of_scope", "unresolved", "no_id", "ambiguous", "conflict", "no_query_date")
_OFFSET = re.compile(r"([+-])([0-9]{2}):([0-9]{2})")


def load_offsets(text: str) -> Mapping[str, str]:
    """`ris_offsets.toml` (cache entry name → `±HH:MM`), checked: every row has exactly `utc_offset`,
    `evidence` and `verified`, and an offset within ±14:00 on a whole minute. A bad row is an import error."""
    table: dict[str, str] = {}
    for name, row in tomllib.loads(text).items():
        where = f"ris_offsets.toml entry {name!r}"
        if not isinstance(row, dict) or set(row) != {"utc_offset", "evidence", "verified"}:
            raise ValueError(f"{where}: needs exactly utc_offset, evidence and verified")
        offset, evidence = row["utc_offset"], row["evidence"]
        if not isinstance(offset, str) or not (m := _OFFSET.fullmatch(offset)):
            raise ValueError(f"{where}: utc_offset must be +HH:MM or -HH:MM")
        if int(m.group(3)) >= 60 or int(m.group(2)) * 60 + int(m.group(3)) > 14 * 60:
            raise ValueError(f"{where}: utc_offset is not a real offset")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError(f"{where}: evidence is empty")
        if type(row["verified"]) is not date:
            raise ValueError(f"{where}: verified must be a date")
        table[name] = offset
    return MappingProxyType(dict(sorted(table.items())))


def _zone(offset: str) -> timezone:
    m = _OFFSET.fullmatch(offset)
    if m is None:
        raise ValueError(f"utc_offset {offset!r} must be +HH:MM or -HH:MM")
    minutes = int(m.group(2)) * 60 + int(m.group(3))
    return timezone(timedelta(minutes=-minutes if m.group(1) == "-" else minutes))


# The recorded offset of each cache entry's Publish or Perish searches (TASK-077, decision-025)
QUERY_DATE_OFFSETS: Mapping[str, str] = load_offsets(
    files("openproceedings.ingest").joinpath("ris_offsets.toml").read_text(encoding="utf-8")
)


@dataclass(frozen=True)
class ImportReport:
    """What one file gave; the snapshot manifest (task-022) records `to_manifest()`."""

    file: str
    mended_sha256: str
    resolved_sha256: str
    parser_version: str  # the installed scholarmend parser's; resolved.json doesn't record its producer's
    read: int
    imported: int
    skipped: Mapping[str, int]  # reason → count, exactly the reasons in SKIP_REASONS (read-only)
    abstract_missing: int
    unknown_track: int
    status_overrides: int  # venueid status replaced by a proceedings listing
    track_status: Mapping[str, Mapping[str, int]]  # track → status → count (read-only)
    # the offset its query dates were converted with (`ris_offsets.toml`); None: local, offset unknown
    utc_offset: str | None = None

    def __post_init__(self) -> None:
        if set(self.skipped) != set(SKIP_REASONS):
            raise ValueError(f"{self.file}: skip reasons {sorted(self.skipped)} != {sorted(SKIP_REASONS)}")
        object.__setattr__(self, "skipped", MappingProxyType(dict(self.skipped)))
        object.__setattr__(
            self,
            "track_status",
            MappingProxyType({t: MappingProxyType(dict(s)) for t, s in self.track_status.items()}),
        )
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
    invitation: str | None = (
        None  # scholarmend 0.1.5's `invitation` claim, when it names this note (TASK-157)
    )


def _claims(entry: dict[str, Any], fld: str, source: str) -> list[dict[str, Any]]:
    return [c for c in entry["claims"] if c["field"] == fld and c["source"] == source]


def _listing(
    entry: dict[str, Any],
) -> tuple[str, int, str, Classification, tuple[str, str], list[str]] | str | None:
    """The proceedings listing (NeurIPS/ICLR page or ICML PMLR volume): venue, year, native id, track
    classification, evidence and every URL; a skip reason if it's unusable; None if there is none."""
    proc = [
        (c, p)
        for c in entry["claims"]
        if c["source"] == "proceedings_url"
        if (p := proceedings(c["evidence"]))
    ]
    if proc:
        # one paper per native id: the same hash on the main and 2021 D&B hosts is two papers (TASK-118)
        if len({proceedings_native(c["evidence"]) or p for c, p in proc}) > 1:
            return "ambiguous"
        (venue, sha), url = proc[0][1], proc[0][0]["evidence"]
        years = {c["value"] for c, _ in proc if c["field"] == "year"}
        tracks = {c["value"] for c, _ in proc if c["field"] == "track"}
        if len(sha) != 32 or len(years) != 1 or len(tracks) != 1:
            return "unresolved"
        year, track = int(years.pop()), tracks.pop()
        if year >= 2100:  # the same ceiling as an OpenReview venueid's year (classify._YEARS)
            return "unresolved"
        try:  # the URL takes any 4-digit year; one before the venue was held would fail PaperRecord.build
            venue_name(venue, year)  # and abort the file, so it skips this entry instead
        except ValueError:
            return "unresolved"
        claimed = classify_proceedings(track).track
        for c, _p in proc:  # the claim must agree with the address it cites: the URL's year and track token
            parts = proceedings_parts(c["evidence"])
            assert parts is not None  # `proc` holds only URLs that parse
            url_venue, url_year, _h, token = parts
            by_url = (  # the NeurIPS miner's host/year/token rules (the 2021 D&B host's round1/round2)
                classify_neurips_listing(urlparse(c["evidence"]).netloc, url_year, token)[0]
                if url_venue == "NeurIPS"
                else classify_proceedings(token or "")
            )
            if url_year != year or by_url.track != claimed:
                return "conflict"
        # a D&B-host URL without round1/round2, or not dated 2021, names no one paper
        if (native := proceedings_native(url)) is None:
            return "unresolved"
        return (venue, year, native, classify_proceedings(track),
                ("proceedings_url", url), sorted({c["evidence"] for c, _ in proc}))  # fmt: skip
    parsed = [(c, pmlr(c["evidence"])) for c in _claims(entry, "pmlr_volume", "pmlr_url")]
    # an ICML volume, by the URL or (when the URL doesn't parse) by scholarmend's volume claim
    icml_claims = [(c, vk) for c, vk in parsed if (vk[0] if vk else _int(c["value"])) in ICML_PMLR_VOLUMES]
    icml = [(c["evidence"], vk) for c, vk in icml_claims if vk is not None]
    if not icml:
        return "unresolved" if icml_claims else None
    if len({p for _, p in icml}) > 1:
        return "ambiguous"
    url, (vol, key) = icml[0]
    year, track = ICML_PMLR_VOLUMES[vol]
    return ("ICML", year, f"pmlr-v{vol}-{key}", Classification(track, "accepted", "ICML", year),
            ("pmlr_url", url), sorted({u for u, _ in icml}))  # fmt: skip


def _int(value: object) -> int | None:
    return int(value) if isinstance(value, str) and value.isdigit() else None


def _url_fields(urls: list[str], source: str) -> tuple[tuple[ClaimField, str, str], ...]:
    """The listing's page and PDF URLs, exactly as they appear (sorted, so the choice is stable)."""
    urls = [u for u in urls if is_url(u)]  # a URL with a newline or control character is never kept
    html = next((u for u in urls if not urlparse(u).path.endswith(".pdf")), None)
    pdf = next((u for u in urls if urlparse(u).path.endswith(".pdf")), None)
    pairs: tuple[tuple[ClaimField, str | None], ...] = (("urls.proceedings", html), ("urls.pdf", pdf))
    return tuple((f, u, source) for f, u in pairs if u)


def _v1_status(
    entry: dict[str, Any], vid: str, cls: Classification
) -> tuple[Classification, tuple[str, str], bool]:
    """An API v1 venue-year's status (its venueid gives none): scholarmend's `venue_string` claim, OpenReview's
    `content.venue` verbatim (scholarmend 0.1.4), through `classify_v1_venue`. It is used only when its
    evidence names this record's venueid and the string names the venueid's venue, year and track (for a
    venueid in `V1_TRACK_FROM_VENUE`, which names no track, venue and year only: the string gives the track
    too; TASK-142); otherwise the status stays `unknown` and the evidence says why. Returns the
    classification, the status evidence and whether the string was used."""
    base = f"venueid={vid}"
    claims = _claims(entry, "venue_string", "openreview_api")
    if not claims:
        return cls, ("openreview_api", f"{base} (API v1 venue-year: not status evidence)"), False
    values = {c["value"] if isinstance(c["value"], str) else "" for c in claims}
    s = values.pop() if len(values) == 1 else ""  # two different strings are no evidence either
    by = classify_v1_venue(s)
    track = by.track if vid in V1_TRACK_FROM_VENUE else cls.track
    if any(c["evidence"] != base for c in claims):
        why = "its evidence names another venueid"
    elif not s:
        why = "not one non-empty string"  # e.g. a withdrawn v1 note's `""`
    elif not by.parsed:
        why = "not in the v1 table"  # the string itself isn't kept: it can be free text
    elif (by.venue, by.year, by.track) != (cls.venue, cls.year, track):
        why = f"{s} names {by.venue} {by.year} {by.track}"
    else:
        used = Classification(track, by.status, cls.venue, cls.year, vid)
        return used, ("openreview_api", f"{base} venue_string={s}"), True
    return (
        cls,
        ("openreview_api", f"{base} (API v1 venue-year: not status evidence; venue_string not used: {why})"),
        False,
    )


def _invitation(entry: dict[str, Any], vid: str) -> str | None:
    """The note's submission invitation from scholarmend 0.1.5's `invitation` claim (OpenReview's top-level
    `invitation`, verbatim): one string, every such claim's evidence naming this record's venueid. None otherwise,
    as for every entry scholarmend cached before 0.1.5."""
    claims = _claims(entry, "invitation", "openreview_api")
    values = {c["value"] for c in claims}
    if len(values) != 1 or any(c["evidence"] != f"venueid={vid}" for c in claims):
        return None
    value = values.pop()
    return value if isinstance(value, str) and value else None


def _twin_outcome(
    cls: Classification, vid: str, invitation: str | None, said: tuple[str, str]
) -> tuple[Classification, tuple[str, str]] | None:
    """The v1 crawler's twin rule (`openreview_v1.is_twin_outcome`, TASK-152) read off the note's invitation: a
    main-track outcome on a note of a non-main submission listing, where the venueid names no track, is its
    conference twin's, so the note takes its listing's track and an unknown status (TASK-157). None when it
    doesn't apply."""
    from openproceedings.ingest.sources.openreview_v1 import is_twin_outcome, submission_listing

    if cls.venue is None or cls.year is None or invitation is None:
        return None
    listing = submission_listing(cls.venue, cls.year, invitation)
    if listing is None or not is_twin_outcome(listing.track, cls.track, classify_venueid(vid)):
        return None
    why = f" invitation={invitation} (the main track's outcome, not this {listing.track} submission's)"
    return Classification(listing.track, "unknown", cls.venue, cls.year, vid), (said[0], said[1] + why)


def _identity(entry: dict[str, Any], urls: list[str]) -> _Identity | str:
    """The record's identity, or the reason it can't be imported (one of SKIP_REASONS)."""
    venueids = {c["value"] for c in _claims(entry, "venue_id", "openreview_api")}
    forums = {c["value"] for c in _claims(entry, "forum_id", "openreview_url")}
    if len(venueids) > 1 or len(forums) > 1:
        return "ambiguous"
    listing = _listing(entry)
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
        if not FORUM_ID.fullmatch(str(fid)):  # a malformed id skips this entry, not the whole file
            return "unresolved"
        evidence = dict.fromkeys(four, ("openreview_api", f"venueid={vid}"))
        status_from = "venueid"
        invitation = None
        if is_v1(venue, year):  # rejected papers carry the bare path too: the venueid never gives status
            invitation = _invitation(entry, vid)
            cls, evidence["status"], used = _v1_status(entry, vid, cls)
            if used:
                status_from = "venue_string"
                if (twin := _twin_outcome(cls, vid, invitation, evidence["status"])) is not None:
                    cls, evidence["status"] = twin
                    evidence["track"] = evidence["status"]
                elif vid in V1_TRACK_FROM_VENUE:  # the venueid names no track: the string gave it
                    evidence["track"] = evidence["status"]
        url_claims: tuple[tuple[ClaimField, str, str], ...] = (
            ("urls.forum", f"https://openreview.net/forum?id={fid}", "openreview_url"),
        )
        override = False
        if isinstance(listing, tuple):  # an unusable listing never outweighs a venueid; it's ignored
            l_venue, l_year, _, l_cls, l_ev, l_urls = listing
            if (l_venue, l_year) != (venue, year) or l_cls.track not in (cls.track, "unknown"):
                return "conflict"  # decision-005: never silently resolved
            override = cls.status != "accepted"
            # the proceedings decide acceptance; an overruled venueid status stays visible in the evidence
            note = f" (overrides {status_from} status {cls.status})" if override else ""
            evidence["status"] = (l_ev[0], l_ev[1] + note)
            cls = Classification(cls.track, "accepted", venue, year, vid)
            url_claims += _url_fields(l_urls, l_ev[0])
        return _Identity(venue, year, fid, cls, evidence, url_claims, override, invitation)
    if isinstance(listing, str):
        return listing
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
    if ident.invitation is not None:
        provenance.append(
            claim(
                "invitation", ident.invitation, f"scholarmend:openreview_api venueid={ident.cls.venue_id_raw}"
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


def _check_shape(name: str, entries: object) -> list[dict[str, Any]]:
    """resolved.json must be a list of entries, each with a string title and a list of claims whose
    field, source and evidence are strings; anything else is a ValueError naming the entry, not its text."""
    if not isinstance(entries, list):
        raise ValueError(f"{name}: resolved.json is not a list of entries")
    for i, e in enumerate(entries):
        claims = e.get("claims") if isinstance(e, dict) else None
        if not isinstance(e, dict) or not isinstance(e.get("title"), str) or not isinstance(claims, list):
            raise ValueError(f"{name}: resolved.json entry {i} lacks a title or a claims list")
        for c in claims:
            if (
                not isinstance(c, dict)
                or "value" not in c
                or not all(isinstance(c.get(k), str) for k in ("field", "source", "evidence"))
            ):
                raise ValueError(f"{name}: resolved.json entry {i} has a malformed claim")
    return entries


def import_ris(
    mended: Path,
    resolved: Path | None = None,
    name: str | None = None,
    cache_entry: str | None = None,
    offsets: Mapping[str, str] = QUERY_DATE_OFFSETS,
) -> tuple[list[PaperRecord], ImportReport]:
    """Records and counts from one scholarmend output (`mended.ris` + its `resolved.json`). `name` is how
    reports and errors refer to it (default `<its directory>/mended.ris`). `cache_entry` is its cache entry name
    (default its directory's name), which picks its query dates' offset from `offsets`: listed, each
    `fetched_at` is the query date converted to UTC; not listed, the wall time labelled UTC."""
    resolved = resolved or mended.with_name("resolved.json")
    name = name or f"{mended.parent.name}/{mended.name}"
    utc_offset = offsets.get(cache_entry if cache_entry is not None else mended.parent.name)
    zone = UTC if utc_offset is None else _zone(utc_offset)
    ris = parse_file(mended)
    resolved_bytes = resolved.read_bytes()
    try:
        entries = _check_shape(name, json.loads(resolved_bytes.decode("utf-8")))
    except UnicodeDecodeError as e:
        raise ValueError(f"{name}: resolved.json is not UTF-8") from e
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
        queried = datetime.strptime(dates[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=zone).astimezone(UTC)
        r = _record(entry, rec.fields, ident, queried)
        records.append(r)
        overrides += ident.status_override
        track_status.setdefault(r.track, Counter())[r.status] += 1
    report = ImportReport(
        file=name,
        mended_sha256=hashlib.sha256(mended.read_bytes()).hexdigest(),
        resolved_sha256=hashlib.sha256(resolved_bytes).hexdigest(),
        parser_version=version("scholarmend"),
        read=len(ris),
        imported=len(records),
        skipped=dict(skipped),
        abstract_missing=sum(r.abstract is None for r in records),
        unknown_track=sum(r.track == "unknown" for r in records),
        status_overrides=overrides,
        track_status={t: dict(c) for t, c in track_status.items()},
        utc_offset=utc_offset,
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
