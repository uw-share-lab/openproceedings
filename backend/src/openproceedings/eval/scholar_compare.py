"""Comparing a RIS set with a query's result on one index (spec 07 §B, scholar-comparison-protocol skill;
TASK-056). The one implementation: `op eval scholar` renders its report from it (`scholar_report.py`), and a
reviewer's own RIS file is compared by the same calls (TASK-177).

Three steps, each a pure function of its arguments (no clock, no environment, no network; the only I/O is
`load_ris`, a file read):

1. `read_ris` → `RisRecord`s: title, venue, year and the ids its URLs name. RIS parsing is scholarmend's
   (`parse_ris`, as `ingest/ris.py` reads the corpus); the venue goes through Scholar mode's `source:` alias table
   (`compat.SOURCE_ALIASES`), exactly, never as a substring.
2. `scope_and_match` → a `ScholarSide`: each record matched to an index record by spec 01's merge rules
   (`MatchIndex.match`: the same OpenReview forum id or proceedings id, else the same DOI in the venue and year
   the file states (TASK-186: Scopus and Web of Science exports), else the same dedup title key
   (`dedup.title_key`) **with the same venue and year**; never a title alone), scoped to the same venues and
   years as the query side, and counted once per paper.
3. `compare_query` → a `QueryComparison`: the query run in its mode on the served engine, and every record of
   either side as kept (both), dropped (only in the RIS set, in the index), not in the index, or added (only in
   the result), each disagreement with its class and evidence.

The classes and their order are the protocol's. Only in the RIS set: `our_bug` (the oracle and the served engine
disagree) → `query_limit` (a filter clause the query itself writes, `year:` or `venue:` say, excludes it:
`query_limits`) → `filtered` (it fails a default filter and matches with them removed, under any reading below, which
its evidence names) → `compat_reading` (it matches the string as Google Scholar reads it: `scholar_reading`) →
`coverage_gap` (no record in the snapshot) → `stemming` (it matches with inflected forms added: `with_variants`)
→ `full_text` (`ReferenceEngine` confirms none of those readings matches its title or abstract; whether it also
fails the filters is in its evidence and in `Row.fails_filters`). Only in the result: `our_bug` → `scholar_cap` → `compat_reading` →
`scholar_missed`. What the automation can't settle is `unsettled`, or a class with `settled=False`: a person
decides it in `review.csv`. That is every `our_bug`, every `scholar_missed` (the protocol sends them all to a
person) and every `coverage_gap` (a real gap and a record Scholar filed under the wrong venue look the same from
here).

A row also says what its index record rests on (`Row.independent`, `Row.abstract_source`). An index built with an
imported RIS set holds that set's own records: a match to one of them is the set matching itself. It shows
nothing about coverage, its text is whatever the import carried, and where the index holds no crawled record at
all (a year not yet crawled) nothing can be only in the result. The report counts the two kinds apart.

The oracle (`ReferenceEngine`) is built over the compared records only: every matched record of the RIS set and
every in-scope match of the served engine. That is every record a row is written about, so a class never rests
on the served engine alone.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol
from urllib.parse import parse_qs, unquote, urlparse

from scholarmend.parse import parse_ris

from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.protocol import EngineInputError, Searchable
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.ingest import dedup, urls
from openproceedings.ingest.record import FORUM_ID, PaperRecord
from openproceedings.ingest.volumes import ICML_PMLR_VOLUMES
from openproceedings.query.ast import (
    FILTER_FIELDS,
    And,
    Filter,
    Near,
    Node,
    Not,
    Or,
    Phrase,
    Span,
    Term,
    TextField,
    Wildcard,
    YearRange,
    structure,
)
from openproceedings.query.canonical import render
from openproceedings.query.compat import SOURCE_ALIASES, source_key
from openproceedings.query.defaults import DEFAULT_CLAUSES, Defaulted, apply_defaults
from openproceedings.query.lexer import MIN_STEM, letters
from openproceedings.query.parser import Mode, parse
from openproceedings.vocab import BOOTSTRAP_SOURCES, TEXT_FIELDS, VENUES

type Cell = tuple[str, int]  # (venue, year)
# a proceedings paper: its native id within its venue and year (a NeurIPS hash repeats from year to year: it is
# md5 of the paper's number, so `nips-<hash>` alone names one paper per year; dedup merges on it per venue-year)
type ProceedingsKey = tuple[str, int, str]
type Fetch = Callable[[AbstractSet[str]], Mapping[str, Searchable]]  # the compared records, by id
type Leaf = Term | Wildcard | Phrase

# the classes (scholar-comparison-protocol §Classification)
OUR_BUG = "our_bug"
QUERY_LIMIT = (
    "query_limit"  # a filter clause the query itself writes (`year:`, `venue:`, …) excludes the record
)
FILTERED = "filtered"
COMPAT_READING = "compat_reading"
COVERAGE_GAP = "coverage_gap"
STEMMING = "stemming"
FULL_TEXT = "full_text"
SCHOLAR_CAP = "scholar_cap"
SCHOLAR_MISSED = "scholar_missed"
UNSETTLED = "unsettled"  # no class: the automation can't tell, and says why in the evidence
ONLY_SCHOLAR = (OUR_BUG, QUERY_LIMIT, FILTERED, COMPAT_READING, COVERAGE_GAP, STEMMING, FULL_TEXT, UNSETTLED)
ONLY_OP = (OUR_BUG, SCHOLAR_CAP, COMPAT_READING, SCHOLAR_MISSED)
# `Match.rule`, `Match.problem` and `Dropped.reason`, every value they take (the API's enums are pinned to them)
MATCH_RULES = ("forum_id", "proceedings_id", "doi", "title_venue_year")
MATCH_PROBLEMS = ("not_found", "ambiguous", "no_year", "no_venue", "truncated_title")
NOT_COMPARED_REASONS = ("venue_unrecognised", "venue", "year")

SCHOLAR_CAP_RESULTS = 1000  # what one Google Scholar search returns at most
MAX_PHRASE_FORMS = (
    512  # a phrase's (or a NEAR's) inflected spellings, all positions combined; more is refused
)
VENUE_TAGS = ("JF", "JO", "T2", "J2", "JA", "BT")  # where a RIS writer puts the venue; the first one present
TITLE_TAGS = ("TI", "T1")
_YEAR_TAGS = ("PY", "Y1", "DA")
_URL_TAGS = ("UR", "L1", "L2")
# Scopus and Web of Science RIS write the DOI in `DO` (`DI` is WoS's plain-text export tag, which is no RIS)
_DOI_TAGS = ("DO",)
# a DOI, matched case-blind (DOIs are case-insensitive, ISO 26324); stricter than `record.Urls.doi`, which
# accepts the bidi characters this refuses in a reviewer's file
# (its suffix: no whitespace, no control character (C0, DEL, C1) and no bidi format character (the marks,
# embeddings, overrides and isolates), which could make a key quoted in a row's evidence read as another)
_DOI = re.compile(r"10\.\d+(?:\.\d+)*/[^\s\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]+")
# a doi.org link, with or without its scheme, `www.` or `dx.`; and a `doi:` / `DOI ` label before a DOI or a link
_DOI_LINK = re.compile(r"(?:https?://)?(?:www\.|dx\.)?doi\.org/", re.IGNORECASE)
_DOI_LABEL = re.compile(r"doi(?::\s*|\s+)", re.IGNORECASE)
_TRAILING = ".,;)"  # punctuation a sentence or a list puts after a DOI (a `)` only when unbalanced)
_YEAR = re.compile(r"\s*([0-9]{4})(?![0-9])")
_QUERY_DATE = re.compile(r"Query date: (.+)")  # Publish or Perish: one per Scholar search
_OPENREVIEW_PATHS = frozenset({"/forum", "/pdf"})
_ELLIPSES = ("…", "...")
MAX_HOSTS = 3  # link hosts kept per record (they are quoted in a row's evidence)
# a host name as DNS writes one (letters, digits and hyphens in dot-separated labels), with an optional port
_HOST = re.compile(
    r"(?=.{1,253}(?::|\Z))[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*(?::[0-9]{1,5})?"
)


# --- the RIS set -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RisRecord:
    """One RIS record as the comparison reads it. `key` names it in every row: `<file name>#<n>`, n from 1."""

    key: str
    title: str
    venue: str | None  # an indexed venue when `venue_raw` is exactly one of Scholar mode's source names
    venue_raw: str
    year: int | None
    forum_ids: tuple[str, ...]  # OpenReview forum ids its URLs name
    proceedings_ids: tuple[ProceedingsKey, ...]  # the proceedings papers its URLs name (`proceedings_key`)
    search: str | None  # the Scholar search it came from (PoP's query date), for the result cap
    # where its links point (valid host names only, the first `MAX_HOSTS`), for a person judging an unmatched record
    hosts: tuple[str, ...] = ()
    dois: tuple[str, ...] = ()  # the DOIs it carries (`DO`, or a doi.org link), as `doi_key` writes them


def doi_key(text: str) -> str | None:
    """A DOI as matching compares it, lower-cased (DOIs are case-insensitive): without a `doi:`/`DOI ` label, then
    without a doi.org link's prefix (`https://`, `www.`/`dx.` optional) and its query and fragment, and without the
    `.`, `,`, `;` or unbalanced `)` a sentence leaves after it. None for anything that is no DOI
    (`10.<registrant>/<suffix>`, no whitespace, control or bidi format character in the suffix, once unquoted)."""
    v = text.strip()
    if label := _DOI_LABEL.match(v):  # `DOI https://doi.org/…` too: the label, then the link
        v = v[label.end() :]
    if link := _DOI_LINK.match(v):
        v = unquote(re.split(r"[?#]", v[link.end() :], maxsplit=1)[0])
    # one pass each, never a character at a time (a hostile file must not defeat /compare's time cap): strip the
    # trailing run, then give back the run's leading `)`s that close a `(` the DOI opened
    kept = v.rstrip(_TRAILING)
    tail = v[len(kept) :]
    closes = min(len(tail) - len(tail.lstrip(")")), max(kept.count("(") - kept.count(")"), 0))
    v = kept + ")" * closes
    return v.lower() if _DOI.fullmatch(v) else None


def openreview_id(url: str) -> str | None:
    """The forum id an OpenReview paper URL names: `openreview.net/forum?id=<id>` or `/pdf?id=<id>` (Scholar
    links the PDF), one `id` only, a valid forum id; else None. `urls.forum_id` stays strict (the form
    `urls.forum` claims are written in); this reads what a RIS export links."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != "openreview.net":
        return None
    if parsed.path not in _OPENREVIEW_PATHS:
        return None
    ids = parse_qs(parsed.query).get("id", [])
    return ids[0] if len(ids) == 1 and FORUM_ID.fullmatch(ids[0]) else None


