"""The ACM proceedings table (spec 01 §Sources, Crossref row; decision-049): which FAccT and AIES proceedings are
read from Crossref, the DOI that names each, the publication window `/works` is asked for, and how many DOIs
extend the proceedings DOI there.

Data, not code: `acm_proceedings.toml` beside this module, loaded and checked once at import; a malformed row is an
import error, never a best guess. The window is the proceedings' own dates, widened to take in every DOI that
extends the proceedings DOI. `dois` counts every such DOI in the window, not-paper rows included: a `[[not_paper]]`
DOI (a tutorial, a keynote, front matter) is counted, never a record, so a row's expected record count is `dois`
minus its not-paper rows.

Crossref has no section data, so every record is `main` unless a `[[section]]` row places it: a page range of one
proceedings (AIES 2018-2023's student abstract blocks, TASK-224) whose works, by their Crossref start page, take
the row's track. A not-paper row beats a section; one proceedings' ranges never overlap.
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

from openproceedings.ingest.page_ranges import checked_range, overlaps
from openproceedings.ingest.page_ranges import (
    start_page as start_page,
)  # re-exported: the sources read pages here
from openproceedings.vocab import venue_name

VENUES: frozenset[str] = frozenset({"AIES", "FAccT"})
# the years a `doi-` id may name: AIES before OJS (Vol. 7, 2024); FAccT after PMLR v81 (2018)
DOI_YEARS: Mapping[str, range] = MappingProxyType({"AIES": range(2018, 2024), "FAccT": range(2019, 10000)})
_TOC = re.compile(r"10\.1145/[0-9]+")
_PAPER = re.compile(r"10\.1145/([0-9]+)\.([0-9]+)")
NOT_PAPER_KINDS = frozenset({"tutorial", "craft session", "keynote", "panel", "front matter"})
_PROCEEDINGS = {"venue", "year", "doi", "title", "window_from", "window_until", "dois", "verified", "source"}
_NOT_PAPER = {"doi", "kind", "reason"}
_SECTION = {"venue", "year", "pages", "track", "label", "verified", "source"}
# the tracks a section row may give (never `main`, nor `iaai`/`eaai`, which are AAAI's alone)
SECTION_TRACKS = frozenset({"student_abstract", "consortium", "demo", "other"})


def paper_doi(doi: str) -> tuple[str, str] | None:
    """(toc, n) of an ACM paper DOI `10.1145/<toc>.<n>` (digits only, compared lower-case), else None. Any
    surrounding whitespace, a trailing newline included, makes it no DOI."""
    if doi != doi.strip():
        return None
    m = _PAPER.fullmatch(doi.lower())
    return (m.group(1), m.group(2)) if m else None


@dataclass(frozen=True, slots=True)
class Proceedings:
    venue: str
    year: int
    doi: str  # `10.1145/<toc>`
    title: str
    window_from: date
    window_until: date
    dois: int  # every DOI extending `doi` in the window, not-paper rows included
    verified: date
    source: str

    @property
    def toc(self) -> str:
        return self.doi.removeprefix("10.1145/")

    def paper(self, doi: str) -> bool:
        """Whether `doi` extends this proceedings' DOI (`10.1145/<toc>.…`)."""
        return doi.strip().lower().startswith(self.doi + ".")


@dataclass(frozen=True, slots=True)
class NotPaper:
    doi: str
    venue: str
    year: int
    kind: str
    reason: str


@dataclass(frozen=True, slots=True)
class Section:
    """A page range of one proceedings whose works take `track` (an inferred section: its source says how)."""

    venue: str
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
class Table:
    proceedings: Mapping[tuple[str, int], Proceedings]
    not_papers: Mapping[str, NotPaper]
    sections: tuple[Section, ...] = ()

    def section(self, venue: str, year: int, page: str | None) -> Section | None:
        """The section row a work of `venue` `year` with Crossref page `page` falls in, else None (`main`)."""
        start = start_page(page)
        return next((s for s in self.sections if (s.venue, s.year) == (venue, year) and s.holds(start)), None)

    def by_toc(self, toc: str) -> Proceedings | None:
        return next((p for p in self.proceedings.values() if p.toc == toc), None)

    def expected(self, venue: str, year: int) -> int:
        """The records of a venue-year: its DOIs less the not-paper ones."""
        row = self.proceedings[(venue, year)]
        return row.dois - sum(1 for n in self.not_papers.values() if (n.venue, n.year) == (venue, year))


def _check(raw: Mapping[str, Any], columns: set[str], where: str) -> None:
    if unknown := set(raw) - columns:
        raise ValueError(f"{where}: unknown columns {sorted(unknown)}")
    if missing := columns - set(raw):
        raise ValueError(f"{where}: missing columns {sorted(missing)}")


