"""The dblp AAAI table (spec 01 §Sources, dblp row; decision-049, milestone B): which `conf/aaai/` proceedings of
the pinned dblp release are AAAI 1980-2008's main conferences and workshops, and which years AAAI was not held.

The table is data, `dblp_aaai.toml` beside this module, loaded and checked once at import (a malformed row is an
import error, never a best guess). Its release and DTD pin is `dblp_icml.toml`'s (`dblp_table.TABLE`): one file,
read once for both venues, so two pins can never drift apart.

- `not_held` lists the years 1980-2009 with no AAAI conference; a `conf/aaai/` proceedings key dblp dates to one
  stops the ingest.
- `[[year]]` is one AAAI year: its main conference's proceedings key(s), the number of inproceedings the release
  lists under them when verified, and the proceedings' title as dblp gives it.
- `[[workshop]]` is a `conf/aaai/` workshop proceedings key of those years: its papers are track `workshop`.
- `[[excluded]]` is any other `conf/aaai/` proceedings key dated 1980-2009, with the reason it is not read.
- `[[not_paper]]` is an entry under a main or workshop key that is no paper (an invited talk, a panel): counted in
  its year's listing, never a record.
- `[[section]]` is one section of a year's official table of contents (aaai.org's contents page, TASK-226) as a
  page range: an entry under the year's main keys whose dblp start page is in it takes the section's track, not
  `main`. A year's ranges never overlap.
- `[[track]]` gives one main-key entry its track by key, where dblp's page field can't place it (a page typo).
  A `[[not_paper]]` row beats a `[[track]]` row (they never name one key), and a `[[track]]` row beats a range.
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

from openproceedings.ingest import dblp_table
from openproceedings.ingest.dblp_table import Pinned
from openproceedings.ingest.page_ranges import checked_range, overlaps
from openproceedings.ingest.page_ranges import (
    start_page as start_page,
)  # re-exported: the sources read pages here
from openproceedings.ingest.record import DBLP_YEARS
from openproceedings.vocab import venue_name

FIRST_YEAR, LAST_YEAR = DBLP_YEARS["AAAI"][0], DBLP_YEARS["AAAI"][-1]  # 1980, 2008: OJS from 2010
CHECKED = range(
    FIRST_YEAR, LAST_YEAR + 2
)  # 1980-2009: every conf/aaai/ proceedings key dated in it is classified
_KEY = re.compile(r"conf/aaai/[A-Za-z0-9_-]+")
NOT_PAPER_KINDS = frozenset({"invited talk", "panel", "front matter", "tutorial summary", "workshop summary"})
_TABLES = {"not_held", "year", "workshop", "excluded", "not_paper", "section", "track"}
# the tracks a section or track row may give: the official contents' sections other than the technical program
SECTION_TRACKS = frozenset({"student_abstract", "consortium", "demo", "iaai", "other"})


@dataclass(frozen=True, slots=True)
class AaaiYear:
    year: int
    proceedings: tuple[str, ...]  # the main conference's dblp proceedings keys
    papers: int  # inproceedings crossref'ing them in the pinned release, when verified
    title: str
    verified: date
    source: str


@dataclass(frozen=True, slots=True)
class Workshop:
    key: str
    year: int
    papers: int
    title: str
    verified: date
    source: str


@dataclass(frozen=True, slots=True)
class Excluded:
    key: str
    year: int
    reason: str


@dataclass(frozen=True, slots=True)
class NotPaper:
    """An entry under a main or workshop key that is no paper: counted in its year's listing, never a record."""

    key: str
    year: int
    kind: str
    reason: str


@dataclass(frozen=True, slots=True)
class Section:
    """One official contents section of a year's main proceedings, as the dblp start pages it spans."""

    year: int
    first: int
    last: int
    track: str
    label: str
    verified: date
    source: str

    def holds(self, page: int | None) -> bool:
        return page is not None and self.first <= page <= self.last


@dataclass(frozen=True, slots=True)
class TrackRow:
    """One main-key entry's track by key, where dblp's pages can't place it in a section."""

    key: str
    year: int
    track: str
    reason: str
    verified: date
    source: str


