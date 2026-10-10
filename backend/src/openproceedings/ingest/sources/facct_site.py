"""The official FAccT abstracts from facctconference.org (spec 01 §Sources, FAccT site row; decision-049).

Crossref gives FAccT's papers no abstracts (`crossref.SELECT` never asks), but the conference site publishes them
for some years. Three official pages, each read once per crawl, only from `HOST` (robots.txt allows everything:
`User-agent: *` with an empty `Disallow:`; checked 2026-10-10). The table `facct_site.toml` beside the ingest
package names each page by year, with the parser that reads it, its join rule and the entries it gave when verified:

- 2022: `/2022/acceptedpapers.html` (`facct2022_html`), 181 entries, joined by title;
- 2025: `/static/docs/facct2025-final.csv` (`facct2025_csv`), 217 rows (206 archival, each with its DOI in `URL`),
  joined by DOI;
- 2026: `/static/docs/facct2026-final.csv` (`facct2026_csv`), 325 rows (no type and no DOI column), joined by title.

The CSVs are served as `application/octet-stream`; a parser takes them with or without a byte-order mark and with
`\\n` or `\\r\\n` line ends. A page that is gone (`site_missing`), whose shape moved (`site_format`), whose entry count
is not the table's (`site_count`) or that repeats an entry key (`site_duplicate_key`) stops the crawl: a person
checks it.

The join is exact and one-to-one, never fuzzy (`match`):
- a 2025 row by its DOI only: a row with no DOI, or one no record has, is unmatched, and never falls back to its
  title;
- a 2022 or 2026 row by the exact title key (`dedup.title_key`, the token contract over the NFC title), attached
  only when exactly one entry and exactly one record share it. The 2022 page's DOI links are never read: entry 295
  links entry 314's DOI.

What is counted, never forced: entries no record matches (`site_unmatched`; the non-archival rows and the titles
worded differently on the page and in Crossref), keys two entries or two records share (`site_ambiguous`), and rows
with no title or no usable abstract (`site_dropped`, `clean_abstract`). An abstract claim (source `facct_site`)
carries the page as fetched as its url, that page's fetch time, and evidence naming the row and the join rule;
`dedup.attribution` credits the record's DOI link, never the CSV or the listing.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import time
import tomllib
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from importlib.resources import files
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse

from openproceedings.ingest.dedup import title_key
from openproceedings.ingest.record import Source, title_text
from openproceedings.ingest.sources.common import CrawlError, clean_abstract
from openproceedings.ingest.sources.html import Element, node_text, parse
from openproceedings.ingest.sources.http import Fetcher
from openproceedings.logs import elapsed_ms
from openproceedings.vocab import venue_name

log = logging.getLogger(__name__)

SOURCE: Source = "facct_site"
CACHE_DIR = "facct_site"  # <data>/cache/facct_site
HOST = "facctconference.org"
HOSTS = frozenset({HOST})
MIN_INTERVAL = 1.0  # three pages per full crawl, a second apart
_DOI = re.compile(r"10\.1145/[0-9]+\.[0-9]+", re.IGNORECASE)
_COLUMNS = {"year", "url", "parser", "join", "rows", "verified", "note"}
JOINS = frozenset({"doi", "title"})


@dataclass(frozen=True, slots=True)
class SitePage:
    """One row of the table: an official page listing a year's papers with their abstracts."""

    year: int
    url: str  # fetched as named, on HOST
    parser: str  # a key of `PARSERS`
    join: str  # "doi" | "title"
    rows: int  # entries the parser read off it when verified
    verified: date
    note: str


@dataclass(frozen=True, slots=True)
class Entry:
    """What a parser reads off a page: the entry's key (a row id, or the 2022 heading's id), its title and abstract
    text as the page gives them (None when empty), and its DOI (2025 only)."""

    key: str
    title: str | None
    abstract: str | None
    doi: str | None


@dataclass(frozen=True, slots=True)
class SiteAbstract:
    """One entry with a title and a usable abstract: the abstract as a record would hold it, and where it came from."""

    key: str
    title: str
    doi: str | None  # lower-case
    abstract: str
    spaced: int  # control characters the abstract lost (decision-044)
    pdf_codes: int  # `(cid:N)` codes repaired (decision-047)
    url: str
    fetched_at: datetime
    evidence: str


@dataclass(frozen=True, slots=True)
class SiteYear:
    """What a year's page gave: the page as fetched, its join rule, its usable entries, its fetch time, and the rows
    dropped for no title or no usable abstract. `dropped_titles` and `dropped_dois` are those rows' title keys and
    DOIs: a dropped row still shares its key or DOI with a good one, which makes the good row ambiguous."""

    page: str
    join: str
    entries: list[SiteAbstract]
    fetched: list[datetime]
    dropped: int
    dropped_titles: tuple[str, ...] = ()
    dropped_dois: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Matched:
    by_doi: dict[str, SiteAbstract]  # record DOI → its one entry
    unmatched: int
    ambiguous: int


# --- parsers: page text → entries ---------------------------------------------------------------------------------


