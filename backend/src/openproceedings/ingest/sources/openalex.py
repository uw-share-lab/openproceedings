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
abstract there (Task 8), so a replay of the same extract gives the same records.

The claim: an `openalex` claim on `abstract` only. Its url is the work's API URL (`work_url`) and its evidence
names OpenAlex's page for the work (`work_page`), so the abstract's origin is shown as OpenAlex, never as the
proceedings (`abstract_kind` `openalex`).

The key: `OPENALEX_API_KEY` (the environment first, then `.env`) is optional and raises the daily budget. It is sent
as a request header (`Fetcher(headers=)`), never in a URL, so never in a cache key, a cache entry, a claim, a log
line or an exception. No contact address is sent to OpenAlex: no `mailto` parameter and no address in the
User-Agent.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from openproceedings.ingest.record import Source
from openproceedings.ingest.sources.common import Cleaned, CrawlError, clean_abstract
from openproceedings.ingest.sources.openreview_client import read_dotenv

if TYPE_CHECKING:
    from openproceedings.ingest.openalex_table import Listing

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
        if not isinstance(word, str) or not word.strip() or not isinstance(positions, list) or not positions:
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
    cleaned = clean_abstract(rebuilt.text)
    return (cleaned, None) if cleaned.text is not None else (None, "abstract_unusable")


def bare_doi(value: object) -> str | None:
    """A DOI as OpenAlex gives it (`https://doi.org/10.…`) bare and lower-case, or None for anything else."""
    if not isinstance(value, str):
        return None
    doi = value.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/").lower()
    return doi if _DOI.fullmatch(doi) else None


def doi_url(dois: Sequence[str]) -> str:
    if not 0 < len(dois) <= BATCH:
        raise ValueError(f"a DOI batch holds 1 to {BATCH} DOIs")
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
    None when it is unset, blank, unreadable or not printable ASCII (a value a header would split on is never sent).
    Never raises, and the value goes into a request header only: never a URL, a log line or an exception."""
    try:
        values = {**(read_dotenv(dotenv) if dotenv else {}), **environ}
    except (OSError, UnicodeError):  # a directory, an unreadable or undecodable file: no key
        values = dict(environ)
    value = values.get(KEY_ENV, "").strip()
    return value if _KEY.fullmatch(value) else None
