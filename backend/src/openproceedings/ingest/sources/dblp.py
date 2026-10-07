"""ICML 1988–2012 from a pinned dblp snapshot release (spec 01 §Sources, dblp row; decision-047; TASK-205).

PMLR starts at ICML 2013 (v28); the earlier proceedings are in print and scattered. dblp lists them, but
dblp.org forbids crawling (robots.txt `Disallow: /`, an Anubis challenge on its pages and API), so its pages
and API are never fetched. Its sanctioned bulk route is the monthly snapshot XML release on Dagstuhl DROPS (CC0,
one DOI per release). `dblp_table.TABLE` pins one release and its DTD by DOI, size and sha256, and names each
year's main-conference proceedings keys.

`op ingest dblp --year 1988-2012`:
1. downloads the pinned release and DTD into `<cache>/dblp/release/` through the shared HTTP layer's
   `fetch_file` (drops.dagstuhl.de only, no redirect, the sha256 checked; a verified copy is not fetched again);
2. reads its `conf/icml/` records once, streaming (`dblp_xml.read_stream`; the file is never loaded whole), into
   `<cache>/dblp/extract/<release sha256>.json`, and checks them against the table (`check_extract`): a
   `conf/icml/` proceedings key of 1988–2012 that the table neither lists nor excludes stops the ingest;
3. for each year, crawls the official ICML pages `icml_sites.toml` lists for its abstracts (`icml_sites.py`,
   TASK-206), then writes the year's crawl marker. `op snapshot build` replays each marked year from the extract
   and the page cache alone.

A record is an `inproceedings` whose `crossref` is one of the year's main-conference keys: track `main`
(the table says so; dblp has no track), status `accepted` (dblp lists published papers), title, authors, year
and links from the release. dblp has no abstracts, so `abstract` is null unless an official ICML page gives one
(`_match`, from the pages `icml_sites.read_year` reads). Every claim's url is the release's DOI and its evidence names the dblp key and the
release, so a reviewer can find the exact record in the exact file.

Text, as dblp writes it: a title's closing period is dblp's convention, not the paper's, and is dropped (one
`.`; a title ending in `?`, `!` or `..` is kept as written); inline markup (`<i>`, `<sub>`, `<sup>`) is
flattened to its text. An author's homonym number (`Wei Wang 0001`) is dblp's disambiguation and is dropped.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from openproceedings import storage
from openproceedings.ingest import urls
from openproceedings.ingest.dblp_table import FIRST_YEAR, LAST_YEAR, TABLE, Table
from openproceedings.ingest.dedup import title_key
from openproceedings.ingest.record import (
    Claim,
    ClaimField,
    ClaimValue,
    PaperRecord,
    Source,
    Urls,
    controls_evidence,
    is_url,
    title_evidence,
    title_text,
)
from openproceedings.ingest.sources.common import (
    CrawlError,
    ListingReport,
    pdf_codes_evidence,
    record_from_claims,
)
from openproceedings.ingest.sources.dblp_xml import DblpEntry, read_stream
from openproceedings.ingest.sources.http import FileEntry, Heartbeat, StreamTransport, fetch_file
from openproceedings.ingest.sources.icml_sites import SOURCE as SITE_SOURCE
from openproceedings.ingest.sources.icml_sites import SiteAbstract, SiteYear
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)

SOURCE: Source = "dblp"
CACHE_DIR = "dblp"  # <data>/cache/dblp
HOSTS = frozenset({"drops.dagstuhl.de"})
PREFIX = "conf/icml/"
NATIVE = re.compile(r"[A-Za-z0-9_-]+")  # the key after `conf/icml/`, as the native id `dblp-<it>` takes it
EXTRACT_FORMAT = "1"
_HOMONYM = re.compile(r"\s+[0-9]{4}\Z")
_DOI_URL = re.compile(r"https?://(?:dx\.)?doi\.org/(10\.\S+)\Z", re.IGNORECASE)


def release_dir(cache: Path) -> Path:
    return cache / CACHE_DIR / "release"


def extract_path(cache: Path, table: Table = TABLE) -> Path:
    return cache / CACHE_DIR / "extract" / f"{table.release.file.sha256}.json"


# --- the release and its extract -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Extract:
    """The release's `conf/icml/` records, and when the release was downloaded (every claim's fetch time)."""

    doi: str
    sha256: str
    fetched_at: datetime
    entries: tuple[DblpEntry, ...]


def fetch_release(cache: Path, transport: StreamTransport | None, table: Table = TABLE,
                  verify: Callable[[Path], str] | None = None) -> tuple[FileEntry, FileEntry]:  # fmt: skip
    """The pinned release and DTD on disk (downloaded once; a copy that doesn't hash to its pin is fetched
    again, or refused offline)."""
    kw: dict[str, Any] = {"hosts": HOSTS} | ({"verify": verify} if verify else {})
    out = release_dir(cache)
    dtd = fetch_file(table.dtd.file, out / table.dtd.filename, transport, **kw)
    release = fetch_file(table.release.file, out / table.release.filename, transport, **kw)
    return release, dtd


def release_on_disk(cache: Path, table: Table = TABLE) -> bool:
    """Whether the pinned release has been downloaded (not re-hashed: `prepare` verifies it)."""
    return (release_dir(cache) / table.release.filename).exists()


def prepare(cache: Path, stream: StreamTransport | None, table: Table = TABLE) -> Extract:
    """The pinned release on disk, its extract written (again when the release had to be fetched), and the
    extract checked against the table; one run at a time (`<cache>/dblp/.lock`)."""
    with storage.exclusive(cache / CACHE_DIR):
        release, dtd = fetch_release(cache, stream, table)
        extract = None
        if release.cached and extract_path(cache, table).exists():
            try:
                extract = load_extract(cache, table)
            except CrawlError as e:  # written under another DTD pin or extract format: read the release again
                log.info("dblp_extract_stale", extra={"doi": table.release.doi, "reason": e.reason})
        if extract is None:
            extract = write_extract(cache, release, dtd, table)
    check_extract(extract, table)
    return extract


def write_extract(
    cache: Path, release: FileEntry, dtd: FileEntry, table: Table = TABLE,
    monotonic: Callable[[], float] = time.monotonic,
) -> Extract:  # fmt: skip
    """Read the release's `conf/icml/` records (streaming) into the extract file, atomically; a
    `dblp_extract_progress` line when a `Heartbeat` on `monotonic` is due."""
    started = time.monotonic()
    beat = Heartbeat(monotonic)
    log.info("dblp_extract_started", extra={"doi": table.release.doi, "bytes": table.release.file.size})

    def progress(lines: int, kept: int) -> None:
        if beat.due():
            log.info(
                "dblp_extract_progress", extra={"doi": table.release.doi, "lines": lines, "records": kept}
            )

    entries = read_stream(release.path, dtd.path.read_bytes(), table.dtd.filename, PREFIX, progress)
    extract = Extract(table.release.doi, table.release.file.sha256, release.fetched_at, tuple(entries))
    storage.write_json(extract_path(cache, table), {
        "format": EXTRACT_FORMAT, "release_doi": extract.doi, "release_sha256": extract.sha256,
        "dtd_sha256": table.dtd.file.sha256, "fetched_at": extract.fetched_at.isoformat(),
        "entries": [e.to_json() for e in entries],
    })  # fmt: skip
    log.info("dblp_extract_written", extra={"doi": extract.doi, "entries": len(entries),
                                            "ms": elapsed_ms(started, time.monotonic)})  # fmt: skip
    return extract


def load_extract(cache: Path, table: Table = TABLE) -> Extract:
    """The pinned release's extract, from the cache alone (a snapshot build never reads the release itself)."""
    path = extract_path(cache, table)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CrawlError(f"no dblp extract for release {table.release.doi}; run op ingest dblp",
                         reason="not_cached") from None  # fmt: skip
    except (OSError, ValueError) as e:
        raise CrawlError(f"dblp extract {path.name} is unreadable ({type(e).__name__}); delete it and run op "
                         "ingest dblp", reason="crawl_file_invalid") from None  # fmt: skip
    try:
        if (raw["format"], raw["release_doi"], raw["release_sha256"], raw["dtd_sha256"]) != (
            EXTRACT_FORMAT,
            table.release.doi,
            table.release.file.sha256,
            table.dtd.file.sha256,
        ):
            raise ValueError("names another release")
        fetched = datetime.fromisoformat(raw["fetched_at"])
        if fetched.tzinfo is None:
            raise ValueError("naive fetched_at")
        entries = tuple(DblpEntry.from_json(e) for e in raw["entries"])
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise CrawlError(f"dblp extract {path.name} is malformed ({e}); delete it and run op ingest dblp",
                         reason="crawl_file_invalid") from None  # fmt: skip
    return Extract(raw["release_doi"], raw["release_sha256"], fetched, entries)


