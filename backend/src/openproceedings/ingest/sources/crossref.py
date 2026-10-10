"""Crossref REST parsing for FAccT and AIES (spec 01 §Sources, Crossref row; decision-049).

The route: a table row's proceedings record (`/works/<doi>`), then `/works` paged by cursor, filtered by
`prefix:10.1145` and the row's publication window, keeping the DOIs that extend `10.1145/<toc>.`. Requests go one at
a time (`MIN_INTERVAL`), because parallel requests get HTTP 429. `CROSSREF_MAILTO` is optional: with it the
User-Agent names a contact (Crossref's polite pool), without it the plain repo User-Agent goes (the public pool);
the address is in the User-Agent only, never a URL, a cache entry, a claim, a log line or an exception. The cursor
is opaque and never a claim's url: a claim's url is the work's own API URL, and `dedup.attribution` credits the
DOI link. A cursor expires within minutes, so a chain that is not whole in the cache restarts from `cursor=*`; the
replay follows the cached chain offline. The fields: no abstracts, which `select` leaves out. FAccT's abstracts
come from the official conference pages instead (`facct_site`), joined here to the records by DOI or by exact title
key, one to one (`mine_proceedings(..., site=)`).
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import ValidationError

from openproceedings.ingest import acm_table
from openproceedings.ingest.acm_table import Proceedings
from openproceedings.ingest.record import (
    Claim,
    ClaimField,
    ClaimValue,
    PaperRecord,
    Source,
    controls_evidence,
    title_evidence,
    title_text,
)
from openproceedings.ingest.sources import facct_site
from openproceedings.ingest.sources.common import (
    CrawlError,
    ListingReport,
    pdf_codes_evidence,
    record_from_claims,
)
from openproceedings.ingest.sources.http import USER_AGENT, Fetcher, Page
from openproceedings.ingest.sources.openreview_client import read_dotenv
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)

SOURCE: Source = "crossref"
CACHE_DIR = "crossref"  # <data>/cache/crossref
HOST = "api.crossref.org"
HOSTS = frozenset({HOST})
MIN_INTERVAL = (
    1.0  # one request at a time, a second apart: parallel requests get HTTP 429 (checked 2026-10-09)
)
ROWS = 1000  # Crossref's page maximum
SELECT = "DOI,title,subtitle,author,type,page,published"  # never `abstract` (design: official sources only)
MAILTO_ENV = "CROSSREF_MAILTO"
# printable ASCII only (no control character, no non-ASCII), and none of the characters a header or a list would split on
_PART = r"(?:(?![@<>()\"';,])[\x21-\x7e])+"
_EMAIL = re.compile(rf"{_PART}@{_PART}\.[A-Za-z]{{2,}}")
_TAG = re.compile(r"<[^<>]*>")


def proceedings_url(doi: str) -> str:
    return f"https://{HOST}/works/{doi}"


work_url = proceedings_url  # a work's own API URL: every claim's url (stable, unlike a cursor page)


def works_url(row: Proceedings, cursor: str = "*") -> str:
    return (f"https://{HOST}/works?filter=prefix:10.1145,from-pub-date:{row.window_from.isoformat()},"
            f"until-pub-date:{row.window_until.isoformat()}&rows={ROWS}&select={SELECT}&cursor={quote(cursor, safe='')}")  # fmt: skip


@dataclass(frozen=True, slots=True)
class Work:
    doi: str  # lower-case
    type: str
    title: str | None
    authors: tuple[str, ...]
    page: str | None
    unnamed_authors: int = 0  # author entries with no given name, family name or name: dropped


@dataclass(frozen=True, slots=True)
class WorksPage:
    works: tuple[Work, ...]
    next_cursor: str | None
    total: int


def clean_title(raw: str) -> str:
    """Crossref's title text: JATS/HTML/MathML tags dropped (their text kept), entities unescaped, whitespace
    collapsed. `title_text` then replaces control characters as for every source."""
    return " ".join(html.unescape(_TAG.sub("", raw)).split())


def _strings(value: Any) -> list[str]:
    """The cleaned strings of a Crossref list field; a bare string or any other shape is no title text."""
    return [clean_title(t) for t in value if isinstance(t, str)] if isinstance(value, list) else []


def title_of(item: Mapping[str, Any]) -> str | None:
    title = next((t for t in _strings(item.get("title")) if t), None)
    if title is None:
        return None
    sub = next((s for s in _strings(item.get("subtitle")) if s), None)
    return f"{title}: {sub}" if sub and sub.casefold() not in title.casefold() else title


def author_name(a: Mapping[str, Any]) -> str | None:
    parts = [" ".join(str(a.get(k) or "").split()) for k in ("given", "family")]
    joined = " ".join(p for p in parts if p)
    return joined or (" ".join(str(a.get("name") or "").split()) or None)


def _message(text: str, kind: str) -> Mapping[str, Any]:
    try:
        body = json.loads(text)
    except ValueError as e:
        raise CrawlError("a Crossref answer is not JSON", reason="crossref_unreadable") from e
    if not isinstance(body, dict):
        raise CrawlError("a Crossref answer is not a JSON object", reason="crossref_unreadable")
    if body.get("status") != "ok":
        raise CrawlError(
            f"Crossref answered with status {str(body.get('status'))[:40]!r}", reason="crossref_error"
        )
    message = body.get("message")
    if body.get("message-type") != kind or not isinstance(message, dict):
        raise CrawlError(f"a Crossref answer is not a {kind}", reason="crossref_unreadable")
    return message


def parse_works(text: str) -> WorksPage:
    message = _message(text, "work-list")
    works: list[Work] = []
    for item in message.get("items") or []:
        if not isinstance(item, dict) or not isinstance(item.get("DOI"), str) or not item["DOI"].strip():
            raise CrawlError("a Crossref work has no DOI", reason="crossref_unreadable")
        page = item.get("page")
        raw = item.get("author") or []
        names = tuple(n for a in raw if isinstance(a, dict) and (n := author_name(a)))
        works.append(Work(
            doi=item["DOI"].strip().lower(), type=str(item.get("type", "")), title=title_of(item),
            authors=names, page=page if isinstance(page, str) else None,
            unnamed_authors=len(raw) - len(names)))  # fmt: skip
    try:
        total = int(message["total-results"])
    except (KeyError, TypeError, ValueError) as e:
        raise CrawlError("a Crossref page has no total-results", reason="crossref_unreadable") from e
    cursor = message.get("next-cursor")
    return WorksPage(tuple(works), cursor if isinstance(cursor, str) and cursor else None, total)


def parse_proceedings(text: str) -> tuple[str, str, tuple[str, ...]]:
    message = _message(text, "work")
    doi = message.get("DOI")
    if message.get("type") != "proceedings" or not isinstance(doi, str):
        raise CrawlError("a Crossref record is not a proceedings", reason="crossref_unreadable")
    isbn = tuple(str(i) for i in message.get("ISBN") or [])
    return doi.strip().lower(), title_of(message) or "", isbn


def contact(environ: Mapping[str, str], dotenv: Path | None) -> str | None:
    """The address Crossref's polite pool asks for, from `CROSSREF_MAILTO` (the environment first, then `.env`),
    or None when it is unset or blank (the crawl then uses the public pool). It goes into the User-Agent only,
    never a URL, a cache entry, a claim, a log line or an exception: a malformed value stops without quoting it."""
    # an exported but empty `CROSSREF_MAILTO=` overrides `.env`: the crawl then uses the public pool
    values = {**(read_dotenv(dotenv) if dotenv else {}), **environ}
    value = values.get(MAILTO_ENV, "").strip()
    if not value:
        return None
    return valid_contact(value)


def valid_contact(value: str) -> str:
    """`value` if it is an e-mail address, else a `bad_contact` stop that never quotes it: the one check for the
    environment's address and an explicit `mailto=`."""
    if not _EMAIL.fullmatch(value):
        raise CrawlError("the Crossref contact (CROSSREF_MAILTO or mailto) is set but is not an e-mail address: "
                         "fix or unset it", reason="bad_contact")  # fmt: skip
    return value


