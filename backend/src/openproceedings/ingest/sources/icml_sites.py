"""Abstracts for ICML 1988–2012 from the official ICML conference pages (spec 01 §Sources, ICML sites row;
decision-047; TASK-206).

dblp gives the pre-2013 ICML papers no abstracts. Some years' official conference sites listed them, and some of
those pages survive: live on icml.cc (which still serves the 2007–2012 sites' pages), or as an Internet Archive
capture of the conference's own site (2001, 2003, 2004 and 2007's per-paper pages). The per-year survey is
`docs/research/2026-10-06-icml-pre-2013-abstract-sources.md`. The table `icml_sites.toml` names each page by year:
the URL fetched (an archived page by its exact capture, `https://web.archive.org/web/<14-digit timestamp>id_/<the
URL the archive holds>`, so the same bytes come back every time and Wayback never redirects to another capture),
the official URL it is a copy of, the parser that reads it, the charset its bytes are in (these servers send bare
`text/html`), and how many entries it gave when verified. Only these pages are fetched (`HOSTS`): never ACM DL,
Scholar, Semantic Scholar, arXiv or an author's page. A year with no row has no abstracts.

A page gives entries: a title and an abstract (most years), a paper number and title (2007's list), or a paper
number and abstract (2007's per-paper pages, whose own titles are mangled by PDF extraction: `Unsup ervised`).
Entries a year's pages give in parts are joined by paper number. They become abstracts only in `dblp.mine_year`,
and only by an exact title key (the dedup key: the token contract over the NFC title) that exactly one entry and
exactly one dblp paper of the year share. Everything else is counted, never guessed: page entries no paper
matches, keys two entries or two papers share, and the papers left with no abstract. An abstract claim (source
`icml_site`) carries the page it came from as fetched (a capture URL names its timestamp), that page's fetch time,
and evidence naming the official URL and the capture.
"""

from __future__ import annotations

import bisect
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
from openproceedings.ingest.sources.html import node_text, parse, text_of
from openproceedings.ingest.sources.http import Fetcher, FetchError, Heartbeat, Page

log = logging.getLogger(__name__)

SOURCE: Source = "icml_site"
CACHE_DIR = "icml_sites"  # <data>/cache/icml_sites
ARCHIVE_HOST = "web.archive.org"
# The official sites a capture may be of: (host, path prefix), each named as that year's ICML site by an official
# page (icml.cc's "past conferences" pages: Conferences/2007/pastconferences.html names the 2001 Purdue, 2003 HP
# Labs and 2004 Banff sites, Conferences/2008/past_icmls.shtml.html the 2007 Oregon State one; the 2003 site's own
# titlesAndAuthors.html links each paper to /conferences/icml2003/allAbstracts.html, and icml.cc names the Banff site
# as /_banff04/icml/, whose pages the archive holds at /banff04/icml/, their stylesheet's own path). A capture of anything else,
# another page of those hosts included, is refused when the table loads: never ACM DL, arXiv, Scholar or an author.
OFFICIAL_SITES: tuple[tuple[str, str], ...] = (
    ("icml.cc", "/"), ("www.icml.cc", "/"), ("machinelearning.org", "/proceedings/"),
    ("www.machinelearning.org", "/proceedings/"), ("www.ecn.purdue.edu", "/ICML2001/"),
    ("www.hpl.hp.com", "/conferences/icml03/"), ("www.hpl.hp.com", "/conferences/icml2003/"),
    ("www.aicml.cs.ualberta.ca", "/banff04/icml/"), ("www.aicml.cs.ualberta.ca", "/_banff04/icml/"),
    ("oregonstate.edu", "/conferences/icml2007/"),
)  # fmt: skip
MIN_INTERVAL = 3.0  # seconds between requests: the Internet Archive's polite pace, kept for icml.cc too
_CAPTURE = re.compile(r"https://web\.archive\.org/web/([0-9]{14})id_/(https?://\S+)")
_S = re.S | re.I


@dataclass(frozen=True, slots=True)
class SitePage:
    """One row of the table: an official page listing some of a year's papers with their abstracts (or, for
    2007, their titles or one abstract)."""

    year: int
    url: str  # what is fetched: the live official page, or its pinned capture
    official: str  # the official page itself
    parser: str  # a key of `PARSERS`
    charset: str  # the bytes' encoding (the servers name none)
    entries: int  # entries the parser read off it when verified
    verified: date
    note: str

    @property
    def capture(self) -> str | None:
        """The Internet Archive capture's 14-digit timestamp, or None for a live page."""
        m = _CAPTURE.fullmatch(self.url)
        return m.group(1) if m else None


