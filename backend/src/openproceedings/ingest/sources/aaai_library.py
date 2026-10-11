"""AAAI's own abstracts for AAAI 1980-2008, read from Internet Archive captures of the old aaai.org paper pages (spec
01 §Sources, aaai_library row; decision-051, TASK-232).

dblp gives AAAI 1980-2008 no abstracts, but each record's dblp `ee` is its aaai.org paper page
(`www.aaai.org/Library/{AAAI,IAAI}/<yyyy>/<id>.php`), and those pages printed the abstract. aaai.org asks crawlers for
a 43,200-second delay (robots.txt), and its 2023 site dropped the pages, so they are read from the archive's copies:
`aaai_library.toml` (`aaai_library_table`) pins one capture per record by URL, timestamp and SHA-1 digest, and
nothing but `web.archive.org` is ever fetched (`HOSTS`), never aaai.org itself.

- **The harvest** (`op ingest aaai-library`, `harvest`): every row's exact capture,
  `https://web.archive.org/web/<timestamp>id_/<url>` (`id_`: the bytes as archived, no banner or rewriting), one at a
  time, `MIN_INTERVAL` apart, into `<cache>/aaai_library/pages` through the shared HTTP layer, read as exact bytes
  (`Fetcher.get(exact_bytes=)`). A body whose SHA-1 is not the row's digest stops (`digest_mismatch`): no other capture
  is ever tried in its place. A capture the archive answers 404/410 is kept as such and counted (`capture_missing`).
  **A redirect** (the CDX lists a 200 that `id_` replay answers with a 3xx to another timestamp: a revisit or
  warc-dedup record; `follow_redirect`): at most one is followed, and only when its `Location` is
  `https://web.archive.org/web/<14 digits>id_/<the row's own page>` (http or https, with or without `www.`, the same
  path, no query; `same_capture`), the target's host checked again by `HttpClient.check`. Its bytes attach only when
  they hash to the row's digest (the same content, deduplicated): cached under the row's own capture key and
  counted `capture_redirected_same`. Anything else (other bytes, another page or host, no `Location`, a second
  redirect, a target the archive refuses) is kept in the cache as the row's 3xx, `capture_redirect`, so the build
  knows it offline. A redirect never stops the harvest and is never a silent fallback.
  When every row is cached, the marker `<cache>/aaai_library/crawls/aaai_library.json` says so.
- **The fill** (`op snapshot build`, `apply`): after dedup and reconcile and before the OpenAlex fill and takedowns,
  offline. Each AAAI 1980-2008 dblp record (`op:aaai:<year>:dblp-<tail>`) is joined to the row of its dblp key
  `conf/aaai/<tail>`, which is exact; its capture is read from the cache, its digest checked again, and the abstract
  attached as an `aaai_library` claim. So an AAAI page's abstract fills the record before OpenAlex can, and an
  OpenAlex abstract never displaces it (precedence: after `ojs`, before `ris` and `openalex`). A row kept as a 404/410
  is `capture_missing` and one kept as a 3xx `capture_redirect`: counted, and the harvest is complete with them.

The page (`parse_page`): `<div id="abstract"><h1>TITLE</h1><p><i>AUTHORS</i></p><p>ABSTRACT</p>…`, then the
`Subjects:` / `Submitted:` paragraphs and the copyright line. The abstract is the paragraphs after the authors' up to
the first that is none of them; entities are decoded and whitespace collapsed (2007's pages break lines inside it).
The bytes are decoded by the charset the page's own `<meta>` names (UTF-8, or ISO-8859-1 read as Windows-1252), UTF-8
when it names none (`decode`). Refusals, each counted, never forced: a page with another layout (`layout_unknown`) or
bytes its charset can't decode (`undecodable`); a title neither equal to the record's by key (`dedup.title_key`,
`common.titles_match`) nor near it (similarity, 1 − Levenshtein / the longer key, at least `NEAR_TITLE`, with the same
digit tokens; counted `title_near` and listed with its score; `title_verdict`) is `title_mismatch`;
a placeholder (`None - 2 page paper is an abstract`), an empty text or one under `MIN_CHARS` characters after the
shared cleaning (`no_abstract`); a lone surrogate (`abstract_surrogate`, `common.clean_abstract`).

The claim: `source=aaai_library`, `url` the capture URL, evidence naming the dblp `ee`, the capture's timestamp and
its digest. The attribution (`dedup.attribution`) links the `ee`, AAAI's own page, never the archive. The text is
AAAI's copyright, served on the posture of decision-018 (with the takedown list) like ojs.aaai.org's abstracts.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import time
import urllib.parse
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from openproceedings.ingest import aaai_library_table
from openproceedings.ingest.aaai_library_table import Page as Row
from openproceedings.ingest.aaai_library_table import Table
from openproceedings.ingest.caps import cap_record
from openproceedings.ingest.dedup import PRECEDENCE, DedupResult, title_key
from openproceedings.ingest.record import DBLP_YEARS, Claim, PaperRecord, Source, controls_evidence
from openproceedings.ingest.sources.common import (
    SURROGATE,
    Cleaned,
    CrawlError,
    Report,
    clean_abstract,
    log_surrogate,
    pdf_codes_evidence,
    read_markers,
    titles_match,
    write_marker,
)
from openproceedings.ingest.sources.html import Element, node_text, parse
from openproceedings.ingest.sources.http import (
    CacheMiss,
    Fetcher,
    Heartbeat,
    HTTPRefused,
    Page,
    PageCache,
    Response,
    Transport,
    urllib_transport,
)
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)

SOURCE: Source = "aaai_library"
CACHE_DIR = "aaai_library"  # <data>/cache/aaai_library
HOST = "web.archive.org"
HOSTS = frozenset({HOST})  # never aaai.org (decision-051)
MIN_INTERVAL = 3.0  # seconds between requests, one at a time: the Internet Archive's polite pace
NEAR_TITLE = 0.9  # the least title similarity a page's abstract attaches at (decision-051)
MIN_CHARS = 40  # an abstract shorter than this after cleaning is no abstract (a placeholder, a fragment)
MARKER = "aaai_library"  # <cache>/aaai_library/crawls/aaai_library.json: every row's capture is cached
MARKER_FORMAT = "1"
_PLACEHOLDER = re.compile(r"none\s*[-–—:]", re.IGNORECASE)  # `None - 2 page paper is an abstract`
_STOP = ("subjects:", "submitted:")  # the paragraphs after the abstract
_META_CHARSET = re.compile(rb"<meta\b[^>]{0,300}?charset\s*=\s*[\"']?([A-Za-z0-9_.:-]{1,40})", re.IGNORECASE)
_CAPTURE_PATH = re.compile(
    r"/web/[0-9]{14}id_/(https?://.+)"
)  # an `id_` capture's path: the original after it
_HEAD = 4096  # bytes searched for the `<meta>` charset
_LATIN = frozenset(
    {"iso-8859-1", "iso8859-1", "latin1", "latin-1", "windows-1252", "cp1252", "us-ascii", "ascii"}
)
# the refusals worth a WARNING (`aaai_library_attention`): a page that is not what the table says it is
_ATTENTION = (
    "capture_missing",
    "capture_redirect",
    "layout_unknown",
    "undecodable",
    "title_mismatch",
    SURROGATE,
)


# --- the bytes ----------------------------------------------------------------------------------------------


def digest(body: bytes) -> str:
    """The archive's digest of a capture: SHA-1 of the bytes, base32 (as the CDX index gives it)."""
    return base64.b32encode(hashlib.sha1(body).digest()).decode("ascii")