def check_extract(extract: Extract, table: Table = TABLE) -> None:
    """Every `conf/icml/` proceedings record of 1988–2012 is a year's main conference or excluded, and every key
    the table names is in the release with the table's year: otherwise the table is stale (`CrawlError`)."""
    proceedings = {e.key: e for e in extract.entries if e.type == "proceedings"}
    for key, e in sorted(proceedings.items()):
        year = int(e.fields["year"]) if e.fields.get("year", "").isdigit() else None
        in_range = year is None or FIRST_YEAR <= year <= LAST_YEAR  # no readable year: it may be in range
        if in_range and table.main_key(key) is None and key not in table.excluded:
            raise CrawlError(f"dblp proceedings {key} ({year or 'no year'}) is neither a main conference nor "
                             "excluded in dblp_icml.toml; a person must classify it",
                             reason="unlisted_proceedings")  # fmt: skip
    for row in table.years.values():
        for key in row.proceedings:
            held = proceedings.get(key)
            if held is None or held.fields.get("year") != str(row.year):
                raise CrawlError(f"dblp_icml.toml names {key} for {row.year}, but release {extract.doi} "
                                 "doesn't hold it for that year", reason="table_mismatch")  # fmt: skip
        listed = sum(e.type == "inproceedings" and e.fields.get("crossref") in row.proceedings
                     for e in extract.entries)  # fmt: skip
        if (
            listed != row.papers
        ):  # the table's count was verified against this release: a difference is a read error
            raise CrawlError(f"ICML {row.year}: release {extract.doi} lists {listed} papers under "
                             f"{', '.join(row.proceedings)}, the table verified {row.papers}", reason="table_mismatch")  # fmt: skip
    papers = {e.key: e.fields.get("crossref") for e in extract.entries if e.type == "inproceedings"}
    for np in table.not_papers.values():
        if papers.get(np.key) not in table.years[np.year].proceedings:
            raise CrawlError(f"dblp_icml.toml's not_paper {np.key} is not an ICML {np.year} paper of release "
                             f"{extract.doi}", reason="table_mismatch")  # fmt: skip