def user_agent(mailto: str | None) -> str:
    return (
        USER_AGENT if mailto is None else f"{USER_AGENT.removesuffix(')')}; mailto:{valid_contact(mailto)})"
    )


@dataclass(kw_only=False)
class CrossrefReport(ListingReport):
    """One ACM proceedings from Crossref: the shared listing counts, plus the works the window returned (every
    prefix:10.1145 DOI, this proceedings' and others'), the cursor pages read, the records with no author and the
    authors dropped for having no name (in the manifest only when above 0); for
    FAccT years with an official page (`facct_site`), the page's entries, the abstracts attached and why the rest
    weren't (listed in the manifest only when a page was read)."""

    window_works: int = 0
    pages: int = 0
    no_authors: int = 0
    unnamed_authors: int = 0  # authors Crossref lists with no given name, family name or name: dropped
    sites: list[str] = field(default_factory=list)  # the official page read, as fetched
    site_entries: int = 0  # page entries with a title and a usable abstract
    abstract_attached: int = 0
    # entries no record joins (no DOI, a DOI no record has, or a title key no record has)
    site_unmatched: int = 0
    site_ambiguous: int = 0  # entries whose DOI or title key two entries, or two records, share
    site_dropped: int = 0  # page rows with no title or no usable abstract

    def to_manifest(self) -> dict[str, Any]:
        out = super().to_manifest() | {"window_works": self.window_works, "pages": self.pages,
                                       "no_authors": self.no_authors}  # fmt: skip
        if self.unnamed_authors:
            out["unnamed_authors"] = self.unnamed_authors
        if self.sites:
            out |= {"sites": list(self.sites), "site_entries": self.site_entries,
                    "abstract_attached": self.abstract_attached, "site_unmatched": self.site_unmatched,
                    "site_ambiguous": self.site_ambiguous, "site_dropped": self.site_dropped}  # fmt: skip
        return dict(sorted(out.items()))