@dataclass(frozen=True, slots=True)
class Entry:
    """What a parser reads off a page: a paper's number (when the page gives one), title and abstract text,
    either of which may be absent (2007's list and per-paper pages each give half)."""

    key: str | None
    title: str | None
    abstract: str | None


@dataclass(frozen=True, slots=True)
class SiteAbstract:
    """One paper on a year's pages: its title as the page gives it, the abstract as a record would hold it, and
    where the abstract came from."""

    title: str
    abstract: str
    spaced: int  # control characters the abstract lost (decision-044)
    url: str
    fetched_at: datetime
    evidence: str
    pdf_codes: int = 0  # `(cid:N)` codes repaired (decision-047)


@dataclass
class SiteYear:
    """What a year's pages gave: the pages as fetched, their papers, every page's fetch time."""

    pages: list[str] = field(default_factory=list)
    entries: list[SiteAbstract] = field(default_factory=list)
    fetched: list[datetime] = field(default_factory=list)
    unjoined: int = (
        0  # halves (a number with only a title, or only an abstract) the year's pages don't complete
    )
    dropped: int = (
        0  # entries with a title and abstract text that leave no title or no usable abstract (empty)
    )


# --- parsers: page text → entries ---------------------------------------------------------------------------------

Parser = Callable[[str, str], list[Entry]]


def _segments(text: str, start: str) -> list[tuple[str, str]]:
    """(the start pattern's first group, the text up to the next start) for each match of `start`."""
    marks = list(re.finditer(start, text, _S))
    return [(m.group(1), text[m.end() : nxt.start() if nxt else len(text)])
            for m, nxt in zip(marks, [*marks[1:], None], strict=True)]  # fmt: skip


# Every parser below finds an opening mark (a pattern that can't run across tags) and then the nearest closing
# string with plain searches, never a lazy `(.*?)` between the two: on a page that lost its closing tags such a
# pattern backtracks from every opening and took minutes on a few hundred kB (the review gate's probe).


def _span(seg: str, opener: str, *ends: str, to_end: bool = False) -> str | None:
    """The text of `seg` after the first match of `opener` up to the nearest of `ends` (case-blind), or to the end
    of `seg` when none is there and `to_end`; None when `opener` isn't there, or no end is and not `to_end`."""
    m = re.search(opener, seg, re.I)
    if m is None:
        return None
    lower = seg.lower()
    found = [i for e in ends if (i := lower.find(e.lower(), m.end())) >= 0]
    if not found and not to_end:
        return None
    return text_of(seg[m.end() : min(found) if found else len(seg)])


def icml2012(text: str, url: str) -> list[Entry]:
    """icml.cc/2012/papers/: `<div class="paper" id="paper-N">` with `<h2>` title, `p.type` and `p.abstract`
    (`<p>` never closed). A paper typed "Not for proceedings" is not in the proceedings and is left out."""
    out = []
    for key, block in _segments(text, r'<div class="paper" id="paper-([0-9]+)">'):
        block = block.split("</div>", 1)[0]
        kind = _span(block, r'<p class="type">', "<p", to_end=True) or ""
        if "not for proceedings" in kind.lower():
            continue
        out.append(Entry(key, _span(block, r"<h2>", "</h2>"),
                         _span(block, r"<strong>\s{0,9}Abstract:\s{0,9}</strong>", "<p", to_end=True)))  # fmt: skip
    return out


def icml2011(text: str, url: str) -> list[Entry]:
    """icml.cc/Conferences/2011/papers.php.html: `<a name='N'><h3>` title, `Abstract:</span>` text `</p>`. The
    Invited Cross-Conference Track after `<a name="cross">` (no abstracts; other venues' papers) is left out."""
    main = text.split('<a name="cross">', 1)[0]
    return [Entry(key, _span(seg, r"<h3\b[^<>]*>", "</h3>"), _span(seg, r"Abstract:\s{0,9}</span>", "</p>"))
            for key, seg in _segments(main, r"<a name='([0-9]+)'>(?=\s*<h3)")]  # fmt: skip