# --- records ---------------------------------------------------------------------------------------------------


@dataclass(kw_only=False)
class DblpReport(ListingReport):
    """One ICML year from the release: the shared listing counts, plus the official pages' abstracts
    (TASK-206): entries read off them, attached, and why the rest weren't."""

    sites: list[str] = field(default_factory=list)  # the pages whose abstracts were read, as fetched
    site_entries: int = 0  # papers (title + abstract) read off the pages
    abstract_attached: int = 0
    site_unmatched: int = 0  # page entries whose title key no record of the year has
    site_ambiguous: int = 0  # page entries whose title key two entries, or two records, share
    site_unjoined: int = 0  # 2007's halves: a paper number with a title but no abstract page, or the reverse
    site_dropped: int = 0  # page entries with no usable title or abstract (an empty abstract page)
    site_withheld: int = 0  # 1997/1998 submission abstracts withheld for a contact detail (TASK-207)
    abstracts_as_submitted: bool = False  # the pages are the submissions (1997, 1998): abstracts as submitted

    def to_manifest(self) -> dict[str, Any]:
        out = super().to_manifest()
        if self.sites:
            out |= {"sites": list(self.sites), "site_entries": self.site_entries,
                    "abstract_attached": self.abstract_attached, "site_unmatched": self.site_unmatched,
                    "site_ambiguous": self.site_ambiguous, "site_unjoined": self.site_unjoined,
                    "site_dropped": self.site_dropped, "site_withheld": self.site_withheld,
                    "abstracts_as_submitted": self.abstracts_as_submitted}  # fmt: skip
        return dict(sorted(out.items()))


@dataclass
class YearResult:
    records: list[PaperRecord]
    reports: list[DblpReport]


def clean_title(raw: str) -> str:
    """dblp's title without dblp's closing period (one `.`, not `..`)."""
    return raw[:-1] if raw.endswith(".") and not raw.endswith("..") else raw


def clean_author(raw: str) -> str:
    return _HOMONYM.sub("", raw)