@dataclass
class ProceedingsResult:
    records: list[PaperRecord]
    reports: list[CrossrefReport]


Get = Callable[[str, bool], Page | None]


def _walk(row: Proceedings, get: Get) -> list[tuple[Page, WorksPage]] | None:
    """The cursor chain from `cursor=*` to its first empty page, through `get` (None: a page `get` can't give).
    The works read may never outnumber the total the first page states (a chain that loops is stopped)."""
    out: list[tuple[Page, WorksPage]] = []
    cursor, total, seen = "*", None, 0
    while True:
        page = get(works_url(row, cursor), cursor == "*")
        if page is None:
            return None
        if not page.ok:
            raise CrawlError(f"{page.url} answered HTTP {page.status}", reason="no_listing")
        parsed = parse_works(page.text)
        if total is None:
            total = parsed.total
        elif parsed.total != total:
            raise CrawlError(f"Crossref {row.venue} {row.year}: total-results moved from {total} to {parsed.total} "
                             "mid-chain; re-run with --refresh", reason="listing_changed")  # fmt: skip
        out.append((page, parsed))
        seen += len(parsed.works)
        if not parsed.works or parsed.next_cursor is None:
            return out
        if seen > total:
            raise CrawlError(f"Crossref {row.venue} {row.year}: the cursor chain returned {seen} works of a "
                             f"stated {total}", reason="listing_changed")  # fmt: skip
        cursor = parsed.next_cursor


def harvest(row: Proceedings, fetcher: Fetcher, *, refresh: bool = False) -> list[tuple[Page, WorksPage]]:
    """The chain the cache holds whole (the replay's route), else, live, a fresh chain from `cursor=*` with its first
    page fetched again: a cursor expires within minutes, so a half-cached chain can't be resumed."""
    chain = (
        None
        if refresh
        else _walk(row, lambda url, _first: fetcher.get(url) if fetcher.is_cached(url) else None)
    )
    if chain is not None:
        return chain
    if fetcher.offline:
        raise CrawlError(f"Crossref {row.venue} {row.year}: the cursor chain is not in the cache; run op ingest "
                         "crossref", reason="not_cached")  # fmt: skip
    fresh = _walk(row, lambda url, first: fetcher.get(url, refresh=first))
    assert fresh is not None  # a live get always gives a page
    return fresh


