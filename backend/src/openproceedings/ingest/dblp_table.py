"""The dblp table (spec 01 §Sources, dblp row; decision-047; TASK-205): which dblp snapshot release the ICML
1988–2012 records come from, and which of its `conf/icml/` proceedings are each year's main conference.

The table is data, `dblp_icml.toml` beside this module, loaded and checked once at import (a malformed row is
an import error, never a best guess):

- `[release]` and `[dtd]` pin the release file and the DTD that defines its entities, each by DOI, URL, size
  and sha256, so the same table always reads the same bytes (guarantee 4).
- `[[year]]` names a year's main-conference proceedings key(s) (`conf/icml/1990`), the number of papers the
  release lists under them when verified, and the proceedings' title as dblp gives it.
- `[[excluded]]` names every other `conf/icml/` proceedings key of those years (workshops, companion volumes)
  with the reason it is not the main conference. The miner refuses an extract holding a `conf/icml/`
  proceedings key of 1988–2012 that is in neither list: a new key is decided by a person, never by its title.
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

from openproceedings.ingest.sources.http import PinnedFile
from openproceedings.vocab import venue_name

FIRST_YEAR, LAST_YEAR = 1988, 2012  # ICML's first conference under its name; PMLR v28 (2013) takes over
_KEY = re.compile(r"conf/icml/[A-Za-z0-9_-]+")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DOI = re.compile(r"10\.4230/dblp\.xml(?:\.dtd)?\.[0-9]{4}-[0-9]{2}-[0-9]{2}")


@dataclass(frozen=True, slots=True)
class Pinned:
    """A release or DTD: its DOI and the pinned file."""

    doi: str
    file: PinnedFile
    license: str
    verified: date

    @property
    def doi_url(self) -> str:
        return f"https://doi.org/{self.doi}"

    @property
    def filename(self) -> str:
        return self.file.url.rsplit("/", 1)[-1]


@dataclass(frozen=True, slots=True)
class IcmlYear:
    year: int
    proceedings: tuple[str, ...]  # the main conference's dblp proceedings keys
    papers: int  # inproceedings crossref'ing them in the pinned release, when verified
    title: str  # the proceedings' title as dblp gives it
    verified: date
    source: str


@dataclass(frozen=True, slots=True)
class Excluded:
    key: str
    year: int
    reason: str


@dataclass(frozen=True, slots=True)
class Table:
    release: Pinned
    dtd: Pinned
    years: Mapping[int, IcmlYear]
    excluded: Mapping[str, Excluded]

    def main_key(self, crossref: str) -> IcmlYear | None:
        """The year whose main conference `crossref` is, or None."""
        return next((y for y in self.years.values() if crossref in y.proceedings), None)


def _check(raw: Mapping[str, Any], columns: set[str], where: str) -> None:
    if unknown := set(raw) - columns:
        raise ValueError(f"dblp_icml.toml {where}: unknown columns {sorted(unknown)}")
    if missing := columns - set(raw):
        raise ValueError(f"dblp_icml.toml {where}: missing columns {sorted(missing)}")


def _pinned(raw: Mapping[str, Any], where: str) -> Pinned:
    _check(raw, {"doi", "url", "size", "sha256", "license", "verified"}, where)
    if not _DOI.fullmatch(str(raw["doi"])):
        raise ValueError(f"dblp_icml.toml {where}: {raw['doi']!r} is not a dblp release DOI")
    if not str(raw["url"]).startswith("https://drops.dagstuhl.de/storage/artifacts/dblp/"):
        raise ValueError(f"dblp_icml.toml {where}: the file must be on drops.dagstuhl.de (dblp.org forbids crawling)")
    if type(raw["size"]) is not int or raw["size"] <= 0 or not _SHA256.fullmatch(str(raw["sha256"])):
        raise ValueError(f"dblp_icml.toml {where}: size must be a positive integer and sha256 64 hex digits")
    if not isinstance(raw["verified"], date):
        raise ValueError(f"dblp_icml.toml {where}: verified must be a date")
    return Pinned(str(raw["doi"]), PinnedFile(str(raw["url"]), raw["size"], str(raw["sha256"])),
                  str(raw["license"]), raw["verified"])  # fmt: skip


def _year(raw: Mapping[str, Any]) -> IcmlYear:
    where = f"year {raw.get('year')!r}"
    _check(raw, {"year", "proceedings", "papers", "title", "verified", "source"}, where)
    year, keys, papers = raw["year"], raw["proceedings"], raw["papers"]
    if type(year) is not int or not FIRST_YEAR <= year <= LAST_YEAR:
        raise ValueError(f"dblp_icml.toml {where}: a year from {FIRST_YEAR} to {LAST_YEAR}")
    venue_name("ICML", year)
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and _KEY.fullmatch(k) for k in keys):
        raise ValueError(f"dblp_icml.toml {where}: proceedings must be conf/icml/<key> strings")
    if type(papers) is not int or papers <= 0:
        raise ValueError(f"dblp_icml.toml {where}: papers must be a positive integer")
    if not isinstance(raw["verified"], date) or not str(raw["source"]) or not str(raw["title"]):
        raise ValueError(f"dblp_icml.toml {where}: every row needs a title, a verified date and a source")
    return IcmlYear(year, tuple(keys), papers, str(raw["title"]), raw["verified"], str(raw["source"]))


def load(text: str) -> Table:
    raw = tomllib.loads(text)
    if unknown := set(raw) - {"release", "dtd", "year", "excluded"}:
        raise ValueError(f"dblp_icml.toml: unknown tables {sorted(unknown)}")
    years: dict[int, IcmlYear] = {}
    seen: set[str] = set()
    for row in (_year(r) for r in raw.get("year", [])):
        if row.year in years:
            raise ValueError(f"dblp_icml.toml: year {row.year} is listed twice")
        if dup := seen & set(row.proceedings):
            raise ValueError(f"dblp_icml.toml: {sorted(dup)} listed under two years")
        seen.update(row.proceedings)
        years[row.year] = row
    excluded: dict[str, Excluded] = {}
    for r in raw.get("excluded", []):
        _check(r, {"key", "year", "reason"}, f"excluded {r.get('key')!r}")
        if not _KEY.fullmatch(str(r["key"])) or type(r["year"]) is not int or not str(r["reason"]):
            raise ValueError(f"dblp_icml.toml excluded {r['key']!r}: a conf/icml key, a year and a reason")
        if r["key"] in seen or r["key"] in excluded:
            raise ValueError(f"dblp_icml.toml: {r['key']} is both excluded and listed, or listed twice")
        excluded[r["key"]] = Excluded(str(r["key"]), r["year"], str(r["reason"]))
    return Table(
        _pinned(raw["release"], "[release]"), _pinned(raw["dtd"], "[dtd]"),
        MappingProxyType(dict(sorted(years.items()))), MappingProxyType(dict(sorted(excluded.items()))),
    )  # fmt: skip


TABLE: Table = load(files("openproceedings.ingest").joinpath("dblp_icml.toml").read_text(encoding="utf-8"))
