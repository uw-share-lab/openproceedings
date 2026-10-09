"""ojs.aaai.org miner: AAAI 2010-2026, AIES 2024+ and IASEAI 2026+ through OAI-PMH (spec 01 §Sources, OJS row;
decision-049).

Each journal (`ojs_table.TABLE.journals`) is harvested whole: `ListRecords` in `oai_dc`, then each
`resumptionToken` in turn, every page through the shared HTTP layer (XML judged whole by its root's closing tag;
the query string names the page, so it is the cache key). A crawl is replayed offline by following the same chain
through the cache. OJS tokens are opaque and expire after 24 h: a resumed crawl whose next token the server no
longer knows gets `badResumptionToken`, which stops the crawl with what to do (`--refresh` starts the chain again).

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
from dataclasses import dataclass
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
_VOLUME = re.compile(r";\s*Vol\.\s*([0-9]+)\s+No\.\s*[0-9]+")
_DOI = re.compile(r"10\.1609/\S+")
_EMPTY_LIST = "noRecordsMatch"  # an OAI-PMH error code that means an empty list, not a failure


def oai_url(journal: str, token: str | None = None) -> str:
    base = f"https://{HOST}/index.php/{journal}/oai?verb=ListRecords&"
    return base + ("metadataPrefix=oai_dc" if token is None else f"resumptionToken={quote(token, safe='')}")


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


def parse_page(text: str) -> tuple[list[OaiRecord], str | None]:
    """The records on one ListRecords page and the next resumption token (None: the list is complete)."""
    root = _root(text)
    if root.tag != f"{_OAI}OAI-PMH":
        raise CrawlError("an ojs.aaai.org page is not an OAI-PMH response", reason="oai_unreadable")
    if (err := root.find(f"{_OAI}error")) is not None:
        code = err.get("code", "")
        if code == _EMPTY_LIST:
            return [], None
        hint = (
            " (the resumption token expired: re-run with --refresh)" if code == "badResumptionToken" else ""
        )
        raise CrawlError(f"ojs.aaai.org answered OAI-PMH error {code}{hint}", reason="oai_error")
    listing = root.find(f"{_OAI}ListRecords")
    if listing is None:
        raise CrawlError("an OAI-PMH response has no ListRecords", reason="oai_unreadable")
    out = []
    for rec in listing.findall(f"{_OAI}record"):
        header = rec.find(f"{_OAI}header")
        ident = header.findtext(f"{_OAI}identifier", "") if header is not None else ""
        m = _ARTICLE.fullmatch(ident.strip())
        if header is None or m is None:
            raise CrawlError(f"an OAI-PMH record has no ojs.aaai.org article id ({ident[:80]!r})",
                             reason="oai_unreadable")  # fmt: skip
        set_spec = (header.findtext(f"{_OAI}setSpec") or "").strip()
        if header.get("status") == "deleted":
            out.append(OaiRecord(int(m.group(1)), True, set_spec))
            continue
        dc = rec.find(f"{_OAI}metadata/*")
        dc = dc if dc is not None else ET.Element("none")
        idents = [(n.text or "").strip() for n in dc.findall(f"{_DC}identifier")]
        sources = " ".join((n.text or "") for n in dc.findall(f"{_DC}source"))
        volume = _VOLUME.search(sources)
        relations = [(n.text or "").strip() for n in dc.findall(f"{_DC}relation")]
        out.append(OaiRecord(
            article=int(m.group(1)), deleted=False, set_spec=set_spec,
            title=_english_first(dc.findall(f"{_DC}title")),
            creators=tuple(c for n in dc.findall(f"{_DC}creator") if (c := (n.text or "").strip())),
            description=_english_first(dc.findall(f"{_DC}description")),
            doi=next((i for i in idents if _DOI.fullmatch(i)), None),
            article_url=next((i for i in idents if i.startswith(f"https://{HOST}/") and "/article/view/" in i), None),
            pdf_url=next((r for r in relations if r.startswith(f"https://{HOST}/") and "/article/view/" in r), None),
            volume=int(volume.group(1)) if volume else None,
        ))  # fmt: skip
    token_node = listing.find(f"{_OAI}resumptionToken")
    token = (token_node.text or "").strip() if token_node is not None else ""
    return out, token or None


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
    pages: int = 0


def mine_journal(
    journal: str, fetcher: Fetcher, *, refresh: bool = False, table: Table | None = None
) -> JournalResult:
    """Every record of one journal, harvested page by page (`refresh`: start the token chain again, fetching the
    first page anew; the next pages' tokens are new, so they are fetched too). `table` is the shipped one unless a
    test passes its own (read when called, so a test may also monkeypatch `ojs.TABLE`)."""
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
    token: str | None = None
    started = last = time.monotonic()
    while True:
        page = fetcher.get(oai_url(journal, token), refresh=refresh and token is None)
        if not page.ok:
            raise CrawlError(f"{base} answered HTTP {page.status}", reason="no_listing")
        result.pages += 1
        entries, token = parse_page(page.text)
        for e in entries:
            if e.deleted:
                result.deleted += 1
                continue
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
                continue
            year = table.year(journal, e.volume)
            report = reports.get(e.volume)
            if report is None:
                report = reports[e.volume] = ListingReport(
                    SOURCE, venue, year, base, "primary", table.expected(journal, e.volume), volume=e.volume
                )
                report.fetched.append(page.fetched_at)
            elif page.fetched_at not in report.fetched:
                report.fetched.append(page.fetched_at)
            report.listed += 1
            if e.article in seen:
                report.skipped["duplicate"] += 1
                continue
            seen.add(e.article)
            if not e.title:
                report.skipped["no_title"] += 1
                continue
            try:
                record, cleaned = _record(journal, venue, year, section.track or "", section.label, e, page)
            except (ValidationError, ValueError) as exc:
                report.skipped["invalid"] += 1
                log.debug(
                    "ojs_record_invalid",
                    extra={"journal": journal, "article": e.article, "error": type(exc).__name__},
                )
                continue
            records.append(record)
            report.count(
                record, None if record.abstract else "no_abstract", cleaned.spaced, cleaned.pdf_codes
            )
        if time.monotonic() - last >= PROGRESS_SECONDS:
            last = time.monotonic()
            log.info(
                "ojs_journal_progress",
                extra={"journal": journal, "pages": result.pages, "records": len(records)},
            )
        if token is None:
            break
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
