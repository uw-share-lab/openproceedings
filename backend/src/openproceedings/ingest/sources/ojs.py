"""ojs.aaai.org miner: AAAI 2010-2026, AIES 2024+ and IASEAI 2026+ through OAI-PMH (spec 01 §Sources, OJS row;
decision-049).

Each journal (`ojs_table.TABLE.journals`) is harvested in three steps, every page through the shared HTTP layer
(XML judged whole by its root's closing tag; the query string names the page, so it is the cache key):

1. **Inventory.** The journal-wide `ListIdentifiers` chain (headers only) is the source of truth for which
   articles exist and which are deleted; deleted headers are counted from it, and only from it (every one, as `completeListSize`
   counts them; AAAI keeps 1-6 stale tombstones for a re-published article).
2. **Sets.** Each of the journal's own sets (`<journal>:…`, from `ListSets`) is read by `ListRecords&set=…` in
   `oai_dc`, following each `resumptionToken`: the metadata in bulk. Per set, not one journal-wide chain, because one
   record the server cannot render makes its whole page answer HTTP 500, and a failed page has no next token
   (AAAI article 39173 hid 2,785 records of the journal-wide chain, checked 2026-10-09). When a set's page answers
   HTTP 5xx after every retry, the set's own `ListIdentifiers` chain lists its articles and each one the set's chain
   had not reached is read by `GetRecord`.
3. **Gaps.** Every live inventory article no set returned is read by `GetRecord`: a set name two sections share
   (AAAI's `EAAI-POS` twice, `EAAI-Full` and `EAAI-FULL`: the server matches `set=` case-blind to one section)
   reaches only one of them.

An article two set requests return is kept once (`duplicates` counts the extra copies); two copies that differ, or
a set record the inventory lacks, stop the crawl. An article neither route serves (`GetRecord` answers 5xx too) is
`unavailable`: listed in its volume and never a record if the table names it in an `[[unavailable]]` row; an unnamed
one stops the crawl.

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

**Layout:** this module has the constants, URL builders, parsers, `mine_journal` and `_record`; the harvest layer
(`_get`, `harvest_set`, `inventory`, `harvest_journal`) is `ojs_harvest.py`, which imports this module (never the
reverse at import time: `mine_journal` imports `harvest_journal` inside the function).
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote
from xml.parsers import expat

from pydantic import ValidationError

from openproceedings.ingest import urls
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
from openproceedings.ingest.sources.http import Fetcher, Page
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
    sets: dict[str, str] = {}
    for node in listing.findall(f"{_OAI}set"):
        if not (spec := (node.findtext(f"{_OAI}setSpec") or "").strip()):
            continue
        name = " ".join((node.findtext(f"{_OAI}setName") or "").split())
        sets[spec] = name if sets.get(spec, name) == name else f"{sets[spec]} | {name}"
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
        for spec, name in found.items():  # a spec two sections share (AAAI's EAAI-POS): both names, kept
            sets[spec] = name if sets.get(spec, name) == name else f"{sets[spec]} | {name}"
        if token is None:
            return sets


def journal_sets(journal: str, fetcher: Fetcher, *, refresh: bool = False) -> list[str]:
    """The journal's own sets (`<journal>:…`), in order: the harvest's units."""
    return sorted(s for s in list_sets(journal, fetcher, refresh=refresh) if s.startswith(f"{journal}:"))


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
    pages: int = 0  # ListIdentifiers, ListRecords and GetRecord pages read (ListSets not counted)
    unavailable: int = 0  # articles named in the table's [[unavailable]] rows: listed, never records
    duplicates: int = 0  # extra identical copies of an article that two set requests returned: counted once
    recovered: int = 0  # live inventory articles no set returned, read by GetRecord


def mine_journal(
    journal: str, fetcher: Fetcher, *, refresh: bool = False, table: Table | None = None
) -> JournalResult:
    """Every record of one journal (`harvest_journal`: the inventory, the sets, then GetRecord for the gaps;
    `refresh`: start each chain again, fetching its first page anew; the next pages' tokens are new, so they are
    fetched too). `table` is the
    shipped one unless a test passes its own (read when called, so a test may also monkeypatch `ojs.TABLE`)."""
    table = table or TABLE
    if journal not in table.journals:
        raise CrawlError(f"OJS journal {journal} is not in ojs_sections.toml", reason="unlisted_journal")
    venue = table.journals[journal].venue
    base = f"https://{HOST}/index.php/{journal}/oai"
    reports: dict[int, ListingReport] = {}
    records: list[PaperRecord] = []
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
        if (stale := table.unavailable.get((journal, e.article))) is not None:
            raise CrawlError(
                f"OJS {journal} article {e.article} is named in ojs_sections.toml [[unavailable]] (set "
                f"{stale.set_spec} v{stale.volume}) but the server now serves it as a record (set {e.set_spec} "
                f"v{e.volume}): delete its [[unavailable]] row, and count it in its section's papers",
                reason="stale_unavailable_row",
            )
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
        report.listed += 1  # each article once: harvest_journal keeps one copy
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

    # imported here, not at the top: ojs_harvest imports this module
    from openproceedings.ingest.sources.ojs_harvest import harvest_journal

    h = harvest_journal(journal, fetcher, refresh=refresh)
    result.pages, result.deleted = h.pages, h.deleted
    result.duplicates, result.recovered = h.duplicates, h.recovered
    for page, e in h.live:
        take(page, e)
        if time.monotonic() - last >= PROGRESS_SECONDS:
            last = time.monotonic()
            log.info("ojs_journal_progress", extra={"journal": journal, "records": len(records)})
    for header, failed in h.unavailable:
        row = table.unavailable.get((journal, header.article))
        if row is None:
            raise CrawlError(
                f"OJS {journal} article {header.article} (set {header.set_spec}) answers HTTP {failed.status} "
                "in every form and is not named in ojs_sections.toml [[unavailable]]: check it, then name it",
                reason="unavailable_record",
            )
        if row.set_spec != header.set_spec:
            raise CrawlError(
                f"OJS {journal} article {header.article} answers HTTP {failed.status} in every form and is named "
                f"in ojs_sections.toml [[unavailable]] under set {row.set_spec} v{row.volume}, but served under "
                f"set {header.set_spec} (an inventory header names no volume): correct its row",
                reason="unavailable_record",
            )
        report = report_for(row.volume, failed)
        report.listed += 1
        report.skipped["unavailable"] += 1
        result.unavailable += 1
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
            "duplicates": result.duplicates,
            "recovered": result.recovered,
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
    # The record names itself by the numeric article URL built from the OAI article id, always: dc:identifier may
    # carry an OJS "public id" (`/article/view/1678-1679`, AAAI 2013 #8500) that `urls.ojs_article` refuses; the
    # server redirects the numeric URL to it (checked live 2026-10-09).
    numeric = f"https://{HOST}/index.php/{journal}/article/view/{e.article}"
    how = f"{listed} (article id from the OAI header)"
    if e.article_url and e.article_url != numeric and urls.ojs_article(e.article_url) != e.article:
        how += f" (dc:identifier gives the public-id URL {e.article_url}; the numeric URL redirects to it)"
    claim("urls.proceedings", numeric, how)
    # A galley URL is claimed only when it names this article by its numeric id; a public-id one is dropped.
    if e.pdf_url and is_url(e.pdf_url) and urls.ojs_article(e.pdf_url) == e.article:
        claim("urls.pdf", e.pdf_url, f"{listed} dc:relation (the article's galley)")
    return record_from_claims(f"op:{venue.lower()}:{year}:ojs-{e.article}", claims), cleaned