def proceedings_key(url: str) -> ProceedingsKey | None:
    """The proceedings paper a URL names, or None: `urls.native`'s id with the venue and year the URL itself
    carries (a NeurIPS or ICLR proceedings path; for PMLR, the ICML volume's year from the volume table). Any
    other native names no key here: a dblp record page (`dblp-<key>`, ICML 1988-2012 and AAAI 1980-2008; decisions 047 and 049) and an
    ojs.aaai.org article or galley (`ojs-<id>`, AAAI, AIES, IASEAI; decision-049) carry no year, so the row
    is matched by its DOI or its title instead, never refused."""
    native = urls.native(url)
    if native is None:
        return None
    if (parts := urls.proceedings_parts(url)) is not None:
        return (parts[0], parts[1], native)
    if (volume := urls.pmlr(url)) is not None and volume[0] in ICML_PMLR_VOLUMES:
        return ("ICML", ICML_PMLR_VOLUMES[volume[0]][0], native)
    return None  # dblp-<key>, ojs-<id>: no year in the URL


def _named[T](read: Callable[[str], T | None], url: str) -> T | None:
    """`read(url)`, or None for a link no reader can take (`http://[x` is no URL to `urlparse`; a volume of
    5,000 digits is no integer): such a link names no paper, and never refuses the file it is in."""
    try:
        return read(url)
    except ValueError:
        return None


def link_host(url: str) -> str | None:
    """The host a link points at, lower-cased, when it is a host name as DNS writes one (at most 253
    characters, no control or other characters); else None. A row's evidence quotes it, so nothing else of
    a link is ever echoed."""
    host = urlparse(url).netloc.lower()
    return host if _HOST.fullmatch(host) else None


def _first(fields: Mapping[str, Sequence[str]], tags: Iterable[str]) -> str:
    return next((v.strip() for t in tags for v in fields.get(t, ()) if v.strip()), "")


def read_ris(text: str, name: str, tick: Callable[[], None] | None = None) -> list[RisRecord]:
    """The records of one RIS text, in file order (`name` is how keys and errors refer to it). ValueError for a
    text that holds content but no record (scholarmend refuses to drop a whole file). `tick`, when given, is
    called before each record is read (its venue string is normalized) and every 256 links within one."""
    out: list[RisRecord] = []
    for n, rec in enumerate(parse_ris(text, name), 1):
        if tick is not None:
            tick()
        links = [u for t in _URL_TAGS for u in rec.fields.get(t, ())]
        forums: dict[str, None] = {}
        listings: dict[ProceedingsKey, None] = {}
        hosts: dict[str, None] = {}
        for n_link, u in enumerate(links):  # one record may hold every link line of the file
            if tick is not None and n_link % 256 == 255:
                tick()
            if (f := _named(openreview_id, u)) is not None:
                forums[f] = None
            if (p := _named(proceedings_key, u)) is not None:
                listings[p] = None
            if len(hosts) < MAX_HOSTS and (h := _named(link_host, u)) is not None:
                hosts[h] = None
        dois = dict.fromkeys(
            k for t in _DOI_TAGS for v in rec.fields.get(t, ()) if (k := doi_key(v)) is not None
        ) | dict.fromkeys(k for u in links if _DOI_LINK.match(u.strip()) and (k := doi_key(u)))
        venue_raw = _first(rec.fields, VENUE_TAGS)
        year = _YEAR.match(_first(rec.fields, _YEAR_TAGS))
        dates = [m.group(1) for v in rec.fields.get("M1", ()) if (m := _QUERY_DATE.fullmatch(v.strip()))]
        out.append(
            RisRecord(
                key=f"{name}#{n}",
                title=_first(rec.fields, TITLE_TAGS),
                venue=SOURCE_ALIASES.get(source_key(venue_raw)),
                venue_raw=venue_raw,
                year=int(year.group(1)) if year else None,
                forum_ids=tuple(forums),
                proceedings_ids=tuple(listings),
                search=dates[0] if dates else None,
                hosts=tuple(hosts),
                dois=tuple(dois),
            )
        )
    return out


