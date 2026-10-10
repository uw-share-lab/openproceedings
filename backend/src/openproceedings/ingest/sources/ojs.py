"""ojs.aaai.org miner: AAAI 2010-2026, AIES 2024+ and IASEAI 2026+ through OAI-PMH (spec 01 §Sources, OJS row;
decision-049).

Each journal (`ojs_table.TABLE.journals`) is harvested set by set: its own sets (`<journal>:…`) from `ListSets`
(paginated for AAAI), then per set `ListRecords&set=…` in `oai_dc` and each `resumptionToken` in turn, every page
through the shared HTTP layer (XML judged whole by its root's closing tag; the query string names the page, so it is
the cache key). Per set, not one journal-wide chain, because one record the server cannot render makes its whole page
answer HTTP 500, and a failed page has no next token: journal-wide that hides everything after it (AAAI article
39173 hid 2,785 records, checked 2026-10-09); per set it hides part of one set, which the fallback recovers.

**Fallback.** When a set's ListRecords page answers HTTP 5xx after every retry, the set's `ListIdentifiers` chain
lists its articles, and each live article the ListRecords chain had not reached is read by `GetRecord`. An article
whose GetRecord also fails is `unavailable`: listed in its volume and never a record, if the table names it in an
`[[unavailable]]` row; an unnamed one stops the crawl. The set's deleted headers are then counted from
ListIdentifiers (every one, as `completeListSize` counts them).

**Replay.** A page that failed with HTTP 5xx after every retry is cached as that status (an empty page: `_get`), so
the failure itself is in the cache: a crawl is replayed offline by following the same chains through the cache, the
cached failure sends the replay down the same fallback, and the replay fetches nothing and gives the same records.
`--refresh` fetches each chain's first page (and a cached failure) again. OJS tokens are opaque and expire after
24 h: a resumed crawl whose next token the server no longer knows gets `badResumptionToken`, which stops the crawl
with what to do (`--refresh` starts the chains again).

A record's article id is its native id (`ojs-<id>`), its section (`setSpec`) and volume (`dc:source`'s
`Vol. N No. M`) name its table row, which gives the track and the year (`ojs_table`); a volume or section the table
lacks stops the crawl. Deleted headers and front-matter sections are counted, never records. The abstract is
`dc:description` (the English one, else the first), cleaned like every abstract (`common.clean_abstract`).
Authors come as `Last, First` and are shown `First Last` (`display_name`). Every record is `accepted`.
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote
from xml.parsers import expat

from pydantic import ValidationError

from openproceedings.ingest.ojs_table import TABLE, Table
from openproceedings.ingest.record import (
    Claim,
    ClaimField,
    ClaimValue,
    PaperRecord,
    Source,
    controls_evidence,
    is_url,
    title_evidence,
    title_text,
)
from openproceedings.ingest.sources.common import (
    Cleaned,
    CrawlError,
    ListingReport,
    clean_abstract,
    pdf_codes_evidence,
    record_from_claims,
)
from openproceedings.ingest.sources.http import Fetcher, Page, RetriesExhausted
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)

SOURCE: Source = "ojs"
CACHE_DIR = "ojs"  # <data>/cache/ojs
HOST = "ojs.aaai.org"
HOSTS = frozenset({HOST})
MIN_INTERVAL = 3.0  # seconds between requests: the server takes 2-3 s a page (checked 2026-10-09)
PROGRESS_SECONDS = 30.0

_OAI = "{http://www.openarchives.org/OAI/2.0/}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_ARTICLE = re.compile(r"oai:ojs\.aaai\.org:article/([0-9]+)")
# A deleted header from before the 2020 move to ojs.aaai.org keeps the old repository's identifier (AAAI holds
# such headers, datestamp 2020-06-02; checked 2026-10-09). A deleted header is only counted, so it may carry one;
# a live record never may (its article id is its native id).
_OLD_DELETED = re.compile(r"oai:ojs\.pkp\.sfu\.ca:article/([0-9]+)")
_VOLUME = re.compile(r";\s*Vol\.\s*([0-9]+)\s+No\.\s*[0-9]+")
_DOI = re.compile(r"10\.1609/\S+")
_EMPTY_LIST = "noRecordsMatch"  # an OAI-PMH error code that means an empty list, not a failure


def _list_url(verb: str, journal: str, token: str | None, set_spec: str | None) -> str:
    base = f"https://{HOST}/index.php/{journal}/oai?verb={verb}&"
    if token is not None:  # OAI-PMH: a resumption token is the request's only other argument
        return base + f"resumptionToken={quote(token, safe='')}"
    return base + "metadataPrefix=oai_dc" + ("" if set_spec is None else f"&set={quote(set_spec, safe=':')}")


def oai_url(journal: str, token: str | None = None, *, set_spec: str | None = None) -> str:
    """A ListRecords page: the first (of the journal, or of one set) or the one a token names."""
    return _list_url("ListRecords", journal, token, set_spec)


def ids_url(journal: str, token: str | None = None, *, set_spec: str | None = None) -> str:
    """A ListIdentifiers page (headers only), the fallback's list of a set's articles."""
    return _list_url("ListIdentifiers", journal, token, set_spec)


def record_url(journal: str, article: int) -> str:
    """One article's GetRecord in oai_dc."""
    return (f"https://{HOST}/index.php/{journal}/oai?verb=GetRecord&metadataPrefix=oai_dc"
            f"&identifier=oai:{HOST}:article/{article}")  # fmt: skip