@dataclass(frozen=True, slots=True)
class Table:
    release: Pinned
    dtd: Pinned
    years: Mapping[int, AaaiYear]
    workshops: Mapping[str, Workshop]
    excluded: Mapping[str, Excluded]
    not_papers: Mapping[str, NotPaper]
    not_held: frozenset[int]
    sections: tuple[Section, ...] = ()
    tracks: Mapping[str, TrackRow] = MappingProxyType({})

    def main_key(self, crossref: str | None) -> AaaiYear | None:
        return next((y for y in self.years.values() if crossref in y.proceedings), None)

    def workshop(self, crossref: str | None) -> Workshop | None:
        return self.workshops.get(crossref or "")

    def main_track(self, key: str, year: int, pages: str | None) -> tuple[str, Section | TrackRow | None]:
        """A main-key entry's track and the row that gives it: its `[[track]]` row, else the `[[section]]` its
        dblp start page is in, else `main` (None)."""
        if (row := self.tracks.get(key)) is not None and row.year == year:
            return row.track, row
        page = start_page(pages)
        section = next((s for s in self.sections if s.year == year and s.holds(page)), None)
        return (section.track, section) if section is not None else ("main", None)

    def stated(self, year: int) -> int:
        """The inproceedings the table verified for `year`: its main conference's and its workshops'."""
        return self.years[year].papers + sum(w.papers for w in self.workshops.values() if w.year == year)


def _check(raw: Mapping[str, Any], columns: set[str], where: str) -> None:
    if unknown := set(raw) - columns:
        raise ValueError(f"dblp_aaai.toml {where}: unknown columns {sorted(unknown)}")
    if missing := columns - set(raw):
        raise ValueError(f"dblp_aaai.toml {where}: missing columns {sorted(missing)}")


def _scalars(raw: Mapping[str, Any], where: str) -> None:
    if type(raw["papers"]) is not int or raw["papers"] <= 0:
        raise ValueError(f"dblp_aaai.toml {where}: papers must be a positive integer")
    if not isinstance(raw["verified"], date) or not str(raw["source"]) or not str(raw["title"]):
        raise ValueError(f"dblp_aaai.toml {where}: every row needs a title, a verified date and a source")


def _year(raw: Mapping[str, Any], not_held: frozenset[int]) -> AaaiYear:
    where = f"year {raw.get('year')!r}"
    _check(raw, {"year", "proceedings", "papers", "title", "verified", "source"}, where)
    year, keys = raw["year"], raw["proceedings"]
    if type(year) is not int or not FIRST_YEAR <= year <= LAST_YEAR:
        raise ValueError(f"dblp_aaai.toml {where}: a year from {FIRST_YEAR} to {LAST_YEAR}")
    if year in not_held:
        raise ValueError(f"dblp_aaai.toml {where}: a year both held and not held")
    venue_name("AAAI", year)
    if (
        not isinstance(keys, list)
        or not keys
        or not all(isinstance(k, str) and _KEY.fullmatch(k) for k in keys)
    ):
        raise ValueError(f"dblp_aaai.toml {where}: proceedings must be conf/aaai/<key> strings")
    if len(set(keys)) != len(keys):
        raise ValueError(f"dblp_aaai.toml {where}: a proceedings key listed twice")
    _scalars(raw, where)
    return AaaiYear(year, tuple(keys), raw["papers"], str(raw["title"]), raw["verified"], str(raw["source"]))


def _key(raw: Mapping[str, Any], where: str) -> str:
    if not isinstance(raw["key"], str) or not _KEY.fullmatch(raw["key"]):
        raise ValueError(f"dblp_aaai.toml {where}: a conf/aaai/<key> string")
    return raw["key"]


def _provenance(raw: Mapping[str, Any], where: str) -> None:
    if raw["track"] not in SECTION_TRACKS:
        raise ValueError(f"dblp_aaai.toml {where}: track must be one of {sorted(SECTION_TRACKS)}")
    if type(raw["verified"]) is not date or not isinstance(raw["source"], str) or not raw["source"]:
        raise ValueError(f"dblp_aaai.toml {where}: a verified date and a source")


def _sections(rows: list[Mapping[str, Any]], years: Mapping[int, AaaiYear]) -> tuple[Section, ...]:
    out: list[Section] = []
    for r in rows:
        where = f"section {r.get('year')!r} {r.get('pages')!r}"
        _check(r, {"year", "pages", "track", "label", "verified", "source"}, where)
        if type(r["year"]) is not int or r["year"] not in years:
            raise ValueError(f"dblp_aaai.toml {where}: a year the table holds")
        first, last = checked_range(r["pages"], f"dblp_aaai.toml {where}")
        if not isinstance(r["label"], str) or not r["label"]:
            raise ValueError(f"dblp_aaai.toml {where}: a label")
        _provenance(r, where)
        row = Section(r["year"], first, last, r["track"], r["label"], r["verified"], r["source"])
        if clash := next((s for s in out if s.year == row.year and overlaps((s.first, s.last), (first, last))),
                         None):  # fmt: skip
            raise ValueError(
                f"dblp_aaai.toml {where}: overlaps {row.year}'s pages {[clash.first, clash.last]}"
            )
        out.append(row)
    return tuple(sorted(out, key=lambda s: (s.year, s.first)))


