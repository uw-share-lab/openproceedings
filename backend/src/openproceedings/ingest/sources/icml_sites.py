"""Abstracts for ICML 1988–2012 from the official ICML conference pages (spec 01 §Sources, ICML sites row;
decision-047; TASK-206).

dblp gives the pre-2013 ICML papers no abstracts. Some years' official conference sites listed them, and some of
those pages survive, live (icml.cc's 2009 and 2012 pages, the 2008 Helsinki site) or as an Internet Archive
capture. The table `icml_sites.toml` names each page by year: the URL fetched (an archived page by its exact
capture, `https://web.archive.org/web/<14-digit timestamp>id_/<official URL>`, so the same bytes come back every
time and Wayback never redirects to another capture), the official URL it is a copy of, the parser that reads it
and how many entries it gave when verified. Only these pages are fetched (`HOSTS`), never ACM DL, Scholar,
Semantic Scholar, arXiv or an author's page. A year with no row has no abstracts.

A page gives (title, abstract) entries. They become abstracts only in `dblp.mine_year`, and only by an exact title
key (the dedup key: the token contract over the NFC title) that exactly one entry and exactly one dblp paper of
the year share. Everything else is counted, never guessed: page entries no paper matches, keys two entries or two
papers share, and the papers left with no abstract. An abstract claim (source `icml_site`) carries the page as
fetched (the capture URL, whose timestamp says when the Internet Archive saw it), the page's own fetch time, and
evidence naming the official URL and the capture.
"""

from __future__ import annotations

import logging
import re
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from importlib.resources import files
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse

from openproceedings.ingest.record import Source, title_text
from openproceedings.ingest.sources.common import CrawlError, clean_abstract
from openproceedings.ingest.sources.html import Element, node_text, parse
from openproceedings.ingest.sources.http import Fetcher, Page

log = logging.getLogger(__name__)

SOURCE: Source = "icml_site"
CACHE_DIR = "icml_sites"  # <data>/cache/icml_sites
ARCHIVE_HOST = "web.archive.org"
_CAPTURE = re.compile(r"https://web\.archive\.org/web/([0-9]{14})id_/(https?://\S+)")


@dataclass(frozen=True, slots=True)
class SitePage:
    """One row of the table: an official page that lists a year's papers with their abstracts."""

    year: int
    url: str  # what is fetched: the live official page, or its pinned capture
    official: str  # the official page itself
    parser: str  # a key of `PARSERS`
    entries: int  # (title, abstract) entries the parser read off it when verified
    verified: date
    note: str

    @property
    def capture(self) -> str | None:
        """The Internet Archive capture's 14-digit timestamp, or None for a live page."""
        m = _CAPTURE.fullmatch(self.url)
        return m.group(1) if m else None


@dataclass(frozen=True, slots=True)
class SiteAbstract:
    """One paper on a page: its title as the page gives it, the abstract as a record would hold it, where."""

    title: str
    abstract: str
    spaced: int  # control characters the abstract lost (decision-044)
    url: str
    fetched_at: datetime
    evidence: str


@dataclass
class SiteYear:
    """What a year's pages gave: the pages as fetched, their entries, every page's fetch time."""

    pages: list[str] = field(default_factory=list)
    entries: list[SiteAbstract] = field(default_factory=list)
    fetched: list[datetime] = field(default_factory=list)


# --- parsers: page text → (title, abstract text) entries --------------------------------------------------------

Parser = Callable[[str, str], list[tuple[str, str]]]


def _blocks_after_headings(text: str, base: str, heading: str) -> list[tuple[str, str]]:
    """A title in each `<heading>`, its abstract the text of the block-level siblings up to the next one."""
    root = parse(text, base)
    out: list[tuple[str, str]] = []
    for container in root.iter():
        kids = [k for k in container.children if isinstance(k, Element)]
        if not any(k.tag == heading for k in kids):
            continue
        current: tuple[str, list[str]] | None = None
        for k in kids:
            if k.tag == heading:
                if current is not None:
                    out.append((current[0], " ".join(current[1])))
                current = (node_text(k), [])
            elif current is not None:
                current[1].append(node_text(k))
        if current is not None:
            out.append((current[0], " ".join(current[1])))
    return out


PARSERS: dict[str, Parser] = {}


# --- the table ----------------------------------------------------------------------------------------------------

_COLUMNS = {"year", "url", "official", "parser", "entries", "verified", "note"}