@dataclass(frozen=True, slots=True)
class OaiRecord:
    article: int
    deleted: bool
    set_spec: str
    title: str | None = None
    creators: tuple[str, ...] = ()
    description: str | None = None
    doi: str | None = None
    article_url: str | None = None
    pdf_url: str | None = None
    volume: int | None = None


def _refuse_doctype(*_args: object) -> None:
    raise CrawlError(
        "an OAI-PMH page declared a DOCTYPE; refused (no entities from a response)", reason="oai_unreadable"
    )


def _root(text: str) -> ET.Element:
    """The document's root element, parsed by expat with every DOCTYPE refused, wherever it sits: no entity is
    ever declared or expanded (no XXE, no billion laughs), the posture `dblp_xml.py` takes with expat (it allows
    only its pinned DTD). The stdlib's C `XMLParser` exposes no expat handlers, so expat feeds a `TreeBuilder`;
    an exception a handler raises (the refusal) comes out of `Parse` unchanged."""
    builder = ET.TreeBuilder()
    # `uri}local` becomes ElementTree's `{uri}local`; the text is already decoded, so its declaration is overridden
    parser = expat.ParserCreate("utf-8", namespace_separator="}")

    def qualified(name: str) -> str:
        return "{" + name if "}" in name else name

    def start(name: str, attrs: dict[str, str]) -> None:
        builder.start(qualified(name), {qualified(k): v for k, v in attrs.items()})

    parser.StartDoctypeDeclHandler = _refuse_doctype
    parser.EntityDeclHandler = _refuse_doctype
    parser.StartElementHandler = start
    parser.EndElementHandler = lambda name: builder.end(qualified(name))
    parser.CharacterDataHandler = builder.data
    parser.buffer_text = True
    try:
        parser.Parse(text.encode("utf-8"), True)
    except expat.ExpatError:
        raise CrawlError("an ojs.aaai.org OAI-PMH page is not XML", reason="oai_unreadable") from None
    return builder.close()


def _english_first(nodes: list[ET.Element]) -> str | None:
    texts = [(n.get(_LANG, ""), (n.text or "").strip()) for n in nodes if (n.text or "").strip()]
    return next((t for lang, t in texts if lang.lower().startswith("en")), texts[0][1] if texts else None)


def _listing(text: str, verb: str, empty: frozenset[str] = frozenset({_EMPTY_LIST})) -> ET.Element | None:
    """The `verb` element of an OAI-PMH response; None for an error code that means an empty answer."""
    root = _root(text)
    if root.tag != f"{_OAI}OAI-PMH":
        raise CrawlError("an ojs.aaai.org page is not an OAI-PMH response", reason="oai_unreadable")
    if (err := root.find(f"{_OAI}error")) is not None:
        code = err.get("code", "")
        if code in empty:
            return None
        hint = (
            " (the resumption token expired: re-run with --refresh)" if code == "badResumptionToken" else ""
        )
        raise CrawlError(f"ojs.aaai.org answered OAI-PMH error {code}{hint}", reason="oai_error")
    listing = root.find(f"{_OAI}{verb}")
    if listing is None:
        raise CrawlError(f"an OAI-PMH response has no {verb}", reason="oai_unreadable")
    return listing


