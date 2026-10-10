"""Crossref REST parsing for FAccT and AIES (spec 01 §Sources, Crossref row; decision-049).

The route: a table row's proceedings record (`/works/<doi>`), then `/works` paged by cursor, filtered by
`prefix:10.1145` and the row's publication window, keeping the DOIs that extend `10.1145/<toc>.`. Requests go one at
a time (`MIN_INTERVAL`), because parallel requests get HTTP 429. `CROSSREF_MAILTO` is optional: with it the
User-Agent names a contact (Crossref's polite pool), without it the plain repo User-Agent goes (the public pool);
the address is in the User-Agent only, never a URL, a cache entry, a claim, a log line or an exception. The cursor
is opaque and never a claim's url (Task 7 fixes the cursor rule). The fields: no abstracts, which `select` leaves out.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from openproceedings.ingest.acm_table import Proceedings
from openproceedings.ingest.record import Source
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.sources.http import USER_AGENT
from openproceedings.ingest.sources.openreview_client import read_dotenv

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
_EMAIL = re.compile(r"[^@\s<>()\"';,]+@[^@\s<>()\"';,]+\.[A-Za-z]{2,}")
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


@dataclass(frozen=True, slots=True)
class WorksPage:
    works: tuple[Work, ...]
    next_cursor: str | None
    total: int


def clean_title(raw: str) -> str:
    """Crossref's title text: JATS/HTML/MathML tags dropped (their text kept), entities unescaped, whitespace
    collapsed. `title_text` then replaces control characters as for every source."""
    return " ".join(html.unescape(_TAG.sub("", raw)).split())


def title_of(item: Mapping[str, Any]) -> str | None:
    titles = [clean_title(t) for t in item.get("title") or [] if isinstance(t, str)]
    title = next((t for t in titles if t), None)
    if title is None:
        return None
    sub = next(
        (s for s in (clean_title(x) for x in item.get("subtitle") or [] if isinstance(x, str)) if s), None
    )
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
        works.append(Work(
            doi=item["DOI"].strip().lower(), type=str(item.get("type", "")), title=title_of(item),
            authors=tuple(n for a in item.get("author") or [] if isinstance(a, dict) and (n := author_name(a))),
            page=page if isinstance(page, str) else None))  # fmt: skip
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
    values = {**(read_dotenv(dotenv) if dotenv else {}), **environ}
    value = values.get(MAILTO_ENV, "").strip()
    if not value:
        return None
    if not _EMAIL.fullmatch(value):
        raise CrawlError(
            f"{MAILTO_ENV} is set but is not an e-mail address: fix or unset it", reason="bad_contact"
        )
    return value


def user_agent(mailto: str | None) -> str:
    return USER_AGENT if mailto is None else f"{USER_AGENT.removesuffix(')')}; mailto:{mailto})"