def body_of(page: Page) -> bytes | None:
    """A cached capture's exact bytes (`Fetcher.get(exact_bytes=True)` read them one character per byte), or None
    when its text holds a character no byte gives (an entry this source never wrote)."""
    try:
        return page.text.encode("latin-1")
    except UnicodeEncodeError:
        return None


def check_digest(page: Page, row: Row) -> bytes:
    """The capture's bytes when they hash to the row's digest; else the crawl or the build stops
    (`digest_mismatch`): another capture is never read in its place, and the message never quotes the body."""
    body = body_of(page)
    if body is None or digest(body) != row.digest:
        raise CrawlError(f"{row.capture}: the bytes are not the capture aaai_library.toml pins for {row.key} (SHA-1 "
                         f"{row.digest}); re-run op ingest aaai-library --refresh, and if it persists the archive "
                         "changed the capture: re-run scripts/aaai_library_census.py", reason="digest_mismatch")  # fmt: skip
    return body


def decode(body: bytes) -> str | None:
    """The page's text in the charset its own `<meta>` names (ISO-8859-1 and ASCII read as Windows-1252, as a browser
    does; a byte Windows-1252 leaves undefined as ISO-8859-1), UTF-8 when it names none; None when the bytes are not
    in it, or it names another charset."""
    m = _META_CHARSET.search(body[:_HEAD])
    named = m.group(1).decode("ascii").lower() if m else "utf-8"
    try:
        if named in ("utf-8", "utf8"):
            return body.decode("utf-8")
        if named in _LATIN:
            try:
                return body.decode("cp1252")
            except UnicodeDecodeError:
                return body.decode("latin-1")
    except UnicodeDecodeError:
        return None
    return None


