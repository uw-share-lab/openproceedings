"""Shared Hypothesis strategies for the query language (property-testing skill; task-017).

`asts()` builds valid trees directly (every node type: terms, wildcards, phrases with wildcard items,
NEAR, filters, NOT, AND, OR), so properties reach shapes that string generators rarely produce.
`queries()` builds query strings. Both draw from VOCABULARY, a small corpus-like token set that includes
the awkward cases: operator words, filter values, digits, marks kept by the tokenizer, CJK.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import NamedTuple

from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query.ast import (
    And,
    Filter,
    Near,
    Node,
    Not,
    Or,
    Phrase,
    Term,
    TextField,
    Wildcard,
    YearRange,
)
from openproceedings.query.clauses import ClauseReason, _widest_clause
from openproceedings.query.normalize import normalize
from openproceedings.query.parser import Mode, parse
from openproceedings.vocab import STATUSES, TRACKS

_ROWS = [
    json.loads(line)
    for line in (Path(__file__).parent / "fixtures" / "corpus" / "reference-200.jsonl")
    .read_text()
    .splitlines()
]
_FIELD_TOKENS = [normalize(r[f] or "") for r in _ROWS for f in ("title", "abstract")]


def _fixture_vocabulary() -> list[str]:
    """The real term dictionary of the 200-record fixture, so generated queries hit documents."""
    return sorted({t for tokens in _FIELD_TOKENS for t in tokens})


# consecutive tokens that really occur in one field, so phrases and NEAR operands match something
NGRAMS = sorted(
    {tuple(ts[i : i + k]) for ts in _FIELD_TOKENS for k in (2, 3) for i in range(len(ts) - k + 1)}
)
# real strict prefixes (`benchmar*`, `relian*`) as well as whole words
PREFIXES = sorted({t[:n] for t in _fixture_vocabulary() if len(t) >= 5 for n in range(3, len(t))})


VOCABULARY = [
    *_fixture_vocabulary(),
    *("trust", "trustworthy", "calibration", "benchmark", "benchmarks", "model", "models", "reliance"),
    *("human", "vision", "language", "large", "llm", "llms", "gpt", "4o", "ai", "agent", "safety"),
    *("and", "or", "not", "near", "the", "of"),  # operator words and stopwords are ordinary tokens
    *("neurips", "iclr", "main", "workshop", "accepted", "2024", "2021"),  # filter values as text
    *("naive", "信頼性", "ป่า", "が"),
]
STEMS = [w for w in VOCABULARY if len(w) >= 3] + PREFIXES
SPAN = (0, 0)
FIELDS: list[TextField | None] = [None, "title", "abstract"]


@dataclass(frozen=True)
class Vocab:
    """What trees are drawn from: terms (the rare ones, df 1-3, drawn a third of the time), wildcard stems
    (one in twenty from `wide`, stems past the 200-term cap, so refusals are exercised; one in ten from `cap`,
    stems at the cap's edge, when there are any), and n-grams that occur (so phrases and NEAR match)."""

    terms: tuple[str, ...]
    stems: tuple[str, ...]
    ngrams: tuple[tuple[str, ...], ...]
    rare: tuple[str, ...] = ()
    wide: tuple[str, ...] = ()
    cap: tuple[str, ...] = ()

    def term(self) -> st.SearchStrategy[str]:
        return _mixed(self.terms, self.rare, 3)

    def stem(self) -> st.SearchStrategy[str]:
        stems = _mixed(self.stems, self.wide, 20)
        if not self.cap:
            return stems
        return st.integers(0, 9).flatmap(lambda k: st.sampled_from(self.cap) if k == 0 else stems)


def _mixed(common: tuple[str, ...], special: tuple[str, ...], one_in: int) -> st.SearchStrategy[str]:
    if not special:
        return st.sampled_from(common)
    return st.integers(0, one_in - 1).flatmap(lambda k: st.sampled_from(special if k == 0 else common))


FIXTURE = Vocab(tuple(VOCABULARY), tuple(STEMS), tuple(NGRAMS))


def _term(token: str, field: TextField | None = None) -> Term:
    return Term(span=SPAN, token=token, field=field)


def _wildcard(stem: str, op: str, field: TextField | None = None) -> Wildcard:
    return Wildcard(span=SPAN, stem=stem, op="*" if op == "*" else "$", field=field)


@st.composite
def leaves(
    draw: st.DrawFn, field: TextField | None = None, vocab: Vocab = FIXTURE
) -> Term | Wildcard | Phrase:
    kind = draw(st.sampled_from(["term", "wildcard", "phrase", "phrase"]))
    if kind == "term":
        return _term(draw(vocab.term()), field)
    if kind == "wildcard":
        return _wildcard(draw(vocab.stem()), draw(st.sampled_from("*$")), field)
    words = list(
        draw(st.one_of(st.sampled_from(vocab.ngrams), st.lists(vocab.term(), min_size=2, max_size=4)))
    )
    items: list[Term | Wildcard] = [_term(w) for w in words]
    if draw(st.booleans()):  # a wildcard item, at any position (decision-001)
        i = draw(st.integers(0, len(items) - 1))
        items[i] = _wildcard(draw(vocab.stem()), draw(st.sampled_from("*$")))
    return Phrase(span=SPAN, items=tuple(items), field=field)


@st.composite
def filters(draw: st.DrawFn) -> Filter:
    field = draw(st.sampled_from(["venue", "year", "track", "status"]))
    if field == "year":
        values: list[str | YearRange] = [
            YearRange(lo=lo, hi=lo + span)
            for lo, span in draw(
                st.lists(st.tuples(st.integers(2018, 2026), st.integers(0, 3)), min_size=1, max_size=3)
            )
        ]
    else:
        pool = {
            "venue": ["NeurIPS", "ICLR", "ICML"],
            "track": list(TRACKS),
            "status": list(STATUSES),
        }[field]
        values = list(draw(st.lists(st.sampled_from(pool), min_size=1, max_size=3)))
    return Filter(span=SPAN, field=field, values=tuple(values))  # type: ignore[arg-type]


@st.composite
def _node(draw: st.DrawFn, depth: int, vocab: Vocab = FIXTURE) -> Node:
    options = ["leaf", "near", "filter"] + (["not", "and", "or"] if depth < 3 else [])
    kind = draw(st.sampled_from(options))
    if kind == "leaf":
        return draw(leaves(draw(st.sampled_from(FIELDS)), vocab))
    if kind == "near":
        field = draw(st.sampled_from(FIELDS))
        return Near(
            span=SPAN,
            left=draw(leaves(field, vocab)),
            right=draw(leaves(field, vocab)),
            distance=draw(st.integers(0, 5)),
        )
    if kind == "filter":
        return draw(filters())
    if kind == "not":
        return Not(span=SPAN, child=draw(_node(depth + 1, vocab)))
    children = tuple(draw(st.lists(_node(depth + 1, vocab), min_size=2, max_size=3)))
    return And(span=SPAN, children=children) if kind == "and" else Or(span=SPAN, children=children)


@st.composite
def negative_asts(draw: st.DrawFn, vocab: Vocab = FIXTURE) -> Node:
    """A tree with no positive part (NOT x, or an OR with a negated branch): must be PARSE_ALL_NEGATIVE."""
    negated = Not(span=SPAN, child=draw(_node(1, vocab)))
    if draw(st.booleans()):
        return negated
    return Or(span=SPAN, children=(draw(_node(1, vocab)), negated))


def engine_asts(vocab: Vocab = FIXTURE) -> st.SearchStrategy[Node]:
    """Any tree an engine may be handed: parser-valid ones, and bare or all-negative ones the parser would
    refuse (an engine takes any AST; spec 03 §Two engines, one contract)."""
    return st.one_of(asts(vocab), _node(0, vocab), negative_asts(vocab))


@st.composite
def asts(draw: st.DrawFn, vocab: Vocab = FIXTURE) -> Node:
    """A valid tree with a positive part (a term ANDed in front), so its canonical string parses."""
    anchor = _term(draw(vocab.term()))
    return And(span=SPAN, children=(anchor, draw(_node(0, vocab))))


# Each decision that changes how much a query strategy draws after it is drawn by its own strategy, so it has its
# own span label (TASK-153): Hypothesis's mutator copies a span over another of the same label, and a copy that
# makes the case draw more than it had overruns, which `--hypothesis-show-statistics` counts as invalid. An
# `st.integers` or `st.booleans` decision shares its label with every other one, and an `st.lists` element with
# every other list's. The first value is the one a failure shrinks to.
_GROUP_SIZES = st.sampled_from((2, 3, 4))
_QUERY_NODES = st.sampled_from(("a leaf", "a group"))
_PHRASE_LENGTHS = st.sampled_from((1, 2, 3, 4))

WORDS = st.sampled_from(
    ["trust", "Calibration", "vision-language", "gpt-4*", "model$", "bench*", "naïve", "GPT-4o", "x"]
)
PHRASES = _PHRASE_LENGTHS.flatmap(lambda k: st.tuples(*[WORDS] * k)).map(lambda ws: '"' + " ".join(ws) + '"')
_FILTER_STRINGS = (
    "venue:ICLR",
    "venue:(neurips OR ICML)",
    "year:2024",
    "year:2019..2021",
    "track:main",
    "status:accepted",
)
FILTER_STRINGS = st.sampled_from(_FILTER_STRINGS)


@st.composite
def queries(draw: st.DrawFn, depth: int = 0, filter_strings: st.SearchStrategy[str] = FILTER_STRINGS) -> str:
    """Query strings: words, phrases, fielded terms, filters, NOT, NEAR, and nested AND/OR groups."""
    leaf = st.one_of(
        WORDS,
        PHRASES,
        filter_strings,
        WORDS.map(lambda w: f"title:{w}"),
        PHRASES.map(lambda p: f"abstract:{p}"),
    )
    if depth >= 3 or draw(_QUERY_NODES) == "a leaf":
        return draw(leaf)
    parts = [draw(queries(depth + 1, filter_strings)) for _ in range(draw(_GROUP_SIZES))]
    body = draw(st.sampled_from([" ", " AND ", " OR ", " | "])).join(parts)
    if draw(st.booleans()):
        body = f"({body})"
    if draw(st.integers(0, 4)) == 0:
        body = f"trust NOT {body}"
    if draw(st.integers(0, 5)) == 0:
        body = f"{body} x NEAR/2 y"
    return body


# Near the 2,000-code-point cap: whatever the parser accepts there must have a canonical string that is
# itself an accepted query (decision-008), however much the canonical form adds (defaults, ANDs, prefixes)
def _near_cap_parts(filter_strings: st.SearchStrategy[str]) -> st.SearchStrategy[str]:
    return st.one_of(
        queries(filter_strings=filter_strings),
        st.integers(0, 99_999).map(lambda i: f"w{i}"),  # distinct words, so deduplication doesn't shrink it
        st.integers(0, 99_999).map(lambda i: f"title:(t{i} OR u{i})"),  # a prefix per leaf in canonical form
        st.sampled_from(["gpt-4*", "abcd⒈", "abcd½*", "(a b) OR c", "track:main", "status:accepted"]),
    )


NEAR_CAP_PARTS = _near_cap_parts(FILTER_STRINGS)


@st.composite
def _near_cap_draw(draw: st.DrawFn, low: int, high: int) -> tuple[str, list[str]]:
    """A separator and near-cap parts that, joined by it, reach a drawn target of `low`..`high` code points."""
    target = draw(st.integers(low, high))
    sep = draw(st.sampled_from([" ", " OR ", " AND ", " | "]))
    parts: list[str] = []
    size = 0
    while size < target:
        part = draw(NEAR_CAP_PARTS)
        parts.append(part)
        size += len(part) + len(sep)
    return sep, parts


@st.composite
def near_cap_queries(draw: st.DrawFn, low: int = 1_500, high: int = 2_000) -> str:
    """A query of `low`..`high` code points: parts joined by one separator, cut back to fit."""
    sep, parts = draw(_near_cap_draw(low, high))
    while len(parts) > 1 and len(sep.join(parts)) > high:
        parts.pop()
    return sep.join(parts)


# Filter-clause queries (spec 02 §Filter clauses; click_cases and year_edit_cases, below): every clause shape a
# facet click may meet (bare, grouped, an OR of one field's filters, parenthesised, negated), mixed with words
# and groups, joined with and without spaces so a clause can be followed directly by a group
# (`track:(main OR workshop)(x OR y)`), and sometimes padded toward the 2,000-code-point cap or nested toward
# the depth limit.
CLAUSE_VALUES: dict[str, tuple[str, ...]] = {
    "venue": ("ICLR", "ICML", "NeurIPS"),
    "track": tuple(TRACKS),
    "status": tuple(STATUSES),
}
_CLAUSE_WORDS = (
    "trust",
    "llm",
    "calibrat*",
    '"language model"',
    "title:agents",
    "abstract:(a OR b)",
    "x",
    "model$",
    "(x OR y)",
)
CLAUSE_WORDS = st.sampled_from(_CLAUSE_WORDS)


CLAUSE_FIELDS = ("venue", "track", "status", "year", "track", "status")
_YEAR_CLAUSES = ("year:2021", "year:2020..2022", "year:(2019 OR 2023..2024)")
YEAR_CLAUSES = st.sampled_from(_YEAR_CLAUSES)
CLAUSE_PREFIXES = ("", "", "", "", "-", "NOT ", "NOT NOT ")


# Their own span labels, as `_GROUP_SIZES`
_VALUE_COUNTS = st.sampled_from((1, 2, 3))
# a field's one to three distinct values, in every order, by count
_VALUE_LISTS = {
    field: {k: st.sampled_from(list(permutations(pool, k))) for k in range(1, min(3, len(pool)) + 1)}
    for field, pool in CLAUSE_VALUES.items()
}
_VENUE_CASES = st.sampled_from(("as written", "as written", "as written", "lowercase"))


@st.composite
def filter_clause_strings(draw: st.DrawFn, fields: tuple[str, ...] = CLAUSE_FIELDS) -> str:
    field = draw(st.sampled_from(fields))
    if field == "year":
        return draw(YEAR_CLAUSES)
    lists = _VALUE_LISTS[field]
    values = list(draw(lists[min(draw(_VALUE_COUNTS), len(lists))]))
    if field == "venue" and draw(_VENUE_CASES) == "lowercase":
        values = [v.lower() for v in values]
    shape = draw(st.sampled_from(["bare", "bare", "grouped", "or", "paren"]))
    if shape == "or" and len(values) > 1:
        return "(" + " OR ".join(f"{field}:{v}" for v in values) + ")"
    if shape == "paren":
        return f"({field}:{values[0]})"
    if shape == "grouped" or len(values) > 1:
        return f"{field}:({' OR '.join(values)})"
    return f"{field}:{values[0]}"


# Year-edit cases (TASK-145): queries whose year clause a year action may rewrite, built to be so rather than
# drawn from clause_queries (since removed: click_cases replaced its last use, TASK-153) or near_cap_queries and
# assume()d (which threw away about 70% of draws and failed the filter_too_much health check on an unlucky
# seed). The shapes are the filter-clause queries' (above) and the near-cap parts',
# with the rules that make a query's year clause toggleable written into the grammar: at most one top-level year
# clause, and other year filters only when there is one, and only nested (in an OR with a part of another field or
# a word, or under NOT), which spec 02 says leaves the top-level clause toggleable; none at all when there is no
# top-level clause; every OR branch with a positive part (else PARSE_ALL_NEGATIVE); an OR group inside an AND
# parenthesised; and two parts written together only where a `)` meets a `(` (anything else touching is a lexical
# error). Only the padding toward the length and depth caps is sized against the server: cut back until the query
# and its widest year edit both parse, as near_cap_queries cuts back to fit.
_NO_YEAR_FIELDS = tuple(f for f in CLAUSE_FIELDS if f != "year")
_NO_YEAR_FILTERS = st.sampled_from([f for f in _FILTER_STRINGS if not f.startswith("year:")])
_NO_YEAR_NEAR_CAP_PARTS = _near_cap_parts(_NO_YEAR_FILTERS)
# the widest year clause a year action writes, as filter_clauses checks it
_WIDEST_YEAR = _widest_clause("year")
# The top-level clause: a year filter, or an OR of year filters (one clause: the canonical form makes it one filter)
_YEAR_SHAPES = st.sampled_from(
    [*_YEAR_CLAUSES, "(year:2021 OR year:2020..2022)", "(year:2019 OR year:2023..2024)"]
)
# Year filters nested beside the top-level clause (never one of its texts, so `str.replace` finds that clause)
_NESTED_YEARS = st.sampled_from(["(year:2017 OR x)", "(llm OR year:2015..2016)", "(year:2017 OR track:main)"])
_POSITIVE_PREFIXES = tuple(p for p in CLAUSE_PREFIXES if p in ("", "NOT NOT "))


class YearEditCase(NamedTuple):
    q: str
    mode: Mode
    source: str  # which shape it was built from, for the property's `event` counts
    # None: the year clause is toggleable. Else a near miss, built one step past a rule, and the reason
    # filter_clauses must give for it: so a clause wrongly reported toggleable is caught, as it was when the
    # property drew any query
    reason: ClauseReason | None = None


def _join(parts: list[str], sep: str) -> str:
    """`parts` joined by `sep`; written together (`sep` "") only where a `)` meets a `(`, else by a space."""
    out = parts[0]
    for part in parts[1:]:
        out += (sep or ("" if out.endswith(")") and part.startswith("(") else " ")) + part
    return out


# Their own span labels, as `_GROUP_SIZES`
_ATOM_OR_GROUP = st.sampled_from(("atom", "group"))


@st.composite
def _part(
    draw: st.DrawFn,
    depth: int,
    positive: bool,
    in_or: bool,
    nested: bool,
    fields: tuple[str, ...] = _NO_YEAR_FIELDS,
) -> str:
    """A filter-clause query part: an atom (a clause of one of `fields`, or a word; negated only if not
    `positive`) or a group. With the default `fields` it has no top-level year filter (year_edit_cases); click_cases
    passes CLAUSE_FIELDS. `nested`: the query has a top-level year clause, so an atom may be a nested year filter
    (`_NESTED_YEARS`)."""
    if depth >= 2 or draw(_ATOM_OR_GROUP) == "atom":
        atoms = [filter_clause_strings(fields), filter_clause_strings(fields), CLAUSE_WORDS]
        atom = draw(st.one_of(*atoms, _NESTED_YEARS, _NESTED_YEARS) if nested else st.one_of(*atoms))
        return draw(st.sampled_from(_POSITIVE_PREFIXES if positive else CLAUSE_PREFIXES)) + atom
    return draw(_group(depth, None, in_or, nested, fields))


@st.composite
def _group(
    draw: st.DrawFn,
    depth: int,
    year: str | None,
    in_or: bool = False,
    nested: bool = False,
    fields: tuple[str, ...] = _NO_YEAR_FIELDS,
) -> str:
    """Two to four parts: an OR group, every part positive; or an AND group (` `, ` AND ` or written together)
    with at least one positive part (the anchor). Only an AND group holds `year` (the year clause, or a near miss
    written into the query as one of its conjuncts), as its own part or inside an AND subgroup. Parenthesised when
    it is an OR group in an AND (so AND's precedence can't split it), else sometimes. `nested` and `fields` as for
    `_part`."""
    seps = [" ", " ", " AND ", " OR ", ""] if year is None else [" ", " ", " AND ", ""]
    sep = draw(st.sampled_from(seps))
    n = draw(_GROUP_SIZES)
    anchor = draw(st.integers(0, n - 1))
    parts = [
        draw(_part(depth + 1, sep == " OR " or i == anchor, sep == " OR ", nested, fields)) for i in range(n)
    ]
    if year is not None:
        at = draw(st.integers(0, n))
        if depth + 1 < 2 and draw(st.booleans()):  # inside an AND subgroup, flattened to the top level
            parts.insert(at, draw(_group(depth + 1, year, nested=nested, fields=fields)))
        else:
            parts.insert(at, year)
    body = _join(parts, sep)
    if depth > 0 and ((sep == " OR " and not in_or) or draw(st.booleans())):
        body = f"({body})"
    return body


def _widest_edit_parses(q: str, year: str | None, mode: Mode) -> bool:
    """Whether `q` and its widest year edit both parse: what `filter_clauses` checks before it reports a year
    clause toggleable (clauses.py `_edit_reason`), in two parses instead of its several. `year` is the clause as
    written in `q` (the only text like it there), spliced over; None: written out as `(q) AND year:(…)`. `q`
    itself is checked too: the edit can be shallower (`NOT NOT year:2021` spliced over is one group, not three).
    The rest of what `_edit_reason` checks, one top-level year clause, holds by construction; the property
    asserts it all."""
    edited = f"({q}) AND {_WIDEST_YEAR}" if year is None else q.replace(year, _WIDEST_YEAR, 1)
    return not parse(q, mode).errors and not parse(edited, mode).errors


def _fit(build: Callable[[int], str], low: int, high: int, fits: Callable[[str], bool]) -> int:
    """The largest `n` in `low`..`high` whose query `build(n)` `fits`, by bisection; `build(low)` (the unpadded
    query) must, so a grammar bug fails here, not silently. When the answer is below `high`, `build(n + 1)` was
    tried and failed."""
    assert fits(build(low)), build(low)
    while low < high:
        mid = (low + high + 1) // 2
        if fits(build(mid)):
            low = mid
        else:
            high = mid - 1
    return low


@st.composite
def _padded(
    draw: st.DrawFn,
    build: Callable[[int], str],
    bounds: tuple[int, int],
    year: str | None,
    mode: Mode,
    over: ClauseReason,
) -> tuple[str, ClauseReason | None]:
    """`build(n)` padded as far as fits; sometimes one step further, when that query still parses: a near
    miss whose year clause filter_clauses must report `over` (too long or too deep to edit)."""
    n = _fit(build, *bounds, lambda q: _widest_edit_parses(q, year, mode))
    if n < bounds[1] and draw(st.integers(0, 4)) == 4 and not parse(build(n + 1), mode).errors:
        return build(n + 1), over
    return build(n), None


# One step past a rule: the year clause written negated, twice, nested (in an OR with a word, in a group under
# NOT, or in an AND group under NOT NOT, top-level only once canonicalised), or in an OR with another field's
# filter. Each is short and has a positive anchor, so it parses, and is reported with this reason.
@st.composite
def _near_miss_year(draw: st.DrawFn, clause: str) -> tuple[str, ClauseReason]:
    reason: ClauseReason = draw(st.sampled_from(["negated", "multiple_clauses", "nested", "mixed_fields"]))
    if reason == "negated":
        return draw(st.sampled_from(["-", "NOT "])) + clause, reason
    if reason == "multiple_clauses":
        return f"{clause} {draw(YEAR_CLAUSES)}", reason
    if reason == "mixed_fields":
        return f"({clause} OR {draw(filter_clause_strings(_NO_YEAR_FIELDS))})", reason
    form = draw(st.sampled_from(["({} OR {})", "NOT ({} {})", "NOT NOT ({} {})"]))
    return form.format(clause, draw(CLAUSE_WORDS)), reason


@st.composite
def year_edit_cases(draw: st.DrawFn) -> YearEditCase:
    """A query whose year clause is toggleable, in either mode: none at all (a year edit writes it out as
    `(q) AND year:(…)`) or one top-level clause. A filter-clause query shape (`_group`/`_part`), sometimes padded
    toward the length or depth cap, or a few near-cap parts (year filters left out) padded with filler toward the
    length cap. Some are near misses instead (`YearEditCase.reason`): a few percent to a quarter of cases, varying
    by run."""
    mode: Mode = draw(st.sampled_from(["native", "scholar"]))
    year = draw(st.sampled_from(_POSITIVE_PREFIXES)) + draw(_YEAR_SHAPES) if draw(st.booleans()) else None
    if draw(st.booleans()):
        target = draw(st.integers(1_800, 2_000))
        sep = draw(st.sampled_from([" ", " OR ", " AND ", " | "]))
        glue = draw(st.sampled_from([" ", " AND ", ""]))
        year_first = draw(st.booleans())
        # A few drawn parts for the shapes, then distinct filler (no draws) up to the target: drawing every
        # part, as near_cap_queries does, takes a hundred or so parts, and the fit cuts the last of them off.
        parts = draw(st.lists(_NO_YEAR_NEAR_CAP_PARTS, min_size=1, max_size=6))
        filler = draw(st.sampled_from(["w{}", "title:(t{} OR u{})", "w{} title:(t{} OR u{})"]))
        while len(sep.join(parts)) < target:
            parts.append(filler.format(*[len(parts)] * filler.count("{}")))

        def near_cap(n: int) -> str:
            body = sep.join(parts[:n])
            if year is None:
                return body
            return _join([year, f"({body})"] if year_first else [f"({body})", year], glue)

        q, reason = draw(_padded(near_cap, (1, len(parts)), year, mode, "too_long"))
        return YearEditCase(q, mode, "near-cap", reason)
    if draw(st.booleans()):  # one atom
        body = year or draw(_part(2, True, False, False))
    elif draw(st.integers(0, 3)) == 3:
        miss, reason = draw(_near_miss_year(year or draw(YEAR_CLAUSES)))
        return YearEditCase(draw(_group(0, miss)), mode, "clause", reason)
    else:
        body = draw(_group(0, year, nested=year is not None))
    pad = draw(st.integers(0, 19))
    if pad == 0:  # toward the length cap: distinct words, so nothing deduplicates
        words = draw(st.integers(330, 400))
        q, reason = draw(
            _padded(lambda n: body + "".join(f" w{i}" for i in range(n)), (0, words), year, mode, "too_long")
        )
        return YearEditCase(q, mode, "clause, toward the length cap", reason)
    if pad == 1:  # toward the depth limit
        deep = draw(st.integers(58, 66))  # past MAX_DEPTH (64) at times, so the fit can stop below the bound
        q, reason = draw(_padded(lambda n: "(" * n + body + ")" * n, (0, deep), year, mode, "too_deep"))
        return YearEditCase(q, mode, "clause, toward the depth cap", reason)
    return YearEditCase(body, mode, "clause")


# Parse cases (TASK-153): queries the clause properties need to parse, built to parse rather than drawn and
# assume()d (the one-wrap property threw away 27 to 30% of its draws, the single-value-click property 30 to 32%).
# Near-cap and padded queries are cut back by the parser itself, as year_edit_cases cuts back to fit. Some cases are
# near misses instead, one step past a rule of the parser, which parse must refuse with that code (and so
# filter_clauses with None): so the properties still see an input wrongly accepted.
class ParseCase(NamedTuple):
    q: str
    mode: Mode
    source: str  # which shape it was built from, for the property's `event` counts
    # None: q parses. Else a near miss, and the error code parse must give for it
    refused: DiagnosticCode | None = None


_MODES: st.SearchStrategy[Mode] = st.sampled_from(["native", "scholar"])


def _parses(mode: Mode) -> Callable[[str], bool]:
    return lambda q: not parse(q, mode).errors


# Their own span labels, as `_GROUP_SIZES`
_NEAR_MISS_RULES = st.sampled_from(("every conjunct negated", "a word before a group"))
_NEGATED_BRANCH = st.sampled_from(("the whole query", "a branch of an OR"))
_ONE_STEP_PAST = st.sampled_from(("fit", "fit", "fit", "fit", "one step past"))
_CLICK_SHAPES = st.sampled_from(("built to parse",) * 9 + ("near miss",))
_CLICK_BODIES = st.sampled_from(("one atom", "a group"))
_PADDING = st.sampled_from(("none",) * 18 + ("length cap", "depth cap"))


@st.composite
def _cut_to_parse(
    draw: st.DrawFn, build: Callable[[int], str], bounds: tuple[int, int], mode: Mode, over: DiagnosticCode
) -> tuple[str, DiagnosticCode | None]:
    """`build(n)` for the largest `n` in `bounds` that parses; sometimes `build(n + 1)` instead, which doesn't: a
    near miss that parse must refuse with `over` (too long or too deep)."""
    n = _fit(build, *bounds, _parses(mode))
    if n < bounds[1] and draw(_ONE_STEP_PAST) == "one step past":
        return build(n + 1), over
    return build(n), None


@st.composite
def wrap_cases(draw: st.DrawFn) -> ParseCase:
    """A `queries()` string (every one parses, in either mode), or near-cap parts joined by one separator and cut
    back until the query parses: raw or canonical, it ends close to the 2,000-code-point cap, where writing every
    field out at once (`clauses._check_wraps`) is too long and each field is checked alone."""
    mode = draw(_MODES)
    if draw(st.booleans()):
        return ParseCase(draw(queries()), mode, "query")
    sep, parts = draw(_near_cap_draw(1_800, 2_000))
    q, refused = draw(
        _cut_to_parse(lambda n: sep.join(parts[:n]), (1, len(parts)), mode, DiagnosticCode.PARSE_TOO_LONG)
    )
    return ParseCase(q, mode, "near-cap", refused)


# A part that ends in a word or a range, not a `)`: written directly before a group it is PARSE_PAREN_TOUCHES_WORD
# (a group, `abstract:(a OR b)(x)`, is not; a full range, `year:2020..2022(x)`, is, decision-028)
_BEFORE_A_GROUP = st.sampled_from(
    [
        *(f"{f}:{v}" for f, values in CLAUSE_VALUES.items() for v in values),
        "year:2021",
        "year:2020..2022",
        # not a `$` word: `model$(model$)` opens LaTeX math at `$(`, so it is no glued parenthesis
        *(w for w in _CLAUSE_WORDS if not w.endswith((")", "$"))),
    ]
)


@st.composite
def _near_miss_parse(draw: st.DrawFn) -> tuple[str, DiagnosticCode]:
    """One step past a rule `_group` keeps: every conjunct negated, or an OR with a negated branch
    (PARSE_ALL_NEGATIVE); or a part that ends in a word written directly before a group, somewhere in an AND
    group (PARSE_PAREN_TOUCHES_WORD)."""
    if draw(_NEAR_MISS_RULES) == "every conjunct negated":
        negated = st.sampled_from(["-", "NOT "]).flatmap(
            lambda p: st.one_of(filter_clause_strings(), CLAUSE_WORDS).map(lambda a: p + a)
        )
        sep = draw(st.sampled_from([" ", " AND "]))
        q = sep.join(draw(negated) for _ in range(draw(_VALUE_COUNTS)))
        if draw(_NEGATED_BRANCH) == "a branch of an OR":
            q = f"{draw(_part(1, True, True, False, CLAUSE_FIELDS))} OR {q}"
        return q, DiagnosticCode.PARSE_ALL_NEGATIVE
    touching = f"{draw(_BEFORE_A_GROUP)}({draw(_part(2, True, False, False, CLAUSE_FIELDS))})"
    return draw(_group(0, touching, fields=CLAUSE_FIELDS)), DiagnosticCode.PARSE_PAREN_TOUCHES_WORD


@st.composite
def click_cases(draw: st.DrawFn) -> ParseCase:
    """A filter-clause query that parses, in either mode: one atom or a `_group` of every field's clauses in every
    shape, written negated, twice, nested or in an OR with another field's, so a venue, track or status clause is
    toggleable or not for each reason; sometimes padded toward the length or depth cap, cut back until it parses.
    Some are near misses (`ParseCase.refused`): roughly one case in ten (`_CLICK_SHAPES`; more in practice, as
    Hypothesis doesn't draw uniformly) written past a rule `_group` keeps, and one padded case in five one step
    past the cap."""
    mode = draw(_MODES)
    if draw(_CLICK_SHAPES) == "near miss":
        q, code = draw(_near_miss_parse())
        return ParseCase(q, mode, "near miss", code)
    if draw(_CLICK_BODIES) == "one atom":
        body = draw(_part(2, True, False, False, CLAUSE_FIELDS))
    else:
        body = draw(_group(0, None, fields=CLAUSE_FIELDS))
    pad = draw(_PADDING)
    if pad == "length cap":  # distinct words, so nothing deduplicates
        words = draw(st.integers(330, 400))
        q, refused = draw(
            _cut_to_parse(
                lambda n: body + "".join(f" w{i}" for i in range(n)),
                (0, words),
                mode,
                DiagnosticCode.PARSE_TOO_LONG,
            )
        )
        return ParseCase(q, mode, "clause, toward the length cap", refused)
    if pad == "depth cap":
        deep = draw(st.integers(58, 66))  # past MAX_DEPTH (64) at times, so the fit can stop below the bound
        q, refused = draw(
            _cut_to_parse(lambda n: "(" * n + body + ")" * n, (0, deep), mode, DiagnosticCode.PARSE_TOO_DEEP)
        )
        return ParseCase(q, mode, "clause, toward the depth cap", refused)
    return ParseCase(body, mode, "clause")