def load_ris(path: Path) -> list[RisRecord]:
    """`read_ris` of a file; `utf-8-sig` drops the BOM Scholar exports begin with."""
    return read_ris(path.read_text(encoding="utf-8-sig"), path.name)


# --- matching (spec 01 §Pipeline 4, dedup-rules skill) -------------------------------------------------------


@dataclass(frozen=True)
class Match:
    """A RIS record's index record, or why it has none. `rule` is how it matched (`forum_id`, `proceedings_id`,
    `title_venue_year`); `problem` why it didn't (`not_found`, `ambiguous`, `no_year`, `no_venue`,
    `truncated_title`); `near` the index records that share its title key in another venue or year, which is
    never a match."""

    op_id: str | None
    rule: str = ""
    problem: str = ""
    near: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()  # an ambiguous match's records
    # a matched record no crawl holds (its only source is an imported RIS set) whose title key another index
    # record has too: the id may have led to an import's copy of a paper the index also holds under another id
    shared: tuple[str, ...] = ()
    # index records its DOI names in another venue or year than the file states: never a match, named for a person
    doi_elsewhere: tuple[str, ...] = ()


def abstract_source(r: PaperRecord) -> str:
    """Where a record's abstract comes from: the source of the claim it resolves to (`dedup.abstract_claim`);
    for an imported RIS set, `ris:` and what scholarmend fetched it from; `none` without an abstract."""
    claim = dedup.abstract_claim(r.abstract, r.provenance)
    if claim is None:
        return "none"
    if claim.source not in BOOTSTRAP_SOURCES:
        return str(claim.source)
    route = (claim.evidence or "").split(" ", 1)[0].removeprefix("scholarmend:")
    return f"{claim.source}:{route}" if route else str(claim.source)


def _several[K](found: Mapping[K, list[str]]) -> dict[K, tuple[str, ...]]:
    return {k: tuple(sorted(set(v))) for k, v in found.items()}


@dataclass(frozen=True)
class MatchIndex:
    """What matching needs of a snapshot, and nothing else of it: each record's cell, and its ids under the
    three merge keys. Built in one pass (`build`); a few tens of megabytes for the full corpus."""

    cells: Mapping[str, Cell]
    forums: Mapping[str, tuple[str, ...]]  # forum id (own or linked: `dedup.forum_ids`) → record ids
    # a proceedings paper (`dedup.proceedings_ids`, in the record's venue and year) → record ids
    proceedings: Mapping[ProceedingsKey, tuple[str, ...]]
    titles: Mapping[tuple[str, int, str], tuple[str, ...]]  # (venue, year, title key) → record ids
    any_cell: Mapping[str, tuple[str, ...]]  # title key → record ids, whatever the venue and year
    # provenance, so a match can say what it rests on: the records some crawl holds (a source other than an
    # imported RIS set, `vocab.BOOTSTRAP_SOURCES`), each record's abstract source, and each cell's crawled count
    independent: frozenset[str] = frozenset()
    abstracts: Mapping[str, str] = MappingProxyType({})
    crawled: Mapping[Cell, int] = MappingProxyType({})
    keys: Mapping[str, str] = MappingProxyType({})  # record id → its title key
    dois: Mapping[str, tuple[str, ...]] = MappingProxyType({})  # `doi_key` → record ids (`urls.doi`)

    @classmethod
    def build(cls, records: Iterable[PaperRecord]) -> MatchIndex:
        cells: dict[str, Cell] = {}
        forums: dict[str, list[str]] = {}
        proceedings: dict[ProceedingsKey, list[str]] = {}
        titles: dict[tuple[str, int, str], list[str]] = {}
        any_cell: dict[str, list[str]] = {}
        independent: set[str] = set()
        abstracts: dict[str, str] = {}
        crawled: Counter[Cell] = Counter()
        keys: dict[str, str] = {}
        dois: dict[str, list[str]] = {}
        for r in records:
            cells[r.id] = (r.venue, r.year)
            abstracts[r.id] = abstract_source(r)
            if {c.source for c in r.provenance if not dedup.is_absence(c)} - BOOTSTRAP_SOURCES:
                independent.add(r.id)
                crawled[(r.venue, r.year)] += 1
            for f in dedup.forum_ids(r):
                forums.setdefault(f, []).append(r.id)
            for p in dedup.proceedings_ids(r.provenance):
                proceedings.setdefault((r.venue, r.year, p), []).append(r.id)
            claimed = {c.value for c in r.provenance if c.field == "urls.doi" and isinstance(c.value, str)}
            for d in {k for v in {r.urls.doi, *claimed} if v and (k := doi_key(v))}:
                dois.setdefault(d, []).append(r.id)
            if key := dedup.title_key(r.title):
                keys[r.id] = key
                titles.setdefault((r.venue, r.year, key), []).append(r.id)
                any_cell.setdefault(key, []).append(r.id)
        return cls(
            cells,
            _several(forums),
            _several(proceedings),
            {k: tuple(sorted(v)) for k, v in titles.items()},
            _several(any_cell),
            frozenset(independent),
            abstracts,
            dict(crawled),
            keys,
            _several(dois),
        )

    def _matched(self, op_id: str, rule: str) -> Match:
        others: tuple[str, ...] = ()
        if op_id not in self.independent:
            others = tuple(i for i in self.any_cell.get(self.keys.get(op_id, ""), ()) if i != op_id)
        return Match(op_id, rule, shared=others)

    def match(self, r: RisRecord) -> Match:
        """`r`'s index record by the merge rules, in their order: an id first (a forum id, then a proceedings
        id, then a DOI), then the title key within `r`'s venue and year. An id or a key that names two records
        is ambiguous, never a pick, and so are two ids that name different records; a record with no year, or
        whose venue is no indexed venue's name, is matched by id only. A DOI never matches across venue or
        year: it names its record only when the file's year, if it gives one, and its venue, if it names one,
        are the record's (`doi_elsewhere` otherwise)."""
        by_forum = {rid for f in r.forum_ids for rid in self.forums.get(f, ())}
        by_listing = {rid for p in r.proceedings_ids for rid in self.proceedings.get(p, ())}
        named = {rid for d in r.dois for rid in self.dois.get(d, ())}
        by_doi = {
            i for i in named if r.venue in (None, self.cells[i][0]) and r.year in (None, self.cells[i][1])
        }
        elsewhere = tuple(sorted(named - by_doi))
        found_by = [ids for ids in (by_forum, by_listing, by_doi) if ids]
        if any(ids != found_by[0] for ids in found_by):  # its ids name different records
            return Match(None, problem="ambiguous", candidates=tuple(sorted(set().union(*found_by))))
        for rule, ids in (("forum_id", by_forum), ("proceedings_id", by_listing), ("doi", by_doi)):
            if len(ids) == 1:
                return self._matched(min(ids), rule)
            if ids:
                return Match(None, problem="ambiguous", candidates=tuple(sorted(ids)))
        key = dedup.title_key(r.title)
        near = self.any_cell.get(key, ()) if key else ()
        if r.venue is None:
            return Match(None, problem="no_venue", near=near, doi_elsewhere=elsewhere)
        if r.year is None:
            return Match(None, problem="no_year", near=near, doi_elsewhere=elsewhere)
        found = list(self.titles.get((r.venue, r.year, key), ())) if key else []
        if len(found) == 1:
            return self._matched(found[0], "title_venue_year")
        if found:
            return Match(None, problem="ambiguous", candidates=tuple(found))
        if r.title.rstrip().endswith(_ELLIPSES):
            return Match(None, problem="truncated_title", near=near, doi_elsewhere=elsewhere)
        return Match(None, problem="not_found", near=near, doi_elsewhere=elsewhere)