# --- the page -----------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Parsed:
    title: str | None
    abstract: str | None  # the abstract paragraphs' text, as the page gives it (None: none)
    refused: str | None = None  # layout_unknown | undecodable


def _children(node: Element) -> list[Element]:
    return [c for c in node.children if isinstance(c, Element)]


def parse_page(text: str, url: str | None = None) -> Parsed:
    """An aaai.org paper page's title and abstract (the module docstring's layout). A page without exactly one
    `<div id="abstract">` holding an `<h1>` and then an authors paragraph (an `<i>` inside) is `layout_unknown`."""
    root = parse(text, url)
    divs = [d for d in root.iter("div") if d.attributes.get("id") == "abstract"]
    if len(divs) != 1:
        return Parsed(None, None, "layout_unknown")
    kids = _children(divs[0])
    at = next((i for i, k in enumerate(kids) if k.tag == "h1"), None)
    if at is None or at + 1 >= len(kids) or kids[at + 1].tag != "p" or not kids[at + 1].iter("i"):
        return Parsed(None, None, "layout_unknown")
    paragraphs: list[str] = []
    for k in kids[at + 2 :]:
        if k.tag != "p" or k.has_class("eight-center"):  # a rule, the copyright line: the abstract has ended
            break
        said = node_text(k)
        if said.casefold().startswith(_STOP):
            break
        if said:
            paragraphs.append(said)
    return Parsed(node_text(kids[at]) or None, " ".join(paragraphs) or None)


def abstract_of(parsed: Parsed) -> tuple[Cleaned | None, str | None]:
    """The page's abstract as a record may hold it (`common.clean_abstract`), or None with why: the page's own
    refusal, `abstract_surrogate`, or `no_abstract` (none, a `None - …` placeholder, or under `MIN_CHARS`)."""
    if parsed.refused:
        return None, parsed.refused
    cleaned = clean_abstract(parsed.abstract)
    if cleaned.refused:
        return None, cleaned.refused
    text = cleaned.text
    if text is None or len(text) < MIN_CHARS or _PLACEHOLDER.match(text):
        return None, "no_abstract"
    return cleaned, None


def levenshtein(a: str, b: str) -> int:
    """The edit distance of two strings (insertions, deletions, substitutions, each 1): the two-row dynamic program."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def title_similarity(one: str, other: str) -> float:
    """1 − Levenshtein / the longer length, over the two titles' keys (`dedup.title_key`); 1.0 for two empty keys."""
    a, b = title_key(one), title_key(other)
    longest = max(len(a), len(b))
    return 1.0 if longest == 0 else 1 - levenshtein(a, b) / longest


def _digit_tokens(title: str) -> list[str]:
    return [t for t in title_key(title).split() if any(c.isdigit() for c in t)]


