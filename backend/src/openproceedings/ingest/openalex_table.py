"""The OpenAlex listing table (spec 01 §Sources 6; decision-049, milestone C): which OpenAlex sources hold each
DOI-less AAAI year's works, for the listing route of `sources/openalex.py`.

The listing route is for the dblp AAAI records of 1980-2008 (`record.DBLP_YEARS["AAAI"]`): they carry no DOI, so
the DOI route cannot reach them, and OpenAlex is asked instead for every work of the year under the row's sources,
matched to a record by exact title key with exactly one candidate. OpenAlex files old AAAI proceedings under
per-era sources (several `S…` ids over the years, sometimes more than one in a year), so every row names its own
venue-year's source ids rather than one AAAI source. `works` is the number of works OpenAlex listed for the row on
the `verified` date: a crawl that finds a different count stops (the listing moved under us), never a best guess.

Data, not code: `openalex_sources.toml` beside this module, loaded and checked once at import; a malformed row is
an import error. Only AAAI, AIES and FAccT can be named (`record.OPENALEX_VENUES`), and only a year whose records
carry no DOI (a held `DBLP_YEARS` year), which today leaves AAAI 1980-2008.

`[[duplicate_choice]]` rows (TASK-231, owner ruling 2026-10-10) are the cited, hand-checked exceptions to the DOI
route's `doi_duplicate` refusal: when OpenAlex answers one DOI with several works whose texts differ, the row's `work`
is the one the fill attaches. A row names a bare DOI and a `W…` work id, why, when it was checked and where that is
recorded; the fill stops (`duplicate_choice_unmatched`) if the extract answers that DOI without the row's work among
two or more works, so a choice never outlives the duplicate it was made for.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from importlib.resources import files
from types import MappingProxyType
from typing import Any

from openproceedings.ingest import dblp_aaai_table
from openproceedings.ingest.record import DBLP_YEARS, OPENALEX_VENUES

_COLUMNS = {"venue", "year", "source_ids", "works", "verified", "source"}
_CHOICE_COLUMNS = {"doi", "work", "reason", "verified", "source"}
_SOURCE_ID = re.compile(r"S[0-9]{1,12}")
_WORK_ID = re.compile(r"W[0-9]{1,12}")
# a bare, lower-case DOI as `sources/openalex.bare_doi` leaves it (that module imports this one, so the shape is here)
_DOI = re.compile(r"10\.[0-9]{1,9}(?:\.[0-9]{1,9}){0,8}/\S{1,1000}")


@dataclass(frozen=True, slots=True)
class Listing:
    venue: str
    year: int
    source_ids: tuple[str, ...]  # OpenAlex `S…` ids whose works of `year` are the venue-year's
    works: int  # works OpenAlex listed for the row when verified
    verified: date
    source: str


@dataclass(frozen=True, slots=True)
class DuplicateChoice:
    doi: str  # bare, lower-case
    work: str  # the `W…` work attached for that DOI
    reason: str
    verified: date
    source: str


@dataclass(frozen=True, slots=True)
class Table:
    listings: Mapping[tuple[str, int], Listing]
    duplicate_choices: Mapping[str, DuplicateChoice] = field(default_factory=lambda: MappingProxyType({}))


def _listing(raw: Mapping[str, Any]) -> Listing:
    where = f"openalex_sources.toml listing {raw.get('venue')!r} {raw.get('year')!r}"
    if unknown := set(raw) - _COLUMNS:
        raise ValueError(f"{where}: unknown columns {sorted(unknown)}")
    if missing := _COLUMNS - set(raw):
        raise ValueError(f"{where}: missing columns {sorted(missing)}")
    if type(raw["verified"]) is not date or not isinstance(raw["source"], str) or not raw["source"]:
        raise ValueError(f"{where}: every row needs a verified date and a source")
    venue, year, ids, works = raw["venue"], raw["year"], raw["source_ids"], raw["works"]
    if venue not in OPENALEX_VENUES:
        raise ValueError(f"{where}: venue {venue!r} is not AAAI, AIES or FAccT (record.OPENALEX_VENUES)")
    if type(year) is not int:
        raise ValueError(f"{where}: year must be an integer")
    if year not in DBLP_YEARS.get(venue, range(0)) or year in dblp_aaai_table.TABLE.not_held:
        raise ValueError(f"{where}: the listing route takes only years whose records carry no DOI "
                         "(a held record.DBLP_YEARS year)")  # fmt: skip
    if (
        not isinstance(ids, list)
        or not ids
        or not all(isinstance(i, str) and _SOURCE_ID.fullmatch(i) for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError(
            f"{where}: source_ids must be distinct OpenAlex source ids (`S` and digits), at least one"
        )
    if type(works) is not int or works <= 0:
        raise ValueError(f"{where}: works must be a positive integer")
    return Listing(venue, year, tuple(ids), works, raw["verified"], raw["source"])


def _choice(raw: Mapping[str, Any]) -> DuplicateChoice:
    where = f"openalex_sources.toml duplicate_choice {raw.get('doi')!r}"
    if unknown := set(raw) - _CHOICE_COLUMNS:
        raise ValueError(f"{where}: unknown columns {sorted(unknown)}")
    if missing := _CHOICE_COLUMNS - set(raw):
        raise ValueError(f"{where}: missing columns {sorted(missing)}")
    if type(raw["verified"]) is not date or not isinstance(raw["source"], str) or not raw["source"]:
        raise ValueError(f"{where}: every row needs a verified date and a source")
    doi, work, reason = raw["doi"], raw["work"], raw["reason"]
    if not isinstance(doi, str) or doi != doi.lower() or not _DOI.fullmatch(doi) or not doi.isascii():
        raise ValueError(f"{where}: doi must be a bare, lower-case DOI (10.…/…)")
    if not isinstance(work, str) or not _WORK_ID.fullmatch(work):
        raise ValueError(f"{where}: work must be an OpenAlex work id (`W` and digits)")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"{where}: every choice needs a reason")
    return DuplicateChoice(doi, work, reason, raw["verified"], raw["source"])


def load(text: str) -> Table:
    raw = tomllib.loads(text)
    listings: dict[tuple[str, int], Listing] = {}
    for row in (_listing(r) for r in raw.get("listing", [])):
        if (row.venue, row.year) in listings:
            raise ValueError(f"openalex_sources.toml: listing {row.venue} {row.year} is listed twice")
        listings[(row.venue, row.year)] = row
    choices: dict[str, DuplicateChoice] = {}
    for choice in (_choice(r) for r in raw.get("duplicate_choice", [])):
        if choice.doi in choices:
            raise ValueError(f"openalex_sources.toml: duplicate_choice {choice.doi} is chosen twice")
        choices[choice.doi] = choice
    return Table(
        MappingProxyType(dict(sorted(listings.items()))), MappingProxyType(dict(sorted(choices.items())))
    )


TABLE: Table = load(
    files("openproceedings.ingest").joinpath("openalex_sources.toml").read_text(encoding="utf-8")
)
