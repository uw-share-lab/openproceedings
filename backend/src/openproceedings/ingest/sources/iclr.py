"""ICLR 2014-2016 accepted-paper archive miner (spec 01 §Sources; TASK-096).

OpenReview cannot supply acceptance for these conference tracks: 2014's notes have no decisions, 2015
has no group, and 2016's conference submissions are absent. The public ICLR archive pages explicitly
list accepted conference papers, so every entry is `accepted` and `main`. They provide titles, authors
and a stable paper target, but no abstract.

The old pages link arXiv or beta OpenReview rather than a proceedings paper path. OpenReview targets keep
their forum id. Other targets use `urls.iclr_archive_target`'s deterministic `iclr-<32 hex>` id, and the
kept `urls.proceedings` claim lets dedup verify that identity.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

from openproceedings.ingest import urls
from openproceedings.ingest.record import Claim, ClaimField, ClaimValue, PaperRecord, Source, Urls
from openproceedings.ingest.sources.common import ListingReport, MinerError, record_from_claims
from openproceedings.ingest.sources.html import collapse, text_of
from openproceedings.ingest.sources.http import Fetcher

log = logging.getLogger(__name__)

SOURCE: Source = "iclr_archive"
CACHE_DIR = "iclr"
HOSTS = frozenset({"iclr.cc"})
LISTINGS = {
    2014: "https://iclr.cc/archive/2014/conference-proceedings/",
    2015: "https://iclr.cc/archive/www/doku.php%3Fid=iclr2015:accepted-main.html",
    2016: "https://iclr.cc/archive/www/doku.php%3Fid=iclr2016:accepted-main.html",
}
VERIFIED_ACCEPTED = {2014: 35, 2015: 31, 2016: 80}

_SECTION = re.compile(r'<h3\b[^>]*\bid="([^"]+)"[^>]*>.*?</h3>(.*?)(?=<h3\b|$)', re.I | re.S)
_ITEM = re.compile(r"<li\b[^>]*>(.*?)</li>", re.I | re.S)
_ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.I | re.S)
_HREF = re.compile(r"""\bhref\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
_PAPER_TARGET = re.compile(
    r"https?://(?:www\.)?(?:arxiv\.org/abs/|(?:beta\.)?openreview\.net/forum\?id=)", re.I
)
_PARAGRAPH = re.compile(r"<p\b[^>]*>(.*?)</p>", re.I | re.S)
_BR = re.compile(r"<br\s*/?>", re.I)


@dataclass(frozen=True, slots=True)
class Entry:
    target: str
    native: str
    title: str
    authors: tuple[str, ...]
    forum: str | None


def _paper_anchor(text: str, base: str) -> tuple[re.Match[str], str, str, str | None] | None:
    for anchor in _ANCHOR.finditer(text):
        href = _HREF.search(anchor.group(1))
        target = urljoin(base, (href.group(1) or href.group(2) or "") if href else "")
        if not _PAPER_TARGET.match(target):
            continue
        identity = urls.iclr_archive_target(target)
        if identity is None:
            continue
        native, canonical = identity
        forum = canonical if not native.startswith("iclr-") else None
        return anchor, native, canonical, forum
    return None


def _authors(text: str) -> tuple[str, ...]:
    plain = text_of(text).lstrip(" ,;:-")
    plain = re.sub(r"\s+and\s+", ", ", plain)
    return tuple(name for name in (collapse(part) for part in re.split(r"\s*[;,]\s*", plain)) if name)


def _list_entries(text: str, base: str) -> list[Entry]:
    entries = []
    for item in _ITEM.finditer(text):
        body = item.group(1)
        found = _paper_anchor(body, base)
        if found is None:
            continue
        anchor, native, target, forum = found
        after = body[anchor.end() :]
        if br := _BR.search(after):
            after = after[br.end() :]
        else:
            after = re.sub(r"<a\b[^>]*>.*?</a>", " ", after, flags=re.I | re.S)
        entries.append(Entry(target, native, text_of(anchor.group(2)), _authors(after), forum))
    return entries