def _csv(text: str, columns: tuple[str, ...], *, key: str, title: str, abstract: str,
         doi_from: str | None = None) -> list[Entry]:  # fmt: skip
    """A FAccT CSV's rows. The header must be exactly `columns`. A byte-order mark, if any, is dropped and either
    line end is read (the csv module's own newline handling: a quoted field keeps its line breaks)."""
    reader = csv.DictReader(io.StringIO(text.removeprefix("\ufeff"), newline=""))
    if tuple(reader.fieldnames or ()) != columns:
        raise CrawlError(f"a FAccT CSV's columns are {reader.fieldnames}, not {list(columns)}: check facct_site.toml",
                         reason="site_format")  # fmt: skip
    out = []
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise CrawlError("a FAccT CSV row has more or fewer fields than its header", reason="site_format")
        doi = m.group(0).lower() if doi_from and (m := _DOI.search(row[doi_from])) else None
        out.append(Entry(row[key].strip(), row[title].strip() or None, row[abstract].strip() or None, doi))
    return out


def facct2025_csv(text: str) -> list[Entry]:
    """The 2025 final CSV: `TYPE, ID, ABSTRACT, AUTHOR, TITLE, URL, URL-OLD`; an archival row's `URL` is its DOI
    link (`https://doi.org/10.1145/3715275.N`), a non-archival row's an arXiv or SSRN link or empty (no DOI)."""
    return _csv(text, ("TYPE", "ID", "ABSTRACT", "AUTHOR", "TITLE", "URL", "URL-OLD"), key="ID", title="TITLE",
                abstract="ABSTRACT", doi_from="URL")  # fmt: skip


def facct2026_csv(text: str) -> list[Entry]:
    """The 2026 final CSV: `Paper ID, Title, Authors, Abstract` (no type, no DOI)."""
    return _csv(
        text, ("Paper ID", "Title", "Authors", "Abstract"), key="Paper ID", title="Title", abstract="Abstract"
    )


def _only_italic(p: Element) -> bool:
    """Whether a `<p>` holds one `<i>` and nothing else but whitespace: the 2022 page's author line."""
    kids = [c for c in p.children if not (isinstance(c, str) and not c.strip())]
    return len(kids) == 1 and isinstance(kids[0], Element) and kids[0].tag == "i"


def facct2022_html(text: str) -> list[Entry]:
    """The 2022 accepted papers page. Inside the one `<div class="col-lg-12">` that holds them, each entry is a run
    of siblings from an `<h4 id="N">` (the title, in `<b>`): an optional `<h5>` award line, `<p><i>authors</i></p>`,
    a `<br>`, one `<p>` abstract, then `<p>`s of `label` links (`Paper`, a DOI; `Video`). The key is the heading's
    id. The DOI links are never read (entry 295 links entry 314's DOI): the join is by title. A page with no such
    container, or an entry with no abstract paragraph or more than one, is `site_format`."""
    holders = [d for d in parse(text).iter("div")
               if d.has_class("col-lg-12") and any("id" in h.attributes for h in d.iter("h4"))]  # fmt: skip
    if len(holders) != 1:
        raise CrawlError(f"the FAccT 2022 page has {len(holders)} paper containers, not 1: check facct_site.toml",
                         reason="site_format")  # fmt: skip
    runs: list[tuple[Element, list[Element]]] = []
    for child in holders[0].children:
        if not isinstance(child, Element):
            continue
        if child.tag == "h4" and "id" in child.attributes:
            runs.append((child, []))
        elif runs:
            runs[-1][1].append(child)
        elif child.tag != "br":
            raise CrawlError(
                f"the FAccT 2022 page has a <{child.tag}> before its first paper", reason="site_format"
            )
    out = []
    for head, rest in runs:
        key = head.attributes["id"].strip()
        paragraphs = [p for p in rest if p.tag == "p" and not _only_italic(p) and not p.iter("span")]
        if len(paragraphs) != 1:
            raise CrawlError(f"FAccT 2022 entry {key!r} has {len(paragraphs)} abstract paragraphs, not 1",
                             reason="site_format")  # fmt: skip
        out.append(Entry(key, node_text(head) or None, node_text(paragraphs[0]) or None, None))
    return out


Parser = Callable[[str], list[Entry]]
PARSERS: Mapping[str, Parser] = MappingProxyType(
    {"facct2022_html": facct2022_html, "facct2025_csv": facct2025_csv, "facct2026_csv": facct2026_csv}
)


# --- the table ----------------------------------------------------------------------------------------------------