def icml2010(text: str, url: str) -> list[Entry]:
    """icml.cc/Conferences/2010/abstracts.html: `<a name="N">`, `<h3>` title, `<p class="abstracts">`."""
    return [Entry(key, _span(seg, r"<h3>", "</h3>"), _span(seg, r'<p class="abstracts">', "</p>"))
            for key, seg in _segments(text, r'<a name="([0-9]+)"></a>')]  # fmt: skip


def icml2009(text: str, url: str) -> list[Entry]:
    """icml.cc/Conferences/2009/abstracts.html: `<h3><a name="N"></a>` title `</h3>`, authors, `paper ID: N`,
    then the abstract up to the `[Full paper]` links. A heading with no `paper ID` (the sidebar's "For
    Participants", which reuses `name="10"`) is no paper."""
    return [Entry(key, _span(seg, r"^", "</h3>"),
                  _span(seg, r"paper ID:\s{0,9}[0-9]{1,9}\s{0,9}</p>", "[<a", "<hr", to_end=True))
            for key, seg in _segments(text, r'<h3>\s*<a name="([0-9]+)"></a>')
            if re.search(r"paper ID:\s{0,9}[0-9]", seg, re.I)]  # fmt: skip


def _between_authors_and_links(seg: str) -> str | None:
    """2008's abstract: the text after the authors' `<p><i>…</p>` and before the `<p>[Full paper]` links, found with
    plain string searches."""
    authors = re.search(r"<p>\s{0,9}<i>", seg, re.I)
    close = seg.find("</p>", authors.end()) if authors else -1
    links = re.compile(r"<p>\s{0,9}\[<a\b", re.I).search(seg, close) if close >= 0 else None
    return text_of(seg[close + 4 : links.start()]) if links else None


def icml2008(text: str, url: str) -> list[Entry]:
    """icml.cc/Conferences/2008/abstracts.shtml.html: `<a name="N">`, `paper ID`, `<h3>` title, `<p><i>` authors
    `</p>`, then the abstract up to the `<p>[Full paper]` links."""
    return [Entry(key, _span(seg, r"<h3>", "</h3>"), _between_authors_and_links(seg))
            for key, seg in _segments(text, r'<a name="([0-9]+)"></a>')]  # fmt: skip


def _cyberchair_tables(text: str, url: str) -> list[tuple[str, str]]:
    """Each CyberChair table's `<th>` title and second `<td>` (the abstract; the first is the authors), read with
    the shared HTML tree (`html.parse`: bounded, linear), never a backtracking pattern."""
    out = []
    for table in parse(text, url).iter("table"):
        heads, cells = table.iter("th"), table.iter("td")
        if heads and len(cells) >= 2:
            out.append((node_text(heads[0]), node_text(cells[1])))
    return out


def cyberchair(text: str, url: str) -> list[Entry]:
    """A CyberChair "all abstracts" page (ICML 2001, 2003, 2004): one `<table>` per paper, `<th>` title, a `<td>`
    of authors, a `<td>` (often `<pre>`) abstract."""
    return [Entry(None, title, abstract) for title, abstract in _cyberchair_tables(text, url)]


def icml2007_list(text: str, url: str) -> list[Entry]:
    """icml.cc/Conferences/2007/paperlist.html: each paper's number and title, `<a name="N"> title</a>`. Every
    `</a>` is found once and each anchor takes the next one (a binary search), so the page is read in linear time
    whatever it holds."""
    closes = [m.start() for m in re.finditer("</a>", text, re.I)]
    out = []
    for m in re.finditer(r'<a name="([0-9]{1,9})">', text, re.I):
        i = bisect.bisect_left(closes, m.end())
        if i < len(closes):
            out.append(Entry(m.group(1), text_of(text[m.end() : closes[i]]), None))
    return out


def icml2007_paper(text: str, url: str) -> list[Entry]:
    """An ICML 2007 per-paper abstract page (`…/icml2007/abstracts/N.htm`, CyberChair): the number from its URL,
    the abstract from the table's second `<td>`. Its own `<th>` title is PDF-extracted and broken, so unused."""
    number = re.search(r"/abstracts/([0-9]+)\.htm\Z", url)
    tables = _cyberchair_tables(text, url)
    return [Entry(number.group(1), None, tables[0][1])] if number and tables else []


PARSERS: dict[str, Parser] = {
    "icml2012": icml2012, "icml2011": icml2011, "icml2010": icml2010, "icml2009": icml2009,
    "icml2008": icml2008, "cyberchair": cyberchair, "icml2007_list": icml2007_list,
    "icml2007_paper": icml2007_paper,
}  # fmt: skip