def _token(listing: ET.Element) -> str | None:
    node = listing.find(f"{_OAI}resumptionToken")
    token = (node.text or "").strip() if node is not None else ""
    return token or None


def _header(header: ET.Element | None) -> OaiRecord:
    """The article id, deletion and set of a record's header (no metadata)."""
    ident = header.findtext(f"{_OAI}identifier", "") if header is not None else ""
    m = _ARTICLE.fullmatch(ident.strip())
    if m is None and header is not None and header.get("status") == "deleted":
        m = _OLD_DELETED.fullmatch(ident.strip())
    if header is None or m is None:
        raise CrawlError(f"an OAI-PMH record has no ojs.aaai.org article id ({ident[:80]!r})",
                         reason="oai_unreadable")  # fmt: skip
    set_spec = (header.findtext(f"{_OAI}setSpec") or "").strip()
    return OaiRecord(int(m.group(1)), header.get("status") == "deleted", set_spec)


def _oai_record(rec: ET.Element) -> OaiRecord:
    head = _header(rec.find(f"{_OAI}header"))
    if head.deleted:
        return head
    dc = rec.find(f"{_OAI}metadata/*")
    dc = dc if dc is not None else ET.Element("none")
    idents = [(n.text or "").strip() for n in dc.findall(f"{_DC}identifier")]
    sources = " ".join((n.text or "") for n in dc.findall(f"{_DC}source"))
    volume = _VOLUME.search(sources)
    relations = [(n.text or "").strip() for n in dc.findall(f"{_DC}relation")]
    return OaiRecord(
        article=head.article, deleted=False, set_spec=head.set_spec,
        title=_english_first(dc.findall(f"{_DC}title")),
        creators=tuple(c for n in dc.findall(f"{_DC}creator") if (c := (n.text or "").strip())),
        description=_english_first(dc.findall(f"{_DC}description")),
        doi=next((i for i in idents if _DOI.fullmatch(i)), None),
        article_url=next((i for i in idents if i.startswith(f"https://{HOST}/") and "/article/view/" in i), None),
        pdf_url=next((r for r in relations if r.startswith(f"https://{HOST}/") and "/article/view/" in r), None),
        volume=int(volume.group(1)) if volume else None,
    )  # fmt: skip


def parse_page(text: str) -> tuple[list[OaiRecord], str | None]:
    """The records on one ListRecords page and the next resumption token (None: the list is complete)."""
    listing = _listing(text, "ListRecords")
    if listing is None:
        return [], None
    return [_oai_record(r) for r in listing.findall(f"{_OAI}record")], _token(listing)


def parse_identifiers(text: str) -> tuple[list[OaiRecord], str | None]:
    """The headers on one ListIdentifiers page (article, deleted, set; no metadata) and the next token."""
    listing = _listing(text, "ListIdentifiers")
    if listing is None:
        return [], None
    return [_header(h) for h in listing.findall(f"{_OAI}header")], _token(listing)


def parse_record(text: str) -> OaiRecord:
    """The one record of a GetRecord response."""
    listing = _listing(text, "GetRecord", frozenset())
    rec = listing.find(f"{_OAI}record") if listing is not None else None
    if rec is None:
        raise CrawlError("an OAI-PMH GetRecord response has no record", reason="oai_unreadable")
    return _oai_record(rec)


def sets_url(journal: str, token: str | None = None) -> str:
    base = f"https://{HOST}/index.php/{journal}/oai?verb=ListSets"
    return base if token is None else f"{base}&resumptionToken={quote(token, safe='')}"


def parse_sets(text: str) -> tuple[dict[str, str], str | None]:
    """The sets (setSpec → setName) on one ListSets page and the next resumption token (None: complete)."""
    listing = _listing(text, "ListSets", frozenset({"noSetHierarchy"}))
    if listing is None:
        return {}, None
    sets = {
        spec: " ".join((s.findtext(f"{_OAI}setName") or "").split())
        for s in listing.findall(f"{_OAI}set")
        if (spec := (s.findtext(f"{_OAI}setSpec") or "").strip())
    }
    return sets, _token(listing)


