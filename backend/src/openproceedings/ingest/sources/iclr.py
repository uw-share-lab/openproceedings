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
from openproceedings.ingest.record import (
    Claim,
    ClaimField,
    ClaimValue,
    PaperRecord,
    Source,
    Urls,
    title_evidence,
    title_text,
)
from openproceedings.ingest.sources.common import ListingReport, MinerError, record_from_claims
from openproceedings.ingest.sources.html import Element, collapse, node_text, parse, text_after
from openproceedings.ingest.sources.http import Fetcher, canonical

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

_PAPER_TARGET = re.compile(
    r"https?://(?:www\.)?(?:arxiv\.org/abs/|(?:beta\.)?openreview\.net/forum\?id=)", re.I
)


@dataclass(frozen=True, slots=True)
class Entry:
    target: str
    native: str
    title: str
    authors: tuple[str, ...]
    forum: str | None


def _paper_anchor(node: Element, base: str) -> tuple[Element, str, str, str | None] | None:
    for anchor in [node] if node.tag == "a" else node.iter("a"):
        target = urljoin(base, anchor.attributes.get("href", ""))
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
    plain = collapse(text).lstrip(" ,;:-")
    plain = re.sub(r"\s+and\s+", ", ", plain)
    return tuple(name for name in (collapse(part) for part in re.split(r"\s*[;,]\s*", plain)) if name)


def _list_entries(items: list[Element], base: str) -> list[Entry]:
    entries = []
    for item in items:
        found = _paper_anchor(item, base)
        if found is None:
            continue
        anchor, native, target, forum = found
        entries.append(Entry(target, native, node_text(anchor), _authors(text_after(item, anchor)), forum))
    return entries


_INLINE = frozenset({"span", "b", "strong", "i", "em", "font"})


def _bare_authors(anchor: Element) -> Element | None:
    """The authors of a paper link outside any `<p>` (the live 2014 page sets one of its 35 papers as
    `<span><b><a>…</a></b></span><div><i>authors</i>…</div>`, TASK-124): the first inline element of the block
    right after the link's outermost inline wrapper. Only that inline element: on the live page the block
    goes on to hold every later entry of the page."""
    wrapper = anchor
    while wrapper.parent is not None and wrapper.parent.tag in _INLINE:
        wrapper = wrapper.parent
    if wrapper.parent is None:
        return None
    siblings = [child for child in wrapper.parent.children if isinstance(child, Element)]
    position = next(
        i for i, child in enumerate(siblings) if child is wrapper
    )  # identity: elements compare by value
    after = siblings[position + 1 :]
    if not after or after[0].tag not in ("div", "p"):
        return None
    for child in after[0].children:  # the block must open with that inline element, not with loose text
        if isinstance(child, Element):
            return child if child.tag in _INLINE else None
        if child.strip():
            return None
    return None


def _google_sites_entries(root: Element, base: str) -> list[Entry]:
    """The 2014 page: a title paragraph followed by an author paragraph, rather than `<li>` entries; or, for a
    link outside any paragraph, the block right after it (`_bare_authors`)."""
    entries = []
    paragraphs = root.iter("p")
    for anchor in root.iter("a"):
        found = _paper_anchor(anchor, base)
        if found is None:
            continue
        _same, native, target, forum = found
        paragraph = anchor.parent
        while paragraph is not None and paragraph.tag != "p":
            paragraph = paragraph.parent
        if paragraph is None:
            authors = _bare_authors(anchor)
        else:
            index = next(i for i, p in enumerate(paragraphs) if p is paragraph)  # identity, not value
            authors = paragraphs[index + 1] if index + 1 < len(paragraphs) else None
        entries.append(
            Entry(
                target,
                native,
                node_text(anchor),
                _authors(node_text(authors)) if authors else (),
                forum,
            )
        )
    return entries


def parse_index(year: int, text: str, base: str) -> list[Entry]:
    """The accepted conference entries, unique by stable target and in page order."""
    root = parse(text, canonical(base))
    if year == 2015:
        ordered = root.iter()
        items: list[Element] = []
        in_main = False
        for node in ordered:
            if node.tag == "h3":
                in_main = node.attributes.get("id", "").startswith("main_conference")
            elif in_main and node.tag == "li":
                items.append(node)
        entries = _list_entries(items, base)
    elif year == 2016:
        entries = _list_entries(root.iter("li"), base)
    elif year == 2014:
        entries = _list_entries(root.iter("li"), base) or _google_sites_entries(root, base)
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
    title, replaced = title_text(entry.title)  # a control character becomes a space (decision-036)
    claims = [
        claim("venue", "ICLR", evidence),
        claim("year", year, evidence),
        claim("track", "main", evidence),
        claim("status", "accepted", evidence),
        claim("title", title, title_evidence(evidence, replaced)),
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
