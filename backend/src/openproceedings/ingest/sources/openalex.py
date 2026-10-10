"""OpenAlex parsing for the abstract fill of AAAI, AIES and FAccT (spec 01 §Sources 6; decision-049, milestone C).

Scope: only AAAI, AIES and FAccT records whose resolved abstract is still null after every official source
(`record.OPENALEX_VENUES`); never a title, an author, a status or any other field, and never NeurIPS, ICLR, ICML or
IASEAI. The fill runs after dedup and reconcile and before takedowns, so it cannot displace an official abstract
and a takedown still withholds what it filled.

Two routes, both through the shared HTTP layer (`http.py`), one request at a time (`MIN_INTERVAL`):
- **DOIs.** A record with a DOI is looked up in batches of `BATCH` (`doi_url`); a work joins the record whose DOI
  it names.
- **Listings.** The dblp AAAI records of 1980-2008 carry no DOI, so each venue-year's works are listed from the
  sources `openalex_sources.toml` names (`openalex_table`, `listing_url`, cursor paged), and a work joins a record
  only by exact title key with exactly one candidate on each side; a listing whose count differs from the table's
  stops the crawl.
Refusals, never a best guess: an inverted index with a gap, two words at one position or any other shape
(`rebuild`); an abstract that cleaning leaves empty or a snippet (`abstract_unusable`, `abstract_of`); an answer
that is not a work list (`CrawlError`, `openalex_unreadable`, whose message never quotes the body).

The extract: a crawl keeps each work's raw `abstract_inverted_index` (`Work.inverted`), writes a content-addressed
extract and a marker naming it, and `op snapshot build` replays the extract offline, rebuilding and cleaning each
abstract there (`load_extract`, `fill`, `apply`), so a replay of the same extract gives the same records. The
extract is `<cache>/openalex/extract/<sha256 of its bytes>.json`, sealed read-only and never rewritten; the marker
`<cache>/openalex/crawls/openalex.json` names the one a build replays, which is re-hashed on every read
(`extract_changed`).

The claim: an `openalex` claim on `abstract` only. Its url is the work's API URL (`work_url`) and its evidence
names OpenAlex's page for the work (`work_page`), so the abstract's origin is shown as OpenAlex, never as the
proceedings (`abstract_kind` `openalex`).

The key: `OPENALEX_API_KEY` (the environment first, then `.env`) is optional and raises the daily budget. It is sent
as a request header (`Fetcher(headers=)`), never in a URL, so never in a cache key, a cache entry, a claim, a log
line or an exception. No contact address is sent to OpenAlex: no `mailto` parameter and no address in the
User-Agent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal
from urllib.parse import quote

from openproceedings import storage
from openproceedings.ingest import openalex_table
from openproceedings.ingest.caps import cap_record
from openproceedings.ingest.dedup import DedupResult, title_key
from openproceedings.ingest.record import OPENALEX_VENUES, Claim, PaperRecord, Source, controls_evidence
from openproceedings.ingest.sources.common import (
    Cleaned,
    CrawlError,
    Report,
    clean_abstract,
    pdf_codes_evidence,
    read_markers,
    write_marker,
)
from openproceedings.ingest.sources.openreview_client import read_dotenv
from openproceedings.logs import elapsed_ms

if TYPE_CHECKING:
    from openproceedings.ingest.openalex_table import Listing, Table
    from openproceedings.ingest.sources.http import Fetcher, Page

log = logging.getLogger(__name__)

SOURCE: Source = "openalex"
CACHE_DIR = "openalex"  # <data>/cache/openalex
HOST = "api.openalex.org"
HOSTS = frozenset({HOST})
MIN_INTERVAL = 1.0  # sequential, a second apart (OpenAlex refuses more than 100 requests a second; be gentle)
BATCH = 50  # DOIs per request (OpenAlex takes up to 100 OR values a filter; 50 keeps URLs short)
PER_PAGE = 200
SELECT = "id,doi,title,publication_year,primary_location,abstract_inverted_index"
KEY_ENV = "OPENALEX_API_KEY"
MAX_POSITIONS = (
    25_000  # more words than any abstract under caps.MAX_ABSTRACT characters: refused, not allocated
)
MAX_ANSWER = 64_000_000  # characters of one answer (a full page is a few MB): a larger one is refused unread
MAX_CURSOR = 2048
_DOI = re.compile(r"10\.[0-9]{1,9}(?:\.[0-9]{1,9}){0,8}/\S{1,1000}")
_ID = re.compile(r"(?:https://openalex\.org/)?(W[0-9]{1,12})")
_SOURCE_ID = re.compile(r"(?:https://openalex\.org/)?(S[0-9]{1,12})")
_CURSOR = re.compile(rf"[\x21-\x7e]{{1,{MAX_CURSOR}}}")
_WORD = re.compile(r"\S+")  # one word: a key with whitespace in it is no inverted index
_DOI_UNSAFE = frozenset(
    "|,&#?%+"
)  # what would split the filter or the query string, or change it once decoded
_KEY = re.compile(r"[\x21-\x7e]{1,256}")  # printable ASCII: nothing a header would split on, nothing to quote


@dataclass(frozen=True, slots=True)
class Work:
    id: str  # `W…`
    doi: str | None  # bare, lower-case
    title: str | None
    year: int | None
    sources: tuple[str, ...]  # `S…` of the primary location
    inverted: Any  # the raw abstract_inverted_index (rebuilt at replay: `rebuild`)


@dataclass(frozen=True, slots=True)
class WorksPage:
    works: tuple[Work, ...]
    total: int  # meta.count: every work the filter matches, over all pages
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class Rebuilt:
    text: str | None
    refused: str | None  # inverted_gap | inverted_conflict | inverted_unreadable


def rebuild(inverted: object) -> Rebuilt:
    """The abstract an `abstract_inverted_index` encodes, its words in position order. A position held by two
    different words, a gap, or anything not `{word: [position, …]}` is refused: no abstract with a silent hole.
    The same word listed twice at one position is kept once. A position at or past `MAX_POSITIONS`, or more
    entries than that in all, is refused before anything is built from it."""
    if inverted is None:
        return Rebuilt(None, None)
    if not isinstance(inverted, dict) or not inverted:
        return Rebuilt(None, "inverted_unreadable")
    at: dict[int, str] = {}
    entries = 0
    for word, positions in inverted.items():
        if (
            not isinstance(word, str)
            or not _WORD.fullmatch(word)
            or not isinstance(positions, list)
            or not positions
        ):
            return Rebuilt(None, "inverted_unreadable")
        entries += len(positions)
        if entries > MAX_POSITIONS:
            return Rebuilt(None, "inverted_unreadable")
        for p in positions:
            if type(p) is not int or not 0 <= p < MAX_POSITIONS:
                return Rebuilt(None, "inverted_unreadable")
            if at.setdefault(p, word) != word:
                return Rebuilt(None, "inverted_conflict")
    if max(at) != len(at) - 1:  # keys are distinct non-negative ints: dense from 0 exactly when max = n - 1
        return Rebuilt(None, "inverted_gap")
    return Rebuilt(" ".join(at[i] for i in range(len(at))), None)


def abstract_of(work: Work) -> tuple[Cleaned | None, str | None]:
    """The work's abstract as a record may hold it (`common.clean_abstract`: controls, the `…` snippet rule,
    placeholders; the caps apply when the record is built), or None with why (`rebuild`'s refusal, or
    `abstract_unusable`); (None, None) when OpenAlex has no abstract."""
    rebuilt = rebuild(work.inverted)
    if rebuilt.text is None:
        return None, rebuilt.refused
    try:
        rebuilt.text.encode("utf-8")
    except (
        UnicodeEncodeError
    ):  # a lone surrogate (JSON's `\ud800`), which no record may hold (`record._utf8`)
        return None, "abstract_unusable"
    cleaned = clean_abstract(rebuilt.text)
    return (cleaned, None) if cleaned.text is not None else (None, "abstract_unusable")


def bare_doi(value: object) -> str | None:
    """A DOI as OpenAlex gives it (`https://doi.org/10.…`) bare and lower-case, or None for anything else."""
    if not isinstance(value, str):
        return None
    doi = value.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/").lower()
    return doi if _DOI.fullmatch(doi) else None


def doi_url(dois: Sequence[str]) -> str:
    """The DOI route's URL for a batch. Every DOI must already be bare (`bare_doi(d) == d`) and hold nothing that
    would split the filter's OR list or the query string, or change once decoded (`| , & # ? % +`, whitespace):
    such a DOI stops (`openalex_bad_doi`, never quoted), never encoded or dropped silently."""
    if not 0 < len(dois) <= BATCH:
        raise ValueError(f"a DOI batch holds 1 to {BATCH} DOIs")
    for d in dois:
        if bare_doi(d) != d or any(c in _DOI_UNSAFE or c.isspace() for c in d):
            raise CrawlError("a DOI for OpenAlex is not a bare DOI safe in a filter (| , & # ? % + or whitespace)",
                             reason="openalex_bad_doi")  # fmt: skip
    return f"https://{HOST}/works?filter=doi:{'|'.join(sorted(dois))}&per-page={BATCH}&select={SELECT}"


def listing_url(row: Listing, cursor: str = "*") -> str:
    return (f"https://{HOST}/works?filter=primary_location.source.id:{'|'.join(row.source_ids)},"
            f"publication_year:{row.year}&per-page={PER_PAGE}&select={SELECT}&cursor={quote(cursor, safe='')}")  # fmt: skip


def work_url(work_id: str) -> str:  # the claim's url (OpenAlex's API)
    return f"https://{HOST}/works/{work_id}"


def work_page(work_id: str) -> str:  # named in the claim's evidence (OpenAlex's page for the work)
    return f"https://openalex.org/{work_id}"


def _unreadable(why: str) -> CrawlError:
    # never quotes the body: an OpenAlex answer is untrusted text
    return CrawlError(f"an OpenAlex answer {why}", reason="openalex_unreadable")


def _sources(location: object) -> tuple[str, ...]:
    source = location.get("source") if isinstance(location, dict) else None
    sid = source.get("id") if isinstance(source, dict) else None
    m = _SOURCE_ID.fullmatch(sid) if isinstance(sid, str) else None
    return (m.group(1),) if m else ()


def _work(item: object) -> Work:
    if not isinstance(item, dict):
        raise _unreadable("has a result that is not an object")
    wid = item.get("id")
    m = _ID.fullmatch(wid) if isinstance(wid, str) else None
    if m is None:
        raise _unreadable("has a work with no OpenAlex work id")
    title, year = item.get("title"), item.get("publication_year")
    return Work(
        id=m.group(1),
        doi=bare_doi(item.get("doi")),
        title=title if isinstance(title, str) else None,
        year=year if type(year) is int and 0 < year < 10_000 else None,
        sources=_sources(item.get("primary_location")),
        inverted=item.get("abstract_inverted_index"),
    )


def parse_works(text: str) -> WorksPage:
    """One `/works` answer: its works, `meta.count` and the next cursor (None at the end). An answer that is not
    a JSON object with a `meta` holding a non-negative integer `count` and a `results` list of at most `PER_PAGE`
    works, each with a `W…` id, stops (`openalex_unreadable`)."""
    if len(text) > MAX_ANSWER:
        raise _unreadable(f"is longer than {MAX_ANSWER} characters")
    try:
        body = json.loads(text)
    except (ValueError, RecursionError) as e:  # ValueError: not JSON, or an integer past int's digit limit
        raise _unreadable("is not JSON") from e
    meta = body.get("meta") if isinstance(body, dict) else None
    results = body.get("results") if isinstance(body, dict) else None
    count = meta.get("count") if isinstance(meta, dict) else None
    if not isinstance(meta, dict) or type(count) is not int or count < 0 or not isinstance(results, list):
        raise _unreadable("is not a work list (meta.count and results)")
    if len(results) > PER_PAGE:
        raise _unreadable(f"holds more than {PER_PAGE} works")
    works = tuple(_work(r) for r in results)
    cursor = meta.get("next_cursor")
    if cursor is not None and not isinstance(cursor, str):
        raise _unreadable("has a next_cursor that is not a string")
    if cursor and not _CURSOR.fullmatch(cursor):
        raise _unreadable("has a next_cursor that is not printable ASCII of a bounded length")
    return WorksPage(works, count, cursor or None)


def api_key(environ: Mapping[str, str], dotenv: Path | None) -> str | None:
    """The optional OpenAlex API key from `OPENALEX_API_KEY` (the environment first, then `.env`), stripped, or
    None when it is unset or blank, or `.env` cannot be read. A value that is set but is not 1-256 printable ASCII
    characters (a header would split on it) stops (`bad_key`, as `crossref.valid_contact` does), never quoting it.
    The value goes into a request header only: never a URL, a cache entry, a log line or an exception."""
    try:
        values = {**(read_dotenv(dotenv) if dotenv else {}), **environ}
    except (OSError, UnicodeError):  # a directory, an unreadable or undecodable file: no key
        values = dict(environ)
    value = values.get(KEY_ENV, "").strip()
    if not value:
        return None
    if not _KEY.fullmatch(value):
        raise CrawlError(
            "OPENALEX_API_KEY is set but is not 1-256 printable ASCII characters: fix or unset it",
            reason="bad_key",
        )
    return value


# --- the extract: what a crawl read, pinned by its sha256 (decision-049) ------------------------------------

EXTRACT_FORMAT = "1"
EXTRACT_DIR = "extract"  # <cache>/openalex/extract/<sha256>.json
MARKER = "openalex"  # <cache>/openalex/crawls/openalex.json names the extract a build replays
_SHA = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class Lookup:
    """One request's answer as the extract keeps it: a DOI batch (`requested`: its DOIs, sorted) or a venue-year's
    listing (`venue`, `year`; every page's works, the first page's fetch time)."""

    route: Literal["doi", "listing"]
    url: str  # the batch's URL, or the listing's first page (`cursor=*`)
    fetched_at: datetime
    requested: tuple[str, ...]
    venue: str | None
    year: int | None
    works: tuple[Work, ...]


@dataclass(frozen=True, slots=True)
class Extract:
    sha256: str  # of the extract file's bytes, as the marker names it
    lookups: tuple[Lookup, ...]


def _extract_path(cache: Path, sha: str) -> Path:
    return cache / CACHE_DIR / EXTRACT_DIR / f"{sha}.json"


def _work_json(w: Work) -> dict[str, Any]:
    return {"id": w.id, "doi": w.doi, "title": w.title, "year": w.year, "sources": list(w.sources),
            "abstract_inverted_index": w.inverted}  # fmt: skip


def _lookup_json(lk: Lookup) -> dict[str, Any]:
    return {"route": lk.route, "url": lk.url, "fetched_at": lk.fetched_at.isoformat(),
            "requested": list(lk.requested), "venue": lk.venue, "year": lk.year,
            "works": [_work_json(w) for w in lk.works]}  # fmt: skip


def write_extract(cache: Path, lookups: Iterable[Lookup]) -> str:
    """Write the lookups (in URL order) as one canonical JSON file named by the sha256 of its bytes, sealed
    read-only, then the marker naming it (last, atomically: a crash leaves the old marker). An extract already
    there with those bytes is left as it is; the old extracts are never rewritten. Returns the sha256."""
    ordered = [_lookup_json(lk) for lk in sorted(lookups, key=lambda lk: lk.url)]
    # ASCII with escapes: a lone surrogate OpenAlex sent (JSON `\ud800`) is kept as it came, never a crash on
    # encoding; the fill refuses it (`abstract_unusable`)
    body = json.dumps({"format": EXTRACT_FORMAT, "lookups": ordered}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")  # fmt: skip
    sha = hashlib.sha256(body).hexdigest()
    path = _extract_path(cache, sha)
    if not (path.exists() and path.read_bytes() == body):
        if path.exists():  # another file under this name (edited by hand): put the extract's bytes back
            path.chmod(0o644)
        storage.write_bytes(path, body)
        path.chmod(0o444)
    write_marker(cache / CACHE_DIR / "crawls", MARKER,
                 {"source": SOURCE, "format": EXTRACT_FORMAT, "extract": sha})  # fmt: skip
    return sha


def _invalid(why: str) -> CrawlError:
    return CrawlError(f"the OpenAlex extract {why}; run op ingest openalex", reason="crawl_file_invalid")


def _work_from(raw: Any) -> Work:
    if not isinstance(raw, dict) or set(raw) != {
        "id",
        "doi",
        "title",
        "year",
        "sources",
        "abstract_inverted_index",
    }:
        raise ValueError("a work is not the extract's shape")
    if not isinstance(raw["id"], str) or not _ID.fullmatch(raw["id"]) or raw["id"].startswith("https:"):
        raise ValueError("a work has no OpenAlex work id")
    doi, title, year, sources = raw["doi"], raw["title"], raw["year"], raw["sources"]
    if (doi is not None and bare_doi(doi) != doi) or (title is not None and not isinstance(title, str)):
        raise ValueError("a work's DOI or title is malformed")
    if (year is not None and type(year) is not int) or not isinstance(sources, list):
        raise ValueError("a work's year or sources are malformed")
    if not all(isinstance(x, str) and _SOURCE_ID.fullmatch(x) for x in sources):
        raise ValueError("a work's source id is malformed")
    return Work(raw["id"], doi, title, year, tuple(sources), raw["abstract_inverted_index"])


def _lookup_from(raw: Any) -> Lookup:
    if not isinstance(raw, dict):
        raise ValueError("a lookup is not an object")
    route, url, requested, venue, year = raw["route"], raw["url"], raw["requested"], raw["venue"], raw["year"]
    fetched = datetime.fromisoformat(raw["fetched_at"])
    if fetched.tzinfo is None:
        raise ValueError("a naive fetched_at")
    if route not in ("doi", "listing") or not isinstance(url, str) or not isinstance(requested, list):
        raise ValueError("a lookup's route, url or requested is malformed")
    if not all(isinstance(d, str) and bare_doi(d) == d for d in requested):
        raise ValueError("a requested DOI is malformed")
    if route == "listing" and (not isinstance(venue, str) or type(year) is not int):
        raise ValueError("a listing names no venue and year")
    return Lookup(
        route, url, fetched, tuple(requested), venue, year, tuple(_work_from(w) for w in raw["works"])
    )


def load_extract(cache: Path) -> Extract | None:
    """The extract the marker names, from the cache alone, its bytes re-hashed (guarantee 4): None when no crawl
    wrote a marker (no fill). A marker that is unreadable or names no extract, or an extract that is malformed,
    is `crawl_file_invalid`; a missing extract `not_cached`; bytes that no longer hash to the marker's sha256
    `extract_changed`. Any other extract beside it is never read."""
    marker = cache / CACHE_DIR / "crawls" / f"{MARKER}.json"
    if not marker.exists():
        return None
    found = dict(read_markers(marker.parent)).get(marker.name)
    sha = found.get("extract") if found else None
    if (
        not found
        or found.get("format") != EXTRACT_FORMAT
        or not isinstance(sha, str)
        or not _SHA.fullmatch(sha)
    ):
        raise CrawlError("the OpenAlex crawl marker names no extract; run op ingest openalex",
                         reason="crawl_file_invalid")  # fmt: skip
    try:
        body = _extract_path(cache, sha).read_bytes()
    except FileNotFoundError:
        raise CrawlError(f"the OpenAlex extract {sha[:12]} the marker names is not in the cache; run op ingest "
                         "openalex", reason="not_cached") from None  # fmt: skip
    except OSError as e:
        raise _invalid(f"{sha[:12]} is unreadable ({type(e).__name__})") from None
    if hashlib.sha256(body).hexdigest() != sha:
        raise CrawlError(f"the OpenAlex extract {sha[:12]} no longer holds what was written; run op ingest "
                         "openalex", reason="extract_changed")  # fmt: skip
    try:
        raw = json.loads(body.decode("utf-8"))
        if (
            not isinstance(raw, dict)
            or raw.get("format") != EXTRACT_FORMAT
            or not isinstance(raw.get("lookups"), list)
        ):
            raise ValueError("not an extract")
        lookups = tuple(_lookup_from(lk) for lk in raw["lookups"])
    except (KeyError, TypeError, ValueError, RecursionError) as e:
        raise _invalid(f"{sha[:12]} is malformed ({type(e).__name__})") from None
    return Extract(sha, lookups)


# --- the harvest (`op ingest openalex`) ---------------------------------------------------------------------


def candidates(records: Iterable[PaperRecord]) -> list[PaperRecord]:
    """The records the fill may touch: AAAI, AIES or FAccT with no abstract."""
    return [r for r in records if r.venue in OPENALEX_VENUES and r.abstract is None]


def queryable(doi: str) -> bool:
    """A DOI `doi_url` takes (nothing that would split the filter or the query string)."""
    return not any(c in _DOI_UNSAFE or c.isspace() for c in doi)


def doi_batches(records: Iterable[PaperRecord]) -> tuple[list[list[str]], int]:
    """The candidates' DOIs, sorted and chunked by `BATCH`, and how many DOIs no filter can carry (counted
    `doi_unqueryable`, never encoded or dropped silently)."""
    dois = {d for r in candidates(records) if (d := bare_doi(r.urls.doi))}
    ok = sorted(d for d in dois if queryable(d))
    return [ok[i : i + BATCH] for i in range(0, len(ok), BATCH)], len(dois) - len(ok)


type _Get = Callable[[str, bool], "Page | None"]


def _walk(row: Listing, get: _Get) -> list[tuple[Page, WorksPage]] | None:
    """A listing's cursor chain from `cursor=*` to its last page, through `get` (None: a page `get` can't give).
    A total that moves mid-chain, or a chain that returns more works than its total, stops (`listing_changed`)."""
    out: list[tuple[Page, WorksPage]] = []
    cursor, total, seen = "*", None, 0
    while True:
        page = get(listing_url(row, cursor), cursor == "*")
        if page is None:
            return None
        if not page.ok:
            raise CrawlError(f"OpenAlex {row.venue} {row.year}: the listing answered HTTP {page.status}",
                             reason="no_listing")  # fmt: skip
        parsed = parse_works(page.text)
        if total is None:
            total = parsed.total
        elif parsed.total != total:
            raise CrawlError(f"OpenAlex {row.venue} {row.year}: meta.count moved from {total} to {parsed.total} "
                             "mid-chain; re-run with --refresh", reason="listing_changed")  # fmt: skip
        out.append((page, parsed))
        seen += len(parsed.works)
        if seen > total:
            raise CrawlError(f"OpenAlex {row.venue} {row.year}: the cursor chain returned {seen} works of a "
                             f"stated {total}", reason="listing_changed")  # fmt: skip
        if not parsed.works or parsed.next_cursor is None:
            return out
        cursor = parsed.next_cursor


def _listing(row: Listing, fetcher: Fetcher, *, refresh: bool) -> Lookup:
    """One table row's works: the chain the cache holds whole, else (live) a fresh chain from `cursor=*` with its
    first page fetched again (a cursor expires, so a half-cached chain can't be resumed). The works must number
    `meta.count` (`listing_changed`) and the table's verified `works` (`count_mismatch`)."""
    chain = (
        None
        if refresh
        else _walk(row, lambda url, _first: fetcher.get(url) if fetcher.is_cached(url) else None)
    )
    if chain is None:
        if fetcher.offline:
            raise CrawlError(f"OpenAlex {row.venue} {row.year}: the listing is not in the cache; run op ingest "
                             "openalex", reason="not_cached")  # fmt: skip
        chain = _walk(row, lambda url, first: fetcher.get(url, refresh=first))
        assert chain is not None  # a live get always gives a page
    works = tuple(w for _, parsed in chain for w in parsed.works)
    if len(works) != chain[0][1].total:
        raise CrawlError(f"OpenAlex {row.venue} {row.year}: the chain returned {len(works)} works of a stated "
                         f"{chain[0][1].total}; re-run with --refresh", reason="listing_changed")  # fmt: skip
    if len(works) != row.works:
        raise CrawlError(f"OpenAlex {row.venue} {row.year}: {len(works)} works under {', '.join(row.source_ids)}, "
                         f"the table verified {row.works}: check openalex_sources.toml", reason="count_mismatch")  # fmt: skip
    return Lookup("listing", listing_url(row), chain[0][0].fetched_at, (), row.venue, row.year, works)


def harvest(
    records: Iterable[PaperRecord], fetcher: Fetcher, *, refresh: bool = False, table: Table | None = None
) -> tuple[Lookup, ...]:
    """Every lookup the fill replays: the candidates' DOIs in batches (`doi_url`), then each listing row of the
    table (`listing_url`, cursor paged). A batch that is not HTTP 200 stops (`no_listing`), and so does one whose
    `meta.count` is more than twice the batch (the filter was misread) or more than the page holds (a work would
    be dropped unseen, `doi_batch_incomplete`)."""
    table = table or openalex_table.TABLE
    out: list[Lookup] = []
    batches, _ = doi_batches(records)
    for chunk in batches:
        url = doi_url(chunk)
        page = fetcher.get(url, refresh=refresh)
        if not page.ok:
            raise CrawlError(f"an OpenAlex DOI batch answered HTTP {page.status}", reason="no_listing")
        parsed = parse_works(page.text)
        if parsed.total > BATCH * 2:
            raise CrawlError(f"an OpenAlex DOI batch of {len(chunk)} matched {parsed.total} works: the filter was "
                             "misread", reason="no_listing")  # fmt: skip
        if parsed.total > len(parsed.works):
            raise CrawlError(f"an OpenAlex DOI batch of {len(chunk)} matched {parsed.total} works, more than its "
                             f"page holds ({len(parsed.works)})", reason="doi_batch_incomplete")  # fmt: skip
        out.append(Lookup("doi", url, page.fetched_at, tuple(chunk), None, None, parsed.works))
    out += [_listing(row, fetcher, refresh=refresh) for row in table.listings.values()]
    return tuple(out)


# --- the fill (`op snapshot build`, after dedup and reconcile, before takedowns) ----------------------------


@dataclass(kw_only=True)
class FillReport(Report):
    """The OpenAlex fill of one snapshot build, replayed from extract `extract` (manifest `sources.openalex.fills`)."""

    extract: str
    candidates: int = 0  # AAAI/AIES/FAccT records whose resolved abstract was null
    attached_doi: int = 0
    attached_title: int = 0
    official_won: int = 0  # records the extract has a work for whose own abstract is official now
    not_queried: int = 0  # candidates no lookup of the extract covered (a DOI not batched; no listing row)
    refused: Counter[str] = field(default_factory=Counter)

    manifest_key: ClassVar[str] = "fills"

    def to_manifest(self) -> dict[str, Any]:
        return {"extract": self.extract, "candidates": self.candidates, "attached_doi": self.attached_doi,
                "attached_title": self.attached_title, "official_won": self.official_won,
                "not_queried": self.not_queried, "refused": dict(sorted(self.refused.items()))}  # fmt: skip


def _id_order(w: Work) -> int:
    return int(w.id[1:])


def _attach(r: PaperRecord, works: Sequence[Work], cleaned: Cleaned, lookup: Lookup, how: str) -> PaperRecord:
    assert cleaned.text is not None
    first = works[0]
    claim = Claim(field="abstract", value=cleaned.text, source=SOURCE, url=work_url(first.id),
                  fetched_at=lookup.fetched_at, evidence=pdf_codes_evidence(controls_evidence(
                      f"OpenAlex work {', '.join(work_page(w.id) for w in works)}; matched {how}",
                      cleaned.spaced), cleaned.pdf_codes))  # fmt: skip
    return cap_record(r.model_copy(update={"abstract": cleaned.text, "provenance": (*r.provenance, claim)}))


def fill(
    records: Iterable[PaperRecord], extract: Extract, table: Table | None = None
) -> tuple[list[PaperRecord], FillReport]:
    """Fill each AAAI, AIES or FAccT record whose abstract is null from the extract, in record id order: by its
    DOI (every work answering for it; one text, or refused `doi_duplicate`), or, with no DOI, by the exact title
    key, year and venue in that venue-year's listing (one work and one record sharing the key, or refused
    `title_ambiguous`; the listing must be the table's row as it stands). Every refusal is counted, never forced;
    a record with an abstract, or outside those venues, is passed through as it is."""
    table = table or openalex_table.TABLE
    report = FillReport(source=SOURCE, extract=extract.sha256)
    ordered = sorted(records, key=lambda r: r.id)
    by_doi: dict[str, list[tuple[Work, Lookup]]] = {}
    queried: set[str] = set()
    listings: dict[tuple[str, int], Lookup] = {}
    for lk in extract.lookups:
        if lk.route == "doi":
            queried.update(lk.requested)
            for w in lk.works:
                if w.doi is not None and w.doi in lk.requested:
                    by_doi.setdefault(w.doi, []).append((w, lk))
                else:
                    report.refused["doi_mismatch"] += 1
        elif lk.venue is not None and lk.year is not None:
            row = table.listings.get((lk.venue, lk.year))
            if (
                row is not None and listing_url(row) == lk.url
            ):  # a row the table changed since is not replayed
                listings[(lk.venue, lk.year)] = lk
    corpus_dois = {d for r in ordered if (d := bare_doi(r.urls.doi))}
    doi_less = Counter(
        (r.venue, r.year, title_key(r.title)) for r in candidates(ordered) if not bare_doi(r.urls.doi)
    )

    def listed(r: PaperRecord, lk: Lookup) -> list[Work]:
        key = title_key(r.title)
        return [w for w in lk.works if key and w.title and w.year == r.year and title_key(w.title) == key]

    out: list[PaperRecord] = []
    for r in ordered:
        doi = bare_doi(r.urls.doi)
        listing = listings.get((r.venue, r.year))
        if r.venue not in OPENALEX_VENUES:
            out.append(r)
            continue
        if r.abstract is not None:
            report.official_won += bool(doi in by_doi if doi else listing is not None and listed(r, listing))
            out.append(r)
            continue
        report.candidates += 1
        refusal, attached = None, r
        if doi:
            hits = sorted(by_doi.get(doi, ()), key=lambda h: _id_order(h[0]))
            if doi not in queried:
                report.not_queried += 1
            elif not hits:
                refusal = "doi_unmatched"
            else:
                read = [(w, hlk, *abstract_of(w)) for w, hlk in hits]
                usable = [(w, hlk, c) for w, hlk, c, _ in read if c is not None]
                if not usable:
                    refusal = next((why for *_, why in read if why), "no_abstract")
                elif len({c.text for *_, c in usable}) > 1:
                    refusal = "doi_duplicate"
                else:
                    attached = _attach(
                        r, [w for w, *_ in usable], usable[0][2], usable[0][1], f"by DOI {doi}"
                    )
                    report.attached_doi += 1
        elif listing is None:
            report.not_queried += 1
        elif doi_less[(r.venue, r.year, title_key(r.title))] > 1:
            refusal = "title_ambiguous"
        elif not (matches := listed(r, listing)):
            refusal = "title_unmatched"
        elif len(matches) > 1:
            refusal = "title_ambiguous"
        elif matches[0].doi in corpus_dois:
            refusal = "doi_mismatch"
        else:
            cleaned, why = abstract_of(matches[0])
            if cleaned is None:
                refusal = why or "no_abstract"
            else:
                how = f"by exact title key, year and venue (openalex_sources.toml {r.venue} {r.year})"
                attached = _attach(r, matches, cleaned, listing, how)
                report.attached_title += 1
        if refusal:
            report.refused[refusal] += 1
        out.append(attached)
    return out, report


def apply(result: DedupResult, cache: Path) -> tuple[DedupResult, list[FillReport]]:
    """`op snapshot build`'s fill: the extract the marker names (`load_extract`; none, nothing changes) replayed
    over the deduped, reconciled records, offline. Returns the result and its one fill report."""
    started = time.monotonic()
    extract = load_extract(cache)
    if extract is None:
        return result, []
    records, report = fill(result.records, extract)
    report.fetched = sorted({lk.fetched_at for lk in extract.lookups})
    log.info("openalex_filled", extra={"extract": extract.sha256, "candidates": report.candidates,
                                       "attached": report.attached_doi + report.attached_title,
                                       "refused": sum(report.refused.values()), "not_queried": report.not_queried,
                                       "ms": elapsed_ms(started, time.monotonic)})  # fmt: skip
    return replace(result, records=tuple(sorted(records, key=lambda r: r.id))), [report]
