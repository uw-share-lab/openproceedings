"""The AAAI library table (spec 01 §Sources, aaai_library row; decision-051, TASK-232): for each dblp AAAI record of
1980-2008, the old aaai.org paper page dblp links it to (its `ee`, `www.aaai.org/Library/{AAAI,IAAI}/<yyyy>/<id>.php`)
and the one Internet Archive capture of that page the abstract is read from.

Each row pins its capture three ways: the page URL, the capture's 14-digit timestamp and the archive's SHA-1 digest
of the captured bytes (base32, as the CDX index gives it), so `sources/aaai_library.py` fetches
`https://web.archive.org/web/<timestamp>id_/<url>` and refuses any other bytes (`digest_mismatch`). `length` is the
CDX record length, kept for the record. aaai.org itself is never fetched (decision-051: its robots.txt asks for a
43,200-second crawl delay; the archive's copies put no load on it).

Data, not code: `aaai_library.toml` beside this module, written by `scripts/aaai_library_census.py` and loaded and
checked once at import; a malformed row is an import error. The loader refuses a key that is not a `conf/aaai/` dblp
key, a key listed twice, and a URL that is not an `http(s)://www.aaai.org/Library/AAAI/…` or `…/Library/IAAI/…`
page (no port, query or fragment, no `..`): the fetcher is never pointed anywhere else.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from types import MappingProxyType
from typing import Any

ARCHIVE = "https://web.archive.org/web"
_HEADER = {"verified", "source", "pages"}
_COLUMNS = {"key", "url", "timestamp", "digest", "length"}
_KEY = re.compile(r"conf/aaai/([A-Za-z0-9_-]{1,128})")
_URL = re.compile(r"https?://www\.aaai\.org/Library/(?:AAAI|IAAI)/[A-Za-z0-9_-]+(?:[./][A-Za-z0-9_-]+){0,8}")
_TIMESTAMP = re.compile(r"[0-9]{14}")
DIGEST = re.compile(r"[A-Z2-7]{32}")  # SHA-1 (20 bytes) in base32, as the CDX index gives it


@dataclass(frozen=True, slots=True)
class Page:
    key: str  # the dblp key, `conf/aaai/<tail>`
    url: str  # the dblp `ee`: the aaai.org paper page
    timestamp: str  # the capture's 14-digit timestamp
    digest: str  # the archive's SHA-1 of the captured bytes, base32
    length: int  # the CDX record length (the compressed capture), for the record

    @property
    def native(self) -> str:
        """The record's native id, `dblp-<tail>` (`record.py`'s dblp form)."""
        return f"dblp-{self.key.removeprefix('conf/aaai/')}"

    @property
    def capture(self) -> str:
        """What is fetched: the exact capture, `id_` (the bytes as archived, no archive banner or rewriting)."""
        return f"{ARCHIVE}/{self.timestamp}id_/{self.url}"


@dataclass(frozen=True, slots=True)
class Table:
    verified: date
    source: str
    pages: Mapping[str, Page]  # by dblp key


def is_library_url(url: str) -> bool:
    """Is `url` an http(s)://www.aaai.org/Library/AAAI/ or /Library/IAAI/ page (no port, query, fragment or `..`)?"""
    return bool(_URL.fullmatch(url)) and ".." not in url


def _page(raw: Any) -> Page:
    if not isinstance(raw, dict):
        raise ValueError("aaai_library.toml: a page row is not a table")
    where = f"aaai_library.toml page {raw.get('key')!r}"
    if set(raw) != _COLUMNS:
        raise ValueError(f"{where}: columns {sorted(_COLUMNS)}, got {sorted(raw)}")
    key, url, timestamp, digest, length = (raw[c] for c in ("key", "url", "timestamp", "digest", "length"))
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError(f"{where}: key must be a conf/aaai/ dblp key")
    if not isinstance(url, str) or not is_library_url(url):
        raise ValueError(
            f"{where}: url must be an http(s)://www.aaai.org/Library/AAAI/ or /Library/IAAI/ page"
        )
    if not isinstance(timestamp, str) or not _TIMESTAMP.fullmatch(timestamp):
        raise ValueError(f"{where}: timestamp must be a 14-digit string")
    if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
        raise ValueError(f"{where}: digest must be a base32 SHA-1 (32 of A-Z2-7)")
    if type(length) is not int or length <= 0:
        raise ValueError(f"{where}: length must be a positive integer")
    return Page(key, url, timestamp, digest, length)


def load(text: str) -> Table:
    raw = tomllib.loads(text)
    if set(raw) != _HEADER:
        raise ValueError(f"aaai_library.toml: top-level keys {sorted(_HEADER)}, got {sorted(raw)}")
    verified, source, rows = raw["verified"], raw["source"], raw["pages"]
    if not isinstance(verified, date):
        raise ValueError("aaai_library.toml: verified must be a date")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("aaai_library.toml: source must name where the census is recorded")
    if not isinstance(rows, list):
        raise ValueError("aaai_library.toml: pages must be a list")
    pages: dict[str, Page] = {}
    for row in rows:
        page = _page(row)
        if page.key in pages:
            raise ValueError(f"aaai_library.toml: {page.key} is listed twice")
        pages[page.key] = page
    return Table(verified, source, MappingProxyType(dict(sorted(pages.items()))))


TABLE = load(files("openproceedings.ingest").joinpath("aaai_library.toml").read_text(encoding="utf-8"))