def _google_sites_entries(text: str, base: str) -> list[Entry]:
    """The 2014 page: a title paragraph followed by an author paragraph, rather than `<li>` entries."""
    entries = []
    anchors = [anchor for anchor in _ANCHOR.finditer(text) if _paper_anchor(anchor.group(0), base)]
    for anchor in anchors:
        found = _paper_anchor(anchor.group(0), base)
        assert found is not None
        _same, native, target, forum = found
        tail = text[anchor.end() :]
        title_close = tail.find("</p>")
        authors = _PARAGRAPH.search(tail, title_close + 4) if title_close >= 0 else None
        entries.append(
            Entry(
                target,
                native,
                text_of(anchor.group(2)),
                _authors(authors.group(1)) if authors else (),
                forum,
            )
        )
    return entries


def parse_index(year: int, text: str, base: str) -> list[Entry]:
    """The accepted conference entries, unique by stable target and in page order."""
    if year == 2015:
        parts = [body for section, body in _SECTION.findall(text) if section.startswith("main_conference")]
        entries = [entry for part in parts for entry in _list_entries(part, base)]
    elif year == 2016:
        entries = _list_entries(text, base)
    elif year == 2014:
        entries = _list_entries(text, base) or _google_sites_entries(text, base)
    else:
        raise MinerError(f"ICLR {year}: the archive source covers 2014-2016", reason="before_window")
    unique: dict[str, Entry] = {}
    for entry in entries:
        unique.setdefault(entry.native, entry)
    return list(unique.values())


@dataclass
class YearResult:
    records: list[PaperRecord]
    reports: list[ListingReport]


def mine_year(
    year: int, fetcher: Fetcher, *, refresh_index: bool = False, plan_only: bool = False
) -> YearResult:
    listing = LISTINGS.get(year)
    if listing is None:
        raise MinerError(f"ICLR {year}: the archive source covers 2014-2016", reason="no_listing")
    page = fetcher.get(listing, refresh=refresh_index)
    if not page.ok:
        raise MinerError(f"ICLR {year}: {listing} answered HTTP {page.status}", reason="no_listing")
    entries = parse_index(year, page.text, listing)
    if not entries:
        raise MinerError(
            f"ICLR {year}: the accepted-paper page has no conference entries", reason="empty_listing"
        )
    report = ListingReport(
        SOURCE, "ICLR", year, listing, "primary", VERIFIED_ACCEPTED[year], listed=len(entries)
    )
    report.fetched.append(page.fetched_at)
    if not report.count_ok:
        log.warning(
            "listing_count_mismatch",
            extra={"year": year, "listing": listing, "listed": report.listed, "stated": report.stated},
        )
    if plan_only:
        report.tracks["main"] = len(entries)
        report.to_fetch = 0
        return YearResult([], [report])
    records = [_record(year, listing, page.fetched_at, entry) for entry in entries]
    for record in records:
        report.count(record, "no_abstract")
    log.info("iclr_archive_mined", extra={"year": year, "listing": listing, "records": len(records)})
    return YearResult(records, [report])


def _record(year: int, listing: str, fetched_at: datetime, entry: Entry) -> PaperRecord:
    def claim(field: ClaimField, value: ClaimValue, evidence: str) -> Claim:
        return Claim(
            field=field,
            value=value,
            source=SOURCE,
            url=listing,
            fetched_at=fetched_at,
            evidence=evidence,
        )

    evidence = f"accepted conference paper listed on {listing}"
    claims = [
        claim("venue", "ICLR", evidence),
        claim("year", year, evidence),
        claim("track", "main", evidence),
        claim("status", "accepted", evidence),
        claim("title", entry.title, evidence),
        claim("authors", entry.authors, evidence),
    ]
    if entry.forum:
        claims.append(claim("urls.forum", entry.forum, "accepted-paper target is an OpenReview forum"))
        record_urls = Urls(forum=entry.forum)
    else:
        claims.append(claim("urls.proceedings", entry.target, "accepted-paper target on the archive page"))
        record_urls = Urls(proceedings=entry.target)
    record = record_from_claims(f"op:iclr:{year}:{entry.native}", claims)
    assert record.urls == record_urls
    return record