def _row(raw: Mapping[str, Any]) -> SitePage:
    where = f"facct_site.toml {raw.get('year')!r} {raw.get('url')!r}"
    if set(raw) != _COLUMNS:
        raise ValueError(f"{where}: columns must be exactly {sorted(_COLUMNS)}")
    page = SitePage(raw["year"], str(raw["url"]), str(raw["parser"]), str(raw["join"]), raw["rows"],
                    raw["verified"], str(raw["note"]))  # fmt: skip
    if type(page.year) is not int:
        raise ValueError(f"{where}: the year is an integer")
    try:
        venue_name("FAccT", page.year)
    except ValueError:
        raise ValueError(f"{where}: FAccT was not held under that name in {page.year}") from None
    parsed = urlparse(page.url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != HOST:
        raise ValueError(f"{where}: the url is an https page on {HOST}")
    if page.parser not in PARSERS:
        raise ValueError(f"{where}: no parser {page.parser!r}")
    if page.join not in JOINS:
        raise ValueError(f"{where}: join is 'doi' or 'title', never anything looser")
    if type(page.rows) is not int or page.rows <= 0:
        raise ValueError(f"{where}: rows is a positive integer")
    if type(page.verified) is not date:
        raise ValueError(f"{where}: verified is a date")
    if not page.note.strip():
        raise ValueError(f"{where}: a note says where the count came from")
    return page


def load(text: str) -> Mapping[int, SitePage]:
    by_year: dict[int, SitePage] = {}
    for raw in tomllib.loads(text).get("page", []):
        page = _row(raw)
        if page.year in by_year:
            raise ValueError(f"facct_site.toml: {page.year} is listed twice (one page per year)")
        by_year[page.year] = page
    return MappingProxyType(dict(sorted(by_year.items())))


TABLE: Mapping[int, SitePage] = load(
    files("openproceedings.ingest").joinpath("facct_site.toml").read_text(encoding="utf-8")
)


# --- reading a year and joining it ----------------------------------------------------------------------------


def read_year(
    year: int, fetcher: Fetcher, *, refresh: bool = False, table: Mapping[int, SitePage] | None = None
) -> SiteYear | None:
    """The year's page through `fetcher` (offline: the cache only), or None when the table has no page for it."""
    p = (TABLE if table is None else table).get(year)
    if p is None:
        return None
    started = time.monotonic()
    page = fetcher.get(p.url, refresh=refresh)
    if not page.ok:
        raise CrawlError(f"FAccT {year}: {p.url} answered HTTP {page.status}; check facct_site.toml",
                         reason="site_missing")  # fmt: skip
    got = PARSERS[p.parser](page.text)
    if len(got) != p.rows:
        raise CrawlError(f"FAccT {year}: {p.url} gives {len(got)} entries, the table verified {p.rows}; check the "
                         "page and the table", reason="site_count")  # fmt: skip
    keys = [e.key for e in got]
    if len(set(keys)) != len(keys):
        raise CrawlError(f"FAccT {year}: {p.url} repeats an entry key", reason="site_duplicate_key")
    entries: list[SiteAbstract] = []
    dropped = 0
    dropped_titles: list[str] = []
    dropped_dois: list[str] = []
    for e in got:
        title = title_text(e.title)[0] if e.title else ""
        cleaned = clean_abstract(e.abstract)
        if not title or cleaned.text is None:
            dropped += 1
            if title and (k := title_key(title)):
                dropped_titles.append(k)
            if e.doi:
                dropped_dois.append(e.doi.lower())
            continue
        entries.append(SiteAbstract(e.key, title, e.doi, cleaned.text, cleaned.spaced, cleaned.pdf_codes, p.url,
                                    page.fetched_at, f"{p.url} row {e.key}"))  # fmt: skip
    log.info("facct_site_year_read", extra={"year": year, "entries": len(entries), "dropped": dropped,
                                            "ms": elapsed_ms(started, time.monotonic)})  # fmt: skip
    return SiteYear(p.url, p.join, entries, [page.fetched_at], dropped, tuple(dropped_titles), tuple(dropped_dois))


def match(papers: Sequence[tuple[str, str]], site: SiteYear) -> Matched:
    """Record DOI → the one entry joined to it, from `papers` (each record's DOI and title). By DOI: an entry with
    no DOI, or a DOI no record has, is unmatched; a DOI two entries share attaches nothing (ambiguous). By title: the
    title key two entries or two records share attaches nothing (ambiguous); a key no record has is unmatched. A row
    dropped for no title or abstract still counts toward a shared DOI or title key: the good row beside it is
    ambiguous, never unique."""
    by_doi: dict[str, SiteAbstract] = {}
    unmatched = ambiguous = 0
    if site.join == "doi":
        known = {doi.lower() for doi, _ in papers}
        groups: dict[str | None, list[SiteAbstract]] = defaultdict(list)
        for entry in site.entries:
            groups[entry.doi.lower() if entry.doi else None].append(entry)
        for doi, group in groups.items():
            if doi is None or doi not in known:
                unmatched += len(group)
            elif len(group) + site.dropped_dois.count(doi) > 1:
                ambiguous += len(group)
            else:
                by_doi[doi] = group[0]
        return Matched(by_doi, unmatched, ambiguous)
    records: dict[str, list[str]] = defaultdict(list)
    for doi, title in papers:
        if k := title_key(title):
            records[k].append(doi)
    pages: dict[str, list[SiteAbstract]] = defaultdict(list)
    for entry in site.entries:
        pages[title_key(entry.title)].append(entry)
    for k, group in pages.items():
        if not k or k not in records:
            unmatched += len(group)
        elif len(group) + site.dropped_titles.count(k) > 1 or len(records[k]) > 1:
            ambiguous += len(group)
        else:
            by_doi[records[k][0]] = group[0]
    return Matched(by_doi, unmatched, ambiguous)
