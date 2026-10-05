"""Comparing a RIS set with a query's result on one index (spec 07 §B, scholar-comparison-protocol skill;
TASK-056). The one implementation: `op eval scholar` renders its report from it (`scholar_report.py`), and a
reviewer's own RIS file is compared by the same calls (TASK-177).

Three steps, each a pure function of its arguments (no clock, no environment, no network; the only I/O is
`load_ris`, a file read):

1. `read_ris` → `RisRecord`s: title, venue, year and the ids its URLs name. RIS parsing is scholarmend's
   (`parse_ris`, as `ingest/ris.py` reads the corpus); the venue goes through Scholar mode's `source:` alias table
   (`compat.SOURCE_ALIASES`), exactly, never as a substring.
2. `scope_and_match` → a `ScholarSide`: each record matched to an index record by spec 01's merge rules
   (`MatchIndex.match`: the same OpenReview forum id or proceedings id, else the same dedup title key
   (`dedup.title_key`) **with the same venue and year**; never a title alone), scoped to the same venues and
   years as the query side, and counted once per paper.
3. `compare_query` → a `QueryComparison`: the query run in its mode on the served engine, and every record of
   either side as kept (both), dropped (only in the RIS set, in the index), not in the index, or added (only in
   the result), each disagreement with its class and evidence.

The classes and their order are the protocol's. Only in the RIS set: `our_bug` (the oracle and the served engine
disagree) → `filtered` (it matches with the default filters removed) → `compat_reading` (it matches the string as
Google Scholar reads it: `scholar_reading`) → `coverage_gap` (no record in the snapshot) → `stemming` (it matches
with inflected forms added: `with_variants`) → `full_text` (`ReferenceEngine` confirms none of those readings
matches its title or abstract). Only in the result: `our_bug` → `scholar_cap` → `compat_reading` →
`scholar_missed`. What the automation can't settle is `unsettled`, or a class with `settled=False`: a person
decides it in `review.csv`. That is every `our_bug`, every `scholar_missed` (the protocol sends them all to a
person) and every `coverage_gap` (a real gap and a record Scholar filed under the wrong venue look the same from
here).

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
from typing import Literal, Protocol
from urllib.parse import parse_qs, urlparse

from scholarmend.parse import parse_ris

from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.protocol import Searchable
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.ingest import dedup, urls
from openproceedings.ingest.record import FORUM_ID, PaperRecord
from openproceedings.ingest.volumes import ICML_PMLR_VOLUMES
from openproceedings.query.ast import (
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
    structure,
)
from openproceedings.query.canonical import render
from openproceedings.query.compat import SOURCE_ALIASES, source_key
from openproceedings.query.defaults import DEFAULT_CLAUSES, Defaulted, apply_defaults
from openproceedings.query.parser import Mode, parse
from openproceedings.vocab import TEXT_FIELDS, VENUES

type Cell = tuple[str, int]  # (venue, year)
# a proceedings paper: its native id within its venue and year (a NeurIPS hash repeats from year to year: it is
# md5 of the paper's number, so `nips-<hash>` alone names one paper per year; dedup merges on it per venue-year)
type ProceedingsKey = tuple[str, int, str]
type Fetch = Callable[[AbstractSet[str]], Mapping[str, Searchable]]  # the compared records, by id
type Leaf = Term | Wildcard | Phrase

# the classes (scholar-comparison-protocol §Classification)
OUR_BUG = "our_bug"
FILTERED = "filtered"
COMPAT_READING = "compat_reading"
COVERAGE_GAP = "coverage_gap"
STEMMING = "stemming"
FULL_TEXT = "full_text"
SCHOLAR_CAP = "scholar_cap"
SCHOLAR_MISSED = "scholar_missed"
UNSETTLED = "unsettled"  # no class: the automation can't tell, and says why in the evidence
ONLY_SCHOLAR = (OUR_BUG, FILTERED, COMPAT_READING, COVERAGE_GAP, STEMMING, FULL_TEXT, UNSETTLED)
ONLY_OP = (OUR_BUG, SCHOLAR_CAP, COMPAT_READING, SCHOLAR_MISSED)

SCHOLAR_CAP_RESULTS = 1000  # what one Google Scholar search returns at most
MAX_PHRASE_FORMS = 512  # a phrase's inflected spellings, all positions combined; more is refused, never cut
_VENUE_TAGS = ("JF", "JO", "T2", "J2", "JA", "BT")  # where a RIS writer puts the venue; the first one present
_TITLE_TAGS = ("TI", "T1")
_YEAR_TAGS = ("PY", "Y1", "DA")
_URL_TAGS = ("UR", "L1", "L2")
_YEAR = re.compile(r"\s*([0-9]{4})(?![0-9])")
_QUERY_DATE = re.compile(r"Query date: (.+)")  # Publish or Perish: one per Scholar search
_OPENREVIEW_PATHS = frozenset({"/forum", "/pdf"})
_ELLIPSES = ("…", "...")


# --- the RIS set -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RisRecord:
    """One RIS record as the comparison reads it. `key` names it in every row: `<file name>#<n>`, n from 1."""

    key: str
    title: str
    venue: str | None  # NeurIPS, ICLR or ICML when `venue_raw` is exactly one of Scholar mode's source names
    venue_raw: str
    year: int | None
    forum_ids: tuple[str, ...]  # OpenReview forum ids its URLs name
    proceedings_ids: tuple[ProceedingsKey, ...]  # the proceedings papers its URLs name (`proceedings_key`)
    search: str | None  # the Scholar search it came from (PoP's query date), for the result cap
    hosts: tuple[str, ...] = ()  # where its links point, for a person judging an unmatched record


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
    carries (a NeurIPS or ICLR proceedings path; for PMLR, the ICML volume's year from the volume table)."""
    native = urls.native(url)
    if native is None:
        return None
    if (parts := urls.proceedings_parts(url)) is not None:
        return (parts[0], parts[1], native)
    volume = urls.pmlr(url)
    assert volume is not None  # `urls.native` names a NeurIPS/ICLR paper or an ICML volume's, nothing else
    return ("ICML", ICML_PMLR_VOLUMES[volume[0]][0], native)