def _row(raw: Mapping[str, Any]) -> SitePage:
    where = f"icml_sites.toml {raw.get('year')!r} {raw.get('url')!r}"
    if set(raw) != _COLUMNS:
        raise ValueError(f"{where}: columns must be exactly {sorted(_COLUMNS)}")
    page = SitePage(raw["year"], str(raw["url"]), str(raw["official"]), str(raw["parser"]), raw["entries"],
                    raw["verified"], str(raw["note"]))  # fmt: skip
    if type(page.year) is not int or not 1988 <= page.year <= 2012:
        raise ValueError(f"{where}: a year from 1988 to 2012")
    if page.parser not in PARSERS:
        raise ValueError(f"{where}: no parser {page.parser!r}")
    if type(page.entries) is not int or page.entries <= 0 or not isinstance(page.verified, date):
        raise ValueError(f"{where}: entries must be a positive integer and verified a date")
    host = (urlparse(page.url).hostname or "").lower()
    if page.capture is not None:
        if _CAPTURE.fullmatch(page.url).group(2) != page.official:  # type: ignore[union-attr]
            raise ValueError(f"{where}: a capture must be of the official URL, exactly")
    elif page.url != page.official or not page.url.startswith("https://"):
        raise ValueError(f"{where}: a live page is fetched at its official https URL")
    if host == ARCHIVE_HOST and page.capture is None:
        raise ValueError(f"{where}: an Internet Archive URL must pin one capture (/web/<14 digits>id_/<url>)")
    return page


def load(text: str) -> Mapping[int, tuple[SitePage, ...]]:
    rows = [_row(r) for r in tomllib.loads(text).get("page", [])]
    by_year: dict[int, list[SitePage]] = {}
    for r in rows:
        if any(p.url == r.url for p in by_year.get(r.year, [])):
            raise ValueError(f"icml_sites.toml: {r.url} is listed twice for {r.year}")
        by_year.setdefault(r.year, []).append(r)
    return MappingProxyType({y: tuple(ps) for y, ps in sorted(by_year.items())})


def _table() -> Mapping[int, tuple[SitePage, ...]]:
    return load(files("openproceedings.ingest").joinpath("icml_sites.toml").read_text(encoding="utf-8"))


PAGES: Mapping[int, tuple[SitePage, ...]] = _table()
# the only hosts this source fetches: the table's pages' (the official sites, and the Internet Archive)
HOSTS: frozenset[str] = frozenset((urlparse(p.url).hostname or "").lower() for ps in PAGES.values() for p in ps)


# --- reading a year --------------------------------------------------------------------------------------------


def _evidence(page: SitePage) -> str:
    if page.capture is not None:
        return f"official ICML {page.year} page {page.official}, Internet Archive capture {page.capture}"
    return f"official ICML {page.year} page {page.official}"


def entries_of(page: SitePage, fetched: Page) -> list[SiteAbstract]:
    """The page's (title, abstract) entries as records would hold them; an entry with no title or no usable
    abstract (empty, or snippet-shaped) is dropped."""
    out = []
    for raw_title, raw_abstract in PARSERS[page.parser](fetched.text, page.url):
        title = title_text(raw_title)[0]
        abstract, spaced = clean_abstract(raw_abstract)
        if title and abstract:
            out.append(SiteAbstract(title, abstract, spaced, page.url, fetched.fetched_at, _evidence(page)))
    return out


def read_year(year: int, fetcher: Fetcher, *, refresh: bool = False, pages: Mapping[int, tuple[SitePage, ...]] | None = None) -> SiteYear | None:
    """The year's pages through `fetcher` (offline: the cache only), or None when the table has none. A page
    that isn't there (404/410), or that now gives a different number of entries than the table verified, stops
    the crawl: a person checks it."""
    rows = (PAGES if pages is None else pages).get(year)
    if not rows:
        return None
    out = SiteYear()
    for page in rows:
        fetched = fetcher.get(page.url, refresh=refresh)
        if not fetched.ok:
            raise CrawlError(f"ICML {year}: {page.url} answered HTTP {fetched.status}", reason="no_listing")
        got = entries_of(page, fetched)
        if len(got) != page.entries:
            raise CrawlError(f"ICML {year}: {page.url} gives {len(got)} entries, the table verified "
                             f"{page.entries}; check the page and the parser", reason="site_count_mismatch")  # fmt: skip
        out.pages.append(page.url)
        out.entries += got
        out.fetched.append(fetched.fetched_at)
    return out


def plan_year(year: int, fetcher: Fetcher, pages: Mapping[int, tuple[SitePage, ...]] | None = None) -> dict[str, Any]:
    """A dry run's view of a year: its pages and which are not yet cached."""
    rows = (PAGES if pages is None else pages).get(year, ())
    return {"year": year, "pages": [p.url for p in rows], "to_fetch": sum(not fetcher.is_cached(p.url) for p in rows)}
