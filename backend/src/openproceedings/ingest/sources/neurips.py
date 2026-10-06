"""NeurIPS proceedings miner (spec 01 §Sources; neurips-proceedings skill; task-052).

The only NeurIPS source before 2021 and a cross-check after it. A year is crawled from its index page
(`https://proceedings.neurips.cc/paper_files/paper/<YYYY>`), never from search; 2021 adds the Datasets and
Benchmarks host's page (`https://datasets-benchmarks-proceedings.neurips.cc/paper/2021`). Every listed paper
is `accepted` (a listing never means rejected, and the proceedings host no workshop papers); its track comes
from the host, year and path token through `classify.classify_neurips_listing`, whose rule is the track
claim's evidence. Each paper's abstract page gives the abstract (only when its `citation_title` is the
listed title), the authors (`citation_author`), the PDF and the DOI.

Claims (source `neurips_proceedings`) carry the paper page's URL and the fetch time of the page they came
from: the year index for venue, year, title, track and status; the abstract page for the rest. The native
id is `urls.proceedings_native`: `nips-<the 32-hex hash in the path>`, plus `-round1`/`-round2` on the 2021
D&B host, which numbers each round and the main track separately (so one hash names up to three papers).

The year page states its own count (`<span class="paper-count">N papers</span>`); the report compares it
with the entries parsed (`count_ok`). OpenReview hosts NeurIPS from 2021, so from then on the proceedings
confirm acceptance and never decide the track (dedup's precedence, decision-005); a disagreement is a
`conflicts.csv` row when the records merge.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from pydantic import ValidationError

from openproceedings.ingest import urls
from openproceedings.ingest.classify import NEURIPS_DB_2021_HOST, classify_neurips_listing
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
    ListingReport,
    MinerError,
    clean_abstract,
    missing_reason,
    record_from_claims,
    titles_match,
)
from openproceedings.ingest.sources.html import collapse, meta, metas, node_text, parse
from openproceedings.ingest.sources.http import Fetcher, Page, canonical
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)

SOURCE: Source = "neurips_proceedings"
CACHE_DIR = "neurips"  # <data>/cache/neurips
MAIN_HOST = "proceedings.neurips.cc"
HOSTS = frozenset({MAIN_HOST, NEURIPS_DB_2021_HOST})
FIRST_YEAR = 2013  # decision-013: every venue from ICLR's first year
OPENREVIEW_FROM = 2021  # OpenReview hosts NeurIPS from 2021 (v1), so the proceedings confirm from then on
PROGRESS_SECONDS = 30.0

_COUNT = re.compile(r"^([0-9][0-9,]*)\s+papers?$", re.I)


def listing_urls(year: int) -> list[str]:
    """The index pages that list a year's papers."""
    main = f"https://{MAIN_HOST}/paper_files/paper/{year}"
    if year == 2021:
        return [main, f"https://{NEURIPS_DB_2021_HOST}/paper/2021"]
    if year == 2025:
        return [main, f"{main}/vol38-main-conference"]
    return [main]


@dataclass(frozen=True, slots=True)
class Entry:
    """One `<li>` on a year page: the abstract page URL (absolute), the title and the authors as listed."""

    url: str
    title: str
    authors: tuple[str, ...]


def split_authors(text: str) -> tuple[str, ...]:
    return tuple(a for a in (collapse(p) for p in text.split(",")) if a)


@dataclass(frozen=True, slots=True)
class YearIndex:
    entries: list[Entry]
    stated: int | None  # the page's own count (`N papers`), None if it states none
    unlinked: int  # `<li>` items with no abstract link (counted, never guessed)
    see_also: list[str]  # other volumes the page points to (2025: a separate main-conference volume)


