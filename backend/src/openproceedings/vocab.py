"""Controlled vocabularies shared by ingestion and the query language (spec 01 §Fields, §Track taxonomy).

Filter values in a query are checked against these; ingestion never writes a value outside them.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, get_args

# The types are the single source; the value tuples derive from them, so they can't drift apart.
Venue = Literal["NeurIPS", "ICLR", "ICML"]
Track = Literal[
    "main",
    "datasets_benchmarks",
    "position",
    "workshop",
    "competition",
    "tiny_papers",
    "blogpost",
    "other",
    "unknown",
]
Status = Literal["accepted", "rejected", "withdrawn", "desk_rejected", "unknown"]

# canonical spelling, keyed by the lowercase form a query may use (`venue:` is case-insensitive)
VENUES: dict[str, str] = {v.lower(): v for v in get_args(Venue)}
TRACKS: tuple[str, ...] = get_args(Track)
STATUSES: tuple[str, ...] = get_args(Status)
# the searched fields (guarantee 2): every module that names them imports this one tuple
TEXT_FIELDS: tuple[Literal["title", "abstract"], ...] = ("title", "abstract")
QUERY_FILTER_FIELDS = (  # every filter field a query may name, incl. Scholar's `source:` (cf. ast.FILTER_FIELDS)
    "venue",
    "year",
    "track",
    "status",
    "source",
)

# Snapshot sources that hold an earlier search's output, not a database (spec 01, the M2 bootstrap): the RIS
# import of a Publish or Perish Scholar search. An index built only from these is a bootstrap corpus, whose
# counts are not PRISMA identification numbers (`op search`'s note and a search record's
# `identification_citable` both use `bootstrap_only`).
BOOTSTRAP_SOURCES: frozenset[str] = frozenset({"ris"})


def bootstrap_only(sources: Iterable[str]) -> bool:
    """True when a snapshot names sources and every one is a bootstrap source. No sources named is not
    evidence of a bootstrap corpus (the caller reports a missing snapshot on its own)."""
    named = set(sources)
    return bool(named) and named <= BOOTSTRAP_SOURCES


# The venue string, RIS `T2` and BibTeX `booktitle` (spec 04 §Exports, task-004, which cites the sources):
# the conference's full name, then the acronym it went by that year, and the year. Each venue lists its
# (first year, acronym) eras in year order. A year before the first era has no name, and a record for it is
# refused when it is built (`PaperRecord`), so an export never meets one. NeurIPS was NIPS until 2017
# (proceedings.neurips.cc labels 2018 on "NeurIPS"; the board renamed it on 2018-11-16, before that
# December's meeting). ICLR began in 2013 (iclr.cc). ICML is held annually as a conference from 1988, its 5th
# meeting (icml.cc calls 2026 the 43rd). It is the conference's name, not a proceedings title ("Advances in
# Neural Information Processing Systems 36", "Proceedings of the 40th International Conference on Machine
# Learning"), because an export also holds workshop, rejected and ICLR papers that no proceedings contain.
type ConferenceTable = dict[str, tuple[str, tuple[tuple[int, str], ...]]]
CONFERENCES: ConferenceTable = {
    "NeurIPS": ("Conference on Neural Information Processing Systems", ((1987, "NIPS"), (2018, "NeurIPS"))),
    "ICLR": ("International Conference on Learning Representations", ((2013, "ICLR"),)),
    "ICML": ("International Conference on Machine Learning", ((1988, "ICML"),)),
}


def check_conferences(table: ConferenceTable) -> None:
    """Every venue has eras, in strictly increasing year order (`venue_name` takes the last one begun), and
    the table names exactly the venues of `Venue`, in its order (so a venue added there can't reach an export
    without a name)."""
    for venue, (_name, eras) in table.items():
        if not eras:
            raise ValueError(f"{venue} has no eras")
        years = [first for first, _acronym in eras]
        if years != sorted(set(years)):
            raise ValueError(f"{venue} eras are not in year order: {years}")
    if tuple(table) != get_args(Venue):
        raise ValueError(f"the conference table must name exactly {get_args(Venue)}, not {tuple(table)}")


check_conferences(CONFERENCES)


def venue_name(venue: str, year: int) -> str:
    """`Conference on Neural Information Processing Systems (NIPS 2017)`: one string per venue and year,
    whatever a paper's track or status, so every copy of a venue-year reads the same in a reference manager.
    Raises ValueError for a venue without a table, or a year before the venue was held under its name."""
    if venue not in CONFERENCES:
        raise ValueError(f"no conference table for venue {venue!r}")
    name, eras = CONFERENCES[venue]
    acronyms = [acronym for first, acronym in eras if first <= year]
    if not acronyms:
        raise ValueError(f"no conference name for {venue} {year}: it was not held under that name then")
    return f"{name} ({acronyms[-1]} {year})"