def title_verdict(record_title: str, page_title: str | None) -> tuple[str | None, float]:
    """Whether the page is the record's paper by its title (decision-051, the controller's ruling of fix round 1):
    `exact` when the title keys agree (`common.titles_match`); else `near` when their similarity is at least
    `NEAR_TITLE` (dblp's OCR typos: `Optimisation … Conputer`) and their digit tokens are the same (`Part 1` is never
    `Part 2`, whatever the score); else None (`title_mismatch`). Returns the verdict and the similarity."""
    if not page_title:
        return None, 0.0
    if titles_match(record_title, page_title):
        return "exact", 1.0
    score = title_similarity(record_title, page_title)
    if score >= NEAR_TITLE and _digit_tokens(record_title) == _digit_tokens(page_title):
        return "near", score
    return None, score


def read(page: Page, row: Row) -> Parsed:
    """A cached capture's page: the digest checked (`check_digest`, which stops on a mismatch), then decoded and
    parsed."""
    text = decode(check_digest(page, row))
    return Parsed(None, None, "undecodable") if text is None else parse_page(text, row.capture)


# --- the harvest (`op ingest aaai-library`) -------------------------------------------------------------------


def fetcher(cache: Path, *, offline: bool, transport: Transport | None = None,
            min_interval: float = MIN_INTERVAL) -> Fetcher:  # fmt: skip
    """The one aaai_library fetcher: web.archive.org only, the repo's generic User-Agent (no contact string), one
    request at a time, never under `MIN_INTERVAL` apart; offline, the cache alone."""
    live = None if offline else (transport or urllib_transport)
    return Fetcher(
        PageCache(cache / CACHE_DIR), live, hosts=HOSTS, min_interval=max(min_interval, MIN_INTERVAL)
    )


def _verified(row: Row) -> Callable[[Page], bool]:
    def ok(page: Page) -> bool:
        body = body_of(page)
        return body is not None and digest(body) == row.digest

    return ok


def _page_of(url: str) -> tuple[str, str, str] | None:
    """An aaai.org page URL as compared: (host without `www.` or a default port, path, query); http and https alike."""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    host = p.netloc.lower().removesuffix(":80").removesuffix(":443").removeprefix("www.")
    return host, p.path, p.query


def same_capture(location: str, row: Row) -> str | None:
    """The archive URL a redirect's `location` names (resolved against the row's capture) when it is another `id_`
    capture of the row's own page: `https://web.archive.org/web/<14 digits>id_/<url>`, the original the row's `url`
    up to http/https, `www.` and a default port, with the same path and no query or fragment; else None."""
    if not location:
        return None
    target = urllib.parse.urljoin(row.capture, location.strip())
    p = urllib.parse.urlparse(target)
    if p.scheme not in ("http", "https") or p.netloc.lower() != HOST or p.params or p.query or p.fragment:
        return None
    m = _CAPTURE_PATH.fullmatch(p.path)
    if m is None or _page_of(m.group(1)) != _page_of(row.url):
        return None
    return target


def follow_redirect(
    fetcher: Fetcher, row: Row, outcomes: Counter[str] | None = None
) -> Callable[[str, Response], Page]:
    """What a 3xx for the row's capture becomes (`Fetcher.get(redirect=)`): the target's page, under the row's own
    capture URL, when `same_capture` names one and its bytes hash to the row's digest (`capture_redirected_same`);
    else the 3xx itself, kept as the row's answer (`capture_redirect`). One hop at most: `Fetcher.fetch` refuses a
    second redirect, and checks the target's host. Each outcome is counted in `outcomes` and logged (no body)."""

    def follow(url: str, response: Response) -> Page:
        target = same_capture(response.headers.get("location", ""), row)
        page: Page | None = None
        if target is not None:
            try:
                page = fetcher.fetch(target, by_length=True, exact_bytes=True)
            except (
                HTTPRefused
            ):  # a second redirect, or a refusal: not the pinned capture, never followed further
                page = None
        if page is not None and page.ok and _verified(row)(page):
            outcome, kept = (
                "capture_redirected_same",
                Page(url, 200, page.text, page.fetched_at, page.content_type),
            )
        else:
            outcome = "capture_redirect"
            kept = Page(
                url, response.status, "", fetcher.clock.now(), response.headers.get("content-type", "")
            )
        if outcomes is not None:
            outcomes[outcome] += 1
        log.info("aaai_library_capture_redirected", extra={"key": row.key, "status": response.status,
                                                           "outcome": outcome, "followed": target is not None})  # fmt: skip
        return kept

    return follow