def list_sets(journal: str, fetcher: Fetcher, *, refresh: bool = False) -> dict[str, str]:
    """Every set of one journal (setSpec → name) through `ListSets`, following resumption tokens (AAAI's list
    is paginated). The harvest walks each of the journal's own sets; the names label the table's rows."""
    sets: dict[str, str] = {}
    token: str | None = None
    while True:
        page = fetcher.get(sets_url(journal, token), refresh=refresh and token is None)
        if not page.ok:
            raise CrawlError(f"{sets_url(journal)} answered HTTP {page.status}", reason="no_listing")
        found, token = parse_sets(page.text)
        sets.update(found)
        if token is None:
            return sets


def journal_sets(journal: str, fetcher: Fetcher, *, refresh: bool = False) -> list[str]:
    """The journal's own sets (`<journal>:…`), in order: the harvest's units."""
    return sorted(s for s in list_sets(journal, fetcher, refresh=refresh) if s.startswith(f"{journal}:"))


def _get(fetcher: Fetcher, url: str, *, refresh: bool = False) -> Page:
    """`fetcher.get`, except that a page the server answers with HTTP 5xx on every retry is cached as that status
    (an empty `Page`), so an offline replay reads the same failure and takes the same fallback; it is fetched
    again only with `refresh` (a token page's URL is new on every fresh chain anyway)."""
    try:
        return fetcher.get(url, refresh=refresh)
    except RetriesExhausted as e:
        if e.status is None or e.status < 500 or fetcher.offline:
            raise
        page = Page(fetcher.check(url), e.status, "", fetcher.clock.now(), "")
        fetcher.cache.put(page)
        log.warning("ojs_page_failed", extra={"url": page.url, "status": e.status})
        return page


@dataclass
class SetHarvest:
    """One set's records as harvested: its live records with the page each came from, its deleted headers, and
    the articles the server could not serve (each with the cached failure)."""

    set_spec: str
    live: list[tuple[Page, OaiRecord]] = field(default_factory=list)
    deleted: int = 0
    unavailable: list[tuple[int, Page]] = field(default_factory=list)
    pages: int = 0
    fallback: bool = False


def harvest_set(journal: str, set_spec: str, fetcher: Fetcher, *, refresh: bool = False) -> SetHarvest:
    """One set's `ListRecords` chain; if a page of it fails with HTTP 5xx (a record the server can't render
    breaks the whole page, and the chain's next token with it), the set's `ListIdentifiers` chain instead, then
    `GetRecord` for each live article the chain had not reached. A `GetRecord` that also fails is `unavailable`."""
    h = SetHarvest(set_spec)
    seen: set[int] = set()
    token: str | None = None
    while True:
        url = oai_url(journal, token, set_spec=set_spec)
        page = _get(fetcher, url, refresh=refresh and token is None)
        if page.status >= 500:
            _fallback(journal, h, seen, fetcher, refresh=refresh, failed=page)
            return h
        if not page.ok:
            raise CrawlError(f"{url} answered HTTP {page.status}", reason="no_listing")
        h.pages += 1
        entries, token = parse_page(page.text)
        for e in entries:
            if e.deleted:
                h.deleted += 1
            else:
                h.live.append((page, e))
                seen.add(e.article)
        if token is None:
            return h


def _fallback(
    journal: str, h: SetHarvest, seen: set[int], fetcher: Fetcher, *, refresh: bool, failed: Page
) -> None:
    log.warning("ojs_set_fallback", extra={"journal": journal, "set": h.set_spec, "status": failed.status})
    h.fallback = True
    deleted = 0
    token: str | None = None
    while True:
        url = ids_url(journal, token, set_spec=h.set_spec)
        page = fetcher.get(url, refresh=refresh and token is None)
        if not page.ok:
            raise CrawlError(f"{url} answered HTTP {page.status}", reason="no_listing")
        h.pages += 1
        headers, token = parse_identifiers(page.text)
        for e in headers:
            if e.deleted:
                deleted += 1
                continue
            if e.article in seen:
                continue
            seen.add(e.article)
            got = _get(fetcher, record_url(journal, e.article), refresh=refresh)
            if got.status >= 500:
                h.unavailable.append((e.article, got))
                continue
            if not got.ok:
                raise CrawlError(f"{got.url} answered HTTP {got.status}", reason="no_listing")
            h.pages += 1
            h.live.append((got, parse_record(got.text)))
        if token is None:
            break
    h.deleted = (
        deleted  # every deleted header of the set; ListRecords' pages before the failure held a subset
    )


