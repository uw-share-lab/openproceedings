"""Controlled vocabularies shared by ingestion and the query language (spec 01 §Fields, §Track taxonomy).

Filter values in a query are checked against these; ingestion never writes a value outside them.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, get_args

# The types are the single source; the value tuples derive from them, so they can't drift apart.
Venue = Literal["NeurIPS", "ICLR", "ICML", "AAAI", "AIES", "FAccT", "IASEAI"]
Track = Literal[
    "main",
    "datasets_benchmarks",
    "position",
    "workshop",
    "competition",
    "tiny_papers",
    "blogpost",
    "student_abstract",  # AAAI and AIES student abstracts and posters (decision-049)
    "consortium",  # AAAI doctoral and undergraduate consortia
    "demo",  # AAAI demonstrations
    "iaai",  # Innovative Applications of AI, printed in the AAAI volumes (AAAI only)
    "eaai",  # Educational Advances in AI, printed in the AAAI volumes (AAAI only)
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


# What a crawl window's ends are (a search record's and `/coverage`'s `crawl_dates_kind`, spec 04; an open set,
# decision-009): fetch times (UTC); a bootstrap source's Publish or Perish query dates, either local wall time
# stored labelled UTC because the offset isn't recorded (so an end can be a day off), or converted to UTC with
# the offset `ingest/ris_offsets.toml` records (TASK-077, decision-025); or the corpus-wide window over a crawl
# and query dates, `mixed` while any of those query dates is local
CRAWL = "crawl"
SCHOLAR_QUERY_DATES = "scholar_query_dates"
SCHOLAR_QUERY_DATES_UTC = "scholar_query_dates_utc"
MIXED = "mixed"
MIXED_UTC = "mixed_utc"


def window_kind(sources: Iterable[str], utc: Iterable[str] = ()) -> str:
    """The kind of the crawl window over `sources`: one kind if they share it, else `mixed` (`mixed_utc` when
    no query date in it is local; none: `crawl`). `utc` are the bootstrap sources whose query dates were
    converted to UTC."""
    converted = set(utc)
    kinds = {
        (SCHOLAR_QUERY_DATES_UTC if s in converted else SCHOLAR_QUERY_DATES)
        if s in BOOTSTRAP_SOURCES
        else CRAWL
        for s in sources
    }
    if len(kinds) == 1:
        return kinds.pop()
    if not kinds:
        return CRAWL
    if kinds == {SCHOLAR_QUERY_DATES, SCHOLAR_QUERY_DATES_UTC}:
        return (
            SCHOLAR_QUERY_DATES  # all query dates, some local: the window is as uncertain as its local part
        )
    return MIXED if SCHOLAR_QUERY_DATES in kinds else MIXED_UTC


def crawl_dates_kind(
    windows: Iterable[str], sources: Iterable[str], everything: str = "*", utc: Iterable[str] = ()
) -> dict[str, str]:
    """Per `crawl_dates` key (`windows`), its window's kind: `everything` (`*`, the corpus-wide window) over
    every one of `sources`, any other key over that source alone; `utc` are the bootstrap sources whose query
    dates are UTC (the manifest's `query_dates`). The one derivation a search record and `/coverage` share
    (TASK-091)."""
    named = list(sources)
    converted = list(utc)
    return {k: window_kind(named if k == everything else [k], converted) for k in windows}


# The venue string, RIS `T2` and BibTeX `booktitle` (spec 04 §Exports, task-004, which cites the sources):
# the conference's full name, then the acronym it went by that year, and the year. Each venue lists its
# (first year, acronym) eras in year order. A year before the first era has no name, and a record for it is
# refused when it is built (`PaperRecord`), so an export never meets one. NeurIPS was NIPS until 2017
# (proceedings.neurips.cc labels 2018 on "NeurIPS"; the board renamed it on 2018-11-16, before that
# December's meeting). ICLR began in 2013 (iclr.cc). ICML is held annually as a conference from 1988, its 5th
# meeting (icml.cc calls 2026 the 43rd). It is the conference's name, not a proceedings title ("Advances in
# Neural Information Processing Systems 36", "Proceedings of the 40th International Conference on Machine
# Learning"), because an export also holds workshop, rejected and ICLR papers that no proceedings contain.
# AAAI was held as the National Conference on AI from 1980; the table uses the name the conference has today.
# AIES began in 2018. FAccT was held as FAT* in 2018-2020 and renamed for 2021. IASEAI first met in 2025,
# though only its 2026 papers are published.
type ConferenceTable = dict[str, tuple[str, tuple[tuple[int, str], ...]]]
CONFERENCES: ConferenceTable = {
    "NeurIPS": ("Conference on Neural Information Processing Systems", ((1987, "NIPS"), (2018, "NeurIPS"))),
    "ICLR": ("International Conference on Learning Representations", ((2013, "ICLR"),)),
    "ICML": ("International Conference on Machine Learning", ((1988, "ICML"),)),
    "AAAI": ("AAAI Conference on Artificial Intelligence", ((1980, "AAAI"),)),
    "AIES": ("AAAI/ACM Conference on AI, Ethics, and Society", ((2018, "AIES"),)),
    "FAccT": (
        "ACM Conference on Fairness, Accountability, and Transparency",
        ((2018, "FAT*"), (2021, "FAccT")),
    ),
    "IASEAI": ("International Association for Safe and Ethical AI Conference", ((2025, "IASEAI"),)),
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
