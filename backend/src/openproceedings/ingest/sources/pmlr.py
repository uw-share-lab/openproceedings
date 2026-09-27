"""PMLR miner for ICML (spec 01 §Sources, PMLR row; pmlr-proceedings skill; task-053).

The primary source for ICML 2013-2022 and a confirming one for 2023+. A volume is crawled only if the
volume table (`ingest/pmlr_volumes.toml`, `volumes.py`) lists it as an ingested ICML volume; anything else,
including every competition and workshop volume, is refused, never coerced into ICML. The volume index's
heading (`<h1>`/`<h2>` `Volume N: …`) must start with the table's `heading`, or the crawl stops: the table
and the site disagree, and a person must look.

Venue, year and track come from the table (never a page footer, PDF or arXiv date); every listed paper is
`accepted`. Each paper page (`/v<N>/<key>.html`) gives the abstract (only when its `citation_title` is the
listed title), the authors and the PDF; a v235-style OpenReview link on the index gives `urls.forum`.
Claims (source `pmlr`) carry the paper page's URL and the fetch time of the page they came from. The native
id is `pmlr-v<N>-<key>`. The report compares the entries on the index with the table's verified count.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlparse

from pydantic import ValidationError

from openproceedings.ingest import urls
from openproceedings.ingest.record import Claim, ClaimField, ClaimValue, PaperRecord, Source, is_url
from openproceedings.ingest.sources.common import (
    ListingReport,
    MinerError,
    clean_abstract,
    missing_reason,
    record_from_claims,
    titles_match,
)
from openproceedings.ingest.sources.html import collapse, meta, metas, text_of
from openproceedings.ingest.sources.http import Fetcher, Page
from openproceedings.ingest.volumes import VOLUMES, Volume
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)

SOURCE: Source = "pmlr"
CACHE_DIR = "pmlr"  # <data>/cache/pmlr
HOST = "proceedings.mlr.press"
HOSTS = frozenset({HOST})
PROGRESS_SECONDS = 30.0

_HEADING = re.compile(r"<h([12])\b[^>]*>(.*?)</h\1\s*>", re.I | re.S)
_VOLUME_PREFIX = re.compile(r"Volume\s+([0-9]+)\s*:\s*")
_PAPER = re.compile(r"<div\s+class=\"paper\"\s*>(.*?)</div>", re.I | re.S)
_TITLE = re.compile(r"<p\s+class=\"title\"\s*>(.*?)</p>", re.I | re.S)
_AUTHORS = re.compile(r"<span\s+class=\"authors\"\s*>(.*?)</span>", re.I | re.S)
_HREF = re.compile(r"""<a\b[^>]*\bhref\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
_ABSTRACT = re.compile(r"<div\b[^>]*\bid=\"abstract\"[^>]*>(.*?)</div>", re.I | re.S)


def ingestable(number: int) -> Volume:
    """The table's row for an ingested ICML volume, or a MinerError: a volume the table doesn't list, or
    lists as competition, workshop or another venue, is never crawled as ICML."""
    volume = VOLUMES.get(number)
    if volume is None:
        raise MinerError(f"PMLR v{number} is not in the volume table: out of scope", reason="unlisted_volume")
    if not volume.ingested or volume.venue != "ICML":
        raise MinerError(
            f"PMLR v{number} is a {volume.venue} {volume.track} volume ({volume.role}): not ingested",
            reason="out_of_scope_volume",
        )
    return volume


@dataclass(frozen=True, slots=True)
class Entry:
    url: str  # the paper page (`abs`)
    title: str
    authors: tuple[str, ...]
    pdf: str | None
    forum: str | None  # an OpenReview forum id (v235 links one)


def heading(text: str) -> tuple[int, str] | None:
    """(volume number, the rest) from the page's first `<h1>`/`<h2>` reading `Volume N: …`."""
    for m in _HEADING.finditer(text):
        title = text_of(m.group(2))
        if prefix := _VOLUME_PREFIX.match(title):
            return int(prefix.group(1)), title[prefix.end() :]
    return None