def get(fetcher: Fetcher, row: Row, *, refresh: bool = False, outcomes: Counter[str] | None = None) -> Page:
    """A row's capture, through the cache: exact bytes, judged whole by its stated length, a 404/410 kept, a 3xx
    judged by `follow_redirect` (the target's verified bytes, or the 3xx kept). A fetched 200 is stored only when its
    bytes hash to the row's digest (`Fetcher.get(verify=)`), so a bad answer never stays in the cache; the caller's
    `check_digest` then refuses it (`digest_mismatch`)."""
    return fetcher.get(row.capture, refresh=refresh, keep_absent=True, by_length=True, exact_bytes=True,
                       verify=_verified(row), redirect=follow_redirect(fetcher, row, outcomes))  # fmt: skip


def is_redirect(page: Page) -> bool:
    """A row kept as the archive's 3xx (`capture_redirect`)."""
    return 300 <= page.status < 400


@dataclass
class Harvest:
    pages: int = 0
    fetched: int = 0  # from the network this run
    missing: int = 0  # the archive answered 404/410 (`capture_missing`)
    redirect: int = 0  # rows kept as a 3xx: a redirect not to the pinned bytes (`capture_redirect`)
    redirected_same: int = 0  # this run: a redirect followed to the pinned bytes (`capture_redirected_same`)


def harvest(table: Table, fetcher: Fetcher, *, refresh: bool = False) -> Harvest:
    """Every row's capture into the cache, in key order, each digest checked as it arrives (a 404/410 counted
    `missing`, a redirect judged by `follow_redirect` and never stopping it); then the marker, when the fetcher is
    live or offline and every row was there. A progress line at most every 30 s."""
    out = Harvest()
    started = time.monotonic()
    beat = Heartbeat(fetcher.clock.monotonic)
    rows = list(table.pages.values())
    log.info("aaai_library_harvest_started", extra={"pages": len(rows), "offline": fetcher.offline})
    outcomes: Counter[str] = Counter()
    for row in rows:
        before = fetcher.stats.network
        page = get(fetcher, row, refresh=refresh, outcomes=outcomes)
        out.pages += 1
        out.fetched += fetcher.stats.network > before
        if page.ok:
            check_digest(page, row)
        elif is_redirect(page):
            out.redirect += 1
        else:
            out.missing += 1
        if beat.due():
            log.info("aaai_library_harvest_progress", extra={"done": out.pages, "of": len(rows),
                                                             "requests": fetcher.stats.network,
                                                             "ms": elapsed_ms(started, time.monotonic)})  # fmt: skip
    out.redirected_same = outcomes["capture_redirected_same"]
    return out  # the end line is the command's (`aaai_library_ingested`)


def write_done(cache: Path, table: Table, done: Harvest) -> None:
    write_marker(cache / CACHE_DIR / "crawls", MARKER, {"source": SOURCE, "format": MARKER_FORMAT,
                                                        "pages": done.pages, "missing": done.missing,
                                                        "redirect": done.redirect,
                                                        "verified": table.verified.isoformat(),
                                                        "table": table.sha256})  # fmt: skip


def harvested(cache: Path, table: Table | None = None) -> bool:
    """Whether a harvest finished (its marker): False, no fill. A marker of another format is `crawl_file_invalid`;
    one naming another table's sha256, or none (a marker written before it named one), is `harvest_stale`: the
    table changed since that harvest."""
    table = table or aaai_library_table.TABLE
    marker = cache / CACHE_DIR / "crawls" / f"{MARKER}.json"
    if not marker.exists():
        return False
    found = dict(read_markers(marker.parent)).get(marker.name)
    if not found or found.get("source") != SOURCE or found.get("format") != MARKER_FORMAT:
        raise CrawlError("the aaai_library crawl marker is unreadable; run op ingest aaai-library",
                         reason="crawl_file_invalid")  # fmt: skip
    if found.get("table") != table.sha256:
        raise CrawlError("the aaai_library harvest was made for another aaai_library.toml (or names none); re-run op "
                         "ingest aaai-library", reason="harvest_stale")  # fmt: skip
    return True


