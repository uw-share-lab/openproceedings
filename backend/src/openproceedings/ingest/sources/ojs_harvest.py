"""The ojs.aaai.org harvest layer: how `ojs.mine_journal` gets every article of one journal over OAI-PMH (spec 01
§Sources, OJS row; decision-049). The three steps (inventory, sets, gaps), the per-set `ListIdentifiers` +
`GetRecord` fallback and the replay behaviour are described in `ojs.py`'s docstring.

**Import direction:** this module imports `ojs` (the constants, URL builders, parsers and `journal_sets`), never
the reverse at import time. `ojs.mine_journal` imports `harvest_journal` from here inside the function, which
keeps the two modules acyclic. Deleted headers are counted from the inventory only (`JournalHarvest.deleted`).
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.sources.http import Fetcher, Page, RetriesExhausted
from openproceedings.ingest.sources.ojs import (
    OaiRecord,
    ids_url,
    journal_sets,
    oai_url,
    parse_identifiers,
    parse_page,
    parse_record,
    record_url,
)

log = logging.getLogger(__name__)


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
    """One set's records as harvested: its live records with the page each came from, and the articles the server
    could not serve (each with the cached failure). Deleted headers are not counted here: `inventory` counts them."""

    set_spec: str
    live: list[tuple[Page, OaiRecord]] = field(default_factory=list)
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
            if not e.deleted:
                h.live.append((page, e))
                seen.add(e.article)
        if token is None:
            return h


def _fallback(
    journal: str, h: SetHarvest, seen: set[int], fetcher: Fetcher, *, refresh: bool, failed: Page
) -> None:
    log.warning("ojs_set_fallback", extra={"journal": journal, "set": h.set_spec, "status": failed.status})
    h.fallback = True
    token: str | None = None
    while True:
        url = ids_url(journal, token, set_spec=h.set_spec)
        page = fetcher.get(url, refresh=refresh and token is None)
        if not page.ok:
            raise CrawlError(f"{url} answered HTTP {page.status}", reason="no_listing")
        h.pages += 1
        headers, token = parse_identifiers(page.text)
        for e in headers:
            if e.deleted or e.article in seen:
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


def inventory(journal: str, fetcher: Fetcher, *, refresh: bool = False) -> tuple[list[OaiRecord], int]:
    """The journal-wide `ListIdentifiers` chain: every header (live and deleted, in list order), the source of truth
    for which articles exist, and the pages read."""
    headers: list[OaiRecord] = []
    token: str | None = None
    pages = 0
    while True:
        url = ids_url(journal, token)
        page = fetcher.get(url, refresh=refresh and token is None)
        if not page.ok:
            raise CrawlError(f"{url} answered HTTP {page.status}", reason="no_listing")
        pages += 1
        found, token = parse_identifiers(page.text)
        headers += found
        if token is None:
            return headers, pages


@dataclass
class JournalHarvest:
    """One journal as harvested: each live inventory article once, in inventory order, with the page its metadata
    came from; the live articles neither route could serve; the deleted headers (from the inventory)."""

    live: list[tuple[Page, OaiRecord]] = field(default_factory=list)
    unavailable: list[tuple[OaiRecord, Page]] = field(
        default_factory=list
    )  # (inventory header, cached failure)
    deleted: int = 0
    deleted_by_set: Counter[str] = field(default_factory=Counter)  # the same headers, per set
    duplicates: int = 0  # extra copies of an article that more than one set request returned (identical)
    recovered: int = 0  # live inventory articles no set returned, read by GetRecord
    pages: int = 0
    fallback_sets: list[str] = field(default_factory=list)


def harvest_journal(journal: str, fetcher: Fetcher, *, refresh: bool = False) -> JournalHarvest:
    """The inventory, then every set's records (`harvest_set`), then `GetRecord` for each live inventory article no
    set returned (a set name two sections share reaches only one of them: AAAI's `EAAI-POS`, `EAAI-Full`). An article
    returned twice is kept once; two copies that differ stop the crawl, as does a set record the inventory lacks."""
    out = JournalHarvest()
    headers, out.pages = inventory(journal, fetcher, refresh=refresh)
    out.deleted_by_set = Counter(h.set_spec for h in headers if h.deleted)
    out.deleted = sum(out.deleted_by_set.values())
    live: dict[int, OaiRecord] = {}
    for h in headers:
        if not h.deleted:
            live.setdefault(h.article, h)
    got: dict[int, tuple[Page, OaiRecord]] = {}
    failed: dict[int, Page] = {}
    for spec in journal_sets(journal, fetcher, refresh=refresh):
        sh = harvest_set(journal, spec, fetcher, refresh=refresh)
        out.pages += sh.pages
        if sh.fallback:
            out.fallback_sets.append(spec)
        for article, page in sh.unavailable:
            failed.setdefault(article, page)
        for page, rec in sh.live:
            if rec.article not in live:
                raise CrawlError(
                    f"OJS {journal} article {rec.article} (set {spec}) is not a live article of the inventory "
                    "(ListIdentifiers): the journal changed during the harvest; run it again with --refresh",
                    reason="not_in_inventory",
                )
            if (first := got.get(rec.article)) is not None:
                if first[1] != rec:
                    raise CrawlError(
                        f"OJS {journal} article {rec.article} came back from two set requests with different "
                        f"metadata ({first[1].set_spec} v{first[1].volume} and {rec.set_spec} v{rec.volume}); "
                        "check it by hand",
                        reason="conflicting_duplicate",
                    )
                out.duplicates += 1
                continue
            got[rec.article] = (page, rec)
    for article, header in live.items():
        if article in got:
            out.live.append(got[article])
            continue
        page = failed.get(article) or _get(fetcher, record_url(journal, article), refresh=refresh)
        if page.status >= 500:
            out.unavailable.append((header, page))
            continue
        if not page.ok:
            raise CrawlError(f"{page.url} answered HTTP {page.status}", reason="no_listing")
        out.pages += 1
        out.recovered += 1
        out.live.append((page, parse_record(page.text)))
    return out