def parse_volume_index(text: str, base: str) -> tuple[list[Entry], int]:
    """The entries on a volume index and the number of `<div class="paper">` blocks without an `abs` link."""
    entries: list[Entry] = []
    unlinked = 0
    for block in _PAPER.finditer(text):
        body = block.group(1)
        hrefs = [urljoin(base, h.group(1) or h.group(2) or "") for h in _HREF.finditer(body)]
        abs_url = next((h for h in hrefs if urlparse(h).path.endswith(".html") and urls.pmlr(h)), None)
        if abs_url is None:
            unlinked += 1
            continue
        pdf = next((h for h in hrefs if h.endswith(".pdf") and "-supp" not in h and urls.pmlr(h)), None)
        forum = next((f for h in hrefs if (f := urls.forum_id(h))), None)
        title = _TITLE.search(body)
        authors = _AUTHORS.search(body)
        entries.append(
            Entry(
                url=abs_url, title=text_of(title.group(1)) if title else "",
                authors=tuple(a for a in (collapse(p) for p in text_of(authors.group(1)).split(",")) if a)
                if authors else (),
                pdf=pdf, forum=forum,
            )
        )  # fmt: skip
    return entries, unlinked


@dataclass(frozen=True, slots=True)
class PaperPage:
    title: str | None
    authors: tuple[str, ...]
    abstract: str | None
    pdf: str | None


def parse_paper_page(text: str) -> PaperPage:
    abstract = _ABSTRACT.search(text)
    return PaperPage(
        title=meta(text, "citation_title"),
        authors=tuple(a for a in metas(text, "citation_author") if a),
        abstract=text_of(abstract.group(1)) if abstract else None,
        pdf=meta(text, "citation_pdf_url"),
    )


@dataclass
class VolumeResult:
    records: list[PaperRecord]
    report: ListingReport

    @property
    def reports(self) -> tuple[ListingReport]:
        return (self.report,)


def mine_volume(
    number: int, fetcher: Fetcher, *, refresh_index: bool = False, plan_only: bool = False
) -> VolumeResult:
    """Every paper on an ingested ICML volume, as records (`plan_only`: read the index, fetch no paper)."""
    volume = ingestable(number)
    assert volume.year is not None and volume.heading is not None  # the table checks ingested rows
    index = fetcher.get(volume.index_url, refresh=refresh_index)
    if not index.ok:
        raise MinerError(
            f"PMLR v{number}: {volume.index_url} answered HTTP {index.status}", reason="no_listing"
        )
    found = heading(index.text)
    if found is None or found[0] != number or not found[1].startswith(volume.heading):
        raise MinerError(
            f"PMLR v{number}: the page heading does not name {volume.heading!r}; check the volume table",
            reason="heading_mismatch",
        )
    entries, unlinked = parse_volume_index(index.text, volume.index_url)
    report = ListingReport(
        SOURCE, "ICML", volume.year, volume.index_url, volume.role, volume.papers, volume=number,
        listed=len(entries) + unlinked,
    )  # fmt: skip
    report.fetched.append(index.fetched_at)
    if unlinked:
        report.skipped["no_link"] = unlinked
    records: list[PaperRecord] = []
    seen: set[str] = set()
    started = last = time.monotonic()
    log.info("pmlr_volume_started", extra={"volume": number, "year": volume.year, "entries": len(entries)})
    for n, entry in enumerate(entries, 1):
        parts = urls.pmlr(entry.url)
        if parts is None or parts[0] != number:
            report.skipped["wrong_volume"] += 1
            continue
        if urlparse(entry.url).netloc.lower() not in HOSTS:  # never fetched off the PMLR host, counted
            report.skipped["off_host"] += 1
            continue
        native = f"pmlr-v{number}-{parts[1]}"
        if native in seen:
            report.skipped["duplicate"] += 1
            continue
        seen.add(native)
        if not entry.title:
            report.skipped["no_title"] += 1
            continue
        if plan_only:
            report.tracks[volume.track] += 1
            report.to_fetch = (report.to_fetch or 0) + (not fetcher.is_cached(entry.url))
            continue
        page = fetcher.get(entry.url, keep_absent=True)
        report.fetched.append(page.fetched_at)
        try:
            record, missing = _record(volume, native, entry, index, page)
        except (ValidationError, ValueError) as e:
            report.skipped["invalid"] += 1
            log.warning(
                "pmlr_record_invalid", extra={"volume": number, "native": native, "error": type(e).__name__}
            )
            continue
        records.append(record)
        report.count(record, missing)
        if time.monotonic() - last >= PROGRESS_SECONDS:
            last = time.monotonic()
            log.info("pmlr_volume_progress", extra={"volume": number, "done": n, "of": len(entries)})
    log.info(
        "pmlr_volume_mined",
        extra={"volume": number, "year": volume.year, "listed": report.listed, "stated": report.stated,
               "records": report.records, "abstract_missing": report.abstract_missing,
               "ms": elapsed_ms(started, time.monotonic)},
    )  # fmt: skip
    if not report.count_ok:
        log.warning(
            "listing_count_mismatch",
            extra={
                "volume": number,
                "listing": report.listing,
                "listed": report.listed,
                "stated": report.stated,
            },
        )
    if report.skipped:
        log.warning("listing_attention", extra={"volume": number, "skipped": dict(report.skipped)})
    return VolumeResult(records, report)


