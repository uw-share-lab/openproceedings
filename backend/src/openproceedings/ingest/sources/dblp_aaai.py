"""AAAI 1980-2008 from the pinned dblp release (spec 01 §Sources, dblp row; decision-049, milestone B).

ojs.aaai.org starts at AAAI 2010 (Vol. 24); the earlier proceedings are on aaai.org, whose robots.txt asks for 12 h
between requests and whose pages give no abstracts. dblp lists them under `conf/aaai/<year>` (1986, 1991, 1994 and
1996 in two volumes). The release is the one ICML reads (`dblp_table.TABLE`'s pin), read in the same streaming pass
into AAAI's own extract (`dblp.AAAI_SLICE`). `dblp_aaai_table.TABLE` names each year's main-conference keys, the
workshop keys (track `workshop`), the `[[not_paper]]` entries (counted, never records), the years AAAI was not
held, and the official contents' sections (`[[section]]` page ranges and `[[track]]` key rows, decision-050): a
main-key entry in one takes its track (student abstracts, doctoral consortium, demonstrations, IAAI, other), else
`main`. A `conf/aaai/` proceedings key dated 1980-2009 the table doesn't classify, a not-held year dblp holds a key
for, a row whose key the release lacks, a count that differs from the table's, a section range that holds no paper,
or a main-key entry of a year with sections that has no readable start page and no row (`unplaced_page`) stops the
ingest, and these checks run again in every replay. dblp's AAAI keys of 2010 on are never read: the extract holds them, but a record
is made only from a key the table lists, and the table's years end at 2008. Fields as for ICML (`dblp.py`):
title without dblp's closing period, authors without homonym numbers, `urls.doi` from a DOI `ee`, `urls.proceedings`
the dblp record page (linked, never fetched). No abstracts. Every record is `accepted`.
"""

from __future__ import annotations

import logging
import time
from collections import Counter

from pydantic import ValidationError

from openproceedings.ingest.dblp_aaai_table import (
    CHECKED,
    FIRST_YEAR,
    LAST_YEAR,
    TABLE,
    Section,
    Table,
    TrackRow,
    start_page,
)
from openproceedings.ingest.record import (
    Claim,
    ClaimField,
    ClaimValue,
    PaperRecord,
    Source,
    title_evidence,
    title_text,
)
from openproceedings.ingest.sources import dblp
from openproceedings.ingest.sources.common import CrawlError, record_from_claims
from openproceedings.ingest.sources.dblp import Extract, YearResult
from openproceedings.ingest.sources.dblp_xml import DblpEntry
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)

SOURCE: Source = "dblp"
PREFIX = "conf/aaai/"
NATIVE = dblp.NATIVE
__all__ = ["NATIVE", "PREFIX", "SOURCE", "check_extract", "mine_year"]


def _year_of(e: DblpEntry) -> int | None:
    raw = e.fields.get("year", "")
    return int(raw) if raw.isdigit() else None