def parse_year_index(text: str, base: str) -> YearIndex:
    """The entries on a year page, with its stated count and the other volumes it points to."""
    root = parse(text, canonical(base))
    block = next((node for node in root.iter("ul") if node.has_class("paper-list")), None)
    entries: list[Entry] = []
    unlinked = 0
    count_node = next((node for node in root.iter("span") if node.has_class("paper-count")), None)
    count_match = _COUNT.match(node_text(count_node)) if count_node else None
    stated = int(count_match.group(1).replace(",", "")) if count_match else None
    see_also = [
        urljoin(base, anchor.attributes.get("href", ""))
        for paragraph in root.iter("p")
        if paragraph.has_class("book-see-also")
        for anchor in paragraph.iter("a")
    ]
    for item in block.iter("li") if block else []:
        anchor = next(
            (node for node in item.iter("a") if "-Abstract" in node.attributes.get("href", "")), None
        )
        if anchor is None:
            unlinked += 1
            continue
        authors = None
        after_anchor = False
        for node in item.iter():
            if node is anchor:
                after_anchor = True
            elif after_anchor and (
                (node.tag == "span" and node.has_class("paper-authors")) or node.tag == "i"
            ):
                authors = node
                break
        author_text = node_text(authors) if authors else ""
        entries.append(
            Entry(
                urljoin(base, anchor.attributes.get("href", "")),
                node_text(anchor),
                split_authors(author_text),
            )
        )
    return YearIndex(entries, stated, unlinked, see_also)


@dataclass(frozen=True, slots=True)
class AbstractPage:
    title: str | None  # citation_title
    authors: tuple[str, ...]  # citation_author, in order
    abstract: str | None  # extracted text, before the snippet check
    pdf: str | None
    doi: str | None


def parse_abstract_page(text: str, url: str | None = None) -> AbstractPage:
    abstract = next((node for node in parse(text, url).iter("p") if node.has_class("paper-abstract")), None)
    return AbstractPage(
        title=meta(text, "citation_title"),
        authors=tuple(a for a in metas(text, "citation_author") if a),
        abstract=node_text(abstract) if abstract else None,
        pdf=meta(text, "citation_pdf_url"),
        doi=meta(text, "citation_doi"),
    )