def display_name(creator: str) -> str:
    """`Doe, Jane` → `Jane Doe` (OJS writes surname first); any other shape (no comma, or more than one, as in
    `Smith, Jr., John`) is kept as published, whitespace collapsed."""
    parts = [" ".join(p.split()) for p in creator.split(",")]
    if len(parts) == 2 and all(parts):
        return f"{parts[1]} {parts[0]}"
    return " ".join(creator.split())


@dataclass
class JournalResult:
    records: list[PaperRecord]
    reports: list[ListingReport]
    deleted: int = 0  # deleted headers: counted, never records
    front_matter: int = 0
    pages: int = 0  # ListRecords, ListIdentifiers and GetRecord pages read (ListSets not counted)
    unavailable: int = 0  # articles named in the table's [[unavailable]] rows: listed, never records


def mine_journal(
    journal: str, fetcher: Fetcher, *, refresh: bool = False, table: Table | None = None
) -> JournalResult:
    """Every record of one journal, harvested set by set (`harvest_set`; `refresh`: start each chain again,
    fetching its first page anew; the next pages' tokens are new, so they are fetched too). `table` is the
    shipped one unless a test passes its own (read when called, so a test may also monkeypatch `ojs.TABLE`)."""
    table = table or TABLE
    if journal not in table.journals:
        raise CrawlError(f"OJS journal {journal} is not in ojs_sections.toml", reason="unlisted_journal")
    venue = table.journals[journal].venue
    base = f"https://{HOST}/index.php/{journal}/oai"
    reports: dict[int, ListingReport] = {}
    records: list[PaperRecord] = []
    seen: set[int] = set()
    listed_volumes = frozenset(table.volumes(journal))
    result = JournalResult(records, [])
    started = last = time.monotonic()

    def report_for(volume: int, page: Page) -> ListingReport:
        report = reports.get(volume)
        if report is None:
            report = reports[volume] = ListingReport(
                SOURCE, venue, table.year(journal, volume), base, "primary", table.expected(journal, volume),
                volume=volume,
            )  # fmt: skip
        if page.fetched_at not in report.fetched:
            report.fetched.append(page.fetched_at)
        return report

    def take(page: Page, e: OaiRecord) -> None:
        if e.volume is None:
            raise CrawlError(
                f"OJS {journal} article {e.article}: dc:source names no volume", reason="oai_unreadable"
            )
        if e.volume not in listed_volumes:
            raise CrawlError(
                f"OJS {journal} v{e.volume} is not in ojs_sections.toml: add its sections "
                f"(article {e.article}, set {e.set_spec})",
                reason="unlisted_volume",
            )
        section = table.sections.get((journal, e.volume, e.set_spec))
        if section is None:
            raise CrawlError(
                f"OJS {journal} v{e.volume} section {e.set_spec} is not in ojs_sections.toml: add "
                f"its row (article {e.article})",
                reason="unlisted_section",
            )
        if section.kind == "front_matter":
            result.front_matter += 1
            return
        year = table.year(journal, e.volume)
        report = report_for(e.volume, page)
        report.listed += 1
        if e.article in seen:
            report.skipped["duplicate"] += 1
            return
        seen.add(e.article)
        if not e.title:
            report.skipped["no_title"] += 1
            return
        try:
            record, cleaned = _record(journal, venue, year, section.track or "", section.label, e, page)
        except (ValidationError, ValueError) as exc:
            report.skipped["invalid"] += 1
            log.debug(
                "ojs_record_invalid",
                extra={"journal": journal, "article": e.article, "error": type(exc).__name__},
            )
            return
        records.append(record)
        report.count(record, None if record.abstract else "no_abstract", cleaned.spaced, cleaned.pdf_codes)

    for set_spec in journal_sets(journal, fetcher, refresh=refresh):
        h = harvest_set(journal, set_spec, fetcher, refresh=refresh)
        result.pages += h.pages
        result.deleted += h.deleted
        for page, e in h.live:
            take(page, e)
        for article, failed in h.unavailable:
            row = table.unavailable.get((journal, article))
            if row is None or row.set_spec != set_spec:
                raise CrawlError(
                    f"OJS {journal} article {article} (set {set_spec}) answers HTTP {failed.status} in every form "
                    "and is not named in ojs_sections.toml [[unavailable]]: check it, then name it",
                    reason="unavailable_record",
                )
            report = report_for(row.volume, failed)
            report.listed += 1
            report.skipped["unavailable"] += 1
            result.unavailable += 1
        if time.monotonic() - last >= PROGRESS_SECONDS:
            last = time.monotonic()
            log.info(
                "ojs_journal_progress",
                extra={"journal": journal, "pages": result.pages, "records": len(records)},
            )
    for v in sorted(
        listed_volumes - reports.keys()
    ):  # a listed volume the harvest never showed: reported, not hidden
        reports[v] = ListingReport(
            SOURCE, venue, table.year(journal, v), base, "primary", table.expected(journal, v), volume=v
        )
    result.reports = [reports[v] for v in sorted(reports)]
    for r in result.reports:
        if not r.count_ok:
            log.warning(
                "listing_count_mismatch",
                extra={"journal": journal, "volume": r.volume, "listed": r.listed, "stated": r.stated},
            )
        if r.skipped:
            log.warning(
                "listing_attention",
                extra={"journal": journal, "volume": r.volume, "skipped": dict(r.skipped)},
            )
    log.info(
        "ojs_journal_mined",
        extra={
            "journal": journal,
            "pages": result.pages,
            "records": len(records),
            "deleted": result.deleted,
            "front_matter": result.front_matter,
            "unavailable": result.unavailable,
            "ms": elapsed_ms(started, time.monotonic),
        },
    )
    return result