# --- the table ----------------------------------------------------------------------------------------------------

_COLUMNS = {"year", "url", "official", "parser", "charset", "entries", "verified", "note"}


def _row(raw: Mapping[str, Any]) -> SitePage:
    where = f"icml_sites.toml {raw.get('year')!r} {raw.get('url')!r}"
    if set(raw) != _COLUMNS:
        raise ValueError(f"{where}: columns must be exactly {sorted(_COLUMNS)}")
    page = SitePage(raw["year"], str(raw["url"]), str(raw["official"]), str(raw["parser"]), str(raw["charset"]),
                    raw["entries"], raw["verified"], str(raw["note"]))  # fmt: skip
    if type(page.year) is not int or not 1988 <= page.year <= 2012:
        raise ValueError(f"{where}: a year from 1988 to 2012")
    if page.parser not in PARSERS:
        raise ValueError(f"{where}: no parser {page.parser!r}")
    if page.charset not in ("utf-8", "cp1252"):
        raise ValueError(f"{where}: charset utf-8 or cp1252")
    if type(page.entries) is not int or page.entries <= 0 or type(page.verified) is not date:
        raise ValueError(f"{where}: entries must be a positive integer and verified a date")
    host = (urlparse(page.url).hostname or "").lower()
    capture = _CAPTURE.fullmatch(page.url)
    if host == ARCHIVE_HOST:
        if capture is None or capture.group(2) != page.official:
            raise ValueError(f"{where}: an Internet Archive URL pins one capture of the official URL, exactly "
                             "(/web/<14 digits>id_/<official>)")  # fmt: skip
        try:
            taken = datetime.strptime(capture.group(1), "%Y%m%d%H%M%S").date()
        except ValueError:
            raise ValueError(f"{where}: the capture timestamp is not a date") from None
        if taken > page.verified:
            raise ValueError(f"{where}: a capture taken after the row was verified")
        if not is_official(page.official):
            raise ValueError(
                f"{where}: a capture of {page.official}, not an official ICML site (OFFICIAL_SITES)"
            )
    elif page.url != page.official or not page.url.startswith("https://") or host != "icml.cc":
        raise ValueError(f"{where}: a live page is an https icml.cc page fetched at its official URL")
    return page


def is_official(url: str) -> bool:
    """Whether `url` is on one of `OFFICIAL_SITES` (host and path prefix; the port the archive keeps is ignored)."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if ".." in parsed.path.split("/"):  # `/ICML2001/../x` is not under /ICML2001/
        return False
    return any(host == h and parsed.path.startswith(prefix) for h, prefix in OFFICIAL_SITES)


def load(text: str) -> Mapping[int, tuple[SitePage, ...]]:
    rows = [_row(r) for r in tomllib.loads(text).get("page", [])]
    by_year: dict[int, list[SitePage]] = {}
    for r in rows:
        if any(p.url == r.url for p in by_year.get(r.year, [])):
            raise ValueError(f"icml_sites.toml: {r.url} is listed twice for {r.year}")
        by_year.setdefault(r.year, []).append(r)
    return MappingProxyType({y: tuple(ps) for y, ps in sorted(by_year.items())})


PAGES: Mapping[int, tuple[SitePage, ...]] = load(
    files("openproceedings.ingest").joinpath("icml_sites.toml").read_text(encoding="utf-8")
)


def hosts_of(pages: Mapping[int, tuple[SitePage, ...]]) -> frozenset[str]:
    """The hosts a table's pages are fetched from."""
    return frozenset((urlparse(p.url).hostname or "").lower() for ps in pages.values() for p in ps)


# the only hosts this source fetches: the table's pages' (icml.cc, and the Internet Archive)
HOSTS: frozenset[str] = hosts_of(PAGES)


# --- reading a year --------------------------------------------------------------------------------------------


def _evidence(page: SitePage) -> str:
    if page.capture is not None:
        return f"official ICML {page.year} page {page.official}, Internet Archive capture {page.capture}"
    return f"official ICML {page.year} page {page.official}"