def mine_proceedings(
    venue: str, year: int, fetcher: Fetcher, *, refresh: bool = False, table: acm_table.Table | None = None,
    site: facct_site.SiteYear | None = None,
) -> ProceedingsResult:  # fmt: skip
    """One ACM proceedings' records from Crossref, with the table's count checked (a mismatch stops the crawl).
    With `site` (a FAccT year's official page), each record takes the abstract of the one page entry joined to it
    (`facct_site.match`: by DOI, or by a title key that entry and record alone share); the rest are counted."""
    started = time.monotonic()
    table = table or acm_table.TABLE
    row = table.proceedings.get((venue, year))
    if row is None:
        raise CrawlError(f"{venue} {year}: no acm_proceedings.toml row", reason="unlisted_proceedings")
    head = fetcher.get(proceedings_url(row.doi), refresh=refresh)
    if not head.ok:
        raise CrawlError(f"{head.url} answered HTTP {head.status}", reason="no_listing")
    doi, title, _isbn = parse_proceedings(head.text)
    if doi != row.doi or not title.startswith(row.title):
        raise CrawlError(f"Crossref's record {doi} is titled {title!r}, not the table's {row.doi} "
                         f"{row.title!r}", reason="proceedings_mismatch")  # fmt: skip
    chain = harvest(row, fetcher, refresh=refresh)
    report = CrossrefReport(
        SOURCE, venue, year, proceedings_url(row.doi), "primary", row.dois, pages=len(chain)
    )
    report.fetched.append(head.fetched_at)
    report.fetched += [page.fetched_at for page, _ in chain]
    seen: dict[str, tuple[Page, Work]] = {}
    for page, parsed in chain:
        for w in parsed.works:
            report.window_works += 1
            if not row.paper(w.doi):
                continue
            if acm_table.paper_doi(w.doi) is None:
                raise CrawlError(f"Crossref {venue} {year}: DOI {w.doi!r} extends {row.doi} but is not "
                                 f"{row.doi}.<digits>: check it before it is indexed", reason="odd_doi")  # fmt: skip
            if w.doi in seen:
                if seen[w.doi][1] != w:
                    raise CrawlError(f"Crossref {venue} {year}: {w.doi} is listed twice with different "
                                     "records", reason="conflicting_duplicate")  # fmt: skip
                report.skipped["duplicate"] += 1
                continue
            seen[w.doi] = (page, w)
            report.listed += 1
    if report.listed != row.dois:
        raise CrawlError(f"Crossref {venue} {year}: {report.listed} DOIs extend {row.doi} in the window, the table "
                         f"verified {row.dois}: check the window and the table", reason="count_mismatch")  # fmt: skip
    if stale := sorted(
        np.doi for np in table.not_papers.values() if row.paper(np.doi) and np.doi not in seen
    ):
        raise CrawlError(f"Crossref {venue} {year}: acm_proceedings.toml's not_paper rows {', '.join(stale)} are not "
                         "in the harvest: check the window and the table", reason="stale_not_paper")  # fmt: skip
    kept: list[tuple[str, Work, Page]] = []
    for doi in sorted(seen, key=lambda d: int((acm_table.paper_doi(d) or ("", "0"))[1])):
        page, w = seen[doi]
        if doi in table.not_papers:
            report.skipped["not_paper"] += 1
            continue
        if w.type != "proceedings-article":
            raise CrawlError(f"Crossref {venue} {year}: {doi} has type {w.type!r}, not 'proceedings-article': name it "
                             "in acm_proceedings.toml [[not_paper]] if it is no paper, else check "
                             "Crossref", reason="unexpected_type")  # fmt: skip
        if w.title is None:
            raise CrawlError(f"Crossref {venue} {year}: {doi} has no title: name it in acm_proceedings.toml "
                             "[[not_paper]] if it is no paper, else check Crossref", reason="no_title")  # fmt: skip
        kept.append((doi, w, page))
    matched = None
    if site is not None:
        matched = facct_site.match([(doi, title_text(w.title or "")[0]) for doi, w, _ in kept], site)
        report.sites = [site.page]
        report.site_entries = len(site.entries)
        report.site_dropped = site.dropped
        report.site_unmatched, report.site_ambiguous = matched.unmatched, matched.ambiguous
        report.fetched += site.fetched
    records: list[PaperRecord] = []
    used: set[acm_table.Section] = set()
    for doi, w, page in kept:
        found = matched.by_doi.get(doi) if matched is not None else None
        section = table.section(venue, year, w.page)
        if section is not None:
            used.add(section)
        try:
            record = _record(row, w, page, found, site.join if site is not None else None, section,
                             sectioned=any((s.venue, s.year) == (venue, year) for s in table.sections))  # fmt: skip
        except (ValidationError, ValueError) as e:
            raise CrawlError(f"Crossref {venue} {year}: {doi} makes no valid record ({type(e).__name__})",
                             reason="invalid_record") from e  # fmt: skip
        report.no_authors += not record.authors
        report.unnamed_authors += w.unnamed_authors
        records.append(record)
        report.count(record, None if record.abstract else "no_abstract", found.spaced if found else 0,
                     found.pdf_codes if found else 0)  # fmt: skip
    if empty := [s for s in table.sections if (s.venue, s.year) == (venue, year) and s not in used]:
        raise CrawlError(f"Crossref {venue} {year}: acm_proceedings.toml's section {empty[0].label!r} pp. "
                         f"{empty[0].first}-{empty[0].last} holds no work of the harvest: check the table",
                         reason="stale_section")  # fmt: skip
    report.abstract_attached = sum(r.abstract is not None for r in records)
    log.info("crossref_proceedings_mined", extra={"venue": venue, "year": year, "listed": report.listed,
                                                  "records": report.records, "window_works": report.window_works,
                                                  "pages": report.pages, "abstract_attached": report.abstract_attached,
                                                  "site_entries": report.site_entries,
                                                  "site_unmatched": report.site_unmatched,
                                                  "site_ambiguous": report.site_ambiguous,
                                                  "site_dropped": report.site_dropped,
                                                  "ms": elapsed_ms(started, time.monotonic)})  # fmt: skip
    if report.no_authors or report.unnamed_authors:
        log.warning("listing_attention", extra={"venue": venue, "year": year, "listing": report.listing,
                                                "no_authors": report.no_authors,
                                                "unnamed_authors": report.unnamed_authors})  # fmt: skip
    return ProceedingsResult(records, [report])


