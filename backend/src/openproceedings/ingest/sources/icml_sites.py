"""Abstracts for ICML 1988–2012 from the official ICML conference pages (spec 01 §Sources, ICML sites row;
decision-047; TASK-206).

dblp gives the pre-2013 ICML papers no abstracts. Some years' official conference sites listed them, and some of
those pages survive: live on icml.cc (which still serves the 2007–2012 sites' pages), or as an Internet Archive
capture of the conference's own site (1997's program page, 1998's per-submission pages, 2001, 2003, 2004 and 2007's
per-paper pages). 1997 and 1998's pages are the submissions as the authors filled in the form, contact details
included: only the abstract is kept, and one that still holds a contact detail is withheld (TASK-207, owner
decision of 2026-10-07). The per-year survey is
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
and evidence naming the official URL and the capture (and, for 1997 and 1998, that the abstract is as submitted).
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

from openproceedings.ingest.dedup import AS_SUBMITTED
from openproceedings.ingest.record import Source, title_text
from openproceedings.ingest.sources.common import CrawlError, clean_abstract
from openproceedings.ingest.sources.html import Element, collapse, node_text, parse, text_of, unescape
from openproceedings.ingest.sources.http import Fetcher, FetchError, Heartbeat, Page

log = logging.getLogger(__name__)

SOURCE: Source = "icml_site"
CACHE_DIR = "icml_sites"  # <data>/cache/icml_sites
ARCHIVE_HOST = "web.archive.org"
# The official sites a capture may be of: (host, path prefix), each named as that year's ICML site by an official
# page (icml.cc's "past conferences" pages: Conferences/2007/pastconferences.html names the 2001 Purdue, 2003 HP
# Labs and 2004 Banff sites, Conferences/2008/past_icmls.shtml.html the 2007 Oregon State one; the 2003 site's own
# titlesAndAuthors.html links each paper to /conferences/icml2003/allAbstracts.html, and icml.cc names the Banff site
# as /_banff04/icml/, whose pages the archive holds at /banff04/icml/, their stylesheet's own path; the same icml.cc
# pages name the 1998 Madison site, www.cs.wisc.edu/icml98/, which also answered at /ICML98/ (the archive holds both
# spellings with the same digests; five papers' earliest captures are under /ICML98/); no icml.cc page names a 1997 site, but the ICML-97/COLT-97
# site's joint schedule, ~mlccolt/schedule.html, capture 19980209071717, links each ICML-97 paper to
# ~icml97/program.html#N, TASK-207). A capture of anything else,
# another page of those hosts included, is refused when the table loads: never ACM DL, arXiv, Scholar or an author.
OFFICIAL_SITES: tuple[tuple[str, str], ...] = (
    ("icml.cc", "/"), ("www.icml.cc", "/"), ("machinelearning.org", "/proceedings/"),
    ("www.machinelearning.org", "/proceedings/"), ("www.ecn.purdue.edu", "/ICML2001/"),
    ("www.hpl.hp.com", "/conferences/icml03/"), ("www.hpl.hp.com", "/conferences/icml2003/"),
    ("www.aicml.cs.ualberta.ca", "/banff04/icml/"), ("www.aicml.cs.ualberta.ca", "/_banff04/icml/"),
    ("oregonstate.edu", "/conferences/icml2007/"), ("cswww.vuse.vanderbilt.edu", "/~icml97/"),
    ("www.cs.wisc.edu", "/icml98/"), ("www.cs.wisc.edu", "/ICML98/"),
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
    # 1997/1998: an abstract withheld (a contact detail, or no field ends it), never kept
    withheld: bool = False


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
    # entries with a title and abstract text that leave no title or no usable abstract (empty; for 1997 and 1998
    # also a submission with no `Abstract` heading)
    dropped: int = 0
    # 1997/1998 abstracts withheld whole: a contact detail, or no field ends them (TASK-207)
    withheld: int = 0
    # the year's pages are submissions (`SUBMISSION_PARSERS`): its abstracts are as submitted
    as_submitted: bool = False


# --- parsers: page text → entries ---------------------------------------------------------------------------------

Parser = Callable[[str, str], list[Entry]]


def _segments(text: str, start: str) -> list[tuple[str, str]]:
    """(the start pattern's first group, the text up to the next start) for each match of `start`."""
    marks = list(re.finditer(start, text, _S))
    nexts = [m.start() for m in marks[1:]] + ([len(text)] if marks else [])  # no mark: no segment at all
    return [(m.group(1), text[m.end() : nxt]) for m, nxt in zip(marks, nexts, strict=True)]


# Every parser below finds an opening mark (a pattern that can't run across tags) and then the nearest closing
# pattern of fixed shape, searched forward once (CyberChair walks the HTML tree, 2007's list uses a binary search),
# never a lazy `(.*?)` between the two: on a page that lost its closing tags such a
# pattern backtracks from every opening and took minutes on a few hundred kB (the review gate's probe).


def _span(seg: str, opener: str, *ends: str, to_end: bool = False) -> str | None:
    """The text of `seg` after the first match of `opener` up to the nearest match of any of `ends` (patterns of
    fixed shape, case-blind, searched forward once), or to the end of `seg` when none is there and `to_end`; None
    when `opener` isn't there, or no end is and not `to_end`."""
    m = re.search(opener, seg, re.I)
    if m is None:
        return None
    end = re.compile("|".join(ends), re.I).search(seg, m.end())
    if end is None and not to_end:
        return None
    return text_of(seg[m.end() : end.start() if end else len(seg)])


def icml2012(text: str, url: str) -> list[Entry]:
    """icml.cc/2012/papers/: `<div class="paper" id="paper-N">` with `<h2>` title, `p.type` and `p.abstract`
    (`<p>` never closed). A paper typed "Not for proceedings" is not in the proceedings and is left out."""
    out = []
    for key, block in _segments(text, r'<div class="paper" id="paper-([0-9]+)">'):
        block = block.split("</div>", 1)[0]
        kind = _span(block, r'<p class="type">', r"<p\b", to_end=True) or ""
        if "not for proceedings" in kind.lower():
            continue
        out.append(Entry(key, _span(block, r"<h2>", r"</h2>"),
                         _span(block, r"<strong>\s{0,9}Abstract:\s{0,9}</strong>", r"<p\b", to_end=True)))  # fmt: skip
    return out


def icml2011(text: str, url: str) -> list[Entry]:
    """icml.cc/Conferences/2011/papers.php.html: `<a name='N'><h3>` title, `Abstract:</span>` text `</p>`. The
    Invited Cross-Conference Track after `<a name="cross">` (no abstracts; other venues' papers) is left out."""
    main = re.split(r'<a name="cross">', text, maxsplit=1, flags=re.I)[0]
    return [Entry(key, _span(seg, r"<h3\b[^<>]*>", r"</h3>"), _span(seg, r"Abstract:\s{0,9}</span>", r"</p>"))
            for key, seg in _segments(main, r"<a name='([0-9]+)'>(?=\s*<h3)")]  # fmt: skip


def icml2010(text: str, url: str) -> list[Entry]:
    """icml.cc/Conferences/2010/abstracts.html: `<a name="N">`, `<h3>` title, `<p class="abstracts">`."""
    return [Entry(key, _span(seg, r"<h3>", r"</h3>"), _span(seg, r'<p class="abstracts">', r"</p>"))
            for key, seg in _segments(text, r'<a name="([0-9]+)"></a>')]  # fmt: skip


def icml2009(text: str, url: str) -> list[Entry]:
    """icml.cc/Conferences/2009/abstracts.html: `<h3><a name="N"></a>` title `</h3>`, authors, `paper ID: N`,
    then the abstract up to the `[Full paper]` links. A heading with no `paper ID` (the sidebar's "For
    Participants", which reuses `name="10"`) is no paper."""
    return [Entry(key, _span(seg, r"^", r"</h3>"),
                  _span(seg, r"paper ID:\s{0,9}[0-9]{1,9}\s{0,9}</p>", r"\[<a\b", r"<hr", to_end=True))
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
    return [Entry(key, _span(seg, r"<h3>", r"</h3>"), _between_authors_and_links(seg))
            for key, seg in _segments(text, r'<a name="([0-9]+)"></a>')]  # fmt: skip


def _cyberchair_tables(text: str, url: str) -> list[tuple[str, str]]:
    """Each top-level CyberChair table's `<th>` title and second `<td>` (the abstract; the first is the authors),
    from one walk of the shared HTML tree (`html.parse`). A cell belongs to its nearest table, and a table inside
    another is no paper's table: each top-level table's subtree is read once, so nested tables can't multiply the
    work (the review gate's probe: a thousand nested tables). The shared tree doesn't close implied end tags, so a
    cell left unclosed holds the next one; the walk goes on inside cells and takes each cell in document order, so
    that next cell is still the table's."""
    tables: list[tuple[list[Element], list[Element]]] = []  # (th cells, td cells) of each top-level table
    stack: list[tuple[Element, int | None, bool]] = [
        (parse(text, url), None, False)
    ]  # (node, its table, nested)
    while stack:  # depth-first, in document order: a frame's children are pushed in reverse
        node, table, nested = stack.pop()
        if node.tag == "table":
            if table is None and not nested:  # a top-level table, met in document order
                tables.append(([], []))
                table = len(tables) - 1
            else:
                table, nested = None, True  # a table inside another: its cells are nobody's
        elif table is not None and node.tag in ("th", "td"):
            tables[table][0 if node.tag == "th" else 1].append(node)
        stack.extend(reversed([(c, table, nested) for c in node.children if isinstance(c, Element)]))
    return [(node_text(th[0]), node_text(td[1])) for th, td in tables if th and len(td) >= 2]


def cyberchair(text: str, url: str) -> list[Entry]:
    """A CyberChair "all abstracts" page (ICML 2001, 2003, 2004): one `<table>` per paper, `<th>` title, a `<td>`
    of authors, a `<td>` (often `<pre>`) abstract."""
    return [Entry(None, title, abstract) for title, abstract in _cyberchair_tables(text, url)]


def icml2007_list(text: str, url: str) -> list[Entry]:
    """icml.cc/Conferences/2007/paperlist.html: each paper's number and title, `<a name="N"> title</a>`. Every
    `</a>` is found once and each anchor takes the next one (a binary search) only when it comes before the next
    anchor; otherwise the anchor gives no entry and the page's entry count stops the crawl. The page is read in
    linear time whatever it holds."""
    closes = [m.start() for m in re.finditer("</a>", text, re.I)]
    marks = list(re.finditer(r'<a name="([0-9]{1,9})">', text, re.I))
    out = []
    nexts = [x.start() for x in marks[1:]] + ([len(text)] if marks else [])  # no anchor: no entry at all
    for m, nxt in zip(marks, nexts, strict=True):
        i = bisect.bisect_left(closes, m.end())
        if (
            i < len(closes) and closes[i] <= nxt
        ):  # its own `</a>`, before the next anchor: slices never overlap
            out.append(Entry(m.group(1), text_of(text[m.end() : closes[i]]), None))
    return out


def icml2007_paper(text: str, url: str) -> list[Entry]:
    """An ICML 2007 per-paper abstract page (`…/icml2007/abstracts/N.htm`, CyberChair): the number from its URL,
    the abstract from the table's second `<td>`. Its own `<th>` title is PDF-extracted and broken, so unused."""
    number = re.search(r"/abstracts/([0-9]+)\.htm\Z", url)
    tables = _cyberchair_tables(text, url)
    return [Entry(number.group(1), None, tables[0][1])] if number and tables else []


# --- 1997 and 1998: submission-time abstracts beside the authors' contact details (TASK-207) ---------------------
#
# Both years' pages are the call for papers' submission form as each author filled it in, free text: a title, the
# authors with postal addresses, an abstract, keywords, then the contact author's e-mail address and phone (and
# fax) number, in a layout and wording that vary by paper. Only the abstract is kept: the text after an `Abstract`
# heading line up to the first line that starts a later field (keywords, e-mail, phone, …); an abstract that no
# such line ends is withheld, since what follows it is unknown. What is kept is checked again (`contact_detail`):
# an abstract that still holds an e-mail address, a phone-shaped number, a contact label or a postal code is
# withheld whole and counted, never cut and never logged. An entry with no `Abstract` heading gives no abstract (the author block and the
# abstract run together there, so no line can be trusted to start it).

_BLOCK = re.compile(
    r"<(?:br|p|/p|ol|/ol|ul|/ul|li|/li|dl|/dl|dt|dd|hr|pre|/pre|h[1-6]|/h[1-6]|div|/div|table|/table|tr|/tr|td|/td|"
    r"th|/th|blockquote|/blockquote|center|/center)\b[^<>]{0,2000}>", re.I)  # fmt: skip
_TAG = re.compile(r"<[^<>]{0,2000}>")
# an `Abstract` heading: the word alone on its line, maybe with a parenthesis ("(200 word maximum)") and a colon,
# or with a colon and the abstract's first words after it
_ABSTRACT_HEAD = re.compile(
    r"abstract(?:[ \t]{0,9}\([^()\n]{0,80}\))?[ \t]{0,9}(?::[ \t]{0,9}(.*)|\.?)", re.I
)
_FIELD = re.compile(  # a line that starts a field the form puts after the abstract
    r"(?:key[ \t-]?words?\b"  # `Keywords`, `KEY WORDS:`
    # a contact field, whatever words follow its label: `Email address of contact author:`, `Phone number (X):`
    r"|(?:e-?mail|electronic mail|phone|telephone|tel\b|fax|voice|contact|corresponding author)[^:\n]{0,60}:"
    # an address block, however it is labelled: `Mailing address`, `Contact author Alex Example`
    r"|(?:mailing|postal|street) address(?:es)?\b|contact(?:ing)? author\b"
    # an author or address heading alone on its line, as a bare `Abstract` heading is
    r"|(?:authors?|author\(s\)|address(?:es)?|affiliations?)[ \t]{0,9}:?[ \t]{0,9}\Z"
    # another field only with its colon right after the label, so `Areas under the ROC curve: …` and `we address
    # this: …` don't end it (the latter's `address:` is a contact label, so `contact_detail` withholds that abstract):
    # `Authors:`, `Address:`, `Affiliation:`, `Title:`, `Topic:`
    r"|(?:topics?|areas?|category|paper (?:category|type)|track|submitted|authors?|author\(s\)|address(?:es)?"
    r"|affiliations?|title)[ \t]{0,9}:)",
    re.I,
)
_EMAIL = re.compile(  # any `@`, or an address spelled out: `name at cs dot example dot edu`, `name {at} host.ac.uk`
    r"@|\b[\w.+-]{1,64} ?(?:\(at\)|\[at\]|\{at\}| at ) ?(?:[\w-]{1,64}(?:\.| ?\(dot\) ?| ?\{dot\} ?| ?\[dot\] ?| dot )){1,4}[a-z]{2,6}\b",
    re.I,
)
_PHONE = re.compile(
    r"(?<![\w)+])\+\(?[0-9][0-9 ()./-]{5,40}[0-9]"  # +1 503 737 5552, +(34-1) 624 9418; never `t+1` or `a + b`
    r"|\([0-9]{3}\)[-. ]{0,3}[0-9]{3}[-. ][0-9]{4}\b"  # (609) 258-4455, (541)-737-5552
)
# digits, alone or in groups joined by `-`, `.`, `/` or a space, read as a phone number when they hold 7 digits or
# more and are not all years: 5550199, 609-258-4455, 972-3-640-8829, 624 9418; never `1993-1997`, `1987 1988 1989`
# or `10 000`. It errs towards withholding: `1 000 000` or `84.5 85.2 86.7` read as a phone number too, which only
# withholds an abstract (counted), never lets a number through; keep it that way.
_DIGIT_GROUPS = re.compile(r"\b[0-9]{1,6}(?:[-./ ][0-9]{1,6}){1,5}\b")
_YEAR = re.compile(r"(?:19|20)[0-9]{2}")
_RUN = re.compile(r"[0-9]{7}")  # seven digits in a row, however long the run: 5550199, 6095550199
_RULE = re.compile(r"[-=_*~ \t]{3,200}")  # a line of dashes under a heading
_LABEL = re.compile(r"\b(?:e-?mail|phone|telephone|tel|fax|voice)\s{0,3}[:.]|\baddress(?:es)?\s{0,3}:", re.I)
_POSTAL = re.compile(  # a postal code or a street address, in the forms an ICML author's address took
    r"\b[A-Z]{2}[ \t]{1,3}[0-9]{5}(?:-[0-9]{4})?\b"  # a US state and ZIP code: `NJ 08544-2087`
    r"|\b[A-Z]{1,2}[0-9][0-9A-Z]? [0-9][A-Z]{2}\b"  # a UK postcode: `EX1 2ZZ`
    r"|\b[A-Z][0-9][A-Z] ?[0-9][A-Z][0-9]\b"  # a Canadian one: `K1A 0R6`
    r"|\b[A-Z]{1,2}-[0-9]{4,5}\b"  # a European one with its country letter: `D-53754`, `NL-6500`
    r"|\b[0-9]{4} ?[A-Z]{2}\b"  # a Dutch one: `6500 HB` (and `4096 MB`, which only withholds)
    r"|\b[0-9]{1,5} [A-Z][a-z]+(?: [A-Z][a-z]+)? (?:Road|Street|Avenue|Ave|St|Rd|Drive|Blvd|Lane|Way|Strasse|Straße)\b"
)


def _phone(text: str) -> bool:
    if _PHONE.search(text) or _RUN.search(text):
        return True
    for m in _DIGIT_GROUPS.finditer(text):
        groups = re.split(r"[-./ ]", m.group())
        if sum(map(len, groups)) >= 7 and not all(_YEAR.fullmatch(g) for g in groups):
            return True
    return False


def contact_detail(text: str) -> str | None:
    """Which kind of contact detail `text` holds (`email`, `phone`, `label`, `postal`), or None. Checked on every
    1997/1998 abstract before it is kept: such an abstract is withheld whole."""
    if _EMAIL.search(text):
        return "email"
    if _phone(text):
        return "phone"
    for kind, pattern in (("label", _LABEL), ("postal", _POSTAL)):
        if pattern.search(text):
            return kind
    return None


def _lines(fragment: str) -> list[str]:
    """A fragment's text, one string per line: block tags become line breaks, other tags go, entities decode."""
    return [collapse(unescape(_TAG.sub(" ", line))) for line in _BLOCK.sub("\n", fragment).split("\n")]


def _submission_abstract(lines: list[str]) -> tuple[str | None, bool]:
    """(the abstract, withheld) from a submission's lines: the text after the first `Abstract` heading up to the
    next field, a blank line after it never ending it; (None, False) with no heading; (None, True) when no field
    ends it (what follows it is unknown) or what is left still holds a contact detail."""
    heads = ((i, m) for i, line in enumerate(lines) if (m := _ABSTRACT_HEAD.fullmatch(line)))
    start, head = next(heads, (None, None))
    if start is None or head is None:
        return None, False
    body: list[str] = [head.group(1)] if head.group(1) else []
    ended = False
    for line in lines[start + 1 :]:
        if _FIELD.match(line):
            ended = True
            break
        if not _RULE.fullmatch(line):  # a line of dashes under the heading is layout, not text
            body.append(line)
    text = collapse(" ".join(body))
    # no field ends it: whatever follows (an address in a layout the rules don't know) may be in it, so withhold
    if not ended or contact_detail(text) is not None:
        return None, True
    return text, False


def icml1997(text: str, url: str) -> list[Entry]:
    """cswww.vuse.vanderbilt.edu/~icml97/program.html: a list `<li><a href="#N"> title</a>`, then each paper's
    `<a name="N"></a>` and its submission as free text (`_submission_abstract`). The title is the list's."""
    titles: dict[str, str] = {}
    for m in re.finditer(r'<li>[ \t]{0,9}<a href="#([0-9]{1,9})">([^<>]{0,2000})</a>', text, re.I):
        titles.setdefault(m.group(1), text_of(m.group(2)))
    out = []
    for key, seg in _segments(text, r'<a name="([0-9]{1,9})"></a>'):
        abstract, withheld = _submission_abstract(_lines(seg))
        out.append(Entry(key, titles.get(key), abstract or "", withheld))
    return out


_TITLE_LABEL = re.compile(r"title[ \t]{0,9}:[ \t]{0,9}(.*)", re.I)
_AFTER_TITLE = re.compile(r"(?:authors?|author\(s\)|abstract)\b", re.I)


def _submission_title(lines: list[str]) -> str | None:
    """A 1998 submission's title: after a `Title:` label (on its line, or the lines after it up to a blank line or
    the authors), else the first lines of text up to a blank line."""
    labels = ((i, m) for i, line in enumerate(lines) if (m := _TITLE_LABEL.fullmatch(line)))
    at, label = next(labels, (None, None))
    rest = lines if at is None or label is None else [label.group(1), *lines[at + 1 :]]
    words: list[str] = []
    for line in rest:
        if not line:
            if words:
                break
            continue
        if words and _AFTER_TITLE.match(line):
            break
        words.append(line)
    return collapse(" ".join(words)) or None


def icml1998_paper(text: str, url: str) -> list[Entry]:
    """A per-submission page of the ICML-98 site (`…/icml98/papers/paperN.html`): `<H1>ICML-98 Submission #N</H1>`,
    then the submission as free text, in a `<PRE>` or in HTML. The number is the URL's and must be the heading's;
    the title is the text's own (`_submission_title`)."""
    number = re.search(r"/paper([0-9]{1,9})\.html\Z", url)
    head = re.search(r"<h1>[ \t]{0,9}ICML-98 Submission #([0-9]{1,9})[ \t]{0,9}</h1>", text, re.I)
    if number is None or head is None or head.group(1) != number.group(1):
        return []
    lines = _lines(text[head.end() :])
    abstract, withheld = _submission_abstract(lines)
    return [Entry(number.group(1), _submission_title(lines), abstract or "", withheld)]


# the parsers whose pages are submissions: their abstracts are as submitted, not as published
SUBMISSION_PARSERS = frozenset({"icml1997", "icml1998_paper"})

PARSERS: dict[str, Parser] = {
    "icml2012": icml2012, "icml2011": icml2011, "icml2010": icml2010, "icml2009": icml2009,
    "icml2008": icml2008, "cyberchair": cyberchair, "icml2007_list": icml2007_list,
    "icml2007_paper": icml2007_paper, "icml1997": icml1997, "icml1998_paper": icml1998_paper,
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
    where = f"official ICML {page.year} page {page.official}"
    if page.capture is not None:
        where += f", Internet Archive capture {page.capture}"
    if page.parser in SUBMISSION_PARSERS:  # the marker `dedup.attribution` reads back (TASK-210)
        where += f": {AS_SUBMITTED}; the page's contact details are not kept"
    return where


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
            # a capture's bytes never change, and some 1990s pages never had `</html>`: whole by Content-Length
            fetched = fetcher.get(
                page.url, refresh=refresh, charset=page.charset, by_length=page.capture is not None
            )
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
        out.as_submitted |= page.parser in SUBMISSION_PARSERS
        out.fetched.append(fetched.fetched_at)
        for e in got:
            # a submission's abstract withheld (a contact detail, or no field ends it): counted, never kept
            if e.withheld:
                out.withheld += 1
            elif e.title is not None and e.abstract is not None:
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
        "dropped": out.dropped, "withheld": out.withheld, "ms": round((fetcher.clock.monotonic() - started) * 1000, 1)})  # fmt: skip
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