def _doi(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return Urls(doi=value).doi
    except ValidationError:
        return None


@dataclass
class YearResult:
    records: list[PaperRecord]
    reports: list[ListingReport]


def mine_year(
    year: int, fetcher: Fetcher, *, refresh_index: bool = False, plan_only: bool = False
) -> YearResult:
    """Every paper the year's listings hold, as records. `plan_only` reads the listings and fetches no paper
    page (the dry run: `skipped` then counts nothing and `records` stays 0). Raises MinerError when a
    listing isn't there (not published yet: re-crawl later, never infer absence)."""
    if year < FIRST_YEAR:
        raise MinerError(
            f"NeurIPS {year}: the crawl starts in {FIRST_YEAR} (decision-013)", reason="before_window"
        )
    records: list[PaperRecord] = []
    reports: list[ListingReport] = []
    seen: set[str] = set()
    for listing in listing_urls(year):
        index = fetcher.get(listing, refresh=refresh_index)
        if not index.ok:
            raise MinerError(
                f"NeurIPS {year}: {listing} answered HTTP {index.status}; not published yet?",
                reason="no_listing",
            )
        report, got = _mine_listing(year, listing, index, fetcher, seen, plan_only=plan_only)
        records += got
        reports.append(report)
    return YearResult(records, reports)


def _mine_listing(
    year: int, listing: str, index: Page, fetcher: Fetcher, seen: set[str], *, plan_only: bool
) -> tuple[ListingReport, list[PaperRecord]]:
    parsed = parse_year_index(index.text, listing)
    entries = parsed.entries
    role = "confirm" if year >= OPENREVIEW_FROM else "primary"
    followed = set(listing_urls(year))
    unfollowed = [url for url in parsed.see_also if url not in followed]
    report = ListingReport(
        SOURCE, "NeurIPS", year, listing, role, parsed.stated, listed=len(entries) + parsed.unlinked,
        see_also=unfollowed,
    )  # fmt: skip
    report.fetched.append(index.fetched_at)
    if parsed.unlinked:
        report.skipped["no_link"] = parsed.unlinked
    if unfollowed:
        log.warning("listing_see_also_unfollowed", extra={"year": year, "see_also": unfollowed})
    records: list[PaperRecord] = []
    started = last = time.monotonic()
    log.info("neurips_listing_started", extra={"year": year, "listing": listing, "entries": len(entries)})
    for n, entry in enumerate(entries, 1):
        parts = urls.proceedings_parts(entry.url)
        if parts is None or parts[0] != "NeurIPS" or len(parts[2]) != 32:
            report.skipped["unparsed_link"] += 1
            continue
        _venue, url_year, _sha, token = parts
        if url_year != year:
            report.skipped["wrong_year"] += 1
            continue
        host = urlparse(entry.url).netloc.lower()
        if host not in HOSTS:  # a link to papers.nips.cc or elsewhere: never fetched, counted
            report.skipped["off_host"] += 1
            continue
        native = urls.proceedings_native(entry.url)
        if native is None:  # a 2021 D&B link without round1/round2: its hash alone names no one paper
            report.skipped["no_round"] += 1
            continue
        if native in seen:
            report.skipped["duplicate"] += 1
            continue
        seen.add(native)
        if not entry.title:
            report.skipped["no_title"] += 1
            continue
        cls, rule = classify_neurips_listing(host, year, token)
        if plan_only:
            report.tracks[cls.track] += 1
            report.to_fetch = (report.to_fetch or 0) + (not fetcher.is_cached(entry.url))
            continue
        page = fetcher.get(entry.url, keep_absent=True)
        report.fetched.append(page.fetched_at)
        try:
            record, missing = _record(year, native, entry, cls.track, rule, listing, index, page)
        except (ValidationError, ValueError) as e:
            report.skipped["invalid"] += 1
            log.debug(  # counted in the listing's one `listing_attention` WARNING
                "neurips_record_invalid",
                extra={"year": year, "native": native, "url": page.url, "error": type(e).__name__},
            )
            continue
        records.append(record)
        report.count(record, missing)
        if time.monotonic() - last >= PROGRESS_SECONDS:
            last = time.monotonic()
            log.info("neurips_listing_progress", extra={"year": year, "done": n, "of": len(entries)})
    _log_done(report, started)
    return report, records


def _record(
    year: int, native: str, entry: Entry, track: str, rule: str, listing: str, index: Page, page: Page
) -> tuple[PaperRecord, str | None]:  # fmt: skip
    """The record and, when it has no abstract, why (`common.MISSING`)."""
    title, replaced = title_text(entry.title)  # a control character becomes a space (decision-036)
    claims: list[Claim] = []

    def claim(fld: ClaimField, value: ClaimValue, evidence: str, at: datetime) -> None:
        claims.append(
            Claim(field=fld, value=value, source=SOURCE, url=entry.url, fetched_at=at, evidence=evidence)
        )

    listed_on = f"year index {listing}"
    for fld, value in (
        ("venue", "NeurIPS"),
        ("year", year),
        ("urls.proceedings", entry.url),
    ):
        claim(fld, value, listed_on, index.fetched_at)  # type: ignore[arg-type]
    claim("title", title, title_evidence(listed_on, replaced), index.fetched_at)
    claim("track", track, rule, index.fetched_at)
    claim("status", "accepted", f"listed on {listing}", index.fetched_at)

    parsed = parse_abstract_page(page.text, page.url) if page.ok else None
    matches = parsed is not None and titles_match(title, parsed.title)
    abstract, spaced = clean_abstract(parsed.abstract) if parsed is not None and matches else (None, 0)
    missing = missing_reason(page.ok, matches, abstract)
    if abstract is not None:
        evidence = controls_evidence(
            "p.paper-abstract (citation_title matches the listing)", spaced
        )  # decision-044
        claim("abstract", abstract, evidence, page.fetched_at)
    if parsed is not None and matches and parsed.authors:
        claim("authors", parsed.authors, "citation_author", page.fetched_at)
    elif entry.authors:
        claim("authors", entry.authors, listed_on, index.fetched_at)
    if parsed is not None and matches:
        if parsed.pdf and is_url(parsed.pdf) and urls.native(parsed.pdf) == native:
            claim("urls.pdf", parsed.pdf, "citation_pdf_url", page.fetched_at)
        if doi := _doi(parsed.doi):
            claim("urls.doi", doi, "citation_doi", page.fetched_at)
    return record_from_claims(f"op:neurips:{year}:{native}", claims), missing


def _log_done(report: ListingReport, started: float) -> None:
    fields: dict[str, Any] = {
        "year": report.year, "listing": report.listing, "listed": report.listed, "stated": report.stated,
        "records": report.records, "abstract_missing": report.abstract_missing,
        "unknown_track": report.unknown_track, "ms": elapsed_ms(started, time.monotonic),
    }  # fmt: skip
    log.info("neurips_listing_mined", extra=fields)
    if not report.count_ok:
        log.warning(
            "listing_count_mismatch", extra={k: fields[k] for k in ("year", "listing", "listed", "stated")}
        )
    if report.unknown_track or report.skipped:
        log.warning(
            "listing_attention",
            extra={"year": report.year, "listing": report.listing, "unknown_track": report.unknown_track,
                   "skipped": dict(report.skipped)},
        )  # fmt: skip