def check_extract(extract: Extract, table: Table | None = None) -> None:
    """Every `conf/aaai/` proceedings record dated 1980-2009 is a main conference, a workshop or excluded, no
    not-held year has one, every key the table names is in the release under its year, and every `[[not_paper]]`
    is an entry of its year (`CrawlError`). Keys dated 2010 on are ignored."""
    table = table or TABLE
    proceedings = {e.key: e for e in extract.entries if e.type == "proceedings"}
    for key, e in sorted(proceedings.items()):
        year = _year_of(e)
        if year is not None and year not in CHECKED:
            continue
        if year in table.not_held:
            raise CrawlError(f"dblp dates {key} to {year}, a year dblp_aaai.toml records AAAI as not held",
                             reason="table_mismatch")  # fmt: skip
        if table.main_key(key) is None and table.workshop(key) is None and key not in table.excluded:
            raise CrawlError(f"dblp proceedings {key} ({year or 'no year'}) is neither a main conference, a "
                             "workshop nor excluded in dblp_aaai.toml; a person must classify it",
                             reason="unlisted_proceedings")  # fmt: skip
    named = [(k, row.year) for row in table.years.values() for k in row.proceedings]
    named += [(w.key, w.year) for w in table.workshops.values()]
    for key, year in named:
        held = proceedings.get(key)
        if held is None or held.fields.get("year") != str(year):
            raise CrawlError(f"dblp_aaai.toml names {key} for {year}, but release {extract.doi} doesn't hold "
                             "it for that year", reason="table_mismatch")  # fmt: skip
    papers = {e.key: e.fields.get("crossref") for e in extract.entries if e.type == "inproceedings"}
    for tr in table.tracks.values():
        if papers.get(tr.key) not in table.years[tr.year].proceedings:
            raise CrawlError(f"dblp_aaai.toml's track row {tr.key} is not an AAAI {tr.year} main-conference entry "
                             f"of release {extract.doi}", reason="table_mismatch")  # fmt: skip
    for np in table.not_papers.values():
        crossref = papers.get(np.key)
        row = table.years[np.year]
        if crossref not in row.proceedings and not (
            (w := table.workshop(crossref)) is not None and w.year == np.year
        ):
            raise CrawlError(f"dblp_aaai.toml's not_paper {np.key} is not an AAAI {np.year} entry of release "
                             f"{extract.doi}", reason="table_mismatch")  # fmt: skip


def mine_year(year: int, extract: Extract, *, table: Table | None = None) -> YearResult:
    """The year's records from the extract: main-conference and workshop papers, the table's counts checked."""
    table = table or TABLE
    started = time.monotonic()
    if year in table.not_held:
        raise CrawlError(f"AAAI {year}: dblp_aaai.toml records AAAI as not held that year", reason="not_held")
    row = table.years.get(year)
    if row is None or not FIRST_YEAR <= year <= LAST_YEAR:
        raise CrawlError(f"AAAI {year}: no row in dblp_aaai.toml (it covers AAAI {FIRST_YEAR}-{LAST_YEAR}; "
                         "OJS from 2010)", reason="no_year")  # fmt: skip
    by_key: dict[str, tuple[str, str]] = {k: ("main", "main") for k in row.proceedings}
    by_key |= {w.key: ("workshop", w.key) for w in table.workshops.values() if w.year == year}
    report = dblp.DblpReport(SOURCE, "AAAI", year, table.release.doi_url, "primary", table.stated(year))
    report.fetched.append(extract.fetched_at)
    skipped: Counter[str] = report.skipped
    listed: list[tuple[DblpEntry, str]] = []
    groups: Counter[str] = Counter()
    for e in extract.entries:
        if e.type != "inproceedings":
            continue
        crossref = e.fields.get("crossref")
        if crossref not in by_key:
            if e.fields.get("year") == str(year):
                skipped["excluded_proceedings" if crossref in table.excluded else "no_main_crossref"] += 1
            continue
        track, group = by_key[crossref]
        report.listed += 1
        groups[group] += 1
        listed.append((e, track))
    expected = {"main": row.papers} | {w.key: w.papers for w in table.workshops.values() if w.year == year}
    for group, want in expected.items():
        if groups[group] != want:
            keys = ", ".join(row.proceedings) if group == "main" else group
            raise CrawlError(f"AAAI {year}: release {extract.doi} lists {groups[group]} under {keys}, the table "
                             f"verified {want}", reason="count_mismatch")  # fmt: skip
    records: list[PaperRecord] = []
    seen: set[str] = set()
    used: set[Section] = set()
    sectioned = any(s.year == year for s in table.sections)
    for e, track in listed:
        tail = e.key[len(PREFIX) :]
        if not NATIVE.fullmatch(tail):
            raise CrawlError(f"dblp key {e.key} has no native id form", reason="unparsed_key")
        if e.key in table.not_papers:
            skipped["not_paper"] += 1
        elif e.publtype is not None:
            skipped[f"publtype_{e.publtype}"] += 1
        elif e.key in seen:
            skipped["duplicate"] += 1
        else:
            seen.add(e.key)
            rule: Section | TrackRow | None = None
            if track == "main":
                track, rule = table.main_track(e.key, year, e.fields.get("pages"))
                if isinstance(rule, Section):
                    used.add(rule)
                elif rule is None and sectioned and start_page(e.fields.get("pages")) is None:
                    raise CrawlError(f"AAAI {year}: {e.key} has no readable start page ({e.fields.get('pages')!r}), so "
                                     "no dblp_aaai.toml section can place it: give it a [[track]] or [[not_paper]] "
                                     "row", reason="unplaced_page")  # fmt: skip
            try:
                record = _record(year, tail, e, track, extract, table, rule)
            except (ValidationError, ValueError) as err:
                raise CrawlError(f"AAAI {year}: dblp record {e.key} won't build ({type(err).__name__}); check the "
                                 "release and the table", reason="invalid_record") from err  # fmt: skip
            records.append(record)
            report.count(record, "no_abstract")
    if stale := [s for s in table.sections if s.year == year and s not in used]:
        raise CrawlError(f"AAAI {year}: dblp_aaai.toml's section {stale[0].label!r} pp. {stale[0].first}-{stale[0].last} "
                         f"holds no paper of release {extract.doi}: check the table", reason="stale_section")  # fmt: skip
    log.info("dblp_aaai_year_mined", extra={"year": year, "listed": report.listed, "stated": report.stated,
                                            "records": report.records, "tracks": dict(sorted(report.tracks.items())),
                                            "skipped": dict(sorted(skipped.items())),
                                            "ms": elapsed_ms(started, time.monotonic)})  # fmt: skip
    return YearResult(records, [report])