def selected(extract: Extract, year: int, table: Table = TABLE) -> tuple[list[DblpEntry], Counter[str]]:
    """The year's main-conference papers (inproceedings crossref'ing its keys), and the release's other
    `conf/icml/` inproceedings of that year counted by why they aren't records."""
    row = table.years.get(year)
    if row is None:
        raise CrawlError(f"ICML {year}: no row in dblp_icml.toml (it covers {FIRST_YEAR}-{LAST_YEAR})",
                         reason="no_year")  # fmt: skip
    keep: list[DblpEntry] = []
    skipped: Counter[str] = Counter()
    for e in extract.entries:
        if e.type != "inproceedings":
            continue
        crossref = e.fields.get("crossref")
        if crossref in row.proceedings:
            keep.append(e)
        elif e.fields.get("year") == str(year):
            skipped["excluded_proceedings" if crossref in table.excluded else "no_main_crossref"] += 1
    return keep, skipped


def mine_year(
    year: int, extract: Extract, *, site: SiteYear | None = None, table: Table = TABLE
) -> YearResult:
    """The year's records from the extract, each with the abstract an official ICML page gives it when exactly
    one of the year's page entries and exactly one of its papers share a title key (`icml_sites`, TASK-206)."""
    started = time.monotonic()
    entries, skipped = selected(extract, year, table)
    row = table.years[year]
    report = DblpReport(SOURCE, "ICML", year, table.release.doi_url, "primary", row.papers,
                        listed=len(entries))  # fmt: skip
    report.skipped.update(skipped)
    report.fetched.append(extract.fetched_at)
    kept: list[tuple[str, DblpEntry, str]] = []  # (native tail, entry, title)
    seen: set[str] = set()
    for e in entries:
        tail = e.key[len(PREFIX) :]
        if not NATIVE.fullmatch(tail):
            report.skipped["unparsed_key"] += 1
        elif e.publtype is not None:  # `withdrawn`, `informal`, …: not a published conference paper
            report.skipped[f"publtype_{e.publtype}"] += 1
        elif e.key in seen:
            report.skipped["duplicate"] += 1
        else:
            seen.add(e.key)
            kept.append((tail, e, title_text(clean_title(e.fields.get("title", "")))[0]))
    abstracts = _match(kept, site, report)
    records: list[PaperRecord] = []
    for tail, e, _title in kept:
        found = abstracts.get(e.key)
        try:
            record = _record(year, tail, e, extract, table, found)
        except (ValidationError, ValueError) as err:
            report.skipped["invalid"] += 1
            log.debug("dblp_record_invalid", extra={"year": year, "key": e.key, "error": type(err).__name__})
            continue
        records.append(record)
        report.count(record, None if record.abstract else "no_abstract", found.spaced if found else 0,
                     found.pdf_codes if found else 0)  # fmt: skip
    report.abstract_attached = sum(r.abstract is not None for r in records)
    log.info("dblp_year_mined", extra={
        "year": year, "listed": report.listed, "stated": report.stated, "records": report.records,
        "abstract_attached": report.abstract_attached, "abstract_missing": report.abstract_missing,
        "site_entries": report.site_entries, "site_unmatched": report.site_unmatched,
        "site_ambiguous": report.site_ambiguous, "site_unjoined": report.site_unjoined,
        "abstract_control_characters": report.abstract_control_characters,
        "abstract_pdf_codes": report.abstract_pdf_codes, "abstract_short": report.abstract_short,
        "site_dropped": report.site_dropped, "site_withheld": report.site_withheld, "ms": elapsed_ms(started, time.monotonic)})  # fmt: skip
    if not report.count_ok:
        log.warning("listing_count_mismatch", extra={"year": year, "listing": report.listing,
                                                     "listed": report.listed, "stated": report.stated})  # fmt: skip
    if report.skipped.get("invalid") or report.skipped.get("unparsed_key"):
        log.warning("listing_attention", extra={"year": year, "listing": report.listing, "unknown_track": 0,
                                                "skipped": dict(report.skipped)})  # fmt: skip
    return YearResult(records, [report])