def _record(
    volume: Volume, native: str, entry: Entry, index: Page, page: Page
) -> tuple[PaperRecord, str | None]:
    """The record and, when it has no abstract, why (`common.missing_reason`)."""
    assert volume.year is not None
    title = collapse(entry.title)
    claims: list[Claim] = []

    def claim(fld: ClaimField, value: ClaimValue, evidence: str, at: datetime) -> None:
        claims.append(
            Claim(field=fld, value=value, source=SOURCE, url=entry.url, fetched_at=at, evidence=evidence)
        )

    table = f"volume table v{volume.number} ({volume.role}, verified {volume.verified.isoformat()})"
    listed_on = f"volume index {volume.index_url}"
    claim("venue", volume.venue, table, index.fetched_at)
    claim("year", volume.year, table, index.fetched_at)
    claim("track", volume.track, table, index.fetched_at)
    claim("status", "accepted", f"listed on {volume.index_url}", index.fetched_at)
    claim("title", title, listed_on, index.fetched_at)
    claim("urls.proceedings", entry.url, listed_on, index.fetched_at)
    if entry.forum:
        claim("urls.forum", f"https://openreview.net/forum?id={entry.forum}", listed_on, index.fetched_at)

    parsed = parse_paper_page(page.text) if page.ok else None
    matches = parsed is not None and titles_match(title, parsed.title)
    abstract = clean_abstract(parsed.abstract) if parsed is not None and matches else None
    missing = missing_reason(page.ok, matches, abstract)
    if abstract is not None:
        claim("abstract", abstract, "div#abstract (citation_title matches the listing)", page.fetched_at)
    if parsed is not None and matches and parsed.authors:
        claim("authors", parsed.authors, "citation_author", page.fetched_at)
    elif entry.authors:
        claim("authors", entry.authors, listed_on, index.fetched_at)
    page_pdf = parsed.pdf if parsed is not None and matches else None
    if page_pdf and is_url(page_pdf) and urls.native(page_pdf) == native:
        claim("urls.pdf", page_pdf, "citation_pdf_url", page.fetched_at)
    elif entry.pdf and is_url(entry.pdf) and urls.native(entry.pdf) == native:
        claim("urls.pdf", entry.pdf, listed_on, index.fetched_at)
    return record_from_claims(f"op:icml:{volume.year}:{native}", claims), missing