# --- the fill (`op snapshot build`, after reconcile, before the OpenAlex fill and takedowns) -----------------


@dataclass(kw_only=True)
class FillReport(Report):
    """The AAAI library fill of one build (manifest `sources.aaai_library.fills`)."""

    pages: int = 0  # rows of the table
    candidates: int = 0  # AAAI 1980-2008 dblp records in the build
    no_page: int = 0  # of candidates: no row (no aaai.org Library `ee` in dblp, or no capture of it)
    attached: int = 0  # abstracts attached from a page
    replaced: int = 0  # of attached: an abstract only a source ranked after aaai_library (ris) gave, replaced
    official_won: int = 0  # a page abstract, but the record's own abstract is from a source ranked before it
    rows_unmatched: int = 0  # rows naming no record of the build
    title_near: int = (
        0  # of attached: by a near title (`title_verdict`), each listed in `near` with its score
    )
    near: list[tuple[str, float]] = field(default_factory=list)  # (record id, score), in id order
    refused: Counter[str] = field(default_factory=Counter)
    # the capture time of each attached page (its row's 14-digit timestamp, UTC): the text's date, which the
    # manifest's `capture_window` shows for this source instead of the harvest's fetch times
    attached_captures: list[datetime] = field(default_factory=list)

    manifest_key: ClassVar[str] = "fills"

    def captured(self) -> list[datetime]:
        return self.attached_captures

    def to_manifest(self) -> dict[str, Any]:
        return {"pages": self.pages, "candidates": self.candidates, "no_page": self.no_page,
                "attached": self.attached, "replaced": self.replaced, "official_won": self.official_won,
                "rows_unmatched": self.rows_unmatched, "title_near": self.title_near,
                "near": [{"id": rid, "score": score} for rid, score in self.near],
                "refused": dict(sorted(self.refused.items()))}  # fmt: skip


def key_of(record: PaperRecord) -> str | None:
    """The dblp key of an AAAI 1980-2008 dblp record (`op:aaai:<year>:dblp-<tail>` → `conf/aaai/<tail>`), else None."""
    native = record.id.split(":", 3)[3]
    if record.venue != "AAAI" or record.year not in DBLP_YEARS["AAAI"] or not native.startswith("dblp-"):
        return None
    return f"conf/aaai/{native.removeprefix('dblp-')}"


_RANK = PRECEDENCE["abstract"]


def _outranked(record: PaperRecord) -> bool:
    """Whether every claim holding the record's abstract is from a source ranked after aaai_library."""
    held = [c.source for c in record.claims("abstract") if c.value == record.abstract]
    return bool(held) and all(_RANK.index(s) > _RANK.index(SOURCE) for s in held)


def _attach(
    r: PaperRecord, row: Row, page: Page, cleaned: Cleaned, *, near: float | None = None
) -> PaperRecord:
    assert cleaned.text is not None
    evidence = (f"AAAI's paper page {row.url} (the dblp ee of {row.key}), Internet Archive capture {row.timestamp}, "
                f"SHA-1 {row.digest}; joined by dblp key")  # fmt: skip
    if near is not None:
        evidence += f"; title near, similarity {near:.3f} (decision-051)"
    claim = Claim(field="abstract", value=cleaned.text, source=SOURCE, url=row.capture, fetched_at=page.fetched_at,
                  evidence=pdf_codes_evidence(controls_evidence(evidence, cleaned.spaced), cleaned.pdf_codes))  # fmt: skip
    # `model_copy` re-validates every field (record.py): the aaai_library guard (an AAAI 1980-2008 dblp record's
    # abstract only) runs again, and the hash is recomputed
    return cap_record(r.model_copy(update={"abstract": cleaned.text, "provenance": (*r.provenance, claim)}))