def _proceedings(raw: Mapping[str, Any]) -> Proceedings:
    where = f"acm_proceedings.toml proceedings {raw.get('venue')!r} {raw.get('year')!r}"
    _check(raw, _PROCEEDINGS, where)
    if raw["venue"] not in VENUES:
        raise ValueError(f"{where}: venue must be FAccT or AIES")
    year = raw["year"]
    if type(year) is not int or year not in DOI_YEARS[raw["venue"]]:
        raise ValueError(
            f"{where}: doi ids are AIES {DOI_YEARS['AIES']} and FAccT {DOI_YEARS['FAccT'].start} on"
        )
    venue_name(raw["venue"], year)
    if not isinstance(raw["doi"], str) or not _TOC.fullmatch(raw["doi"]):
        raise ValueError(f"{where}: the proceedings DOI must be 10.1145/<digits>")
    for column in ("title", "source"):
        if not isinstance(raw[column], str) or not raw[column]:
            raise ValueError(f"{where}: {column} must be a non-empty string")
    for column in ("window_from", "window_until", "verified"):
        if type(raw[column]) is not date:
            raise ValueError(f"{where}: {column} must be a date")
    if raw["window_from"] > raw["window_until"]:
        raise ValueError(f"{where}: the window runs backwards")
    if type(raw["dois"]) is not int or raw["dois"] <= 0:
        raise ValueError(f"{where}: dois must be a positive integer")
    return Proceedings(raw["venue"], year, raw["doi"], raw["title"], raw["window_from"], raw["window_until"],
                       raw["dois"], raw["verified"], raw["source"])  # fmt: skip


def load(text: str) -> Table:
    data = tomllib.loads(text)
    rows: dict[tuple[str, int], Proceedings] = {}
    dois: set[str] = set()
    for p in (_proceedings(r) for r in data.get("proceedings", [])):
        if (p.venue, p.year) in rows or p.doi in dois:
            raise ValueError(f"acm_proceedings.toml: proceedings {p.venue} {p.year} {p.doi} is listed twice")
        rows[(p.venue, p.year)] = p
        dois.add(p.doi)
    by_toc = {p.toc: p for p in rows.values()}
    not_papers: dict[str, NotPaper] = {}
    for raw in data.get("not_paper", []):
        where = f"acm_proceedings.toml not_paper {raw.get('doi')!r}"
        _check(raw, _NOT_PAPER, where)
        doi = raw["doi"]
        parts = paper_doi(doi) if isinstance(doi, str) else None
        if parts is None:
            raise ValueError(f"{where}: not an ACM paper DOI (10.1145/<digits>.<digits>)")
        if parts[0] not in by_toc:
            raise ValueError(f"{where}: no proceedings row for 10.1145/{parts[0]}")
        if raw["kind"] not in NOT_PAPER_KINDS:
            raise ValueError(f"{where}: kind must be one of {sorted(NOT_PAPER_KINDS)}")
        if not isinstance(raw["reason"], str) or not raw["reason"]:
            raise ValueError(f"{where}: reason must be a non-empty string")
        if doi in not_papers:
            raise ValueError(f"acm_proceedings.toml: not_paper {doi} is listed twice")
        row = by_toc[parts[0]]
        not_papers[doi] = NotPaper(doi, row.venue, row.year, raw["kind"], raw["reason"])
    for (venue, year), row in rows.items():
        if sum(1 for n in not_papers.values() if (n.venue, n.year) == (venue, year)) >= row.dois:
            raise ValueError(f"acm_proceedings.toml: {venue} {year} needs fewer not-paper rows than its dois")
    sections: list[Section] = []
    for raw in data.get("section", []):
        where = f"acm_proceedings.toml section {raw.get('venue')!r} {raw.get('year')!r} {raw.get('pages')!r}"
        _check(raw, _SECTION, where)
        if (raw["venue"], raw["year"]) not in rows:
            raise ValueError(f"{where}: no proceedings row for that venue and year")
        first, last = checked_range(raw["pages"], where)
        if raw["track"] not in SECTION_TRACKS:
            raise ValueError(f"{where}: track must be one of {sorted(SECTION_TRACKS)}")
        for column in ("label", "source"):
            if not isinstance(raw[column], str) or not raw[column]:
                raise ValueError(f"{where}: {column} must be a non-empty string")
        if type(raw["verified"]) is not date:
            raise ValueError(f"{where}: verified must be a date")
        sec = Section(raw["venue"], raw["year"], first, last, raw["track"], raw["label"], raw["verified"],
                      raw["source"])  # fmt: skip
        if any((s.venue, s.year) == (sec.venue, sec.year) and overlaps((s.first, s.last), (first, last))
               for s in sections):  # fmt: skip
            raise ValueError(f"{where}: overlaps another section of {sec.venue} {sec.year}")
        sections.append(sec)
    return Table(MappingProxyType(dict(sorted(rows.items()))), MappingProxyType(not_papers),
                 tuple(sorted(sections, key=lambda s: (s.venue, s.year, s.first))))  # fmt: skip


TABLE: Table = load(
    files("openproceedings.ingest").joinpath("acm_proceedings.toml").read_text(encoding="utf-8")
)