# --- scope and the RIS side -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Scope:
    """The venues and years both sides are limited to (`years` inclusive; None is every year)."""

    venues: frozenset[str] = frozenset(VENUES.values())
    years: tuple[int, int] | None = None

    def holds(self, venue: str | None, year: int | None) -> bool:
        if venue not in self.venues:
            return False
        return self.years is None or (year is not None and self.years[0] <= year <= self.years[1])

    def describe(self) -> str:
        years = "every year" if self.years is None else f"{self.years[0]}–{self.years[1]}"
        return f"{', '.join(sorted(self.venues))}; {years}"


@dataclass(frozen=True)
class Entry:
    """One paper of the RIS set, in scope: its first record, how it matched, the cell it is scoped by (the index
    record's when it matched, else the RIS record's) and how many RIS records are this paper."""

    record: RisRecord
    match: Match
    venue: str | None
    year: int | None
    copies: int = 1


@dataclass(frozen=True)
class Dropped:
    """A RIS record left out before comparing: `reason` is `venue_unrecognised`, `venue` or `year`."""

    record: RisRecord
    reason: str
    near: tuple[str, ...] = ()  # in-scope index records with its title key: a person may want to look


@dataclass(frozen=True)
class ScholarSide:
    read: int
    entries: tuple[Entry, ...]  # in scope, one per paper
    out_of_scope: tuple[Dropped, ...]
    duplicates: int  # in-scope records that repeat an entry's paper
    searches: Mapping[str, int]  # Scholar search (query date) → records read from it
    capped: frozenset[Cell]  # cells of the searches that returned the cap or more

    @property
    def by_id(self) -> dict[str, Entry]:
        return {e.match.op_id: e for e in self.entries if e.match.op_id is not None}


def scope_and_match(
    records: Sequence[RisRecord],
    index: MatchIndex,
    scope: Scope,
    cap: int = SCHOLAR_CAP_RESULTS,
    tick: Callable[[], None] | None = None,
) -> ScholarSide:
    """Every RIS record matched, scoped and counted once per paper. A matched record is scoped by its index
    record's venue and year (the two sides then share one definition of the scope); an unmatched one by its own.
    An unmatched record with no year can't be scoped: it stays in, for a person (`unsettled`). So does an
    unmatched record whose venue string is empty or cut (`…`) and whose title key an in-scope index record of
    the same year has: it may be that paper, and only a person can say. A record that names another venue in
    full is out of scope, whatever its title. Two records are one paper when they match one index record, or,
    unmatched, share venue, year and title key. `tick`, when given, is called before each record (a title key
    is milliseconds of normalization on a long title): a caller with a time limit raises from it."""
    entries: dict[tuple[object, ...], Entry] = {}
    dropped: list[Dropped] = []
    duplicates = 0
    by_search: dict[str, list[Cell]] = {}
    for r in records:
        if tick is not None:
            tick()
        m = index.match(r)
        if m.op_id is not None:
            venue, year = index.cells[m.op_id]
            cell: tuple[str | None, int | None] = (venue, year)
        else:
            cell = (r.venue, r.year)
        if r.search is not None:
            cells = by_search.setdefault(r.search, [])
            if cell[0] is not None and cell[1] is not None:
                cells.append((cell[0], cell[1]))
        near = tuple(i for i in m.near if scope.holds(*index.cells[i]))
        # an empty or cut venue string says nothing; a complete name of another venue says the record is elsewhere
        unsaid = not r.venue_raw or any(cut in r.venue_raw for cut in _ELLIPSES)
        in_scope = scope.holds(*cell) or (
            m.op_id is None
            and (
                (r.year is None and r.venue in scope.venues)
                or (m.problem == "no_venue" and unsaid and any(index.cells[i][1] == r.year for i in near))
            )
        )
        if not in_scope:
            reason = (
                "venue_unrecognised"
                if cell[0] is None
                else "venue"
                if cell[0] not in scope.venues
                else "year"
            )
            dropped.append(Dropped(r, reason, near))
            continue
        paper: tuple[object, ...] = (
            ("id", m.op_id)
            if m.op_id is not None
            else ("title", r.venue, r.year, dedup.title_key(r.title) or r.key)
        )
        if (seen := entries.get(paper)) is not None:
            entries[paper] = Entry(seen.record, seen.match, seen.venue, seen.year, seen.copies + 1)
            duplicates += 1
        else:
            entries[paper] = Entry(r, m, cell[0], cell[1])
    searches = dict(Counter(r.search for r in records if r.search is not None))
    capped = frozenset(c for s, cells in by_search.items() if searches[s] >= cap for c in cells)
    return ScholarSide(len(records), tuple(entries.values()), tuple(dropped), duplicates, searches, capped)


# --- the string as Google Scholar reads it (decision-002; scholar-syntax-compat skill) ------------------------


def _word(item: Term | Wildcard, field: TextField | None, dollars: bool) -> Term | Wildcard:
    """A phrase item as a search word of its own, without its `$` when `dollars`."""
    if isinstance(item, Wildcard) and not (dollars and item.op == "$"):
        return Wildcard(span=item.span, stem=item.stem, op=item.op, field=field)
    return Term(span=item.span, token=item.stem if isinstance(item, Wildcard) else item.token, field=field)


def _leaf_reading(n: Leaf, dollars: bool) -> Leaf:
    if isinstance(n, Phrase):
        return Phrase(span=n.span, items=tuple(_word(i, None, dollars) for i in n.items), field=n.field)
    return _word(n, n.field, dollars)


def _combine(kind: type[And] | type[Or], nodes: Sequence[Node], span: Span) -> Node:
    return nodes[0] if len(nodes) == 1 else kind(span=span, children=tuple(nodes))


def scholar_reading(
    n: Node, pop_phrases: AbstractSet[Span] = frozenset(), *, phrases: bool = True, dollars: bool = True
) -> Node:
    """`n` (a Scholar-mode tree as typed, spans into the input) as Google Scholar itself reads the string, written
    natively. Two rewrites, each switchable so a row can say which one decided it:

    - `dollars`: Scholar has no `$` wildcard, so `benchmark$` is the word `benchmark` (Scholar mode reads it as
      the Web of Science zero-or-one wildcard).
    - `phrases`: an unquoted multi-word `|` item, which Scholar mode reads as a phrase (decision-002; its span is
      in `pop_phrases`, the spans of the parse's `COMPAT_POP_PHRASE` notices), is separate words, and `|` binds
      tighter than juxtaposition: `(large language model | LLM | foundation model)` is
      `large AND language AND (model OR llm OR foundation) AND model`.
    """
    if isinstance(n, Term | Wildcard | Phrase):
        if isinstance(n, Phrase) and phrases and n.span in pop_phrases:  # one outside an OR: just its words
            return _combine(And, [_word(i, n.field, dollars) for i in n.items], n.span)
        return _leaf_reading(n, dollars) if dollars else n
    if isinstance(n, Near):
        if not dollars:
            return n
        return Near(
            span=n.span,
            left=_leaf_reading(n.left, dollars),
            right=_leaf_reading(n.right, dollars),
            distance=n.distance,
        )
    if isinstance(n, Not):
        return Not(span=n.span, child=scholar_reading(n.child, pop_phrases, phrases=phrases, dollars=dollars))
    if isinstance(n, And):
        return And(
            span=n.span,
            children=tuple(
                scholar_reading(c, pop_phrases, phrases=phrases, dollars=dollars) for c in n.children
            ),
        )
    if isinstance(n, Or):
        # words in input order: `|` joins a child's last word to the next child's first, juxtaposition is AND
        chains: list[list[Node]] = [[]]
        for child in sorted(n.children, key=lambda c: c.span):
            if isinstance(child, Phrase) and phrases and child.span in pop_phrases:
                words = [_word(i, child.field, dollars) for i in child.items]
                chains[-1].append(words[0])
                chains.extend([w] for w in words[1:])
            else:
                chains[-1].append(scholar_reading(child, pop_phrases, phrases=phrases, dollars=dollars))
        return _combine(And, [_combine(Or, chain, n.span) for chain in chains], n.span)
    return n  # a filter


