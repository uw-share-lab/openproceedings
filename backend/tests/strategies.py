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
from pathlib import Path
from typing import NamedTuple

from hypothesis import strategies as st
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
from openproceedings.query.clauses import WIDEST_YEAR, ClauseReason
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
    (one in twenty from `wide`, stems past the 200-term cap, so refusals are exercised), and n-grams that
    occur (so phrases and NEAR match)."""

    terms: tuple[str, ...]
    stems: tuple[str, ...]
    ngrams: tuple[tuple[str, ...], ...]
    rare: tuple[str, ...] = ()
    wide: tuple[str, ...] = ()

    def term(self) -> st.SearchStrategy[str]:
        return _mixed(self.terms, self.rare, 3)

    def stem(self) -> st.SearchStrategy[str]:
        return _mixed(self.stems, self.wide, 20)


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


WORDS = st.sampled_from(
    ["trust", "Calibration", "vision-language", "gpt-4*", "model$", "bench*", "naïve", "GPT-4o", "x"]
)
PHRASES = st.lists(WORDS, min_size=1, max_size=4).map(lambda ws: '"' + " ".join(ws) + '"')
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
def queries(draw: st.DrawFn, depth: int = 0, filters: st.SearchStrategy[str] = FILTER_STRINGS) -> str:
    """Query strings: words, phrases, fielded terms, filters, NOT, NEAR, and nested AND/OR groups."""
    leaf = st.one_of(
        WORDS,
        PHRASES,
        filters,
        WORDS.map(lambda w: f"title:{w}"),
        PHRASES.map(lambda p: f"abstract:{p}"),
    )
    if depth >= 3 or draw(st.booleans()):
        return draw(leaf)
    parts = draw(st.lists(queries(depth + 1, filters), min_size=2, max_size=4))
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
def _near_cap_parts(filters: st.SearchStrategy[str]) -> st.SearchStrategy[str]:
    return st.one_of(
        queries(filters=filters),
        st.integers(0, 99_999).map(lambda i: f"w{i}"),  # distinct words, so deduplication doesn't shrink it
        st.integers(0, 99_999).map(lambda i: f"title:(t{i} OR u{i})"),  # a prefix per leaf in canonical form
        st.sampled_from(["gpt-4*", "abcd⒈", "abcd½*", "(a b) OR c", "track:main", "status:accepted"]),
    )


NEAR_CAP_PARTS = _near_cap_parts(FILTER_STRINGS)


@st.composite
def near_cap_queries(draw: st.DrawFn, low: int = 1_500, high: int = 2_000) -> str:
    """A query of `low`..`high` code points: parts joined by one separator, cut back to fit."""
    target = draw(st.integers(low, high))
    sep = draw(st.sampled_from([" ", " OR ", " AND ", " | "]))
    parts: list[str] = []
    size = 0
    while size < target:
        part = draw(NEAR_CAP_PARTS)
        parts.append(part)
        size += len(part) + len(sep)
    while len(parts) > 1 and len(sep.join(parts)) > high:
        parts.pop()
    return sep.join(parts)


# Filter-clause queries (spec 02 §Filter clauses): every clause shape a facet click may meet (bare, grouped, an
# OR of one field's filters, parenthesised, negated), mixed with words and groups, joined with and without
# spaces so a clause can be followed directly by a group (`track:(main OR workshop)(x OR y)`), and sometimes
# padded toward the 2,000-code-point cap or nested toward the depth limit.
CLAUSE_VALUES: dict[str, tuple[str, ...]] = {
    "venue": ("ICLR", "ICML", "NeurIPS"),
    "track": tuple(TRACKS),
    "status": tuple(STATUSES),
}
CLAUSE_WORDS = st.sampled_from(
    [
        "trust",
        "llm",
        "calibrat*",
        '"language model"',
        "title:agents",
        "abstract:(a OR b)",
        "x",
        "model$",
        "(x OR y)",
    ]
)


CLAUSE_FIELDS = ("venue", "track", "status", "year", "track", "status")
YEAR_CLAUSES = st.sampled_from(["year:2021", "year:2020..2022", "year:(2019 OR 2023..2024)"])
CLAUSE_PREFIXES = ("", "", "", "", "-", "NOT ", "NOT NOT ")


@st.composite
def filter_clause_strings(draw: st.DrawFn, fields: tuple[str, ...] = CLAUSE_FIELDS) -> str:
    field = draw(st.sampled_from(fields))
    if field == "year":
        return draw(YEAR_CLAUSES)
    pool = CLAUSE_VALUES[field]
    values = draw(st.lists(st.sampled_from(pool), min_size=1, max_size=min(3, len(pool)), unique=True))
    if field == "venue" and draw(st.integers(0, 3)) == 0:
        values = [v.lower() for v in values]
    shape = draw(st.sampled_from(["bare", "bare", "grouped", "or", "paren"]))
    if shape == "or" and len(values) > 1:
        return "(" + " OR ".join(f"{field}:{v}" for v in values) + ")"
    if shape == "paren":
        return f"({field}:{values[0]})"
    if shape == "grouped" or len(values) > 1:
        return f"{field}:({' OR '.join(values)})"
    return f"{field}:{values[0]}"


@st.composite
def clause_queries(draw: st.DrawFn, depth: int = 0) -> str:
    """A query built from filter clauses and words (see above)."""
    atom = draw(st.one_of(filter_clause_strings(), filter_clause_strings(), CLAUSE_WORDS))
    atom = draw(st.sampled_from(CLAUSE_PREFIXES)) + atom
    if depth >= 2 or draw(st.booleans()):
        body = atom
    else:
        parts = draw(st.lists(clause_queries(depth + 1), min_size=2, max_size=4))
        body = draw(st.sampled_from([" ", " ", " AND ", " OR ", ""])).join(parts)
        if depth > 0 and draw(st.booleans()):
            body = f"({body})"
    if depth == 0:
        pad = draw(st.integers(0, 19))
        if pad == 0:  # toward the cap: distinct words, so nothing deduplicates
            body += "".join(f" w{i}" for i in range(draw(st.integers(330, 400))))
        elif pad == 1:  # toward the depth limit
            deep = draw(st.integers(58, 64))
            body = "(" * deep + body + ")" * deep
    return body


# Year-edit cases (TASK-145): queries whose year clause a year action may rewrite, built to be so rather than
# drawn from clause_queries or near_cap_queries and assume()d (which threw away about 70% of draws and failed
# the filter_too_much health check on an unlucky seed). The shapes are clause_queries' and the near-cap parts',
# with the rules that make a query's year clause toggleable written into the grammar: no year filter but the
# one top-level clause, when there is one; every OR branch with a positive part (else PARSE_ALL_NEGATIVE); an
# OR group inside an AND parenthesised; and two parts written together only where a `)` meets a `(` (anything
# else touching is a lexical error). Only the padding toward the length and depth caps is sized against the
# server: cut back until the widest year edit parses, as near_cap_queries cuts back to fit.
_NO_YEAR_FIELDS = tuple(f for f in CLAUSE_FIELDS if f != "year")
_NO_YEAR_FILTERS = st.sampled_from([f for f in _FILTER_STRINGS if not f.startswith("year:")])
_NO_YEAR_NEAR_CAP_PARTS = _near_cap_parts(_NO_YEAR_FILTERS)
# the widest year clause a year action writes (clauses.WIDEST_YEAR, written as the reducer writes it)
_WIDEST_YEAR = "year:(" + " OR ".join(f"{r.lo}..{r.hi}" for r in WIDEST_YEAR) + ")"
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


@st.composite
def _year_free_part(draw: st.DrawFn, depth: int, positive: bool, in_or: bool) -> str:
    """A clause_queries part with no year filter: an atom (negated only if not `positive`) or a group."""
    if depth >= 2 or draw(st.booleans()):
        atom = draw(
            st.one_of(
                filter_clause_strings(_NO_YEAR_FIELDS), filter_clause_strings(_NO_YEAR_FIELDS), CLAUSE_WORDS
            )
        )
        return draw(st.sampled_from(_POSITIVE_PREFIXES if positive else CLAUSE_PREFIXES)) + atom
    return draw(_group(depth, None, in_or))


@st.composite
def _group(draw: st.DrawFn, depth: int, year: str | None, in_or: bool = False) -> str:
    """Two to four parts: an OR group, every part positive; or an AND group (` `, ` AND ` or written together)
    with one positive part, which alone may hold the year clause, as its own part or inside an AND subgroup.
    Parenthesised when it is an OR group in an AND (so AND's precedence can't split it), else sometimes."""
    seps = [" ", " ", " AND ", " OR ", ""] if year is None else [" ", " ", " AND ", ""]
    sep = draw(st.sampled_from(seps))
    n = draw(st.integers(2, 4))
    anchor = draw(st.integers(0, n - 1))
    parts = [draw(_year_free_part(depth + 1, sep == " OR " or i == anchor, sep == " OR ")) for i in range(n)]
    if year is not None:
        at = draw(st.integers(0, n))
        if depth + 1 < 2 and draw(st.booleans()):  # inside an AND subgroup, flattened to the top level
            parts.insert(at, draw(_group(depth + 1, year)))
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


def _fit(build: Callable[[int], str], low: int, high: int, year: str | None, mode: Mode) -> int:
    """The largest `n` in `low`..`high` whose `build(n)` has a widest year edit that parses, by bisection;
    `build(low)` (the unpadded query) must, so a grammar bug fails here, not silently. When the answer is below
    `high`, `build(n + 1)` was tried and failed."""
    assert _widest_edit_parses(build(low), year, mode), build(low)
    while low < high:
        mid = (low + high + 1) // 2
        if _widest_edit_parses(build(mid), year, mode):
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
    n = _fit(build, *bounds, year, mode)
    if n < bounds[1] and draw(st.integers(0, 4)) == 4 and not parse(build(n + 1), mode).errors:
        return build(n + 1), over
    return build(n), None


# One step past a rule: the year clause written negated, twice, in an OR with a word, or in an OR with another
# field's filter. Each is short and has a positive anchor, so it parses, and is reported with this reason.
@st.composite
def _near_miss_year(draw: st.DrawFn, clause: str) -> tuple[str, ClauseReason]:
    reason: ClauseReason = draw(st.sampled_from(["negated", "multiple_clauses", "nested", "mixed_fields"]))
    if reason == "negated":
        return draw(st.sampled_from(["-", "NOT "])) + clause, reason
    if reason == "multiple_clauses":
        return f"{clause} {draw(YEAR_CLAUSES)}", reason
    other = draw(CLAUSE_WORDS if reason == "nested" else filter_clause_strings(_NO_YEAR_FIELDS))
    return f"({clause} OR {other})", reason


@st.composite
def year_edit_cases(draw: st.DrawFn) -> YearEditCase:
    """A query whose year clause is toggleable, in either mode: none at all (a year edit writes it out as
    `(q) AND year:(…)`) or one top-level clause. A clause_queries shape, sometimes padded toward the length or
    depth cap, or near-cap parts (as near_cap_queries(1_800, 2_000) draws them, year filters left out). About
    one in five is a near miss instead (`YearEditCase.reason`)."""
    mode: Mode = draw(st.sampled_from(["native", "scholar"]))
    year = draw(st.sampled_from(_POSITIVE_PREFIXES)) + draw(YEAR_CLAUSES) if draw(st.booleans()) else None
    if draw(st.booleans()):
        target = draw(st.integers(1_800, 2_000))
        sep = draw(st.sampled_from([" ", " OR ", " AND ", " | "]))
        glue = draw(st.sampled_from([" ", " AND ", ""]))
        year_first = draw(st.booleans())
        # A few drawn parts, then distinct filler up to the target: drawing every part, as near_cap_queries
        # does, overran Hypothesis's test-case size in about a third of these draws.
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
        body = year or draw(_year_free_part(2, True, False))
    elif draw(st.integers(0, 3)) == 3:
        miss, reason = draw(_near_miss_year(year or draw(YEAR_CLAUSES)))
        return YearEditCase(draw(_group(0, miss)), mode, "clause", reason)
    else:
        body = draw(_group(0, year))
    pad = draw(st.integers(0, 19))
    if pad == 0:  # toward the length cap: distinct words, so nothing deduplicates
        words = draw(st.integers(330, 400))
        q, reason = draw(
            _padded(lambda n: body + "".join(f" w{i}" for i in range(n)), (0, words), year, mode, "too_long")
        )
        return YearEditCase(q, mode, "clause, toward the length cap", reason)
    if pad == 1:  # toward the depth limit
        deep = draw(st.integers(58, 64))
        q, reason = draw(_padded(lambda n: "(" * n + body + ")" * n, (0, deep), year, mode, "too_deep"))
        return YearEditCase(q, mode, "clause, toward the depth cap", reason)
    return YearEditCase(body, mode, "clause")