def fill(
    records: Iterable[PaperRecord], fetcher: Fetcher, table: Table | None = None
) -> tuple[list[PaperRecord], FillReport]:
    """Attach each AAAI 1980-2008 dblp record's page abstract, in record id order, from the cache alone (`fetcher`
    is offline). A row whose capture is not cached stops (`not_cached`), and so does a digest mismatch; every other
    refusal is counted, never forced (a row kept as a 404/410 is `capture_missing`, one kept as a 3xx
    `capture_redirect`). A record whose abstract a source ranked before aaai_library gave keeps it
    (`official_won`); one only a source ranked after it gave (ris) takes the page's (`replaced`)."""
    table = table or aaai_library_table.TABLE
    report = FillReport(source=SOURCE, pages=len(table.pages))
    out: list[PaperRecord] = []
    seen: set[str] = set()
    for r in sorted(records, key=lambda r: r.id):
        key = key_of(r)
        if key is None:
            out.append(r)
            continue
        report.candidates += 1
        row = table.pages.get(key)
        if row is None:
            report.no_page += 1
            out.append(r)
            continue
        seen.add(key)
        try:
            page = get(fetcher, row)
        except CacheMiss:
            raise CrawlError(f"{row.capture} ({row.key}) is not in the cache; run op ingest aaai-library",
                             reason="not_cached") from None  # fmt: skip
        report.fetched.append(page.fetched_at)
        refusal: str | None = None
        cleaned: Cleaned | None = None
        how, score = None, 0.0
        if not page.ok:
            refusal = "capture_redirect" if is_redirect(page) else "capture_missing"
        else:
            parsed = read(page, row)
            if parsed.refused is None:
                how, score = title_verdict(r.title, parsed.title)
            if parsed.refused is None and how is None:
                refusal = "title_mismatch"
            else:
                cleaned, refusal = abstract_of(parsed)
        if refusal is not None or cleaned is None:
            report.refused[refusal or "no_abstract"] += 1
            if refusal == SURROGATE:
                log_surrogate(SOURCE, r.id)
            out.append(r)
        elif r.abstract is None or _outranked(r):
            report.replaced += r.abstract is not None
            report.attached += 1
            if how == "near":
                report.title_near += 1
                report.near.append((r.id, round(score, 3)))
            report.attached_captures.append(
                datetime.strptime(row.timestamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            )
            out.append(_attach(r, row, page, cleaned, near=score if how == "near" else None))
        else:
            report.official_won += 1
            out.append(r)
    report.rows_unmatched = len(set(table.pages) - seen)
    report.fetched = sorted(set(report.fetched))
    return out, report


def apply(
    result: DedupResult, cache: Path, table: Table | None = None
) -> tuple[DedupResult, list[FillReport]]:
    """`op snapshot build`'s fill, when a harvest finished (`harvested`; else nothing changes), offline. Returns the
    result and its one fill report, after its INFO line (`aaai_library_filled`, every refusal by reason) and, when a
    page was not what the table says it is, one WARNING (`aaai_library_attention`)."""
    started = time.monotonic()
    if not harvested(cache, table):
        return result, []
    records, report = fill(result.records, fetcher(cache, offline=True), table)
    counts = {"candidates": report.candidates, "attached": report.attached, "title_near": report.title_near,
              "replaced": report.replaced,
              "official_won": report.official_won, "no_page": report.no_page,
              "rows_unmatched": report.rows_unmatched, "refused": dict(sorted(report.refused.items()))}  # fmt: skip
    log.info("aaai_library_filled", extra={**counts, "ms": elapsed_ms(started, time.monotonic)})
    attention = {k: report.refused[k] for k in _ATTENTION if report.refused[k]}
    if attention or report.title_near:
        log.warning("aaai_library_attention", extra={**attention, "title_near": report.title_near})
    return replace(result, records=tuple(sorted(records, key=lambda r: r.id))), [report]