# --- inflected forms (the `stemming` test) ---------------------------------------------------------------------

_VOWELS = frozenset("aeiouy")


def inflection_stem(token: str) -> str:
    """`token` without one English inflection: a plural or third-person `s`/`es`/`ies`, `ed` or `ing`; then a
    doubled final consonant undoubled (`l`, `s`, `z` kept, as Porter does) and a final `e` dropped, so
    `evaluate`, `evaluates`, `evaluated` and `evaluating` share a stem. Inflection only: `trustworthy` is not a
    form of `trust`, nor `evaluation` of `evaluate`. Two tokens are forms of one word iff their stems are equal.
    A token that is not ASCII letters, or whose stem would be under three letters (or, for `ed` and `ing`,
    have no vowel), is its own stem. Google Scholar's stemmer is not documented; this is a fixed, stated stand-in, never tuned to a result.
    """
    if not (token.isascii() and token.isalpha()):
        return token
    stem, cut = token, False
    for suffix, put in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if not token.endswith(suffix):
            continue
        base = token[: -len(suffix)] + put
        if len(base) < 3 or (suffix in ("ing", "ed") and not _VOWELS & set(base)):
            continue  # `thing`, `string`, `need`: not inflections (a plural acronym, `llms`, needs no vowel)
        if suffix == "s" and token[-2] in "aius":  # bias, analysis, corpus, class: not plurals
            continue
        stem, cut = base, suffix in ("ing", "ed")
        break
    if cut and len(stem) > 3 and stem[-1] == stem[-2] and stem[-1] not in "aeioulsz":
        stem = stem[:-1]
    return stem[:-1] if len(stem) > 3 and stem.endswith("e") else stem