def _track_evidence(year: int, e: DblpEntry, track: str, rule: Section | TrackRow | None) -> str:
    crossref = e.fields["crossref"]
    if isinstance(rule, Section):
        return (f"crossref {crossref}, dblp pages {e.fields.get('pages')} (start page {start_page(e.fields.get('pages'))}): "
                f"in AAAI {year}'s official contents section \"{rule.label}\", pp. {rule.first}-{rule.last} "
                f"(dblp_aaai.toml [[section]], verified {rule.verified.isoformat()}; {rule.source})")  # fmt: skip
    if isinstance(rule, TrackRow):
        return (f"crossref {crossref}: {rule.reason} (dblp_aaai.toml [[track]], verified "
                f"{rule.verified.isoformat()}; {rule.source})")  # fmt: skip
    kind = "main conference" if track == "main" else "workshop"
    return f"crossref {crossref}: AAAI {year} {kind} (dblp_aaai.toml)"


def _record(year: int, tail: str, e: DblpEntry, track: str, extract: Extract, table: Table,
            rule: Section | TrackRow | None = None) -> PaperRecord:  # fmt: skip
    title, replaced = title_text(dblp.clean_title(e.fields.get("title", "")))
    if not title:
        raise ValueError("no title")
    at = extract.fetched_at
    where = f"dblp record {e.key} in release {table.release.doi} (sha256 {table.release.file.sha256[:16]})"
    claims: list[Claim] = []

    def claim(fld: ClaimField, value: ClaimValue, evidence: str) -> None:
        claims.append(Claim(field=fld, value=value, source=SOURCE, url=table.release.doi_url, fetched_at=at,
                            evidence=evidence))  # fmt: skip

    claim("venue", "AAAI", where)
    claim("year", year, f"{where}; AAAI {year} by dblp_aaai.toml")
    claim("title", title, title_evidence(f"{where}: title, dblp's closing period dropped", replaced))
    if authors := tuple(a for a in (dblp.clean_author(x) for x in e.lists.get("author", [])) if a):
        claim("authors", authors, f"{where}: author (dblp homonym numbers dropped)")
    claim("track", track, _track_evidence(year, e, track, rule))
    claim("status", "accepted", f"in AAAI {year}'s proceedings {e.fields['crossref']}: {where}")
    for fld, link in dblp.links(e.key, e.lists.get("ee", []), pdf_hosts=frozenset()).items():
        claim(fld, link, where if fld == "urls.proceedings" else f"{where}: ee")
    return record_from_claims(f"op:aaai:{year}:dblp-{tail}", claims)
