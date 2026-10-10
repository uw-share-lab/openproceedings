"""The PMLR volume table (spec 01 §Sources, PMLR row; pmlr-proceedings skill; task-053).

The table is data: `pmlr_volumes.toml` beside this module, one row per volume with its venue, year, track,
role, verified paper count, page heading, index title, verification date and source. It is loaded and
checked once, at import; a malformed row is an import error, never a best guess.

`ICML_PMLR_VOLUMES` (volume → ICML year and track) is derived from the ICML rows that are ingested (role
`primary` or `confirm`). The RIS importer and `urls.native` read it, so they and the PMLR miner share one
table. A volume that holds more than one track gives `unknown`: ICML added position papers in 2024, and
they sit in the same volume as the main conference, so a PMLR URL alone can't say which track a paper is in.

`PMLR_NATIVE_VOLUMES` (volume → venue, year, track) covers every ingested volume, FAccT 2018 (v81) as well as
ICML: it is what a `pmlr-v<N>-<key>` native id names (`urls.native`, the record check). `ICML_PMLR_VOLUMES`
stays ICML-only, so a v81 `pmlr_url` in a RIS file is still out of scope. A non-ICML volume is primary, and
its `not_papers` (the prefaces and front matter the index lists) are counted, never records.

Competition and workshop volumes are rows too (role `out_of_scope`): classified, never `main`, never
ingested, and never in `ICML_PMLR_VOLUMES`. A volume missing from the table is out of scope.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from types import MappingProxyType
from typing import Any, Literal, get_args

from openproceedings.vocab import TRACKS, VENUES, venue_name

Role = Literal["primary", "confirm", "out_of_scope"]
ROLES: tuple[str, ...] = get_args(Role)
INGESTED: frozenset[str] = frozenset({"primary", "confirm"})
PMLR_VENUES: frozenset[str] = frozenset(
    {"ICML", "FAccT"}
)  # FAccT 2018 (FAT*) is v81 (decision-049, milestone B)
_COLUMNS = {
    "number", "venue", "year", "track", "role", "papers", "not_papers", "heading", "index_title", "verified",
    "source",
}  # fmt: skip
_KEY = re.compile(r"[A-Za-z0-9_-]+")
_REQUIRED = {"number", "venue", "track", "role", "verified", "source"}
_NEVER_MAIN = {"competition", "workshop"}


@dataclass(frozen=True, slots=True)
class Volume:
    """One row of the table."""

    number: int
    venue: str
    year: int | None
    track: str
    role: Role
    papers: int | None
    heading: str | None  # the volume page's heading after `Volume N: ` starts with this
    index_title: str | None
    verified: date
    source: str
    not_papers: tuple[str, ...] = ()  # index entries that are no paper (a preface): counted, never records

    @property
    def ingested(self) -> bool:
        return self.role in INGESTED

    @property
    def index_url(self) -> str:
        return f"https://proceedings.mlr.press/v{self.number}/"


def _row(raw: Mapping[str, Any]) -> Volume:
    where = f"pmlr_volumes.toml volume {raw.get('number')!r}"
    if unknown := set(raw) - _COLUMNS:
        raise ValueError(f"{where}: unknown columns {sorted(unknown)}")
    if missing := _REQUIRED - set(raw):
        raise ValueError(f"{where}: missing columns {sorted(missing)}")
    number, year, papers = raw["number"], raw.get("year"), raw.get("papers")
    if type(number) is not int or number <= 0:
        raise ValueError(f"{where}: number must be a positive integer")
    if raw["venue"] not in VENUES.values():
        raise ValueError(f"{where}: venue {raw['venue']!r} is not one of {sorted(VENUES.values())}")
    if raw["track"] not in TRACKS:
        raise ValueError(f"{where}: track {raw['track']!r} is not a spec 01 track")
    if raw["role"] not in ROLES:
        raise ValueError(f"{where}: role {raw['role']!r} is not one of {ROLES}")
    if year is not None:
        if type(year) is not int:
            raise ValueError(f"{where}: year must be an integer")
        venue_name(raw["venue"], year)  # a year the venue wasn't held under its name is refused
    if papers is not None and (type(papers) is not int or papers <= 0):
        raise ValueError(f"{where}: papers must be a positive integer")
    not_papers = raw.get("not_papers", [])
    if (
        not isinstance(not_papers, list)
        or not all(isinstance(k, str) and _KEY.fullmatch(k) for k in not_papers)
        or len(set(not_papers)) != len(not_papers)
    ):
        raise ValueError(f"{where}: not_papers must be a list of distinct PMLR keys")
    if not isinstance(raw["verified"], date) or not isinstance(raw["source"], str) or not raw["source"]:
        raise ValueError(f"{where}: every row needs a verified date and a source")
    volume = Volume(
        number=number, venue=raw["venue"], year=year, track=raw["track"], role=raw["role"], papers=papers,
        not_papers=tuple(not_papers), heading=raw.get("heading"), index_title=raw.get("index_title"), verified=raw["verified"],
        source=raw["source"],
    )  # fmt: skip
    if volume.track in _NEVER_MAIN and volume.ingested:
        raise ValueError(f"{where}: a {volume.track} volume is never ingested (role out_of_scope)")
    if volume.ingested and (volume.year is None or volume.papers is None or not volume.heading):
        raise ValueError(f"{where}: an ingested volume needs its year, paper count and heading")
    if volume.ingested and volume.venue not in PMLR_VENUES:
        raise ValueError(f"{where}: only ICML and FAccT volumes are ingested from PMLR (spec 01 §Sources)")
    if volume.ingested and volume.venue != "ICML" and volume.role != "primary":
        raise ValueError(f"{where}: a non-ICML volume is primary (OpenReview holds none of it)")
    if volume.not_papers and not volume.ingested:
        raise ValueError(f"{where}: only an ingested volume names not_papers")
    if papers is not None and len(volume.not_papers) >= papers:
        raise ValueError(f"{where}: fewer not_papers than papers")
    return volume


def load(text: str) -> Mapping[int, Volume]:
    """The table from TOML text, checked: known columns and values, unique volume numbers, at most one
    ingested volume per venue-year."""
    rows = [_row(r) for r in tomllib.loads(text).get("volume", [])]
    table: dict[int, Volume] = {}
    years: set[tuple[str, int | None]] = set()
    for v in rows:
        if v.number in table:
            raise ValueError(f"pmlr_volumes.toml: volume {v.number} is listed twice")
        table[v.number] = v
        if v.ingested:
            if (v.venue, v.year) in years:
                raise ValueError(f"pmlr_volumes.toml: two ingested volumes for {v.venue} {v.year}")
            years.add((v.venue, v.year))
    return MappingProxyType(dict(sorted(table.items())))


VOLUMES: Mapping[int, Volume] = load(
    files("openproceedings.ingest").joinpath("pmlr_volumes.toml").read_text(encoding="utf-8")
)
ICML_PMLR_VOLUMES: Mapping[int, tuple[int, str]] = MappingProxyType(
    {
        n: (v.year, v.track)
        for n, v in VOLUMES.items()
        if v.venue == "ICML" and v.ingested and v.year is not None
    }
)


# every ingested volume's (venue, year, track): what a `pmlr-v<N>-<key>` native id names (urls.native, record);
# ICML_PMLR_VOLUMES above stays ICML-only (the RIS importer and scholar_compare's ICML rule read it)
PMLR_NATIVE_VOLUMES: Mapping[int, tuple[str, int, str]] = MappingProxyType(
    {n: (v.venue, v.year, v.track) for n, v in VOLUMES.items() if v.ingested and v.year is not None}
)


def ingested_volume(venue: str, year: int) -> Volume | None:
    """The ingested volume of a venue's conference year, or None if the table has none (not yet verified)."""
    return next((v for v in VOLUMES.values() if v.venue == venue and v.ingested and v.year == year), None)


def icml_volume(year: int) -> Volume | None:
    """The ingested ICML volume for a conference year, or None if the table has none (not yet verified)."""
    return ingested_volume("ICML", year)
