"""The ojs.aaai.org table (spec 01 §Sources, OJS row; decision-049): which journals are harvested, how a volume
names its year, and, per journal, volume and OAI set (an OJS section), the track and the verified paper count.

Data, not code: `ojs_sections.toml` beside this module, loaded and checked once at import; a malformed row is an
import error, never a best guess. An OJS issue is not a track (AAAI 2026 has 48 issues, most "Technical Tracks N";
an issue may mix IAAI, EAAI and student abstracts), so the track comes from the record's section (its OAI
`setSpec`, one per record), and set names change by year (`ML-I`, `ML-I-23`; `AI24-n` and `AI26-n` mean different
tracks), so every row names its volume. A record whose volume or section has no row stops the crawl
(`sources/ojs.py`). `front_matter` rows (prefaces, indexes) are counted, never records.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from types import MappingProxyType
from typing import Any, Literal, get_args

from openproceedings.ingest.record import VENUE_ONLY_TRACKS
from openproceedings.vocab import TRACKS, VENUES, venue_name

Kind = Literal["papers", "front_matter"]
KINDS: tuple[str, ...] = get_args(Kind)
_JOURNAL_COLUMNS = {"code", "venue", "year_offset", "verified", "source"}
_SECTION_COLUMNS = {"journal", "volume", "set_spec", "kind", "track", "label", "papers", "verified", "source"}


@dataclass(frozen=True, slots=True)
class Journal:
    code: str  # the OJS path, `https://ojs.aaai.org/index.php/<code>/oai`
    venue: str
    year_offset: int  # year = volume + year_offset
    verified: date
    source: str


@dataclass(frozen=True, slots=True)
class Section:
    journal: str
    volume: int
    set_spec: str  # the OAI setSpec, e.g. `AAAI:AISI`
    kind: Kind
    track: str | None  # None only for front matter
    label: str  # the section's title on ojs.aaai.org, kept in the track claim's evidence
    papers: int  # records in this section of this volume when verified
    verified: date
    source: str


@dataclass(frozen=True, slots=True)
class Table:
    journals: Mapping[str, Journal]
    sections: Mapping[tuple[str, int, str], Section]

    def year(self, journal: str, volume: int) -> int:
        return volume + self.journals[journal].year_offset

    def volumes(self, journal: str) -> tuple[int, ...]:
        return tuple(sorted({v for (j, v, _s) in self.sections if j == journal}))

    def expected(self, journal: str, volume: int) -> int:
        return sum(s.papers for (j, v, _s), s in self.sections.items() if (j, v) == (journal, volume)
                   and s.kind == "papers")  # fmt: skip


def _check(raw: Mapping[str, Any], columns: set[str], required: set[str], where: str) -> None:
    if unknown := set(raw) - columns:
        raise ValueError(f"{where}: unknown columns {sorted(unknown)}")
    if missing := required - set(raw):
        raise ValueError(f"{where}: missing columns {sorted(missing)}")
    if not isinstance(raw["verified"], date) or not isinstance(raw["source"], str) or not raw["source"]:
        raise ValueError(f"{where}: every row needs a verified date and a source")


def _journal(raw: Mapping[str, Any]) -> Journal:
    where = f"ojs_sections.toml journal {raw.get('code')!r}"
    _check(raw, _JOURNAL_COLUMNS, _JOURNAL_COLUMNS, where)
    if raw["venue"] not in VENUES.values():
        raise ValueError(f"{where}: venue {raw['venue']!r} is not one of {sorted(VENUES.values())}")
    if type(raw["year_offset"]) is not int:
        raise ValueError(f"{where}: year_offset must be an integer")
    return Journal(raw["code"], raw["venue"], raw["year_offset"], raw["verified"], raw["source"])


def _section(raw: Mapping[str, Any], journals: Mapping[str, Journal]) -> Section:
    where = f"ojs_sections.toml section {raw.get('journal')!r} v{raw.get('volume')!r} {raw.get('set_spec')!r}"
    _check(raw, _SECTION_COLUMNS, _SECTION_COLUMNS - {"track"}, where)
    journal = journals.get(raw["journal"])
    if journal is None:
        raise ValueError(f"{where}: no journal row for {raw['journal']!r}")
    volume, papers, kind, track = raw["volume"], raw["papers"], raw["kind"], raw.get("track")
    if type(volume) is not int or volume <= 0:
        raise ValueError(f"{where}: volume must be a positive integer")
    if type(papers) is not int or papers <= 0:
        raise ValueError(f"{where}: papers must be a positive integer")
    if kind not in KINDS:
        raise ValueError(f"{where}: kind {kind!r} is not one of {KINDS}")
    if kind == "front_matter" and track is not None:
        raise ValueError(f"{where}: front matter has no track (it is counted, never a record)")
    if kind == "papers":
        if track not in TRACKS:
            raise ValueError(f"{where}: track {track!r} is not a spec 01 track")
        if (only := VENUE_ONLY_TRACKS.get(track)) is not None and only != journal.venue:
            raise ValueError(f"{where}: {track!r} is only an {only} track")
    venue_name(journal.venue, volume + journal.year_offset)  # a year the venue wasn't held is refused
    if not isinstance(raw["label"], str) or not raw["label"]:
        raise ValueError(f"{where}: label must be the section's title")
    return Section(raw["journal"], volume, raw["set_spec"], kind, track, raw["label"], papers, raw["verified"],
                   raw["source"])  # fmt: skip


def load(text: str) -> Table:
    data = tomllib.loads(text)
    journals: dict[str, Journal] = {}
    for j in (_journal(r) for r in data.get("journal", [])):
        if j.code in journals:
            raise ValueError(f"ojs_sections.toml: journal {j.code} is listed twice")
        journals[j.code] = j
    sections: dict[tuple[str, int, str], Section] = {}
    for s in (_section(r, journals) for r in data.get("section", [])):
        key = (s.journal, s.volume, s.set_spec)
        if key in sections:
            raise ValueError(f"ojs_sections.toml: section {key} is listed twice")
        sections[key] = s
    return Table(MappingProxyType(journals), MappingProxyType(dict(sorted(sections.items()))))


TABLE: Table = load(files("openproceedings.ingest").joinpath("ojs_sections.toml").read_text(encoding="utf-8"))