def _match(
    kept: list[tuple[str, DblpEntry, str]], site: SiteYear | None, report: DblpReport
) -> dict[str, SiteAbstract]:
    """dblp key → the one page entry whose title key is that paper's alone (the dedup title key: the token
    contract over the NFC title, never a fuzzy match). A key two page entries or two papers share attaches
    nothing (`site_ambiguous`); a page entry no paper's key matches is `site_unmatched`."""
    if site is None:
        return {}
    report.sites = list(site.pages)
    report.site_entries = len(site.entries)
    report.site_unjoined = site.unjoined
    report.site_dropped = site.dropped
    report.site_withheld = site.withheld
    report.abstracts_as_submitted = site.as_submitted
    report.fetched += site.fetched
    papers: dict[str, list[str]] = defaultdict(list)
    for _tail, e, title in kept:
        if k := title_key(title):
            papers[k].append(e.key)
    pages: dict[str, list[SiteAbstract]] = defaultdict(list)
    for entry in site.entries:
        pages[title_key(entry.title)].append(entry)
    out: dict[str, SiteAbstract] = {}
    for k, group in pages.items():
        if not k or k not in papers:
            report.site_unmatched += len(group)
        elif len(group) > 1 or len(papers[k]) > 1:
            report.site_ambiguous += len(group)
        else:
            out[papers[k][0]] = group[0]
    return out


def _record(year: int, tail: str, e: DblpEntry, extract: Extract, table: Table,
            found: SiteAbstract | None = None) -> PaperRecord:  # fmt: skip
    title, replaced = title_text(clean_title(e.fields.get("title", "")))
    if not title:
        raise ValueError("no title")
    at = extract.fetched_at
    where = f"dblp record {e.key} in release {table.release.doi} (sha256 {table.release.file.sha256[:16]})"
    claims: list[Claim] = []

    def claim(fld: ClaimField, value: ClaimValue, evidence: str) -> None:
        claims.append(Claim(field=fld, value=value, source=SOURCE, url=table.release.doi_url, fetched_at=at,
                            evidence=evidence))  # fmt: skip

    claim("venue", "ICML", where)
    claim("year", year, f"{where}; ICML {year} by dblp_icml.toml")
    claim("title", title, title_evidence(f"{where}: title, dblp's closing period dropped", replaced))
    if authors := tuple(a for a in (clean_author(x) for x in e.lists.get("author", [])) if a):
        claim("authors", authors, f"{where}: author (dblp homonym numbers dropped)")
    if (np := table.not_papers.get(e.key)) is not None:  # in the proceedings, but no paper: never `main`
        claim("track", "other", f"crossref {e.fields['crossref']}: in the ICML {year} proceedings but not a paper "
                                f"({np.kind}; dblp_icml.toml not_paper: {np.reason})")  # fmt: skip
    else:
        claim(
            "track", "main", f"crossref {e.fields['crossref']}: ICML {year} main conference (dblp_icml.toml)"
        )
    claim("status", "accepted", f"in ICML {year}'s proceedings {e.fields['crossref']}: {where}")
    for fld, link in links(e.key, e.lists.get("ee", [])).items():
        claim(fld, link, where if fld == "urls.proceedings" else f"{where}: ee")
    if found is not None:
        claims.append(Claim(field="abstract", value=found.abstract, source=SITE_SOURCE, url=found.url,
                            fetched_at=found.fetched_at,
                            evidence=pdf_codes_evidence(controls_evidence(
                                f"{found.evidence}; its title key is dblp record {e.key}'s", found.spaced),
                                found.pdf_codes)))  # fmt: skip
    return record_from_claims(f"op:icml:{year}:dblp-{tail}", claims)


# the hosts whose PDF an `ee` may name as the paper's (icml.cc's 2010-2012 papers); dblp also lists DOIs (kept as
# `urls.doi`), AAAI's ICML 2003 landing pages, wikidata and ORKG entries (dropped: the dblp page links them all)
PDF_HOSTS = frozenset({"icml.cc", "www.icml.cc"})


def links(key: str, ee: Iterable[str]) -> dict[ClaimField, str]:
    """`urls.proceedings`: the record's dblp page (`urls.dblp_record_url`, which names its native id, as dedup
    requires of a proceedings record; linked, never fetched); `urls.doi` from the first doi.org `ee`; `urls.pdf`
    from the first PDF on a `PDF_HOSTS` host. Every other link is dropped."""
    out: dict[ClaimField, str] = {"urls.proceedings": urls.dblp_record_url(key)}
    for link in ee:
        if (m := _DOI_URL.match(link)) is not None:
            try:
                doi = Urls(doi=m.group(1)).doi
            except ValidationError:
                continue
            if doi:
                out.setdefault("urls.doi", doi)
        elif is_url(link) and (urlparse(link).hostname or "").lower() in PDF_HOSTS \
                and urlparse(link).path.lower().endswith(".pdf"):  # fmt: skip
            out.setdefault("urls.pdf", link)
    return out