def _first(fields: Mapping[str, Sequence[str]], tags: Iterable[str]) -> str:
    return next((v.strip() for t in tags for v in fields.get(t, ()) if v.strip()), "")


def read_ris(text: str, name: str) -> list[RisRecord]:
    """The records of one RIS text, in file order (`name` is how keys and errors refer to it). ValueError for a
    text that holds content but no record (scholarmend refuses to drop a whole file)."""
    out: list[RisRecord] = []
    for n, rec in enumerate(parse_ris(text, name), 1):
        links = [u for t in _URL_TAGS for u in rec.fields.get(t, ())]
        venue_raw = _first(rec.fields, _VENUE_TAGS)
        year = _YEAR.match(_first(rec.fields, _YEAR_TAGS))
        dates = [m.group(1) for v in rec.fields.get("M1", ()) if (m := _QUERY_DATE.fullmatch(v.strip()))]
        out.append(
            RisRecord(
                key=f"{name}#{n}",
                title=_first(rec.fields, _TITLE_TAGS),
                venue=SOURCE_ALIASES.get(source_key(venue_raw)),
                venue_raw=venue_raw,
                year=int(year.group(1)) if year else None,
                forum_ids=tuple(dict.fromkeys(f for u in links if (f := openreview_id(u)))),
                proceedings_ids=tuple(dict.fromkeys(p for u in links if (p := proceedings_key(u)))),
                search=dates[0] if dates else None,
                hosts=tuple(dict.fromkeys(h for u in links if (h := urlparse(u).netloc.lower()))),
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

    @classmethod
    def build(cls, records: Iterable[PaperRecord]) -> MatchIndex:
        cells: dict[str, Cell] = {}
        forums: dict[str, list[str]] = {}
        proceedings: dict[ProceedingsKey, list[str]] = {}
        titles: dict[tuple[str, int, str], list[str]] = {}
        any_cell: dict[str, list[str]] = {}
        for r in records:
            cells[r.id] = (r.venue, r.year)
            for f in dedup.forum_ids(r):
                forums.setdefault(f, []).append(r.id)
            for p in dedup.proceedings_ids(r.provenance):
                proceedings.setdefault((r.venue, r.year, p), []).append(r.id)
            if key := dedup.title_key(r.title):
                titles.setdefault((r.venue, r.year, key), []).append(r.id)
                any_cell.setdefault(key, []).append(r.id)
        return cls(
            cells,
            _several(forums),
            _several(proceedings),
            {k: tuple(sorted(v)) for k, v in titles.items()},
            _several(any_cell),
        )

    def match(self, r: RisRecord) -> Match:
        """`r`'s index record by the merge rules, in their order: an id first (a forum id, then a proceedings
        id), then the title key within `r`'s venue and year. An id or a key that names two records is ambiguous,
        never a pick; a record with no year, or whose venue is not one of the three, is matched by id only."""
        by_forum = {rid for f in r.forum_ids for rid in self.forums.get(f, ())}
        by_listing = {rid for p in r.proceedings_ids for rid in self.proceedings.get(p, ())}
        for rule, ids in (("forum_id", by_forum), ("proceedings_id", by_listing)):
            if len(ids) == 1:
                return Match(min(ids), rule)
            if ids:
                return Match(None, problem="ambiguous", candidates=tuple(sorted(ids)))
        key = dedup.title_key(r.title)
        near = self.any_cell.get(key, ()) if key else ()
        if r.venue is None:
            return Match(None, problem="no_venue", near=near)
        if r.year is None:
            return Match(None, problem="no_year", near=near)
        found = list(self.titles.get((r.venue, r.year, key), ())) if key else []
        if len(found) == 1:
            return Match(found[0], "title_venue_year")
        if found:
            return Match(None, problem="ambiguous", candidates=tuple(found))
        if r.title.rstrip().endswith(_ELLIPSES):
            return Match(None, problem="truncated_title", near=near)
        return Match(None, problem="not_found", near=near)


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
    records: Sequence[RisRecord], index: MatchIndex, scope: Scope, cap: int = SCHOLAR_CAP_RESULTS
) -> ScholarSide:
    """Every RIS record matched, scoped and counted once per paper. A matched record is scoped by its index
    record's venue and year (the two sides then share one definition of the scope); an unmatched one by its own.
    An unmatched record with no year can't be scoped: it stays in, for a person (`unsettled`). Two records are
    one paper when they match one index record, or, unmatched, share venue, year and title key."""
    entries: dict[tuple[object, ...], Entry] = {}
    dropped: list[Dropped] = []
    duplicates = 0
    by_search: dict[str, list[Cell]] = {}
    for r in records:
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
        in_scope = scope.holds(*cell) or (m.op_id is None and r.year is None and r.venue in scope.venues)
        if not in_scope:
            reason = (
                "venue_unrecognised"
                if cell[0] is None
                else "venue"
                if cell[0] not in scope.venues
                else "year"
            )
            near = tuple(i for i in m.near if scope.holds(*index.cells[i]))
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
    searches = {s: sum(r.search == s for r in records) for s in by_search}
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
        raise ValueError(f"a phrase has {count} inflected spellings (more than {MAX_PHRASE_FORMS})")
    return [Phrase(span=leaf.span, items=combo, field=leaf.field) for combo in itertools.product(*positions)]


def with_variants(n: Node, forms: Mapping[str, Sequence[str]]) -> Node:
    """`n` with every searched word also matching its other inflected forms in `forms` (`forms_of` a
    vocabulary): a word becomes an OR of its forms, a phrase an OR of the phrase in every combination of its
    words' forms, a wildcard keeps its own expansion beside its stem's forms. Filters are untouched."""
    if isinstance(n, Term | Wildcard | Phrase):
        return _combine(Or, _leaf_forms(n, forms), n.span)
    if isinstance(n, Near):
        pairs = [
            Near(span=n.span, left=left, right=right, distance=n.distance)
            for left in _leaf_forms(n.left, forms)
            for right in _leaf_forms(n.right, forms)
        ]
        return _combine(Or, pairs, n.span)
    if isinstance(n, Not):
        return Not(span=n.span, child=with_variants(n.child, forms))
    if isinstance(n, And | Or):
        return type(n)(span=n.span, children=tuple(with_variants(c, forms) for c in n.children))
    return n


def _tokens(n: Node) -> set[str]:
    """Every exact token a tree searches (wildcard stems aside)."""
    if isinstance(n, Term):
        return {n.token}
    if isinstance(n, Phrase):
        return {i.token for i in n.items if isinstance(i, Term)}
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


def _not_in_index(e: Entry, index: MatchIndex) -> Row:
    m, r = e.match, e.record
    cells = "; ".join(f"{i} ({index.cells[i][0]} {index.cells[i][1]})" for i in m.near)
    if m.problem == "ambiguous":
        cls, evidence, settled = UNSETTLED, f"its id or title names {len(m.candidates)} records: {', '.join(m.candidates)}", False  # fmt: skip
    elif m.problem == "no_year":
        cls, evidence, settled = UNSETTLED, "no year and no id: matched by id only" + (f"; same title: {cells}" if cells else ""), False  # fmt: skip
    elif m.problem == "truncated_title":
        cls, evidence, settled = UNSETTLED, "the title is cut (…), so its key can't match" + (f"; same title: {cells}" if cells else ""), False  # fmt: skip
    else:  # a gap, or a record Scholar filed under the wrong venue or year: a person checks which
        where = f"; its links are on {', '.join(r.hosts)}" if r.hosts else ""
        cls, settled = COVERAGE_GAP, False
        if m.near:  # the same title in another venue or year is never a match
            evidence = f"no id or title match in {e.venue} {e.year}; same title elsewhere: {cells}{where}"
        else:
            evidence = f"no forum id, proceedings id or title+venue+year match in the snapshot{where}"
    return Row("scholar", r.key, "", r.title, e.venue or r.venue_raw, e.year, cls, evidence, settled)


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
) -> QueryComparison:
    """`q` run in `mode` on `engine`, compared with `side`. `fetch` returns the compared records (title,
    abstract, track, status) by id: every id it is asked for must come back. The result set is exactly
    `engine.match_ids` of the query's effective tree, limited to `scope`: nothing here changes what matches."""
    parsed = parse(q, mode, engine.tokenizer_version)
    if parsed.effective_ast is None or parsed.ast is None or parsed.canonical is None:
        raise QueryRefused(name, [str(d.code) for d in parsed.errors])
    served = engine.match_ids(parsed.effective_ast)
    unknown = sorted(i for i in served if i not in index.cells)
    if unknown:
        raise ValueError(
            f"the index holds {len(unknown)} record(s) the snapshot doesn't (first: {unknown[0]})"
        )
    in_scope = frozenset(i for i in served if scope.holds(*index.cells[i]))
    by_id = side.by_id
    compared = frozenset(by_id) | in_scope
    docs = fetch(compared)
    if missing := sorted(compared - set(docs)):
        raise ValueError(f"{len(missing)} compared record(s) could not be read (first: {missing[0]})")
    oracle = ReferenceEngine(docs.values(), tokenizer=engine.tokenizer_version)
    forms = forms_of(oracle.vocabulary)

    memo: dict[str, frozenset[str]] = {}

    def ids(n: Node | None) -> frozenset[str]:
        """The oracle's matches of a tree among the compared records (None: every record), computed once."""
        if n is None:
            return oracle.universe
        key = n.model_dump_json()
        if key not in memo:
            memo[key] = oracle.match_ids(n)
        return memo[key]

    # the readings: as run; as Scholar reads the string (each rewrite alone, and both); each with inflected forms
    run = apply_defaults(parsed.ast, len(q))
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
    stemmed = [with_variants(t, forms) for t in (run.identification, both.identification) if t is not None]
    o_stem = frozenset().union(*(ids(t) for t in stemmed)) if stemmed else oracle.universe
    bugs = o_run ^ (served & compared)  # the oracle and the served engine must agree on every compared record
    groups = _text_conjuncts(run.identification)
    group_ids = [(ids(g), ids(with_variants(g, forms))) for g in groups]
    queried = sorted({t for tree in (run.identification, both.identification) if tree for t in _tokens(tree)})
    variants = {t: tuple(_other_forms(t, forms)) for t in queried if _other_forms(t, forms)}
    variant_tokens = {v for vs in variants.values() for v in vs}

    def fields(i: str, leaf: Term | Wildcard | Phrase | Near) -> str:
        """Where `leaf` matches record `i`: `title`, `abstract`, `title+abstract`, or "" for no match."""
        if isinstance(leaf, Near):
            return "title or abstract" if i in ids(leaf) else ""
        return "+".join(
            f
            for f in TEXT_FIELDS
            if leaf.field in (None, f) and i in ids(leaf.model_copy(update={"field": f}))
        )

    def filters_failed(d: Searchable) -> str:
        failed = [f"{f}={getattr(d, f)}" for f in run.defaults if getattr(d, f) not in DEFAULT_CLAUSES[f]]
        return ", ".join(failed)

    def also_filtered(d: Searchable) -> str:
        return f"; also filtered ({failed})" if (failed := filters_failed(d)) else ""

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

    def dropped(e: Entry) -> Row:
        i = e.match.op_id
        assert i is not None
        d = docs[i]
        if i in bugs:
            cls, evidence, settled = OUR_BUG, "the oracle matches it and the served engine doesn't", False
        elif i in o_ident:
            cls, evidence, settled = FILTERED, filters_failed(d) or "fails a filter of the query", True
        elif differs and i in o_sch_ident:
            cls, evidence, settled = COMPAT_READING, rewrites(i, eff=False) + also_filtered(d), True
        elif i in o_stem:
            seen = [v for v in sorted(variant_tokens) if i in ids(Term(span=(0, 0), token=v))]
            cls, evidence, settled = STEMMING, f"matches with {', '.join(seen)}" + also_filtered(d), True
        elif d.abstract is None:
            cls, evidence, settled = UNSETTLED, "no title match, and the corpus has no abstract for it" + also_filtered(d), False  # fmt: skip
        else:
            failing = [str(k) for k, (_, loose) in enumerate(group_ids, 1) if i not in loose]
            cls, settled = FULL_TEXT, True
            evidence = (
                f"no title or abstract match for group {', '.join(failing)}, inflected forms included"
                if failing
                else "no title or abstract match, inflected forms included"
            ) + also_filtered(d)
        return Row("scholar", e.record.key, i, e.record.title, d.venue, d.year, cls, evidence, settled)

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
        return Row(
            "openproceedings", "", i, " ".join(d.title.split()), d.venue, d.year, cls, evidence, settled
        )

    kept, only, gaps = [], [], []
    for e in side.entries:
        if e.match.op_id is None:
            gaps.append(_not_in_index(e, index))
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
            kept.append(
                Row("scholar", e.record.key, d.id, e.record.title, d.venue, d.year, cls, evidence, not bug)
            )
    members = frozenset(by_id)
    notices = Counter(str(d.code) for d in (*parsed.translations, *parsed.warnings))
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
        added=tuple(added(i) for i in sorted(in_scope - members)),
        groups=tuple(
            Group(render(g), len(exact & members), len(loose & members))
            for g, (exact, loose) in zip(groups, group_ids, strict=True)
        ),
        matched=len(members),
        variants=variants,
    )