def forms_of(vocabulary: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Inflection stem → the vocabulary's tokens with that stem, sorted."""
    found: dict[str, list[str]] = {}
    for token in vocabulary:
        found.setdefault(inflection_stem(token), []).append(token)
    return {stem: tuple(sorted(tokens)) for stem, tokens in found.items()}


class TooManyForms(ValueError):
    """A phrase or a NEAR would have more inflected spellings than MAX_PHRASE_FORMS: refused, never cut."""

    def __init__(self, what: str, count: int) -> None:
        super().__init__(f"a {what} has {count} inflected spellings (more than {MAX_PHRASE_FORMS})")
        self.count = count


def _other_forms(token: str, forms: Mapping[str, Sequence[str]]) -> list[str]:
    return [t for t in forms.get(inflection_stem(token), ()) if t != token]


def _item_forms(item: Term | Wildcard, forms: Mapping[str, Sequence[str]]) -> list[Term | Wildcard]:
    token = item.stem if isinstance(item, Wildcard) else item.token
    return [item, *(Term(span=item.span, token=t, field=item.field) for t in _other_forms(token, forms))]


def _leaf_forms(leaf: Leaf, forms: Mapping[str, Sequence[str]]) -> list[Leaf]:
    if not isinstance(leaf, Phrase):
        return list(_item_forms(leaf, forms))
    positions = [_item_forms(i, forms) for i in leaf.items]
    count = 1
    for p in positions:
        count *= len(p)
    if count > MAX_PHRASE_FORMS:
        raise TooManyForms("phrase", count)
    return [Phrase(span=leaf.span, items=combo, field=leaf.field) for combo in itertools.product(*positions)]


def with_variants(n: Node, forms: Mapping[str, Sequence[str]]) -> Node:
    """`n` with every searched word also matching its other inflected forms in `forms` (`forms_of` a
    vocabulary): a word becomes an OR of its forms, a phrase an OR of the phrase in every combination of its
    words' forms, a wildcard keeps its own expansion beside its stem's forms. Filters are untouched."""
    if isinstance(n, Term | Wildcard | Phrase):
        return _combine(Or, _leaf_forms(n, forms), n.span)
    if isinstance(n, Near):
        lefts, rights = _leaf_forms(n.left, forms), _leaf_forms(n.right, forms)
        if len(lefts) * len(rights) > MAX_PHRASE_FORMS:
            raise TooManyForms("NEAR", len(lefts) * len(rights))
        pairs = [
            Near(span=n.span, left=left, right=right, distance=n.distance)
            for left in lefts
            for right in rights
        ]
        return _combine(Or, pairs, n.span)
    if isinstance(n, Not):
        return Not(span=n.span, child=with_variants(n.child, forms))
    if isinstance(n, And | Or):
        return type(n)(span=n.span, children=tuple(with_variants(c, forms) for c in n.children))
    return n


def with_prefixes(n: Node, tokenizer: str) -> Node:
    """`n` with every searched word replaced by its inflection stem read as a prefix (`inflection_stem(word)*`:
    `benchmarks` → `benchmark*`, `evaluating` → `evaluat*`), so both a stripped ending and any added one are
    covered. For the report's sensitivity figure, never for a class. It is not a stemmer: it does not strip
    derivational endings (`evaluation` stays `evaluation*`, which `evaluate` does not match). A word whose
    stem is under the wildcard's minimum stays a word; a `$` wildcard becomes `*`; filters are untouched."""

    def wide(item: Term | Wildcard, field: TextField | None) -> Term | Wildcard:
        typed = item.stem if isinstance(item, Wildcard) else item.token
        stem = inflection_stem(typed)
        if letters(stem, tokenizer) < MIN_STEM:
            return Term(span=item.span, token=typed, field=field) if isinstance(item, Term) else item
        return Wildcard(span=item.span, stem=stem, op="*", field=field)

    def leaf(x: Leaf) -> Leaf:
        if isinstance(x, Phrase):
            return Phrase(span=x.span, items=tuple(wide(i, None) for i in x.items), field=x.field)
        return wide(x, x.field)

    if isinstance(n, Term | Wildcard | Phrase):
        return leaf(n)
    if isinstance(n, Near):
        return Near(span=n.span, left=leaf(n.left), right=leaf(n.right), distance=n.distance)
    if isinstance(n, Not):
        return Not(span=n.span, child=with_prefixes(n.child, tokenizer))
    if isinstance(n, And | Or):
        return type(n)(span=n.span, children=tuple(with_prefixes(c, tokenizer) for c in n.children))
    return n


def _tokens(n: Node) -> set[str]:
    """Every word a tree searches: its exact tokens and its wildcards' stems."""
    if isinstance(n, Term):
        return {n.token}
    if isinstance(n, Wildcard):
        return {n.stem}
    if isinstance(n, Phrase):
        return {i.stem if isinstance(i, Wildcard) else i.token for i in n.items}
    if isinstance(n, Near):
        return _tokens(n.left) | _tokens(n.right)
    if isinstance(n, Not):
        return _tokens(n.child)
    if isinstance(n, And | Or):
        return {t for c in n.children for t in _tokens(c)}
    return set()


def _leaves(n: Node) -> list[Term | Wildcard | Phrase | Near]:
    """The leaves a match can rest on: every text leaf outside a NOT, in order."""
    if isinstance(n, Term | Wildcard | Phrase | Near):
        return [n]
    if isinstance(n, And | Or):
        return [leaf for c in n.children for leaf in _leaves(c)]
    return []


# --- one query --------------------------------------------------------------------------------------------------


class QueryRefused(ValueError):
    """The query has parse errors; `codes` are their diagnostic codes (the messages quote the query)."""

    def __init__(self, name: str, codes: Sequence[str]) -> None:
        super().__init__(f"query `{name}` doesn't parse: {', '.join(codes)}")
        self.codes = tuple(codes)


class Served(Protocol):
    """The engine a comparison runs on: the served index (or, in tests, the oracle)."""

    index_version: str
    tokenizer_version: str

    def match_ids(self, ast: Node) -> frozenset[str]: ...


@dataclass(frozen=True)
class Row:
    """One record of a comparison. `scholar_key` is empty on the `openproceedings` side and `op_id` for a record
    the index doesn't hold; the title is the RIS record's on the `scholar` side (raw, as exported) and the index
    record's on the other. `settled` is False when a person must decide (`review.csv`)."""

    side: Literal["scholar", "openproceedings"]
    scholar_key: str
    op_id: str
    title: str
    venue: str
    year: int | None
    auto_class: str
    auto_evidence: str
    settled: bool = True
    # what the row's index record rests on (None and "" without one): whether some crawl holds it, or only an
    # imported RIS set (a match to the set's own import says nothing about coverage, and its text is the import's)
    independent: bool | None = None
    abstract_source: str = ""
    fails_filters: bool = False  # its index record fails a default filter of the query
    shared_title: bool = (
        False  # matched to a RIS-only record whose title another index record has (`Match.shared`)
    )
    # for a row with no index record: the index records its evidence names as holding the same title (in scope
    # and of its year for a record with no venue). One of them is what an `in_both` call pairs the row with.
    near: tuple[str, ...] = ()


@dataclass(frozen=True)
class Group:
    """A top-level text conjunct of the query (a concept group), and how many of the RIS set's matched records
    hold it in title or abstract: exactly as run, and with inflected forms added."""

    text: str  # canonical
    exact: int
    with_forms: int


@dataclass(frozen=True)
class QueryComparison:
    name: str
    query: str
    mode: Mode
    canonical: str
    canonical_hash: str
    notices: Mapping[str, int]  # translation and warning codes → how many (never their messages)
    scholar_reading: (
        str | None
    )  # canonical, with the default filters; None when Scholar reads the string as run
    total: int  # the served result, every venue and year
    in_scope: int  # of them, in scope
    scholar_in_scope: int  # RIS papers in scope
    kept: tuple[Row, ...]  # in both
    dropped: tuple[Row, ...]  # only in the RIS set, in the index
    not_in_index: tuple[Row, ...]  # only in the RIS set, no index record
    added: tuple[Row, ...]  # only in the result
    groups: tuple[Group, ...]
    matched: int  # RIS papers with an index record: what `groups` counts over
    variants: Mapping[str, tuple[str, ...]]  # query token → its other inflected forms in the compared records
    # of the `full_text` rows, how many a prefix reading of every word (`word*`) matches; None when a prefix
    # expands past the engine's cap (then no figure is given, never a partial one)
    full_text_by_prefix: int | None = None

    @property
    def only_scholar(self) -> tuple[Row, ...]:
        return self.dropped + self.not_in_index

    @property
    def disagreements(self) -> tuple[Row, ...]:
        """Every row with a class: the records of one side only, and any kept record that is an `our_bug`."""
        return self.dropped + self.not_in_index + self.added + tuple(r for r in self.kept if r.auto_class)

    @property
    def our_bug(self) -> int:
        return sum(r.auto_class == OUR_BUG for r in self.disagreements)

    def counts(self, side: str) -> Counter[str]:
        return Counter(r.auto_class for r in self.disagreements if r.side == side)


def _text_conjuncts(n: Node | None) -> list[Node]:
    if n is None:
        return []
    conjuncts = list(n.children) if isinstance(n, And) else [n]
    return [c for c in conjuncts if not isinstance(c.child if isinstance(c, Not) else c, Filter)]


def query_limits(d: Defaulted) -> list[Node]:
    """The query's own limits: its top-level filter clauses (`year:2020..2022`, `NOT venue:ICML`, `track:main`)
    that are not a default (spec 02 §Default filters). A record one of them excludes is `query_limit`, whatever
    its text: the query as written leaves it out. A clause under an OR or a NOT group is part of the search."""
    conjuncts = list(d.effective.children) if isinstance(d.effective, And) else [d.effective]

    def own(c: Node) -> bool:
        inner = c.child if isinstance(c, Not) else c
        return isinstance(inner, Filter) and not (
            inner.field in d.defaults and inner.values == DEFAULT_CLAUSES.get(inner.field)
        )

    return [c for c in conjuncts if own(c)]


def _holds(clause: Node, values: Mapping[str, str | int | None]) -> bool | None:
    """Whether a record with these field values passes a limit (`query_limits`); None when the value it reads
    is unknown (a record the index doesn't hold has only the file's venue and year)."""
    negated = isinstance(clause, Not)
    f = clause.child if isinstance(clause, Not) else clause
    assert isinstance(f, Filter)
    value = values.get(f.field)
    if value is None:
        return None
    if f.field == "year":
        inside = any(isinstance(v, YearRange) and v.lo <= int(value) <= v.hi for v in f.values)
    else:
        inside = value in f.values
    return inside != negated


def _outside(limits: Sequence[Node], values: Mapping[str, str | int | None]) -> str:
    """The limits a record fails, each with the value that fails it (`year:2020..2022` (year 2019)); "" for none."""
    return "; ".join(
        f"`{render(c)}` ({f.field} {values[f.field]})"
        for c in limits
        if _holds(c, values) is False and isinstance(f := c.child if isinstance(c, Not) else c, Filter)
    )


def _cells_of(ids: Iterable[str], index: MatchIndex) -> str:
    return "; ".join(f"{i} ({index.cells[i][0]} {index.cells[i][1]})" for i in ids)


def result_in_scope(
    engine: Served, ast: Node, index: MatchIndex, scope: Scope
) -> tuple[frozenset[str], frozenset[str]]:
    """The query's result on `engine` (`match_ids` of its effective tree, nothing else) and the part of it in
    `scope`. ValueError if the engine holds a record `index` doesn't: the two are not one index's."""
    served = engine.match_ids(ast)
    unknown = sorted(i for i in served if i not in index.cells)
    if unknown:
        raise ValueError(
            f"the index holds {len(unknown)} record(s) the snapshot doesn't (first: {unknown[0]})"
        )
    return served, frozenset(i for i in served if scope.holds(*index.cells[i]))


def only_in_result(in_scope: AbstractSet[str], side: ScholarSide) -> list[str]:
    """The ids of the result that no record of the RIS set matched (the `added` rows), ascending."""
    return sorted(in_scope - frozenset(side.by_id))


def _not_in_index(e: Entry, index: MatchIndex, scope: Scope, limits: Sequence[Node] = ()) -> Row:
    m, r = e.match, e.record
    cells = _cells_of(m.near, index)
    same = f"; same title: {cells}" if cells else ""
    near = m.near
    if m.problem == "ambiguous":
        cls, evidence = (
            UNSETTLED,
            f"its id or title names {len(m.candidates)} records: {', '.join(m.candidates)}",
        )
    elif m.problem == "no_year":
        cls, evidence = UNSETTLED, f"no year and no id: matched by id only{same}"
    elif m.problem == "no_venue":  # kept only because an in-scope record has its title (`scope_and_match`)
        near = tuple(i for i in m.near if scope.holds(*index.cells[i]) and index.cells[i][1] == e.year)
        cls, evidence = (
            UNSETTLED,
            f"its venue string is no venue, so no title match is made; same title: {_cells_of(near, index)}",
        )
    elif m.problem == "truncated_title":
        cls, evidence = UNSETTLED, f"the title is cut (…), so its key can't match{same}"
    else:  # a gap, or a record Scholar filed under the wrong venue or year: a person checks which
        where = f"; its links are on {', '.join(r.hosts)}" if r.hosts else ""
        cls = COVERAGE_GAP
        # judged on the file's own venue and year (the only ones it has), so still for a person
        if outside := _outside(limits, {"venue": e.venue, "year": e.year}):
            cls = QUERY_LIMIT
            evidence = f"outside the query's own limit, by the file's venue and year: {outside}; not in the snapshot{same}{where}"
        elif m.near:  # the same title in another venue or year is never a match
            evidence = f"no id or title match in {e.venue} {e.year}; same title elsewhere: {cells}{where}"
        else:
            evidence = f"no forum id, proceedings id, DOI or title+venue+year match in the snapshot{where}"
    if m.doi_elsewhere:
        evidence += (
            f"; its DOI names {_cells_of(m.doi_elsewhere, index)}, another venue or year: never a match"
        )
    return Row("scholar", r.key, "", r.title, e.venue or r.venue_raw, e.year, cls, evidence, False, near=near)


def compare_query(
    name: str,
    q: str,
    *,
    side: ScholarSide,
    index: MatchIndex,
    engine: Served,
    fetch: Fetch,
    scope: Scope,
    mode: Mode = "scholar",
    tick: Callable[[], None] | None = None,
) -> QueryComparison:
    """`q` run in `mode` on `engine`, compared with `side`. `fetch` returns the compared records (title,
    abstract, track, status) by id: every id it is asked for must come back. The result set is exactly
    `engine.match_ids` of the query's effective tree, limited to `scope`: nothing here changes what matches.
    `TooManyForms` when a phrase or NEAR of the query has more inflected spellings than the cap. `tick`, when
    given, is called before each of the oracle's evaluations and before each row is written (the comparison's
    cost): a caller with a time limit raises from it (`POST /compare`), and nothing is returned."""
    parsed = parse(q, mode, engine.tokenizer_version)
    if parsed.effective_ast is None or parsed.ast is None or parsed.canonical is None:
        raise QueryRefused(name, [str(d.code) for d in parsed.errors])
    served, in_scope = result_in_scope(engine, parsed.effective_ast, index, scope)
    by_id = side.by_id
    compared = frozenset(by_id) | in_scope
    docs = fetch(compared)
    if missing := sorted(compared - set(docs)):
        raise ValueError(f"{len(missing)} compared record(s) could not be read (first: {missing[0]})")
    # the oracle holds the compared records only, so a wildcard expands over their vocabulary, not the snapshot's:
    # the same matches for these records (a record matches a wildcard through its own tokens), a shorter expansion
    oracle = ReferenceEngine(docs.values(), tokenizer=engine.tokenizer_version)
    forms = forms_of(oracle.vocabulary)

    memo: dict[str, frozenset[str]] = {}
    # by identity too: a tree asked about again (once per row) is never serialised again (TASK-200). The tree is
    # held beside its matches, so its id can't be reused by another object while the comparison runs
    seen: dict[int, tuple[Node, frozenset[str]]] = {}

    def ids(n: Node | None) -> frozenset[str]:
        """The oracle's matches of a tree among the compared records (None: every record), computed once."""
        if n is None:
            return oracle.universe
        if (hit := seen.get(id(n))) is not None and hit[0] is n:
            return hit[1]
        key = n.model_dump_json()
        if key not in memo:
            if tick is not None:
                tick()
            memo[key] = oracle.match_ids(n)
        seen[id(n)] = (n, memo[key])
        return memo[key]

    # the readings: as run; as Scholar reads the string (each rewrite alone, and both); each with inflected forms
    run = apply_defaults(parsed.ast, len(q))
    limits = query_limits(run)
    # the query as run without its limits or the defaults: its text conjuncts (None: every record)
    rest = _text_conjuncts(run.identification)
    unlimited = _combine(And, rest, run.effective.span) if rest else None
    pop = frozenset(
        d.span
        for d in parsed.translations
        if d.code == DiagnosticCode.COMPAT_POP_PHRASE and d.span is not None
    )
    both = apply_defaults(scholar_reading(parsed.ast, pop), len(q))
    differs = structure(both.effective) != structure(run.effective)
    only_phrases = apply_defaults(scholar_reading(parsed.ast, pop, dollars=False), len(q))
    only_dollars = apply_defaults(scholar_reading(parsed.ast, pop, phrases=False), len(q))
    o_run, o_ident = ids(run.effective), ids(run.identification)
    o_sch, o_sch_ident = ids(both.effective), ids(both.identification)
    readings = [t for t in (run.identification, both.identification) if t is not None]
    o_stem = (
        frozenset().union(*(ids(with_variants(t, forms)) for t in readings)) if readings else oracle.universe
    )
    bugs = o_run ^ (served & compared)  # the oracle and the served engine must agree on every compared record
    groups = _text_conjuncts(run.identification)
    group_ids = [(ids(g), ids(with_variants(g, forms))) for g in groups]
    queried = sorted({t for tree in readings for t in _tokens(tree)})
    variants = {t: tuple(_other_forms(t, forms)) for t in queried if _other_forms(t, forms)}
    # the trees a row's evidence asks about, built once so `ids` meets each again by identity
    form_terms = {v: Term(span=(0, 0), token=v) for vs in variants.values() for v in vs}
    # (a leaf's id, a text field) → the leaf and its copy searched in that field (held, as `seen` holds its trees)
    in_field: dict[tuple[int, str], tuple[Node, Node]] = {}

    def fields(i: str, leaf: Term | Wildcard | Phrase | Near) -> str:
        """Where `leaf` matches record `i`: `title`, `abstract`, `title+abstract`, or "" for no match."""
        if isinstance(leaf, Near):
            return "title or abstract" if i in ids(leaf) else ""
        found = []
        for f in TEXT_FIELDS:
            if leaf.field not in (None, f):
                continue
            hit = in_field.get((id(leaf), f))
            if hit is None or hit[0] is not leaf:
                hit = in_field[(id(leaf), f)] = (leaf, leaf.model_copy(update={"field": f}))
            if i in ids(hit[1]):
                found.append(f)
        return "+".join(found)

    def filters_failed(d: Searchable) -> str:
        failed = [f"{f}={getattr(d, f)}" for f in run.defaults if getattr(d, f) not in DEFAULT_CLAUSES[f]]
        return ", ".join(failed)

    def rewrites(i: str, eff: bool) -> str:
        """Which Scholar-reading rewrite alone accounts for record `i` (with or without the defaults)."""

        def has(t: Defaulted) -> bool:
            return i in ids(t.effective if eff else t.identification)

        names = []
        if has(only_phrases) != has(run):
            names.append(
                "decision-002: the unquoted `|` items are phrases here, neighbouring words ORed in Scholar"
            )
        if has(only_dollars) != has(run):
            names.append("`$`: a zero-or-one wildcard here, no wildcard in Scholar")
        return "; ".join(names) or "decision-002 phrases and `$` together"

    def deciding(i: str) -> str:
        """The inflected forms that make record `i` match: for each group it fails as run and holds with forms,
        the forms of that group's words the record has. (Every form it has, when no single group explains it:
        the match then comes through Scholar's reading.)"""
        held = {v for v, term in form_terms.items() if i in ids(term)}
        named = {
            v
            for g, (exact, loose) in zip(groups, group_ids, strict=True)
            if i not in exact and i in loose
            for t in _tokens(g)
            for v in variants.get(t, ())
        }
        return ", ".join(sorted(held & named or held))

    def provenance(i: str, d: Searchable) -> tuple[bool, str, bool]:
        return i in index.independent, index.abstracts.get(i, ""), bool(filters_failed(d))

    def dropped(e: Entry) -> Row:
        """A matched record the result lacks. The filters are judged before the text (the protocol's order): a
        record that fails them and matches under any reading is `filtered`, and its evidence names the reading."""
        i = e.match.op_id
        assert i is not None
        d, failed = docs[i], filters_failed(docs[i])
        settled = True
        if i in bugs:
            cls, evidence, settled = OUR_BUG, "the oracle matches it and the served engine doesn't", False
        elif outside := _outside(limits, {f: getattr(d, f) for f in FILTER_FIELDS}):
            also = (
                "the rest of the query matches it"
                if i in ids(unlimited)
                else "the rest of the query doesn't match it either"
            )
            cls, evidence = QUERY_LIMIT, f"outside the query's own limit: {outside}; {also} (as run)"
        elif i in o_ident:
            cls, evidence = FILTERED, failed or "fails a filter of the query"
        elif differs and i in o_sch_ident:
            cls, evidence = (FILTERED, f"{failed}; also compat_reading ({rewrites(i, eff=False)})") if failed else (COMPAT_READING, rewrites(i, eff=False))  # fmt: skip
        elif i in o_stem:
            cls, evidence = (FILTERED, f"{failed}; also stemming (matches with {deciding(i)})") if failed else (STEMMING, f"matches with {deciding(i)}")  # fmt: skip
        elif d.abstract is None:
            cls, evidence, settled = UNSETTLED, "no title match, and the corpus has no abstract for it", False
        else:
            failing = [str(k) for k, (_, loose) in enumerate(group_ids, 1) if i not in loose]
            cls = FULL_TEXT
            evidence = (
                f"no title or abstract match for group {', '.join(failing)}, inflected forms included"
                if failing
                else "no title or abstract match, inflected forms included"
            )
        if cls in (QUERY_LIMIT, FULL_TEXT, UNSETTLED) and failed:
            evidence += f"; also fails the filters ({failed})"
        if (
            e.match.shared and cls != OUR_BUG
        ):  # the id led to an import's record whose title the index has twice
            evidence = (
                f"matched by {e.match.rule.replace('_', ' ')} to a record only the imported set holds, whose title "
                f"is also on {_cells_of(e.match.shared, index)}: possibly one paper under two ids; otherwise "
                f"`{cls}` ({evidence})"
            )
            cls, settled = UNSETTLED, False
        return Row("scholar", e.record.key, i, e.record.title, d.venue, d.year, cls, evidence, settled, *provenance(i, d), bool(e.match.shared))  # fmt: skip

    def added(i: str) -> Row:
        d = docs[i]
        if i in bugs:
            cls, evidence, settled = OUR_BUG, "the served engine matches it and the oracle doesn't", False
        elif index.cells[i] in side.capped:
            cls, evidence, settled = SCHOLAR_CAP, f"a Scholar search covering {d.venue} {d.year} returned its cap", True  # fmt: skip
        elif differs and i not in o_sch:
            cls, evidence, settled = COMPAT_READING, rewrites(i, eff=True), True
        else:
            hits = [
                f"group {k}: {', '.join(found[:3])}"
                for k, g in enumerate(groups, 1)
                if (
                    found := [
                        f"{render(leaf)} ({where})" for leaf in _leaves(g) if (where := fields(i, leaf))
                    ]
                )
            ]
            cls, evidence, settled = SCHOLAR_MISSED, "exact match on " + "; ".join(hits), False
        return Row("openproceedings", "", i, " ".join(d.title.split()), d.venue, d.year, cls, evidence, settled, *provenance(i, d))  # fmt: skip

    def step() -> None:
        if tick is not None:
            tick()

    def added_row(i: str) -> Row:
        step()
        return added(i)

    kept, only, gaps = [], [], []
    for e in side.entries:
        step()
        if e.match.op_id is None:
            gaps.append(_not_in_index(e, index, scope, limits))
        elif e.match.op_id not in in_scope:
            only.append(dropped(e))
        else:  # in both; served without the oracle's agreement is still a bug, and is never hidden as kept
            d = docs[e.match.op_id]
            bug = d.id in bugs
            cls, evidence = (
                (OUR_BUG, "the served engine matches it and the oracle doesn't")
                if bug
                else ("", e.match.rule)
            )
            kept.append(Row("scholar", e.record.key, d.id, e.record.title, d.venue, d.year, cls, evidence, not bug, *provenance(d.id, d), bool(e.match.shared)))  # fmt: skip
    members = frozenset(by_id)
    notices = Counter(str(d.code) for d in (*parsed.translations, *parsed.warnings))
    full = frozenset(r.op_id for r in only if r.auto_class == FULL_TEXT)
    try:
        wide = frozenset().union(*(ids(with_prefixes(t, engine.tokenizer_version)) for t in readings))
        by_prefix: int | None = len(full & wide)
    except EngineInputError:  # a prefix expands past the cap: no figure, never a partial one
        by_prefix = None
    return QueryComparison(
        name=name,
        query=q,
        mode=mode,
        canonical=parsed.canonical,
        canonical_hash=parsed.canonical_hash or "",
        notices=dict(sorted(notices.items())),
        scholar_reading=render(both.effective) if differs else None,
        total=len(served),
        in_scope=len(in_scope),
        scholar_in_scope=len(side.entries),
        kept=tuple(kept),
        dropped=tuple(only),
        not_in_index=tuple(gaps),
        added=tuple(added_row(i) for i in only_in_result(in_scope, side)),
        groups=tuple(
            Group(render(g), len(exact & members), len(loose & members))
            for g, (exact, loose) in zip(groups, group_ids, strict=True)
        ),
        matched=len(members),
        variants=variants,
        full_text_by_prefix=by_prefix,
    )
