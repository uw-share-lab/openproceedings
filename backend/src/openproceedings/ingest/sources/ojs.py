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
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import quote
from xml.parsers import expat

from openproceedings.ingest.sources.common import CrawlError

log = logging.getLogger(__name__)

SOURCE = "ojs"
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
    raise CrawlError("an OAI-PMH page declared a DOCTYPE; refused (no entities from a response)",
                     reason="oai_unreadable")


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
        hint = " (the resumption token expired: re-run with --refresh)" if code == "badResumptionToken" else ""
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