def load(text: str, pins: dblp_table.Table | None = None) -> Table:
    pins = pins or dblp_table.TABLE
    raw = tomllib.loads(text)
    if unknown := set(raw) - _TABLES:
        raise ValueError(f"dblp_aaai.toml: unknown tables {sorted(unknown)}")
    held = raw.get("not_held", [])
    if (
        not isinstance(held, list)
        or not all(type(y) is int and y in CHECKED for y in held)
        or len(set(held)) != len(held)
    ):
        raise ValueError(
            f"dblp_aaai.toml: not_held must be distinct years from {CHECKED[0]} to {CHECKED[-1]}"
        )
    not_held = frozenset(held)
    years: dict[int, AaaiYear] = {}
    seen: set[str] = set()
    for r in raw.get("year", []):
        row = _year(r, not_held)
        if row.year in years:
            raise ValueError(f"dblp_aaai.toml: year {row.year} is listed twice")
        if dup := seen & set(row.proceedings):
            raise ValueError(f"dblp_aaai.toml: {sorted(dup)} listed twice")
        seen.update(row.proceedings)
        years[row.year] = row
    workshops: dict[str, Workshop] = {}
    for r in raw.get("workshop", []):
        where = f"workshop {r.get('key')!r}"
        _check(r, {"key", "year", "papers", "title", "verified", "source"}, where)
        key = _key(r, where)
        if type(r["year"]) is not int or r["year"] not in years:
            raise ValueError(f"dblp_aaai.toml {where}: a year the table holds")
        _scalars(r, where)
        if key in seen or key in workshops:
            raise ValueError(f"dblp_aaai.toml: {key} listed twice")
        workshops[key] = Workshop(
            key, r["year"], r["papers"], str(r["title"]), r["verified"], str(r["source"])
        )
    excluded: dict[str, Excluded] = {}
    for r in raw.get("excluded", []):
        where = f"excluded {r.get('key')!r}"
        _check(r, {"key", "year", "reason"}, where)
        key = _key(r, where)
        if type(r["year"]) is not int or r["year"] not in CHECKED or not str(r["reason"]):
            raise ValueError(
                f"dblp_aaai.toml {where}: a year from {CHECKED[0]} to {CHECKED[-1]} and a reason"
            )
        if key in seen or key in workshops or key in excluded:
            raise ValueError(f"dblp_aaai.toml: {key} listed twice")
        excluded[key] = Excluded(key, r["year"], str(r["reason"]))
    not_papers: dict[str, NotPaper] = {}
    for r in raw.get("not_paper", []):
        where = f"not_paper {r.get('key')!r}"
        _check(r, {"key", "year", "kind", "reason"}, where)
        key = _key(r, where)
        if type(r["year"]) is not int or r["year"] not in years:
            raise ValueError(f"dblp_aaai.toml {where}: a year the table holds")
        if r["kind"] not in NOT_PAPER_KINDS:
            raise ValueError(f"dblp_aaai.toml {where}: kind must be one of {sorted(NOT_PAPER_KINDS)}")
        if not str(r["reason"]):
            raise ValueError(f"dblp_aaai.toml {where}: a reason")
        if key in seen or key in workshops or key in excluded or key in not_papers:
            raise ValueError(f"dblp_aaai.toml: {key} listed twice")
        not_papers[key] = NotPaper(key, r["year"], str(r["kind"]), str(r["reason"]))
    tracks: dict[str, TrackRow] = {}
    for r in raw.get("track", []):
        where = f"track {r.get('key')!r}"
        _check(r, {"key", "year", "track", "reason", "verified", "source"}, where)
        key = _key(r, where)
        if type(r["year"]) is not int or r["year"] not in years:
            raise ValueError(f"dblp_aaai.toml {where}: a year the table holds")
        if not isinstance(r["reason"], str) or not r["reason"]:
            raise ValueError(f"dblp_aaai.toml {where}: a reason")
        _provenance(r, where)
        if key in seen or key in workshops or key in excluded or key in not_papers or key in tracks:
            raise ValueError(f"dblp_aaai.toml: {key} listed twice")
        tracks[key] = TrackRow(key, r["year"], r["track"], r["reason"], r["verified"], r["source"])
    sections = _sections(raw.get("section", []), years)
    return Table(
        pins.release, pins.dtd,
        MappingProxyType(dict(sorted(years.items()))), MappingProxyType(dict(sorted(workshops.items()))),
        MappingProxyType(dict(sorted(excluded.items()))), MappingProxyType(dict(sorted(not_papers.items()))),
        not_held, sections, MappingProxyType(dict(sorted(tracks.items()))),
    )  # fmt: skip


TABLE: Table = load(files("openproceedings.ingest").joinpath("dblp_aaai.toml").read_text(encoding="utf-8"))