def read_year(
    year: int, fetcher: Fetcher, *, refresh: bool = False, pages: Mapping[int, tuple[SitePage, ...]] | None = None,
) -> SiteYear | None:  # fmt: skip
    """The year's papers from its pages through `fetcher` (offline: the cache only), or None when the table has
    none. A page that isn't there (404/410), or that now gives another number of entries than the table verified,
    stops the crawl: a person checks it. A paper needs a title and an abstract that is not empty or snippet-shaped
    (`clean_abstract`); 2007's halves are joined by paper number."""
    rows = (PAGES if pages is None else pages).get(year)
    if not rows:
        return None
    out = SiteYear()
    started = fetcher.clock.monotonic()
    beat = Heartbeat(fetcher.clock.monotonic)  # 2007 has 151 pages, 3 s apart
    log.info("icml_site_year_started", extra={"year": year, "pages": len(rows)})
    titles: dict[str, str] = {}
    halves: list[tuple[str, str, SitePage, Page]] = []  # (number, abstract text, page, fetched)
    complete: list[tuple[str, str, SitePage, Page]] = []  # (title, abstract text, page, fetched)
    for n, page in enumerate(rows, 1):
        if beat.due():
            log.info("icml_site_year_progress", extra={"year": year, "done": n - 1, "of": len(rows)})
        try:
            fetched = fetcher.get(page.url, refresh=refresh, charset=page.charset)
        except FetchError as err:
            if err.reason != "undecodable":
                raise
            raise CrawlError(f"ICML {year}: {page.url} is not {page.charset}; its table row's charset is wrong "
                             "(fix it, then fetch the page again)", reason="wrong_charset") from err  # fmt: skip
        if not fetched.ok:
            raise CrawlError(f"ICML {year}: {page.url} answered HTTP {fetched.status}", reason="no_listing")
        got = PARSERS[page.parser](fetched.text, page.url)
        if len(got) != page.entries:
            raise CrawlError(f"ICML {year}: {page.url} gives {len(got)} entries, the table verified "
                             f"{page.entries}; check the page and the parser", reason="site_count_mismatch")  # fmt: skip
        if page.charset == "cp1252" and _utf8_in_cp1252(fetched.text):
            raise CrawlError(f"ICML {year}: {page.url} reads as UTF-8 decoded as cp1252; its table row's charset "
                             "is wrong (fix it, then fetch the page again with --refresh)",
                             reason="wrong_charset")  # fmt: skip
        out.pages.append(page.url)
        out.fetched.append(fetched.fetched_at)
        for e in got:
            if e.title is not None and e.abstract is not None:
                complete.append((e.title, e.abstract, page, fetched))
            elif e.title is not None and e.key is not None:
                if e.key in titles:
                    raise CrawlError(f"ICML {year}: paper {e.key} is listed twice on {page.url}",
                                     reason="duplicate_paper")  # fmt: skip
                titles[e.key] = e.title
            elif e.abstract is not None and e.key is not None:
                halves.append((e.key, e.abstract, page, fetched))
    complete += [(titles[k], a, p, f) for k, a, p, f in halves if k in titles]
    joined = {k for k, *_ in halves if k in titles}
    out.unjoined = sum(k not in titles for k, *_ in halves) + sum(k not in joined for k in titles)
    for raw_title, raw_abstract, page, fetched in complete:
        title = title_text(raw_title)[0]
        cleaned = clean_abstract(raw_abstract)
        if title and cleaned.text:
            out.entries.append(SiteAbstract(title, cleaned.text, cleaned.spaced, page.url, fetched.fetched_at,
                                            _evidence(page), cleaned.pdf_codes))  # fmt: skip
        else:
            out.dropped += 1
    log.info("icml_site_year_read", extra={
        "year": year, "pages": len(out.pages), "entries": len(out.entries), "unjoined": out.unjoined,
        "dropped": out.dropped, "ms": round((fetcher.clock.monotonic() - started) * 1000, 1)})  # fmt: skip
    return out


def _utf8_in_cp1252(text: str) -> bool:
    """Whether text decoded as cp1252 was UTF-8 (`â€™` for `’`): its non-ASCII bytes form valid UTF-8."""
    if text.isascii():
        return False
    try:
        raw = text.encode("cp1252")
        raw.decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return False
    return True


def plan_year(
    year: int, fetcher: Fetcher, pages: Mapping[int, tuple[SitePage, ...]] | None = None
) -> dict[str, Any]:
    """A dry run's view of a year: its pages and how many are not yet cached."""
    rows = (PAGES if pages is None else pages).get(year, ())
    return {"year": year, "pages": len(rows), "to_fetch": sum(not fetcher.is_cached(p.url) for p in rows)}