def _record(row: Proceedings, w: Work, page: Page, found: facct_site.SiteAbstract | None = None,
            join: str | None = None, section: acm_table.Section | None = None,
            sectioned: bool = False) -> PaperRecord:  # fmt: skip
    """The record of one Crossref work: every claim at the work's own API URL (never a cursor page), and the
    official page's abstract when `found` (its claim at the page as fetched; `join` says how it was joined).
    Track `main`, or the track of the `section` row its Crossref start page falls in; `sectioned` says the
    proceedings has section rows, so a `main` claim names the pages it falls outside."""
    where = f"Crossref work {w.doi} in proceedings {row.doi} (acm_proceedings.toml {row.venue} {row.year})"
    claims: list[Claim] = []

    def claim(fld: ClaimField, value: ClaimValue, evidence: str) -> None:
        claims.append(Claim(field=fld, value=value, source=SOURCE, url=work_url(w.doi),
                            fetched_at=page.fetched_at, evidence=evidence))  # fmt: skip

    title, replaced = title_text(w.title or "")
    claim("venue", row.venue, where)
    claim("year", row.year, where)
    if section is None and sectioned:
        claim("track", "main", f"{where}: page {w.page} is in no acm_proceedings.toml [[section]] of the "
                               "proceedings, so main (decision-049, decision-050)")  # fmt: skip
    elif section is None:
        claim("track", "main", f"{where}: every paper of the proceedings is main (decision-049)")
    else:
        claim("track", section.track, f"{where}: page {w.page} is in \"{section.label}\", pp. {section.first}-"
                                      f"{section.last} (acm_proceedings.toml [[section]], verified "
                                      f"{section.verified.isoformat()}; {section.source})")  # fmt: skip
    claim("status", "accepted", f"published in {row.doi}")
    claim("title", title, title_evidence(f"{where}: title", replaced))
    if w.authors:
        claim("authors", w.authors, f"{where}: author, in Crossref's order")
    claim("urls.doi", w.doi, where)
    claim("urls.proceedings", f"https://doi.org/{w.doi}", where)
    if found is not None:
        how = "DOI" if join == "doi" else "its title key, the record’s alone"
        claims.append(Claim(field="abstract", value=found.abstract, source=facct_site.SOURCE, url=found.url,
                            fetched_at=found.fetched_at, evidence=pdf_codes_evidence(controls_evidence(
                                f"{found.evidence}; joined to {w.doi} by {how}", found.spaced), found.pdf_codes)))  # fmt: skip
    return record_from_claims(f"op:{row.venue.lower()}:{row.year}:doi-{w.doi.split('/', 1)[1]}", claims)