def _record(
    journal: str, venue: str, year: int, track: str, label: str, e: OaiRecord, page: Page
) -> tuple[PaperRecord, Cleaned]:
    """The record and what cleaning its abstract changed. Claims carry the OAI page's URL and fetch time."""
    assert e.title is not None
    title, replaced = title_text(e.title)
    claims: list[Claim] = []
    at: datetime = page.fetched_at

    def claim(fld: ClaimField, value: ClaimValue, evidence: str) -> None:
        claims.append(
            Claim(field=fld, value=value, source=SOURCE, url=page.url, fetched_at=at, evidence=evidence)
        )

    row = f"ojs_sections.toml {journal} v{e.volume} {e.set_spec} ({label})"
    listed = f"OAI-PMH record oai:ojs.aaai.org:article/{e.article}"
    claim("venue", venue, f"ojs_sections.toml journal {journal}")
    claim("year", year, f"ojs_sections.toml {journal} v{e.volume}")
    claim("track", track, row)
    claim("status", "accepted", f"published in {journal} v{e.volume}")
    claim("title", title, title_evidence(listed, replaced))
    if authors := tuple(display_name(c) for c in e.creators):
        flipped = any(a != " ".join(c.split()) for a, c in zip(authors, e.creators, strict=True))
        how = "(Last, First shown First Last)" if flipped else "as published"
        claim("authors", authors, f"{listed} dc:creator {how}")
    cleaned = clean_abstract(e.description)
    if cleaned.text is not None:
        claim(
            "abstract",
            cleaned.text,
            pdf_codes_evidence(
                controls_evidence(f"{listed} dc:description", cleaned.spaced), cleaned.pdf_codes
            ),
        )
    if e.doi:
        claim("urls.doi", e.doi, f"{listed} dc:identifier")
    if e.article_url and is_url(e.article_url):
        claim("urls.proceedings", e.article_url, f"{listed} dc:identifier")
    if e.pdf_url and is_url(e.pdf_url):
        claim("urls.pdf", e.pdf_url, f"{listed} dc:relation (the article's galley)")
    return record_from_claims(f"op:{venue.lower()}:{year}:ojs-{e.article}", claims), cleaned
